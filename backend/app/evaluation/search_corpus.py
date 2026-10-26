"""Public corpus-only validation and an isolated real-SQL projection fixture.

This module never opens the persistent library or annotated holdout. Its SQL
facts come from accepted corpus fields; absent/conflicted values stay unknown.
"""
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.public_movies import load_fixture
from app.services.semantic_search import ContentDocument, ContentSource, SemanticError

CORPUS_SHA = "6a3ed86909e95c058db3be1bbb64d6e60f47403a04e3509e6f3acb70fd3028ec"


class CorpusFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted", "missing", "unknown", "conflicted"]
    sources: list[str]
    reason: str


class ListFact(CorpusFact):
    value: list[str] | None

    @model_validator(mode="after")
    def accepted_only(self):
        if self.status == "accepted" and (not self.value or not self.sources):
            raise ValueError("Accepted public fact needs a value and source")
        if self.status != "accepted":
            if self.value:
                raise ValueError("Unknown public fact cannot supply matching values")
            self.value = []
        return self


class ScalarFact(CorpusFact):
    value: int | None = Field(strict=True, ge=1, le=10000)

    @model_validator(mode="after")
    def accepted_only(self):
        if (self.status == "accepted") != (self.value is not None) or self.value is not None and not self.sources:
            raise ValueError("Unknown scalar cannot be matched")
        return self


class CorpusTitle(BaseModel):
    locale: str
    value: str = Field(min_length=1, max_length=300)
    source: str | None = None
    sources: list[str] = Field(default_factory=list)


class CorpusFilm(BaseModel):
    # The original bytes are hash-bound. Read only the declared runtime fields;
    # the corpus's evidence and cohort metadata stay untouched in the source.
    id: str = Field(pattern=r"^film_[a-f0-9]{32}$")
    title_en: str
    title_zh: str | None
    titles: list[CorpusTitle] = Field(min_length=1, max_length=60)
    document_text: str = Field(min_length=1, max_length=512)
    year: ScalarFact
    minutes: ScalarFact
    countries: ListFact
    directors: ListFact
    genres: ListFact


def load_corpus(path: Path):
    raw = path.read_bytes()
    if len(raw) != 225932 or sha256(raw).hexdigest() != CORPUS_SHA:
        raise SemanticError("search_public_corpus_hash_mismatch")
    payload = json.loads(raw)
    if (payload.get("version") != "semantic-quality.public-corpus.v2"
            or any(key in payload for key in ("cases", "queries", "qrels", "gold"))
            or payload.get("film_count") != 64 or len(payload["films"]) != 64):
        raise SemanticError("search_public_corpus_invalid")
    films = tuple(CorpusFilm.model_validate(film)
                  for film in payload["films"])
    if len({film.id for film in films}) != 64:
        raise SemanticError("search_public_corpus_invalid")
    old = load_fixture(Path(__file__).resolve().parents[2] / "fixtures/semantic_search/public-movies-v1.json")
    by_id = {film.id: film for film in films}
    if any(film.id not in by_id or by_id[film.id].document_text != film.document_text for film in old.films):
        raise SemanticError("search_legacy_content_changed")
    return payload, films


def documents(films):
    return tuple(ContentDocument(film.id, film.title_en, tuple(sorted({t.value for t in film.titles})),
        (ContentSource("overview", film.document_text, "rule"),)) for film in films)


