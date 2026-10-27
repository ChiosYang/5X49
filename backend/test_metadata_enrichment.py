import unittest
from sqlmodel import Session, select
import app.models
from app.canonical_models import ExternalIdentity, Film, GraphEntity, LibraryItem, Person, Credit
from app.contracts.structured_metadata import CreditObservation
from app.services.metadata_enrichment import apply_enrichment
from app.services.search_local import LocalSearch
import test_search_metadata_coverage as coverage
import test_structured_metadata_runtime as fixture

class MetadataEnrichmentTests(unittest.TestCase):
    setUp=coverage.MetadataCoverageTests.setUp
    def prepare(self,protected=False):
        self.payload.update(id=42,spoken_languages=[{'iso_639_1':'en'}])
        self.payload['credits']['crew']=[{'id':100,'name':'Public Director','original_name':'Public Director','job':'Director'}]
        self.people={100:{'id':100,'name':'Public Director','also_known_as':['导者','Literal Alias']}}
        self.second='film_'+'7'*32
        with Session(self.engine) as s:
            s.add(ExternalIdentity(id='identity_'+'1'*32,entity_id=fixture.FILM_ID,provider='tmdb.movie',external_id='42',provenance_kind='nfo',provenance_ref='nfo:fixture'))
            s.add(GraphEntity(id=self.second,entity_type='film'));s.add(Film(id=self.second,canonical_title='Second'))
            s.add(LibraryItem(id='lib_'+'7'*32,profile_id='profile_local',film_id=self.second,source_type='local',source_instance_id='local',source_item_key='synthetic:second'));s.flush()
            self.sync.sync(s,film_id=self.second,library_item_id=None,observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:second',credits=[CreditObservation('Public Director','Directing','Director',provider='tmdb.person',external_id='100')]))
            self.sync.sync(s,film_id=fixture.FILM_ID,library_item_id=fixture.ITEM_ID,observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:main',credits=[CreditObservation('导者','Directing','Director')]))
            if protected:self.sync.sync(s,film_id=fixture.FILM_ID,library_item_id=None,observation=fixture.StructuredMetadataRuntimeTests._observation('curated','user:director',credits=[CreditObservation('导者','Directing','Director')]))
            s.commit()
            old=s.exec(select(Person).where(Person.canonical_name=='导者')).all();self.old_ids=[x.id for x in old]
    def test_unique_official_id_context_redirect_retains_source_and_search(self):
        self.prepare()
        with Session(self.engine) as s:
            report=apply_enrichment(s,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);s.commit()
            self.assertEqual(report['redirected_provisional_identities'],1)
            old=s.get(Person,self.old_ids[0]);self.assertEqual(old.lifecycle_status,'merged');self.assertIsNotNone(old.merged_into_id)
        result=LocalSearch(self.engine).interpret('films directed by 导者')
        self.assertEqual(result['status'],'ready');self.assertEqual(result['results']['total'],2)
        result=LocalSearch(self.engine).interpret('films directed by Literal Alias')
        self.assertEqual(result['results']['total'],2)
    def test_curated_person_is_never_redirected(self):
        self.prepare(protected=True)
        with Session(self.engine) as s:
            report=apply_enrichment(s,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);s.commit()
            self.assertEqual(report['redirected_provisional_identities'],0)
            self.assertTrue(all(s.get(Person,p).lifecycle_status=='active' for p in self.old_ids))
    def test_complete_provider_cast_supplements_nfo_but_respects_curated_set(self):
        from app.services.structured_metadata_observations import tmdb_structured_metadata_observation
        self.prepare()
        with Session(self.engine) as session:
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
        self.assertEqual(LocalSearch(self.engine).interpret('films starring Local Actor 14')['results']['total'],1)
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=fixture.FILM_ID,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('curated','user:cast',credits=[CreditObservation('Curated Actor','Acting','Actor')]))
            session.commit()
        self.assertEqual(LocalSearch(self.engine).interpret('films starring Local Actor 14')['status'],'needs_clarification')
        self.assertEqual(LocalSearch(self.engine).interpret('films starring Curated Actor')['results']['total'],1)

    def test_director_alias_withdrawal_is_scoped_and_ambiguous_alias_needs_choice(self):
        self.prepare()
        with Session(self.engine) as session:
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
        self.assertEqual(LocalSearch(self.engine).interpret('films directed by Literal Alias')['results']['total'],2)
        self.people[100]['also_known_as']=['导者']
        with Session(self.engine) as session:
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
        self.assertEqual(LocalSearch(self.engine).interpret('films directed by Literal Alias')['status'],'needs_clarification')
        # A different verified ID can legitimately share an alias; never merge it.
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=self.second,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:second',credits=[CreditObservation('Public Director','Directing','Director',provider='tmdb.person',external_id='100'),CreditObservation('Other Director','Directing','Director',provider='tmdb.person',external_id='101',aliases=('导者',))]))
            session.commit()
        self.assertEqual(LocalSearch(self.engine).interpret('films directed by 导者')['status'],'needs_clarification')

    def test_malformed_enrichment_rolls_back_source_and_projection_changes(self):
        from app.services.projections import projection_reader
        self.prepare()
        with Session(self.engine) as session:
            before='\n'.join(session.connection().connection.driver_connection.iterdump())
        self.payload['translations']={'translations':[{'data':{'title':'New alias'},'iso_639_1':'bad locale'}]}
        with self.assertRaises(ValueError):
            with Session(self.engine) as session:
                apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2)
                session.commit()
        with Session(self.engine) as session:
            self.assertEqual(before,'\n'.join(session.connection().connection.driver_connection.iterdump()))
        self.assertEqual(projection_reader.film_page(self.engine,query='New alias')['total'],0)

    def test_incomplete_provider_identity_snapshot_cannot_keep_full_cast_marker(self):
        from app.metadata_source_models import FilmMetadataSourceSnapshot
        self.prepare()
        with Session(self.engine) as session:
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
            self.assertEqual(len(session.exec(select(FilmMetadataSourceSnapshot).where(FilmMetadataSourceSnapshot.field_kind=='cast')).all()),1)
        for actor in self.payload['credits']['cast']:actor.pop('id')
        observation=__import__('app.services.structured_metadata_observations',fromlist=['tmdb_structured_metadata_observation']).tmdb_structured_metadata_observation(self.payload,42,language='en',observed_at=fixture.T2)
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=fixture.FILM_ID,library_item_id=None,observation=observation);session.commit()
            self.assertEqual(session.exec(select(FilmMetadataSourceSnapshot).where(FilmMetadataSourceSnapshot.field_kind=='cast')).all(),[])

    def test_enrichment_refuses_conflicting_or_inactive_film_identity(self):
        self.prepare()
        with Session(self.engine) as session:
            session.add(ExternalIdentity(id='identity_'+'9'*32,entity_id=fixture.FILM_ID,provider='tmdb.movie',external_id='43',provenance_kind='nfo',provenance_ref='nfo:conflict'));session.commit()
        with self.assertRaises(ValueError):
            with Session(self.engine) as session:
                apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2)
        with Session(self.engine) as session:
            row=session.exec(select(ExternalIdentity).where(ExternalIdentity.external_id=='43')).one();session.delete(row)
            film=session.get(Film,fixture.FILM_ID);film.lifecycle_status='merged';session.add(film);session.commit()
        with self.assertRaises(ValueError):
            with Session(self.engine) as session:
                apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2)

    def test_fresh_id_never_certifies_a_cross_film_shared_provisional_person(self):
        self.prepare()
        # Both NFO observations share the same local source/person key. Only
        # the first film's public data corroborates this name; the second is not proof.
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=self.second,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:cross-film',credits=[CreditObservation('Local Actor 0','Acting','Actor',character='Role 0',billing_order=0)]))
            self.sync.sync(session,film_id=fixture.FILM_ID,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:single-film',credits=[CreditObservation('Local Actor 0','Acting','Actor',character='Role 0',billing_order=0)]))
            session.commit()
            person=session.exec(select(Person).where(Person.canonical_name=='Local Actor 0')).one()
            provisional=person.id
            before=[(c.id,c.film_id,c.person_id) for c in session.exec(select(Credit).where(Credit.person_id==provisional)).all()]
            self.assertEqual(len(before),2)
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
            self.assertEqual(session.get(Person,provisional).resolution_status,'provisional')
            self.assertIsNone(session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==provisional,ExternalIdentity.provider=='tmdb.person')).first())
            self.assertEqual(before,[(c.id,c.film_id,c.person_id) for c in session.exec(select(Credit).where(Credit.person_id==provisional)).all()])

    def test_fresh_id_preserves_curated_alias_assertion_and_other_provider_evidence(self):
        from app.canonical_models import PersonAlias, Assertion, AssertionPredicate, CreditProvenance
        from app.services.metadata_enrichment import _can_link_single_context
        self.prepare()
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=fixture.FILM_ID,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:fresh',credits=[CreditObservation('Local Actor 0','Acting','Actor',character='Role 0',billing_order=0)]))
            session.commit()
            person=session.exec(select(Person).where(Person.canonical_name=='Local Actor 0')).one()
            credit=session.exec(select(Credit).where(Credit.person_id==person.id)).one()
            identity=session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==person.id)).one()
            self.assertTrue(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            identity.provenance_kind='curated';session.add(identity);session.flush()
            self.assertFalse(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            identity.provenance_kind='nfo';session.add(identity)
            alias=PersonAlias(id='person_alias_'+'a'*32,person_id=person.id,film_id=fixture.FILM_ID,
                identity_id=identity.id,locale='und',name='User Alias',normalized_name='user alias',
                origin_kind='curated',origin_ref='user:alias',observed_at=fixture.T1)
            session.add(alias);session.flush()
            self.assertFalse(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            session.delete(alias);session.flush()
            curated=CreditProvenance(id='credit_provenance_'+'c'*32,credit_id=credit.id,
                origin_kind='curated',origin_ref='user:credit',observed_at=fixture.T1)
            session.add(curated);session.flush()
            self.assertFalse(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            session.delete(curated);session.flush()
            session.add(AssertionPredicate(key='SYNTHETIC_PERSON_CONTEXT',vocabulary_version='synthetic.v1',
                subject_entity_type='person',object_entity_type='film',evidence_policy='optional'))
            session.flush()
            assertion=Assertion(subject_entity_id=person.id,object_entity_id=fixture.FILM_ID,
                predicate='SYNTHETIC_PERSON_CONTEXT',qualifier_hash='c'*64,assertion_key='d'*64,
                source_scope='curated',first_seen_at=fixture.T1,last_seen_at=fixture.T1)
            session.add(assertion);session.flush()
            self.assertFalse(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            session.delete(assertion);session.flush()
            other=ExternalIdentity(id='identity_'+'b'*32,entity_id=person.id,provider='other.person',external_id='known-other',provenance_kind='nfo',provenance_ref='nfo:other')
            session.add(other);session.flush()
            self.assertFalse(_can_link_single_context(session,person,credit,fixture.FILM_ID))
            apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
            self.assertIsNone(session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==person.id,ExternalIdentity.provider=='tmdb.person')).first())

    def test_two_conflicting_credit_contexts_never_use_the_last_public_candidate(self):
        self.prepare()
        self.payload['credits']['cast']=[
            {'id':200,'name':'Shared Actor','original_name':'Shared Actor','character':'Role One','order':0},
            {'id':201,'name':'Shared Actor','original_name':'Shared Actor','character':'Role Two','order':1}]
        with Session(self.engine) as session:
            self.sync.sync(session,film_id=fixture.FILM_ID,library_item_id=None,
                observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:conflicting-roles',credits=[
                    CreditObservation('Shared Actor','Acting','Actor',character='Role One',billing_order=0),
                    CreditObservation('Shared Actor','Acting','Actor',character='Role Two',billing_order=1)]))
            session.commit()
            provisional=session.exec(select(Person).where(Person.canonical_name=='Shared Actor')).one().id
            report=apply_enrichment(session,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);session.commit()
            self.assertGreaterEqual(report['unresolved_contexts'],2)
            self.assertEqual(session.get(Person,provisional).resolution_status,'provisional')
            self.assertIsNone(session.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==provisional,ExternalIdentity.provider=='tmdb.person')).first())

    def test_missing_credit_roles_preserve_each_other(self):
        self.payload['spoken_languages']=[{'iso_639_1':'en'}]
        self.apply=coverage.MetadataCoverageTests.apply.__get__(self)
        self.apply();local=LocalSearch(self.engine)
        self.payload['credits'].pop('crew');self.payload['credits']['cast']=self.payload['credits']['cast'][:10];self.apply()
        self.assertEqual(local.interpret('films directed by Test Director')['results']['total'],1)
        self.assertEqual(local.interpret('films starring Local Actor 14')['status'],'needs_clarification')
        self.payload['credits']['crew']=[];self.payload['credits'].pop('cast');self.apply()
        self.assertEqual(local.interpret('films starring Local Actor 0')['results']['total'],1)
    def test_same_name_with_wrong_credit_context_never_attaches_id(self):
        self.prepare()
        with Session(self.engine) as s:
            self.sync.sync(s,film_id=fixture.FILM_ID,library_item_id=fixture.ITEM_ID,observation=fixture.StructuredMetadataRuntimeTests._observation('nfo','nfo:actor',credits=[CreditObservation('Actor 0','Acting','Actor',character='Different character',billing_order=0)]));s.commit()
            provisional=s.exec(select(Person).where(Person.canonical_name=='Actor 0')).one().id
            apply_enrichment(s,fixture.FILM_ID,self.payload,self.people,observed_at=fixture.T2);s.commit()
            self.assertIsNone(s.exec(select(ExternalIdentity).where(ExternalIdentity.entity_id==provisional,ExternalIdentity.provider=='tmdb.person')).first())

if __name__=='__main__':unittest.main()
