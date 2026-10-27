"""Explicit, ID-bound public metadata enrichment. No network or commit here."""
import re
from uuid import uuid4
from sqlmodel import Session, select, delete
from sqlalchemy import or_
from app.canonical_models import Assertion, Credit, CreditProvenance, ExternalIdentity, Film, FilmTitle, Person, PersonAlias, GraphEntity, GraphNodeReadModel, GraphEdgeReadModel
from app.contracts.structured_metadata import normalize_metadata_text, credit_semantic_key
from app.services.structured_metadata_observations import tmdb_structured_metadata_observation
from app.services.structured_metadata_sync import StructuredMetadataSynchronizer

def _names(person):
    if not isinstance(person,dict) or type(person.get('id')) is not int or person['id']<=0:
        raise ValueError('Invalid public person identity')
    names=person.get('also_known_as')
    if not isinstance(names,list) or len(names)>100 or any(not isinstance(x,str) or not x.strip() or len(x)>100 for x in names):
        raise ValueError('Invalid person alias snapshot')
    name=person.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Invalid person name')
    return {x.strip() for x in [name,*names]}

def _can_link_single_context(session, person, credit, film_id):
    """A provisional person key can be shared across films; never certify it globally.

    A fresh provider ID is safe here only for one active local identity context,
    one credit on this film and no user-owned or independent identity evidence.
    Other cases stay unresolved instead of borrowing this movie's proof.
    """
    if person.lifecycle_status != "active" or person.resolution_status != "provisional":
        return False
    identities = session.exec(select(ExternalIdentity).where(
        ExternalIdentity.entity_id == person.id)).all()
    if not identities or any(identity.provider != "local.person"
            or identity.identity_status != "active"
            or identity.provenance_kind in {"curated", "user"}
            for identity in identities):
        return False
    credits = session.exec(select(Credit).where(Credit.person_id == person.id)).all()
    if len(credits) != 1 or credits[0].id != credit.id or credits[0].film_id != film_id:
        return False
    if session.exec(select(PersonAlias.id).where(PersonAlias.person_id == person.id)).first():
        return False
    if session.exec(select(Assertion.id).where(or_(
            Assertion.subject_entity_id == person.id,
            Assertion.object_entity_id == person.id))).first():
        return False
    if session.exec(select(CreditProvenance.id).where(
            CreditProvenance.credit_id == credit.id,
            CreditProvenance.origin_kind == "curated")).first():
        return False
    return True


def _redirect_provisional_director(session,old_id,target_id,film_id,provider_identity,observed_at):
    """Only a locally provisional, single-film director with no curated facts.

    Called after unique official movie-credit + person-ID AKA verification.
    Never merges two verified IDs, homonyms, or general graph assertions.
    """
    old=session.get(Person,old_id);target=session.get(Person,target_id)
    if not old or not target or old.resolution_status!="provisional" or old.lifecycle_status!="active" or target.lifecycle_status!="active" or target.resolution_status!="verified":return False
    identities=session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==old_id)).all()
    if not identities or any(x.provider!="local.person" or x.identity_status!="active" or x.provenance_kind in {"curated","user"} for x in identities):return False
    credits=session.exec(select(Credit).where(Credit.person_id==old_id)).all()
    if not credits or any(x.film_id!=film_id or (x.department,x.job)!=("Directing","Director") for x in credits):return False
    if session.exec(select(PersonAlias.id).where(PersonAlias.person_id==old_id)).first():return False
    if session.exec(select(Assertion.id).where(or_(Assertion.subject_entity_id==old_id,Assertion.object_entity_id==old_id))).first():return False
    if session.exec(select(CreditProvenance.id).where(CreditProvenance.credit_id.in_([x.id for x in credits]),CreditProvenance.origin_kind=="curated")).first():return False
    nfo_refs=set()
    for credit in credits:
        key=credit_semantic_key(credit.film_id,target_id,credit.department,credit.job,credit.character)
        duplicate=session.exec(select(Credit).where(Credit.semantic_key==key)).first()
        provenances=session.exec(select(CreditProvenance).where(CreditProvenance.credit_id==credit.id)).all()
        nfo_refs.update(p.origin_ref for p in provenances if p.origin_kind=="nfo" and p.superseded_at is None)
        if duplicate is None:
            credit.person_id=target_id;credit.semantic_key=key;credit.updated_at=observed_at;session.add(credit)
        else:
            for p in provenances:
                existing=session.exec(select(CreditProvenance).where(CreditProvenance.credit_id==duplicate.id,CreditProvenance.origin_kind==p.origin_kind,CreditProvenance.origin_ref==p.origin_ref)).first()
                if existing is None:p.credit_id=duplicate.id;session.add(p)
                else:
                    if p.superseded_at is None:existing.superseded_at=None;session.add(existing)
                    session.delete(p)
            session.flush();session.delete(credit)
    for ext in identities:ext.entity_id=target_id;ext.updated_at=observed_at;session.add(ext)
    for ref in nfo_refs:
        session.add(PersonAlias(id='person_alias_'+uuid4().hex,person_id=target_id,film_id=film_id,
            identity_id=provider_identity.id,locale='und',name=old.canonical_name,
            normalized_name=old.normalized_name,origin_kind='nfo',origin_ref=ref,observed_at=observed_at))
    old.lifecycle_status="merged";old.merged_into_id=target_id;old.updated_at=observed_at;session.add(old)
    graph=session.get(GraphEntity,old_id)
    if graph:graph.lifecycle_status="merged";graph.updated_at=observed_at;session.add(graph)
    session.exec(delete(GraphNodeReadModel).where(GraphNodeReadModel.entity_id==old_id))
    session.exec(delete(GraphEdgeReadModel).where(or_(GraphEdgeReadModel.subject_entity_id==old_id,GraphEdgeReadModel.object_entity_id==old_id)))
    from app.models import EventRecord
    session.add(EventRecord(aggregate_type='person',aggregate_id=old_id,type='ProvisionalPersonSourceLinked',
        actor_type='system',payload={'target_person_id':target_id,'provider':'tmdb.person','external_id':provider_identity.external_id,
        'evidence':'unique-public-movie-director-and-official-person-alias'}))
    session.flush();return True


