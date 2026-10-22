"""Resolve literal identities locally and execute complete v2 plans in SQLite."""
from __future__ import annotations

import json

from sqlalchemy import case, func
from sqlmodel import Session, select

from app.canonical_models import Concept, ExploreFacetReadModel, ExploreFilmReadModel, LibraryFilmReadModel
from app.contracts.search_plan import SearchPlan
from app.services import ask as ask_module
from app.services.ask import AskError
from app.services.explore_query import ExploreQueryService, EXPLORE_VISIBILITY_POLICY, EXPLORE_PROJECTION_VERSION
from app.services.projections import ProjectionReader
from app.services.structured_metadata_vocab import STRUCTURED_METADATA_VOCABULARY as vocabulary


class SearchPlanExecutor:
    def resolve(self, plan: SearchPlan, people_ids=None):
        selections = people_ids or {}
        if set(selections) - {str(i) for i in range(len(plan.people))}:
            raise AskError("ask_invalid_selection", 422)
        constraints, issues, chosen = [], [], {}
        with Session(ask_module.engine) as session:
            ExploreQueryService._require(session)
            for field, dimension in (("genres", "genre"), ("countries", "country"),
                    ("exclude_genres", "genre"), ("exclude_countries", "country")):
                for index, value in enumerate(getattr(plan, field)):
                    key, label = None, value
                    labels = {}
                    if dimension == "country":
                        key = vocabulary.resolve_country(value)
                        label = key or value
                    else:
                        genre = vocabulary.resolve_genre(value)
                        concept = session.exec(select(Concept).where(Concept.kind == "genre",
                            Concept.canonical_key == genre.canonical_key,
                            Concept.lifecycle_status == "active")).first() if genre else None
                        if concept:
                            key, label = concept.id, concept.canonical_name
                            labels = {"en": label, "zh": next((name for locale, name in genre.aliases
                                if locale.startswith("zh")), label)}
                    if key is None:
                        issues.append({"field": field, "index": index, "code": "unknown_value", "candidates": []})
                    else:
                        constraints.append({"id": f"{field}:{index}", "field": field, "index": index,
                            "dimension": dimension, "key": key, "label": label,
                            "labels": labels,
                            "exclude": field.startswith("exclude_")})
            people_cache = {}
            for index, person in enumerate(plan.people):
                if person.name not in people_cache:
                    people_cache[person.name] = ask_module.AskService._people(session, person.name)
                candidates, exact = people_cache[person.name]
                selected = next((p for p in candidates if p["key"] == selections.get(str(index))), None)
                if str(index) not in selections and exact and len(candidates) == 1:
                    selected = candidates[0]
                if selected is None:
                    issues.append({"field": "people", "index": index,
                        "code": "choose_person" if candidates else "unknown_value", "candidates": candidates})
                else:
                    chosen[str(index)] = selected["key"]
                    constraints.append({"id": f"people:{index}", "field": "people", "index": index,
                        "dimension": "person", "key": selected["key"], "label": selected["label"],
                        "role": person.role, "exclude": person.exclude})
        for field in ("year", "duration"):
            lower, upper = getattr(plan, field + "_min"), getattr(plan, field + "_max")
            if lower is not None or upper is not None:
                constraints.append({"id": field, "field": field, "dimension": field,
                    "key": field, "label": field, "min": lower, "max": upper,
                    "min_exclusive": getattr(plan, field + "_min_exclusive", False),
                    "max_exclusive": getattr(plan, field + "_max_exclusive", False)})
        return {"version": "discovery.v2", "status": "needs_clarification" if issues else "ready",
            "source": "local", "reason": None, "plan": plan.model_dump(), "person_id": None,
            "people_ids": chosen, "constraints": constraints, "issues": issues, "results": None}

    def eligible_ids(self, plan: SearchPlan, *, people_ids=None, maximum=5000):
        """Offline retrieval bridge: reuse every hard predicate before ranking."""
        if type(maximum) is not int or not 1 <= maximum <= 5000:
            raise AskError("search_candidate_limit", 422)
        return self.query(plan, people_ids=people_ids, _ids_limit=maximum)

    def query(self, plan: SearchPlan, *, people_ids=None, offset=0, _ids_limit=None):
        result = self.resolve(plan, people_ids)
        if result["status"] != "ready":
            return result
        facet, film, library = ExploreFacetReadModel, ExploreFilmReadModel, LibraryFilmReadModel
        conditions = [library.visible.is_(True)]
        positive = {"genre": [], "country": [], "person": [], "decade": []}
        with Session(ask_module.engine) as session:
            ExploreQueryService._require(session)
            ProjectionReader._require(session, "library")
            # Positive alternatives are OR within a dimension; all dimensions,
            # each person/role and each exclusion combine with AND.
            for dimension in ("genre", "country"):
                for excluded in (False, True):
                    keys = [c["key"] for c in result["constraints"]
                        if c["dimension"] == dimension and c.get("exclude", False) == excluded]
                    if not keys:
                        continue
                    known = select(facet.film_id).where(facet.dimension == dimension, facet.eligible.is_(True))
                    matching = known.where(facet.facet_key.in_(keys))
                    if excluded:
                        conditions.extend((film.film_id.in_(known), film.film_id.not_in(matching)))
                    else:
                        conditions.append(film.film_id.in_(matching))
                        positive[dimension] = keys
            for condition in result["constraints"]:
                if condition["dimension"] != "person":
                    continue
                known = select(facet.film_id).where(facet.dimension == "person", facet.eligible.is_(True))
                if condition["role"] != "any":
                    known = known.where(facet.payload["roles"].as_string().contains('"' + condition["role"] + '"'))
                matching = known.where(facet.facet_key == condition["key"])
                if condition["exclude"]:
                    conditions.extend((film.film_id.in_(known), film.film_id.not_in(matching)))
                else:
                    conditions.append(film.film_id.in_(matching))
                    positive["person"].append(condition["key"])
            if plan.view != "all":
                conditions.append(film.watched.is_(plan.view == "watched"))
            seconds = library.payload["primary_item"]["video"]["duration_seconds"].as_float()
            minutes = library.payload["runtime_minutes"].as_integer()
            duration = func.coalesce(case((seconds > 0, seconds)), case((minutes > 0, minutes * 60)))
            for value, field, factor in ((film.release_year, "year", 1), (duration, "duration", 60)):
                lower, upper = getattr(plan, field + "_min"), getattr(plan, field + "_max")
                if lower is not None:
                    conditions.append(value > lower * factor if getattr(plan, field + "_min_exclusive", False) else value >= lower * factor)
                if upper is not None:
                    conditions.append(value < upper * factor if getattr(plan, field + "_max_exclusive", False) else value <= upper * factor)
            base = select(film).join(library, film.film_id == library.film_id).where(*conditions)
            if _ids_limit is not None:
                ids = session.exec(base.with_only_columns(film.film_id).order_by(
                    film.film_id).limit(_ids_limit + 1)).all()
                if len(ids) > _ids_limit:
                    raise AskError("search_candidate_limit", 422)
                return {**result, "eligible_ids": ids}
            total = session.exec(select(func.count()).select_from(base.subquery())).one()
            limit = 40
            offset = min(offset, max(0, (total - 1) // limit * limit))
            value = film.release_year if plan.sort == "year" else film.sort_title
            rows = session.exec(base.order_by(value.is_(None), value.desc() if plan.direction == "desc" else value.asc(),
                film.sort_title, film.film_id).limit(limit).offset(offset)).all()
            ids = [row.film_id for row in rows]
            summaries = {row.film_id: row.payload for row in session.exec(select(library).where(library.film_id.in_(ids))).all()}
            matches = ExploreQueryService()._matched_facts(session, ids, positive)
        result["results"] = {"visibility_policy": EXPLORE_VISIBILITY_POLICY, "strict": True,
            "projection_version": EXPLORE_PROJECTION_VERSION, "projection_versions": ExploreQueryService._projection_versions(),
            "active_filters": {**positive, "view": plan.view, "sort": plan.sort, "dir": plan.direction, "person_match": "all"},
            "filters": [{"dimension": c["dimension"], "key": c["key"], "label": c["label"]}
                for c in result["constraints"] if c["dimension"] in positive and not c.get("exclude")],
            "unresolved_filters": [], "items": [
                {"film": json.loads(json.dumps(summaries[row.film_id], ensure_ascii=False)),
                 "matched_facts": matches.get(row.film_id, [])} for row in rows],
            "total": total, "limit": limit, "offset": offset,
            "next_offset": offset + len(rows) if offset + len(rows) < total else None}
        return result


search_plan_executor = SearchPlanExecutor()