def seed_projection_database(engine, payload, films):
    """Create only a new caller-owned evaluation DB, never modify a library.

    Use the production projection schemas and production SQL executor; no query
    oracle/expected IDs are injected. This is public fixture state, not an import
    or a production migration. No media paths, credentials or personal reviews.
    """
    from sqlalchemy import inspect
    from sqlmodel import SQLModel
    import app.models  # Register the event table referenced by canonical FKs.
    from app.canonical_models import (Concept, ExploreFacetReadModel, ExploreFilmReadModel,
        ExternalIdentity, Film, FilmDetailReadModel, FilmSearchReadModel, GraphEntity,
        LibraryFilmReadModel, Person, PersonAlias, ProjectionState)
    from app.services.projections import PROJECTION_VERSIONS
    from app.contracts.structured_metadata import normalize_metadata_text as norm
    from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary

    if inspect(engine).get_table_names():
        raise SemanticError("search_evaluation_database_not_empty")
    SQLModel.metadata.create_all(engine)
    people = {}
    by_id = {film["id"]: film for film in payload["films"]}
    for film in films:
        names = by_id[film.id]["director_names"]
        if film.directors.status == "accepted" and names["status"] == "accepted" and len(film.directors.value) == len(names["value"]):
            for qid, name in zip(film.directors.value, names["value"]):
                people.setdefault(qid, {"name": name, "aliases": set(), "films": set()})["films"].add(film.id)
                people[qid]["aliases"].add(name)
    # Existing independently sourced aliases can be reused; never invent a
    # translated/transliterated identity for a new director.
    old = load_fixture(Path(__file__).resolve().parents[2] / "fixtures/semantic_search/public-movies-v1.json")
    for person in old.people:
        if person.qid in people:
            people[person.qid]["aliases"].update(person.aliases)
    ids = {qid: "person_" + sha256(qid.encode()).hexdigest()[:32] for qid in people}
    with engine.begin() as connection:
        def add(model, **fields):
            row = model(**fields)
            connection.execute(model.__table__.insert().values(**row.model_dump()))
        for name in ("library", "search", "detail", "explore_films", "explore_facets"):
            add(ProjectionState, name=name, projection_version=PROJECTION_VERSIONS[name], status="ready", row_count=len(films))
        genres = {}
        for label in {g for film in films for g in film.genres.value}:
            entry = vocabulary.resolve_genre(label)
            if entry is None:
                raise SemanticError("search_corpus_unknown_genre")
            key = "concept_" + sha256(entry.canonical_key.encode()).hexdigest()[:32]
            genres[label] = key
            if list(genres.values()).count(key) == 1:
                add(GraphEntity, id=key, entity_type="concept")
                add(Concept, id=key, kind="genre", canonical_name=entry.canonical_name, canonical_key=entry.canonical_key)
        for qid, person in people.items():
            identifier = ids[qid]
            add(GraphEntity, id=identifier, entity_type="person")
            add(Person, id=identifier, canonical_name=person["name"], normalized_name=norm(person["name"]), resolution_status="verified")
            identity = "external_" + sha256(qid.encode()).hexdigest()[:32]
            add(ExternalIdentity, id=identity, entity_id=identifier,
                provider="wikidata" if qid.startswith("Q") else "public-corpus.person", external_id=qid,
                provenance_kind="public-fixture", provenance_ref=qid)
            unique_aliases = dict(sorted((norm(alias), alias) for alias in person["aliases"]))
            for index, (normalized, alias) in enumerate(unique_aliases.items()):
                add(PersonAlias, id=f"alias_{qid}_{index}", person_id=identifier, film_id=sorted(person["films"])[0],
                    identity_id=identity, name=alias, normalized_name=normalized, origin_kind="public-fixture",
                    origin_ref=qid, observed_at="2026-10-23T00:00:00Z")
        for film in films:
            aliases = sorted({t.value for t in film.titles})
            summary = {"id": film.id, "title": film.title_en, "original_title": film.title_zh,
                "year": film.year.value, "runtime_minutes": film.minutes.value, "overview": film.document_text,
                "identities": {}, "countries": film.countries.value, "genres": film.genres.value,
                "directors": by_id[film.id]["director_names"]["value"], "primary_item": None,
                "profile_state": {"favorite": False, "rating": None, "notes": None, "watched": False},
                "external_scores": [], "analysis": {"status": "pending"}}
            add(GraphEntity, id=film.id, entity_type="film")
            add(Film, id=film.id, canonical_title=film.title_en, original_title=film.title_zh,
                release_year=film.year.value, runtime_minutes=film.minutes.value, overview=film.document_text)
            add(LibraryFilmReadModel, film_id=film.id, sort_title=norm(film.title_en), release_year=film.year.value,
                payload=summary, source_hash="0" * 64, projection_version=PROJECTION_VERSIONS["library"])
            add(FilmDetailReadModel, film_id=film.id, payload={**summary, "editions": []}, source_hash="0" * 64,
                projection_version=PROJECTION_VERSIONS["detail"])
            add(FilmSearchReadModel, film_id=film.id, normalized_title=norm(film.title_en), release_year=film.year.value,
                exact_titles="\n" + "\n".join(sorted({norm(n) for n in aliases})) + "\n",
                search_text="\n".join(sorted({norm(n) for n in aliases} | {
                    norm(alias) for person in film.directors.value if person in people
                    for alias in people[person]["aliases"]})), source_hash="0" * 64,
                projection_version=PROJECTION_VERSIONS["search"])
            add(ExploreFilmReadModel, film_id=film.id, sort_title=norm(film.title_en), release_year=film.year.value,
                source_hash="0" * 64, projection_version=PROJECTION_VERSIONS["explore_films"])
            for dimension, values in (("country", film.countries.value), ("genre", [genres[g] for g in film.genres.value]),
                    ("person", [ids[p] for p in film.directors.value if p in ids])):
                for key in values:
                    add(ExploreFacetReadModel, dimension=dimension, facet_key=key, film_id=film.id,
                        display_label=key, normalized_label=norm(key), payload={"roles": ["director"]} if dimension == "person" else {},
                        source_hash="0" * 64, projection_version=PROJECTION_VERSIONS["explore_facets"])
