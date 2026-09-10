from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.canonical_models import Assertion, Concept, Credit, Film, Person
from app.services.provenance_resolver import ResolvedFilmMetadata


FACT_DIMENSIONS = ("genre", "person", "country", "decade")


def build_factual_facets(
    session: Session, film: Film, resolved: ResolvedFilmMetadata,
) -> list[dict[str, Any]]:
    """Build stable factual memberships, independent of Library visibility."""
    facets: list[dict[str, Any]] = []

    def add(**facet: Any) -> None:
        facets.append(facet)

    genre_names = set(resolved.genres.value)
    genre_assertions = session.exec(
        select(Assertion)
        .where(Assertion.subject_entity_id == film.id)
        .where(Assertion.predicate == "HAS_GENRE")
        .where(Assertion.source_scope == "factual")
        .where(Assertion.review_status == "accepted")
        .where(Assertion.superseded_at.is_(None))
        .order_by(Assertion.object_entity_id, Assertion.id)
    ).all()
    genres: dict[str, Concept] = {}
    for assertion in genre_assertions:
        concept = session.get(Concept, assertion.object_entity_id)
        if (
            concept is not None
            and concept.kind == "genre"
            and concept.lifecycle_status == "active"
            and concept.canonical_name in genre_names
        ):
            genres[concept.id] = concept
    for concept in genres.values():
        add(
            dimension="genre",
            facet_key=concept.id,
            film_id=film.id,
            display_label=concept.canonical_name,
            conflicted=resolved.genres.conflicted,
            payload={
                "source_kind": resolved.genres.source_kind,
                "observed_at": resolved.genres.observed_at,
                "policy_version": resolved.genres.policy_version,
            },
        )

    people: dict[str, dict[str, Any]] = {}
    for credit_id in resolved.credits.value:
        credit = session.get(Credit, credit_id)
        if credit is None:
            continue
        role = None
        if (credit.department, credit.job) == ("Directing", "Director"):
            role = "director"
        elif (credit.department, credit.job) == ("Acting", "Actor"):
            role = "actor"
        if role is None:
            continue
        person = session.get(Person, credit.person_id)
        if person is None or person.lifecycle_status != "active":
            continue
        item = people.setdefault(person.id, {"person": person, "roles": set()})
        item["roles"].add(role)
    for person_id in sorted(people):
        person = people[person_id]["person"]
        add(
            dimension="person",
            facet_key=person_id,
            film_id=film.id,
            display_label=person.canonical_name,
            conflicted=resolved.credits.conflicted,
            payload={
                "source_kind": resolved.credits.source_kind,
                "observed_at": resolved.credits.observed_at,
                "policy_version": resolved.credits.policy_version,
                "roles": sorted(people[person_id]["roles"]),
            },
        )

    for country_code in resolved.countries.value:
        add(
            dimension="country",
            facet_key=country_code,
            film_id=film.id,
            display_label=country_code,
            conflicted=resolved.countries.conflicted,
            payload={
                "source_kind": resolved.countries.source_kind,
                "observed_at": resolved.countries.observed_at,
                "policy_version": resolved.countries.policy_version,
            },
        )

    if film.release_year is not None:
        decade = film.release_year // 10 * 10
        add(
            dimension="decade",
            facet_key=str(decade),
            film_id=film.id,
            display_label=f"{decade}s",
            conflicted=False,
            payload={
                "source_kind": "canonical",
                "policy_version": "release-year-decade.v1",
                "derivation": "release_year",
            },
        )

    return facets
