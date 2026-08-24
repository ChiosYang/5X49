from __future__ import annotations

from sqlmodel import Session, select

from app.models import LegacyMovieAlias, Movie, MovieUserState
from app.services.canonical_runtime import canonical_runtime_writer
from app.services.canonical_shadow import CanonicalShadowReader, FIELD_SOURCES


def rebuild_legacy_compatibility_projections(engine) -> dict[str, int]:
    """Idempotently align Legacy rows with fields owned by Canonical data."""
    reader = CanonicalShadowReader(engine)
    movie_fields = set(Movie.model_fields)
    movies_updated = 0
    user_states_updated = 0
    with Session(engine) as session:
        aliases = session.exec(
            select(LegacyMovieAlias).order_by(LegacyMovieAlias.legacy_movie_id)
        ).all()
        for alias in aliases:
            movie = session.get(Movie, alias.legacy_movie_id)
            canonical = reader.get_movie(alias.legacy_movie_id)
            if movie is None or canonical is None:
                continue
            changed = False
            for field, source in FIELD_SOURCES.items():
                if (
                    source == "legacy_projection"
                    or field not in movie_fields
                    or field not in canonical
                ):
                    continue
                value = canonical[field]
                if getattr(movie, field) != value:
                    setattr(movie, field, value)
                    changed = True
            if changed:
                session.add(movie)
                movies_updated += 1

            before = session.get(MovieUserState, alias.legacy_movie_id)
            before_dump = before.model_dump() if before is not None else None
            canonical_runtime_writer.sync_user_state(
                session,
                alias.legacy_movie_id,
                fields_set=set(),
            )
            after = session.get(MovieUserState, alias.legacy_movie_id)
            after_dump = after.model_dump() if after is not None else None
            if before_dump != after_dump:
                user_states_updated += 1
        session.commit()
    return {
        "movies_updated": movies_updated,
        "user_states_updated": user_states_updated,
    }