def apply_enrichment(session:Session,film_id,details,people,*,observed_at):
    """Caller owns transaction, backup, public-ID whitelist and final commit.

    Fresh IDs require a single-film, single-credit local identity with no manual
    or independent identity evidence. Provisional IDs then require unique source context: actors
    require exact name, character and billing; directors also require the
    official person-ID alias snapshot. Two verified IDs are never merged; a uniquely verified local-only director
    may be redirected with a retained identity/history and an audit event.
    """
    mid=details.get('id')
    film=session.get(Film,film_id)
    if type(mid) is not int or mid<=0 or film is None or film.lifecycle_status!='active':
        raise ValueError('Invalid Film')
    identities=session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==film_id,
        ExternalIdentity.provider=='tmdb.movie',ExternalIdentity.identity_status=='active')).all()
    if len(identities)!=1 or identities[0].external_id!=str(mid):
        raise ValueError('Film ID is not unambiguously bound to this TMDB movie')
    credits=details.get('credits')
    if not isinstance(credits,dict) or not all(isinstance(credits.get(k),list) for k in ('crew','cast')):raise ValueError('Incomplete public credits')
    directors=[x for x in credits['crew'] if isinstance(x,dict) and x.get('job')=='Director']
    person_names={int(pid):_names(data) for pid,data in people.items()}
    if any(int(pid)!=data['id'] for pid,data in people.items()):raise ValueError('Person ID mismatch')
    observation=tmdb_structured_metadata_observation(details,mid,language='zh-CN',observed_at=observed_at)
    proposals={};unresolved=0
    rows=session.exec(select(Credit,Person).join(Person,Credit.person_id==Person.id).where(
        Credit.film_id==film_id,Credit.id.in_(select(CreditProvenance.credit_id).where(
            CreditProvenance.origin_kind=='nfo',CreditProvenance.superseded_at.is_(None))))).all()
    for old,person in rows:
        existing=session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==person.id,
            ExternalIdentity.provider=='tmdb.person')).all()
        if existing or person.resolution_status!='provisional':continue
        if not _can_link_single_context(session,person,old,film_id):
            unresolved+=1;continue
        local=session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==person.id,
            ExternalIdentity.provider=='local.person',ExternalIdentity.identity_status=='active')).first()
        if local is None:continue
        name=normalize_metadata_text(person.canonical_name);possible=set()
        for candidate in directors if old.department=='Directing' and old.job=='Director' else credits['cast'] if old.department=='Acting' and old.job=='Actor' else []:
            pid=candidate.get('id')
            if type(pid) is not int or pid<=0:continue
            if old.department=='Directing':
                matches=pid in person_names and name in {normalize_metadata_text(x) for x in sorted(person_names[pid])}
            else:
                names={normalize_metadata_text(candidate.get(k) or '') for k in ('name','original_name')}
                matches=(name in names and bool(old.character) and normalize_metadata_text(old.character)==normalize_metadata_text(candidate.get('character') or '') and old.billing_order is not None and old.billing_order==candidate.get('order'))
            if matches:possible.add(pid)
        if len(possible)==1:proposals.setdefault(person.id,set()).update(possible)
        else:unresolved+=1
    linked=0;redirected=0
    for old_id,candidates in proposals.items():
        # Never last-wins: contradictory contexts cannot certify a person.
        if len(candidates)!=1:
            unresolved+=1;continue
        pid=next(iter(candidates))
        if sum(pid in values for values in proposals.values())!=1:
            unresolved+=1;continue
        conflict=session.exec(select(ExternalIdentity).where(ExternalIdentity.provider=='tmdb.person',ExternalIdentity.external_id==str(pid))).first()
        if conflict is not None:
            if conflict.identity_status=="active" and conflict.verified_at and _redirect_provisional_director(session,old_id,conflict.entity_id,film_id,conflict,observed_at):
                redirected+=1
            else:unresolved+=1
            continue
        session.add(ExternalIdentity(id='identity_'+uuid4().hex,entity_id=old_id,provider='tmdb.person',external_id=str(pid),
            identity_status='active',verified_at=observed_at,provenance_kind='tmdb',provenance_ref=f'tmdb.movie:{mid}',created_at=observed_at,updated_at=observed_at))
        person=session.get(Person,old_id);person.resolution_status='verified';session.add(person);linked+=1
    session.flush()
    sync=StructuredMetadataSynchronizer()
    sync.sync(session,film_id=film_id,library_item_id=None,observation=observation)
    # Only explicit director snapshots from these movie credits are consumed.
    for director in directors:
        pid=director.get('id')
        if pid not in person_names:continue
        ext=session.exec(select(ExternalIdentity).where(ExternalIdentity.provider=='tmdb.person',ExternalIdentity.external_id==str(pid),ExternalIdentity.identity_status=='active')).first()
        if ext is None:continue
        ref=f'tmdb.person:{pid}';desired={normalize_metadata_text(x):x for x in sorted(person_names[pid])}
        old_rows=session.exec(select(PersonAlias).where(PersonAlias.person_id==ext.entity_id,PersonAlias.film_id==film_id,PersonAlias.origin_kind=='tmdb',PersonAlias.origin_ref==ref)).all()
        for alias in old_rows:
            if alias.normalized_name not in desired:alias.superseded_at=observed_at;session.add(alias)
        for normalized,name in desired.items():
            alias=next((x for x in old_rows if x.normalized_name==normalized and x.locale=='und'),None)
            if alias is None:alias=PersonAlias(id='person_alias_'+uuid4().hex,person_id=ext.entity_id,film_id=film_id,identity_id=ext.id,
                locale='und',name=name,normalized_name=normalized,origin_kind='tmdb',origin_ref=ref,observed_at=observed_at)
            alias.identity_id=ext.id;alias.name=name;alias.observed_at=observed_at;alias.superseded_at=None;session.add(alias)
    translations=details.get('translations')
    if translations is not None:
        entries=translations.get('translations') if isinstance(translations,dict) else None
        if not isinstance(entries,list):raise ValueError('Malformed translation snapshot')
        desired={}
        for item in entries:
            if not isinstance(item,dict) or not isinstance(item.get('data'),dict):raise ValueError('Malformed translation row')
            title=item['data'].get('title')
            if title in (None,''):continue
            if isinstance(title,str) and not title.strip():continue
            language=item.get('iso_639_1');country=item.get('iso_3166_1')
            if not isinstance(title,str) or len(title)>300 or not re.fullmatch('[a-z]{2,3}',language or '') or country and not re.fullmatch('[A-Z]{2}',country):raise ValueError('Invalid translated title')
            locale=language+('-'+country if country else '')
            desired[(normalize_metadata_text(title),locale)]=title.strip()
        ref=f'tmdb.movie:{mid}:translations'
        old_rows=session.exec(select(FilmTitle).where(FilmTitle.film_id==film_id,FilmTitle.origin_kind=='tmdb',FilmTitle.origin_ref==ref)).all()
        for title in old_rows:
            if (title.normalized_title,title.locale) not in desired:title.superseded_at=observed_at;session.add(title)
        for (normalized,locale),name in desired.items():
            row=next((x for x in old_rows if x.normalized_title==normalized and x.locale==locale),None)
            if row is None:row=FilmTitle(id='title_'+uuid4().hex,film_id=film_id,title=name,title_type='alternative',locale=locale,normalized_title=normalized,origin_kind='tmdb',origin_ref=ref,observed_at=observed_at)
            row.title=name;row.observed_at=observed_at;row.superseded_at=None;session.add(row)
    return {'linked_provisional_identities':linked,'redirected_provisional_identities':redirected,'unresolved_contexts':unresolved}
