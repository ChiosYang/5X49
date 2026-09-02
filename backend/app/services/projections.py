from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import event, inspect
from sqlmodel import Session, delete, select

from app.canonical_models import (
    AnalysisResolutionReview,
    AnalysisRun,
    Assertion,
    AssertionEvidence,
    AssertionProvenance,
    Concept,
    Credit,
    CreditProvenance,
    ExploreFacetReadModel,
    ExploreFilmReadModel,
    ExternalIdentity,
    ExternalScoreRefreshState,
    Film,
    FilmCountry,
    FilmCountryProvenance,
    FilmDetailReadModel,
    FilmExternalScore,
    FilmProfileState,
    FilmSearchReadModel,
    FilmTitle,
    GraphEdgeReadModel,
    GraphEntity,
    GraphNodeReadModel,
    IdentityReview,
    LibraryFilmReadModel,
    LibraryItem,
    MediaAsset,
    Person,
    ProjectionState,
    StructuredMetadataReview,
    Viewing,
)
from app.contracts.structured_metadata import normalize_metadata_text
from app.services.provenance_resolver import provenance_resolver


PROJECTION_VERSIONS = {
    "library": "library-film.v1",
    "detail": "film-detail.v1",
    "search": "film-search.v1",
    "explore_films": "factual-explore-film.v1",
    "explore_facets": "factual-explore-facet.v1",
    "graph_nodes": "graph-node.v1",
    "graph_edges": "graph-edge.v1",
}
_TABLES = {
    "library": LibraryFilmReadModel,
    "detail": FilmDetailReadModel,
    "search": FilmSearchReadModel,
    "explore_films": ExploreFilmReadModel,
    "explore_facets": ExploreFacetReadModel,
    "graph_nodes": GraphNodeReadModel,
    "graph_edges": GraphEdgeReadModel,
}
_PRIVATE_KEYS = {
    "absolute_path",
    "file_path",
    "folder_path",
    "locator",
    "media_path",
    "path",
    "secret",
    "token",
}
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


class ProjectionUnavailable(RuntimeError):
    code = "projection_unavailable"


