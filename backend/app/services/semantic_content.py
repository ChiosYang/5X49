"""Explicit read-only content extraction for offline semantic experiments."""
from dataclasses import dataclass

from sqlmodel import Session, select

from app.canonical_models import Film, FilmTitle, FilmMetadataOverride, LibraryFilmReadModel
from app.services.provenance_resolver import provenance_resolver
from app.services.semantic_search import ContentDocument, ContentSource, SemanticError, MAX_DOCUMENTS, corpus_revision


@dataclass(frozen=True)
class ContentCorpus:
    documents: tuple[ContentDocument, ...]
    identities: dict[str, tuple[str, ...]]
    excluded: dict[str, str]

    @property
    def revision(self):
        return corpus_revision(self.documents)


def collect_content(database_engine) -> ContentCorpus:
    documents, identities, excluded = [], {}, {}
    with Session(database_engine) as session:
        films = session.exec(select(Film).join(LibraryFilmReadModel,
            LibraryFilmReadModel.film_id == Film.id).where(
                Film.lifecycle_status == "active", LibraryFilmReadModel.visible.is_(True))
            .order_by(Film.id).limit(MAX_DOCUMENTS + 1)).all()
        if len(films) > MAX_DOCUMENTS:
            raise SemanticError("corpus_limit")
        for film in films:
            if provenance_resolver.identity_conflicted(session, film.id):
                excluded[film.id] = "identity_conflict"
                continue
            title, original = provenance_resolver.resolve_titles(session, film.id)
            if title.conflicted or original.conflicted:
                excluded[film.id] = "title_conflict"
                continue
            overrides = session.get(FilmMetadataOverride, film.id)
            manual = overrides.values if overrides else {}
            names = {film.canonical_title, film.original_title,
                     manual.get("title"), manual.get("original_title")}
            names.update(session.exec(select(FilmTitle.title).where(
                FilmTitle.film_id == film.id, FilmTitle.superseded_at.is_(None))).all())
            names = tuple(sorted(n for n in names if isinstance(n, str) and n.strip()))
            identities[film.id] = names  # Includes reference Films lacking plot.
            sources = []
            overview = manual.get("overview", film.overview)
            if overview:
                try:
                    sources.append(ContentSource("overview", overview,
                        "user" if "overview" in manual else "library"))
                except SemanticError as exc:
                    excluded[film.id] = exc.code
                    continue
            themes = provenance_resolver.resolve_concepts(session, film.id,
                predicate="HAS_THEME", kind="theme", scopes=("factual", "curated", "inferred"))
            if not themes.conflicted:
                try:
                    sources.extend(ContentSource("reviewed_theme", text, themes.source_kind or "library")
                                   for text in themes.value)
                except SemanticError as exc:
                    excluded[film.id] = exc.code
                    continue
            if not sources:
                excluded[film.id] = "missing_content"
                continue
            try:
                documents.append(ContentDocument(film.id, manual.get("title", film.canonical_title),
                                                 names, tuple(sources)))
            except SemanticError as exc:
                excluded[film.id] = exc.code
    return ContentCorpus(tuple(documents), identities, excluded)
