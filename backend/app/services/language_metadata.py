"""Source-owned language snapshots, resolved without inference or network."""
from sqlmodel import Session, select
from app.canonical_models import FilmMetadataOverride
from app.metadata_source_models import FilmMetadataSourceSnapshot
from app.contracts.languages import language_code

FIELDS={'original':'original_language','spoken':'spoken_languages'}

def sync_languages(session:Session,film_id,observation):
    if getattr(observation,'complete_cast',False):
        row=session.exec(select(FilmMetadataSourceSnapshot).where(
            FilmMetadataSourceSnapshot.film_id==film_id,FilmMetadataSourceSnapshot.field_kind=="cast",
            FilmMetadataSourceSnapshot.origin_kind==observation.origin_kind,
            FilmMetadataSourceSnapshot.origin_ref==observation.origin_ref)).first()
        if row is None:row=FilmMetadataSourceSnapshot(film_id=film_id,field_kind="cast",
            origin_kind=observation.origin_kind,origin_ref=observation.origin_ref)
        row.values=[];row.observed_at=observation.observed_at;session.add(row)
    elif ("Acting","Actor") in getattr(observation,"complete_credit_roles",()):
        # A supplied replacement without verified person IDs is not evidence
        # for supplementing the higher-priority NFO cast. Missing blocks keep it.
        for row in session.exec(select(FilmMetadataSourceSnapshot).where(
                FilmMetadataSourceSnapshot.film_id==film_id,
                FilmMetadataSourceSnapshot.field_kind=="cast",
                FilmMetadataSourceSnapshot.origin_kind==observation.origin_kind,
                FilmMetadataSourceSnapshot.origin_ref==observation.origin_ref)).all():
            session.delete(row)
    snapshots=getattr(observation,'language_snapshots',{})
    for kind,values in snapshots.items():
        field=FIELDS[kind]
        values=sorted({language_code(x) for x in values})
        if kind=='original' and len(values)>1:raise ValueError('Original language must be singular')
        row=session.exec(select(FilmMetadataSourceSnapshot).where(
            FilmMetadataSourceSnapshot.film_id==film_id,
            FilmMetadataSourceSnapshot.field_kind==field,
            FilmMetadataSourceSnapshot.origin_kind==observation.origin_kind,
            FilmMetadataSourceSnapshot.origin_ref==observation.origin_ref)).first()
        if row is None:
            row=FilmMetadataSourceSnapshot(film_id=film_id,field_kind=field,
                origin_kind=observation.origin_kind,origin_ref=observation.origin_ref)
        row.values=values;row.observed_at=observation.observed_at;session.add(row)

def resolved_languages(session:Session,film_id,*,ignore_manual=False):
    from app.services.provenance_resolver import provenance_resolver
    override=session.get(FilmMetadataOverride,film_id)
    manual=override.values if override and not ignore_manual else {}
    payload={'original_language':None,'spoken_languages':[],'language_coverage':{},'language_sources':{}}
    for kind,field in FIELDS.items():
        if field in manual:
            raw=manual[field]
            values=([raw] if kind=='original' and raw else raw or [])
            values=sorted({language_code(x) for x in values})
            state='known' if values else 'unknown'
            source={'source_kind':'user','conflicted':False,'manual':True}
        else:
            rows=session.exec(select(FilmMetadataSourceSnapshot).where(
                FilmMetadataSourceSnapshot.film_id==film_id,
                FilmMetadataSourceSnapshot.field_kind==field)).all()
            values=[];state='unknown';source={'source_kind':None,'conflicted':False,'manual':False}
            if rows:
                rank=min(provenance_resolver.source_rank(r.origin_kind) for r in rows)
                owners=[r for r in rows if provenance_resolver.source_rank(r.origin_kind)==rank]
                sets={tuple(sorted(set(r.values))) for r in owners}
                conflicted=len(sets)>1
                chosen=max(owners,key=lambda r:(r.observed_at,r.origin_ref))
                values=[] if conflicted else list(next(iter(sets)))
                state='conflicted' if conflicted else 'known' if values else 'unknown'
                source={'source_kind':chosen.origin_kind,'conflicted':conflicted,'manual':False}
        payload[field]=values[0] if kind=='original' and values else None if kind=='original' else values
        payload['language_coverage'][kind]=state
        payload['language_sources'][kind]=source
    return payload