class ProjectionVerificationError(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectionCoordinator:
    def refresh_film(
        self,
        session: Session,
        film_id: str,
        *,
        update_states: bool = True,
    ) -> None:
        from app.services.library import library_manager

        film = session.get(Film, film_id)
        detail = library_manager._canonical_film_view(session, film_id, include_editions=True)
        summary = library_manager._canonical_film_view(session, film_id, include_editions=False)
        if detail is None:
            self._delete_film_views(session, film_id)
        else:
            resolved = provenance_resolver.resolve_film(session, film_id)
            detail = self._safe_payload({**detail, "resolved_sources": resolved.public_sources()})
            summary_payload = summary or {key: value for key, value in detail.items() if key != "editions"}
            summary_payload = self._safe_payload(
                {**summary_payload, "resolved_sources": resolved.public_sources()}
            )
            self._upsert_library(session, film_id, summary_payload, visible=summary is not None)
            self._upsert_detail(session, film_id, detail)
            self._upsert_search(session, film_id, detail)
            if summary is None or film is None:
                self._delete_explore_views(session, film_id)
            else:
                self._refresh_explore(session, film, summary_payload, resolved)
        if film is None or film.lifecycle_status != "active":
            session.exec(delete(GraphEdgeReadModel).where(GraphEdgeReadModel.subject_entity_id == film_id))
            session.exec(delete(GraphNodeReadModel).where(GraphNodeReadModel.entity_id == film_id))
        else:
            self._refresh_graph(session, film_id)
        session.flush()
        if update_states:
            self.refresh_states(session)

    def rebuild_all(self, session: Session) -> dict[str, Any]:
        session.info["skip_projection_hook"] = True
        try:
            for model in (
                ExploreFacetReadModel,
                ExploreFilmReadModel,
                GraphEdgeReadModel,
                GraphNodeReadModel,
                FilmSearchReadModel,
                FilmDetailReadModel,
                LibraryFilmReadModel,
                ProjectionState,
            ):
                session.exec(delete(model))
            session.flush()
            film_ids = session.exec(
                select(Film.id).where(Film.lifecycle_status == "active").order_by(Film.id)
            ).all()
            for film_id in film_ids:
                self.refresh_film(session, film_id, update_states=False)
            session.flush()
            self.refresh_states(session, rebuilt=True)
            session.flush()
            report = self.verify_session(session)
            return report
        finally:
            session.info.pop("skip_projection_hook", None)

    def bootstrap(self, engine) -> dict[str, Any]:
        with Session(engine) as session:
            if self.is_ready(session):
                return self.verify_session(session)
            report = self.rebuild_all(session)
            session.commit()
            return report

    def is_ready(self, session: Session) -> bool:
        if not self.tables_available(session):
            return False
        states = {row.name: row for row in session.exec(select(ProjectionState)).all()}
        return all(
            name in states
            and states[name].status == "ready"
            and states[name].projection_version == version
            for name, version in PROJECTION_VERSIONS.items()
        )

    def refresh_states(self, session: Session, *, rebuilt: bool = False) -> None:
        now = _now()
        for name, model in _TABLES.items():
            rows = session.exec(select(model)).all()
            digest = _hash(sorted((self._row_id(row), row.source_hash) for row in rows))
            state = session.get(ProjectionState, name)
            if state is None:
                state = ProjectionState(name=name, projection_version=PROJECTION_VERSIONS[name])
            state.projection_version = PROJECTION_VERSIONS[name]
            state.status = "ready"
            state.row_count = len(rows)
            state.digest = digest
            state.rebuilt_at = now if rebuilt or state.rebuilt_at is None else state.rebuilt_at
            state.updated_at = now
            session.add(state)

    def verify_session(self, session: Session) -> dict[str, Any]:
        if not self.is_ready(session):
            raise ProjectionVerificationError("projection state is missing or stale")
        checks: dict[str, dict[str, Any]] = {}
        for name, model in _TABLES.items():
            rows = session.exec(select(model)).all()
            for row in rows:
                expected = self._expected_hash(row)
                if expected != row.source_hash:
                    raise ProjectionVerificationError(f"{name} row hash mismatch")
                payload = getattr(row, "payload", None)
                if payload is not None:
                    self._validate_public_payload(payload)
            digest = _hash(sorted((self._row_id(row), row.source_hash) for row in rows))
            state = session.get(ProjectionState, name)
            if state is None or state.row_count != len(rows) or state.digest != digest:
                raise ProjectionVerificationError(f"{name} projection digest mismatch")
            checks[name] = {
                "status": "passed",
                "row_count": len(rows),
                "digest": digest[:16],
                "version": state.projection_version,
            }
        return {"status": "passed", "checks": checks}

    @staticmethod
    def tables_available(session: Session) -> bool:
        try:
            inspector = inspect(session.connection())
            return all(inspector.has_table(model.__tablename__) for model in _TABLES.values()) and inspector.has_table(
                ProjectionState.__tablename__
            )
        except Exception:
            return False

    def _upsert_library(self, session: Session, film_id: str, payload: dict[str, Any], *, visible: bool) -> None:
        source_hash = _hash(payload)
        row = session.get(LibraryFilmReadModel, film_id) or LibraryFilmReadModel(
            film_id=film_id,
            sort_title=normalize_metadata_text(str(payload.get("title") or "")),
            source_hash=source_hash,
            projection_version=PROJECTION_VERSIONS["library"],
        )
        row.sort_title = normalize_metadata_text(str(payload.get("title") or ""))
        row.release_year = payload.get("year")
        row.primary_item_id = (payload.get("primary_item") or {}).get("id")
        row.visible = visible
        row.payload = payload
        row.source_hash = source_hash
        row.projection_version = PROJECTION_VERSIONS["library"]
        row.projected_at = _now()
        session.add(row)

    def _upsert_detail(self, session: Session, film_id: str, payload: dict[str, Any]) -> None:
        source_hash = _hash(payload)
        row = session.get(FilmDetailReadModel, film_id) or FilmDetailReadModel(
            film_id=film_id,
            source_hash=source_hash,
            projection_version=PROJECTION_VERSIONS["detail"],
        )
        row.payload = payload
        row.source_hash = source_hash
        row.projection_version = PROJECTION_VERSIONS["detail"]
        row.projected_at = _now()
        session.add(row)

    def _upsert_search(self, session: Session, film_id: str, detail: dict[str, Any]) -> None:
        searchable = [
            detail.get("title"),
            detail.get("original_title"),
            *(detail.get("countries") or []),
            *(detail.get("genres") or []),
            *(detail.get("directors") or []),
        ]
        search_text = " ".join(
            sorted({normalize_metadata_text(str(value)) for value in searchable if value})
        )
        source = {
            "normalized_title": normalize_metadata_text(str(detail.get("title") or "")),
            "release_year": detail.get("year"),
            "search_text": search_text,
        }
        source_hash = _hash(source)
        row = session.get(FilmSearchReadModel, film_id) or FilmSearchReadModel(
            film_id=film_id,
            normalized_title=source["normalized_title"],
            search_text=search_text,
            source_hash=source_hash,
            projection_version=PROJECTION_VERSIONS["search"],
        )
        row.normalized_title = source["normalized_title"]
        row.release_year = detail.get("year")
        row.search_text = search_text
        row.source_hash = source_hash
        row.projection_version = PROJECTION_VERSIONS["search"]
        row.projected_at = _now()
        session.add(row)

    def _refresh_graph(self, session: Session, film_id: str) -> None:
        session.exec(delete(GraphEdgeReadModel).where(GraphEdgeReadModel.subject_entity_id == film_id))
        self._upsert_graph_node(session, film_id)
        selected_credit_ids = set(provenance_resolver.resolve_credits(session, film_id).value)
        for credit_id in sorted(selected_credit_ids):
            credit = session.get(Credit, credit_id)
            if credit is None or (credit.department, credit.job) not in {
                ("Directing", "Director"),
                ("Acting", "Actor"),
            }:
                continue
            self._upsert_graph_node(session, credit.person_id)
            provenances = session.exec(
                select(CreditProvenance)
                .where(CreditProvenance.credit_id == credit.id)
                .where(CreditProvenance.superseded_at.is_(None))
            ).all()
            relation = "DIRECTED_BY" if credit.job == "Director" else "FEATURES_ACTOR"
            payload = {
                "review_status": "accepted",
                "source_scope": "factual",
                "source_kinds": sorted({item.origin_kind for item in provenances}),
                "evidence_count": 0,
                "billing_order": credit.billing_order,
                "character": credit.character or None,
            }
            self._upsert_graph_edge(
                session,
                edge_id=f"credit:{credit.id}",
                edge_kind="credit",
                subject=film_id,
                object_id=credit.person_id,
                relation=relation,
                priority=10 if relation == "DIRECTED_BY" else 30,
                payload=payload,
            )
        assertions = session.exec(
            select(Assertion)
            .where(Assertion.subject_entity_id == film_id)
            .where(Assertion.superseded_at.is_(None))
            .order_by(Assertion.predicate, Assertion.id)
        ).all()
        for assertion in assertions:
            self._upsert_graph_node(session, assertion.object_entity_id)
            provenances = session.exec(
                select(AssertionProvenance)
                .where(AssertionProvenance.assertion_id == assertion.id)
                .where(AssertionProvenance.superseded_at.is_(None))
            ).all()
            evidence_count = len(
                session.exec(
                    select(AssertionEvidence.id)
                    .where(AssertionEvidence.assertion_id == assertion.id)
                    .where(AssertionEvidence.link_status == "active")
                ).all()
            )
            payload = {
                "assertion_id": assertion.id,
                "review_status": assertion.review_status,
                "source_scope": assertion.source_scope,
                "source_kinds": sorted({item.origin_kind for item in provenances}),
                "evidence_count": evidence_count,
                "conflicted": False,
            }
            self._upsert_graph_edge(
                session,
                edge_id=f"assertion:{assertion.id}",
                edge_kind="assertion",
                subject=assertion.subject_entity_id,
                object_id=assertion.object_entity_id,
                relation=assertion.predicate,
                priority=0 if assertion.predicate == "HAS_GENRE" else 20,
                payload=payload,
            )

    def _refresh_explore(
        self,
        session: Session,
        film: Film,
        summary: dict[str, Any],
        resolved,
    ) -> None:
        self._delete_explore_views(session, film.id)
        sort_title = normalize_metadata_text(str(summary.get("title") or ""))
        watched = bool((summary.get("profile_state") or {}).get("watched"))
        film_source = {
            "sort_title": sort_title,
            "release_year": film.release_year,
            "watched": watched,
        }
        session.add(
            ExploreFilmReadModel(
                film_id=film.id,
                sort_title=sort_title,
                release_year=film.release_year,
                watched=watched,
                source_hash=_hash(film_source),
                projection_version=PROJECTION_VERSIONS["explore_films"],
                projected_at=_now(),
            )
        )

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
            self._add_explore_facet(
                session,
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
            self._add_explore_facet(
                session,
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
            self._add_explore_facet(
                session,
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
            self._add_explore_facet(
                session,
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

    def _add_explore_facet(
        self,
        session: Session,
        *,
        dimension: str,
        facet_key: str,
        film_id: str,
        display_label: str,
        conflicted: bool,
        payload: dict[str, Any],
    ) -> None:
        safe_payload = self._safe_payload(payload)
        source = {
            "dimension": dimension,
            "facet_key": facet_key,
            "film_id": film_id,
            "display_label": display_label,
            "normalized_label": normalize_metadata_text(display_label),
            "eligible": not conflicted,
            "conflicted": conflicted,
            "payload": safe_payload,
        }
        session.add(
            ExploreFacetReadModel(
                **source,
                source_hash=_hash(source),
                projection_version=PROJECTION_VERSIONS["explore_facets"],
                projected_at=_now(),
            )
        )

    def _upsert_graph_node(self, session: Session, entity_id: str) -> None:
        graph = session.get(GraphEntity, entity_id)
        if graph is None or graph.lifecycle_status != "active":
            return
        label = entity_id
        secondary: str | None = None
        owned = False
        payload: dict[str, Any] = {}
        if graph.entity_type == "film":
            film = session.get(Film, entity_id)
            if film is None:
                return
            label = film.canonical_title
            secondary = str(film.release_year) if film.release_year else None
            owned = session.exec(
                select(LibraryItem.id)
                .where(LibraryItem.film_id == entity_id)
                .where(LibraryItem.availability_status.notin_(("retired", "ignored")))
            ).first() is not None
            payload = {"release_year": film.release_year}
        elif graph.entity_type == "person":
            person = session.get(Person, entity_id)
            if person is None:
                return
            label = person.canonical_name
            secondary = person.sort_name
        elif graph.entity_type == "concept":
            concept = session.get(Concept, entity_id)
            if concept is None:
                return
            label = concept.canonical_name
            secondary = concept.kind
            payload = {"kind": concept.kind}
        source = {
            "entity_type": graph.entity_type,
            "display_label": label,
            "secondary_label": secondary,
            "owned": owned,
            "payload": payload,
        }
        source_hash = _hash(source)
        row = session.get(GraphNodeReadModel, entity_id) or GraphNodeReadModel(
            entity_id=entity_id,
            entity_type=graph.entity_type,
            display_label=label,
            source_hash=source_hash,
            projection_version=PROJECTION_VERSIONS["graph_nodes"],
        )
        row.entity_type = graph.entity_type
        row.display_label = label
        row.secondary_label = secondary
        row.owned = owned
        row.payload = payload
        row.source_hash = source_hash
        row.projection_version = PROJECTION_VERSIONS["graph_nodes"]
        row.projected_at = _now()
        session.add(row)

    def _upsert_graph_edge(
        self,
        session: Session,
        *,
        edge_id: str,
        edge_kind: str,
        subject: str,
        object_id: str,
        relation: str,
        priority: int,
        payload: dict[str, Any],
    ) -> None:
        source = {
            "edge_kind": edge_kind,
            "subject_entity_id": subject,
            "object_entity_id": object_id,
            "relation": relation,
            "priority": priority,
            "payload": payload,
        }
        source_hash = _hash(source)
        row = session.get(GraphEdgeReadModel, edge_id) or GraphEdgeReadModel(
            edge_id=edge_id,
            edge_kind=edge_kind,
            subject_entity_id=subject,
            object_entity_id=object_id,
            relation=relation,
            source_hash=source_hash,
            projection_version=PROJECTION_VERSIONS["graph_edges"],
        )
        row.edge_kind = edge_kind
        row.subject_entity_id = subject
        row.object_entity_id = object_id
        row.relation = relation
        row.priority = priority
        row.payload = payload
        row.source_hash = source_hash
        row.projection_version = PROJECTION_VERSIONS["graph_edges"]
        row.projected_at = _now()
        session.add(row)

    @staticmethod
    def _delete_film_views(session: Session, film_id: str) -> None:
        for model in (
            ExploreFacetReadModel,
            ExploreFilmReadModel,
            LibraryFilmReadModel,
            FilmDetailReadModel,
            FilmSearchReadModel,
        ):
            session.exec(delete(model).where(model.film_id == film_id))

    @staticmethod
    def _delete_explore_views(session: Session, film_id: str) -> None:
        session.exec(delete(ExploreFacetReadModel).where(ExploreFacetReadModel.film_id == film_id))
        session.exec(delete(ExploreFilmReadModel).where(ExploreFilmReadModel.film_id == film_id))

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        copied = json.loads(_canonical_json(payload))
        self._validate_public_payload(copied)
        return copied

    def _validate_public_payload(self, value: Any, *, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key.casefold() in _PRIVATE_KEYS:
                    raise ProjectionVerificationError("projection payload contains a private field")
                self._validate_public_payload(child, key=child_key)
        elif isinstance(value, list):
            for child in value:
                self._validate_public_payload(child, key=key)
        elif isinstance(value, str) and key in _PRIVATE_KEYS:
            if _WINDOWS_ABSOLUTE.match(value) or value.startswith("/"):
                raise ProjectionVerificationError("projection payload contains an absolute path")

    @staticmethod
    def _row_id(row: Any) -> str:
        if isinstance(row, ExploreFacetReadModel):
            return f"{row.dimension}:{row.facet_key}:{row.film_id}"
        for field in ("film_id", "entity_id", "edge_id", "name"):
            if hasattr(row, field):
                return str(getattr(row, field))
        raise ProjectionVerificationError("projection row has no stable ID")

    @staticmethod
    def _expected_hash(row: Any) -> str:
        if isinstance(row, (LibraryFilmReadModel, FilmDetailReadModel)):
            return _hash(row.payload)
        if isinstance(row, FilmSearchReadModel):
            return _hash(
                {
                    "normalized_title": row.normalized_title,
                    "release_year": row.release_year,
                    "search_text": row.search_text,
                }
            )
        if isinstance(row, ExploreFilmReadModel):
            return _hash(
                {
                    "sort_title": row.sort_title,
                    "release_year": row.release_year,
                    "watched": row.watched,
                }
            )
        if isinstance(row, ExploreFacetReadModel):
            return _hash(
                {
                    "dimension": row.dimension,
                    "facet_key": row.facet_key,
                    "film_id": row.film_id,
                    "display_label": row.display_label,
                    "normalized_label": row.normalized_label,
                    "eligible": row.eligible,
                    "conflicted": row.conflicted,
                    "payload": row.payload,
                }
            )
        if isinstance(row, GraphNodeReadModel):
            return _hash(
                {
                    "entity_type": row.entity_type,
                    "display_label": row.display_label,
                    "secondary_label": row.secondary_label,
                    "owned": row.owned,
                    "payload": row.payload,
                }
            )
        if isinstance(row, GraphEdgeReadModel):
            return _hash(
                {
                    "edge_kind": row.edge_kind,
                    "subject_entity_id": row.subject_entity_id,
                    "object_entity_id": row.object_entity_id,
                    "relation": row.relation,
                    "priority": row.priority,
                    "payload": row.payload,
                }
            )
        raise ProjectionVerificationError("unsupported projection row")


class ProjectionReader:
    def list_films(self, engine, query: str | None = None) -> list[dict[str, Any]]:
        with Session(engine) as session:
            self._require(session, "library")
            statement = select(LibraryFilmReadModel).where(LibraryFilmReadModel.visible.is_(True))
            if query and query.strip():
                self._require(session, "search")
                term = normalize_metadata_text(query)
                matching_ids = session.exec(
                    select(FilmSearchReadModel.film_id).where(
                        FilmSearchReadModel.search_text.contains(term)
                    )
                ).all()
                statement = statement.where(LibraryFilmReadModel.film_id.in_(matching_ids))
            rows = session.exec(
                statement.order_by(
                    LibraryFilmReadModel.sort_title,
                    LibraryFilmReadModel.release_year,
                    LibraryFilmReadModel.film_id,
                )
            ).all()
            return [json.loads(_canonical_json(row.payload)) for row in rows]

    def get_film(self, engine, film_id: str) -> dict[str, Any] | None:
        with Session(engine) as session:
            self._require(session, "detail")
            row = session.get(FilmDetailReadModel, film_id)
            return json.loads(_canonical_json(row.payload)) if row is not None else None

    @staticmethod
    def _require(session: Session, name: str) -> None:
        state = session.get(ProjectionState, name)
        if (
            state is None
            or state.status != "ready"
            or state.projection_version != PROJECTION_VERSIONS[name]
        ):
            raise ProjectionUnavailable(f"{name} projection is unavailable")


projection_coordinator = ProjectionCoordinator()
projection_reader = ProjectionReader()


_HOOKS_INSTALLED = False


def install_projection_hooks() -> None:
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    event.listen(Session, "before_flush", _collect_projection_changes)
    event.listen(Session, "before_commit", _refresh_before_commit)
    _HOOKS_INSTALLED = True


def _collect_projection_changes(session: Session, _flush_context, _instances) -> None:
    if session.info.get("skip_projection_hook") or session.info.get("projection_hook_active"):
        return
    affected = session.info.setdefault("projection_affected_films", set())
    affected.update(_affected_film_ids(session))


def _refresh_before_commit(session: Session) -> None:
    if session.info.get("skip_projection_hook") or session.info.get("projection_hook_active"):
        return
    if not projection_coordinator.tables_available(session):
        return
    film_ids = set(session.info.pop("projection_affected_films", set()))
    film_ids.update(_affected_film_ids(session))
    if not film_ids:
        return
    session.info["projection_hook_active"] = True
    try:
        session.flush()
        for film_id in sorted(film_ids):
            projection_coordinator.refresh_film(session, film_id, update_states=False)
        session.flush()
        projection_coordinator.refresh_states(session)
        session.flush()
    finally:
        session.info.pop("projection_hook_active", None)
        session.info.pop("projection_affected_films", None)


def _affected_film_ids(session: Session) -> set[str]:
    values = list(session.new) + list(session.dirty) + list(session.deleted)
    film_ids: set[str] = set()
    with session.no_autoflush:
        for value in values:
            if isinstance(value, (
                ProjectionState,
                LibraryFilmReadModel,
                FilmDetailReadModel,
                FilmSearchReadModel,
                ExploreFilmReadModel,
                ExploreFacetReadModel,
                GraphNodeReadModel,
                GraphEdgeReadModel,
            )):
                continue
            if isinstance(value, Film):
                film_ids.add(value.id)
                continue
            direct = getattr(value, "film_id", None)
            if isinstance(direct, str):
                film_ids.add(direct)
            if isinstance(value, ExternalIdentity):
                film_ids.add(value.entity_id)
            elif isinstance(value, MediaAsset) and value.library_item_id:
                item = session.get(LibraryItem, value.library_item_id)
                if item is not None:
                    film_ids.add(item.film_id)
            elif isinstance(value, CreditProvenance):
                credit = session.get(Credit, value.credit_id)
                if credit is not None:
                    film_ids.add(credit.film_id)
            elif isinstance(value, FilmCountryProvenance):
                country = session.get(FilmCountry, value.film_country_id)
                if country is not None:
                    film_ids.add(country.film_id)
            elif isinstance(value, AssertionProvenance):
                assertion = session.get(Assertion, value.assertion_id)
                if assertion is not None:
                    film_ids.add(assertion.subject_entity_id)
            elif isinstance(value, AssertionEvidence):
                assertion = session.get(Assertion, value.assertion_id)
                if assertion is not None:
                    film_ids.add(assertion.subject_entity_id)
            elif isinstance(value, Person):
                film_ids.update(
                    session.exec(select(Credit.film_id).where(Credit.person_id == value.id)).all()
                )
            elif isinstance(value, Concept):
                film_ids.update(
                    session.exec(
                        select(Assertion.subject_entity_id).where(Assertion.object_entity_id == value.id)
                    ).all()
                )
    return {film_id for film_id in film_ids if isinstance(film_id, str) and film_id.startswith("film_")}


__all__ = [
    "PROJECTION_VERSIONS",
    "ProjectionCoordinator",
    "ProjectionReader",
    "ProjectionUnavailable",
    "ProjectionVerificationError",
    "install_projection_hooks",
    "projection_coordinator",
    "projection_reader",
]
