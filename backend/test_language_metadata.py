"""Synthetic language/source boundary tests; no remote providers."""
import unittest
from unittest.mock import patch
from sqlmodel import Session
import app.models
from app.canonical_models import Film, FilmMetadataOverride, GraphEntity, LibraryItem
from app.metadata_source_models import FilmMetadataSourceSnapshot
from app.services.search_local import LocalSearch
from app.services.search_rules import parse_extended
from app.contracts.languages import tmdb_language_snapshots
import test_search_metadata_coverage as fixture

class LanguageMetadataTests(unittest.TestCase):
    setUp=fixture.MetadataCoverageTests.setUp
    apply=fixture.MetadataCoverageTests.apply
    def setup_languages(self):
        self.payload['original_language']='en'
        self.payload['spoken_languages']=[{'iso_639_1':'en'},{'iso_639_1':'ja'}]
        self.apply();return LocalSearch(self.engine)
    def test_original_spoken_country_and_literal_identity_are_distinct(self):
        local=self.setup_languages()
        for q,total in [('Japanese-language films',1),('films in Japanese',1),('原始语言为日语的电影',0),('原始语言为英语的电影',1),('不要日语电影',0),('films not in French',1)]:
            r=local.interpret(q);self.assertEqual(r['status'],'ready',q);self.assertEqual(r['results']['total'],total,q)
        with Session(self.engine) as s:
            fid='film_'+'8'*32;s.add(GraphEntity(id=fid,entity_type='film'));s.add(Film(id=fid,canonical_title='In Japanese'))
            s.add(LibraryItem(id='lib_'+'8'*32,profile_id='profile_local',film_id=fid,source_type='local',source_instance_id='local',source_item_key='synthetic:unknown'));s.commit()
        self.assertEqual(local.interpret('In Japanese')['status'],'keyword')
        self.assertEqual(local.interpret('films not in French')['results']['total'],1)
    def test_missing_null_empty_and_malformed_snapshots(self):
        local=self.setup_languages()
        self.payload.pop('spoken_languages');self.apply();self.assertEqual(local.interpret('films in Japanese')['results']['total'],1)
        self.payload['spoken_languages']=None;self.apply();self.assertEqual(local.interpret('films in Japanese')['results']['total'],1)
        self.payload['spoken_languages']=[{'iso_639_1':'zz'}]
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],1)
        self.payload['spoken_languages']=[];self.apply()
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],0)
        self.assertEqual(local.interpret('films not in French')['results']['total'],0)
    def test_same_priority_conflict_is_unknown_for_positive_and_negative(self):
        local=self.setup_languages()
        with Session(self.engine) as s:
            s.add(FilmMetadataSourceSnapshot(film_id=fixture.fixture.FILM_ID,field_kind='spoken_languages',origin_kind='tmdb',origin_ref='tmdb.movie:99',values=['fr']));s.commit()
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],0)
        self.assertEqual(local.interpret('films not in French')['results']['total'],0)
    def test_manual_clear_and_reset_survive_automatic_refresh(self):
        local=self.setup_languages()
        with Session(self.engine) as s:
            row=FilmMetadataOverride(film_id=fixture.fixture.FILM_ID,values={'spoken_languages':None});s.add(row);s.commit()
        self.apply();self.assertEqual(local.interpret('films not in French')['results']['total'],0)
        with Session(self.engine) as s:
            row=s.get(FilmMetadataOverride,fixture.fixture.FILM_ID);row.values={};s.add(row);s.commit()
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],1)
    def test_literal_people_are_protected_and_unknown_clauses_are_not_dropped(self):
        plan,leftover,issue=parse_extended('films directed by English Language in Japanese after 2000')
        self.assertIsNone(issue);self.assertFalse(leftover);self.assertEqual(plan.people[0].name,'English Language');self.assertEqual(plan.languages[0].code,'ja')
        local=self.setup_languages()
        self.assertEqual(local.interpret('films in Japanese about friendship')['status'],'unsupported')
        self.assertEqual(local.interpret('films in Japanese or under 90 minutes')['status'],'unsupported')
    def test_language_edit_service_updates_projection_and_reset_restores_source(self):
        from app.contracts.film_metadata import MetadataUpdate
        from app.services.film_metadata import metadata_view, update_metadata
        local=self.setup_languages()
        with Session(self.engine) as session:before=metadata_view(session,fixture.fixture.FILM_ID)
        response=update_metadata(self.engine,fixture.fixture.FILM_ID,MetadataUpdate.model_validate({
            'revision':before['revision'],'idempotency_key':'language-edit-0001',
            'changes':{'original_language':{'action':'set','value':'fr'},'spoken_languages':{'action':'set','value':['fr']}}}))
        self.assertEqual(local.interpret('original language French')['results']['total'],1)
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],0)
        self.assertEqual(response['fields']['spoken_languages']['automatic_value'],['en','ja'])
        self.apply()
        self.assertEqual(local.interpret('films in French')['results']['total'],1)
        with Session(self.engine) as session:current=metadata_view(session,fixture.fixture.FILM_ID)
        update_metadata(self.engine,fixture.fixture.FILM_ID,MetadataUpdate.model_validate({
            'revision':current['revision'],'idempotency_key':'language-reset-001',
            'changes':{'original_language':{'action':'reset'},'spoken_languages':{'action':'reset'}}}))
        self.assertEqual(local.interpret('films in Japanese')['results']['total'],1)
        self.assertEqual(local.interpret('original language English')['results']['total'],1)

    def test_language_grammar_keeps_unsupported_and_person_boundaries(self):
        local=self.setup_languages()
        for q in ['只看日语电影','我想找包含日语对白的电影','English-language films after 2000']:
            self.assertEqual(local.interpret(q)['status'],'ready',q)
        for q in ['films in UnknownLanguage','original language Japanese or English']:
            self.assertNotEqual(local.interpret(q)['status'],'ready',q)

    def test_tmdb_cantonese_is_explicit_not_inferred_from_country(self):
        self.assertEqual(tmdb_language_snapshots({'original_language':'cn','spoken_languages':[{'iso_639_1':'cn'}]}),{'original':('yue',),'spoken':('yue',)})

if __name__=='__main__':unittest.main()
