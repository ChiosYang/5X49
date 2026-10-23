"""The existing literal parser, identity and SQL services on an explicit database.

This bridge has no model, credential lookup or new search index. Its database
dependency keeps public evaluation instances separate from the user's canonical
service, without monkey-patching a process-global engine.
"""
import re
from pydantic import ValidationError
from sqlmodel import Session, select

from app.canonical_models import FilmSearchReadModel, LibraryFilmReadModel
from app.contracts.bound_search_plan import SearchPlan, SearchPerson
from app.contracts.structured_metadata import normalize_metadata_text
from app.services.ask import AskService
from app.services.discovery_search import keyword_text, local_plan, remaining, unsupported_reason
from app.services.search_execution import SearchPlanExecutor
from app.services.search_rules import is_extended_request, parse_extended
from app.services.semantic_search import _safe
from app.services.search_literals import bind_literal


class LocalSearch:
    def __init__(self, engine):
        self.engine = engine
        self.executor = SearchPlanExecutor(engine)

    def reference_candidates(self, title):
        term = normalize_metadata_text(keyword_text(title))
        with Session(self.engine) as session:
            rows = session.exec(select(LibraryFilmReadModel).join(FilmSearchReadModel,
                FilmSearchReadModel.film_id == LibraryFilmReadModel.film_id).where(
                LibraryFilmReadModel.visible.is_(True), FilmSearchReadModel.exact_titles.contains(
                    "\n" + term + "\n", autoescape=True)).order_by(LibraryFilmReadModel.film_id).limit(9)).all()
            return [{"key": row.film_id, "label": row.payload.get("title", ""),
                     "year": row.release_year} for row in rows]

    def known_literal(self, text):
        binding = self.literal_binding(text)
        return binding is not None and binding.keyword is not None

    def _known_person(self, text):
        with Session(self.engine) as session:
            return AskService._people(session, text, exact_only=True)[1]

    def literal_binding(self, text):
        return bind_literal(text, self.reference_candidates, self._known_person)

    def title_mentions(self, text):
        """Literal aliases only; no fuzzy match or name-based identity merge."""
        with Session(self.engine) as session:
            rows = session.exec(select(FilmSearchReadModel).join(LibraryFilmReadModel,
                FilmSearchReadModel.film_id == LibraryFilmReadModel.film_id).where(
                LibraryFilmReadModel.visible.is_(True))).all()
            aliases = {alias for row in rows for alias in row.exact_titles.split("\n") if alias}
        matches = []
        for alias in aliases:
            boundary = (r"(?<!\w)" + re.escape(alias) + r"(?!\w)") if alias.isascii() else re.escape(alias)
            for match in re.finditer(boundary, text, re.I):
                matches.append({"title": text[match.start():match.end()], "start": match.start(), "end": match.end()})
        matches.sort(key=lambda row: (-(row["end"] - row["start"]), row["start"], row["title"]))
        selected = []
        for row in matches:
            if not any(row["start"] < old["end"] and old["start"] < row["end"] for old in selected):
                selected.append(row)
        return sorted(selected, key=lambda row: row["start"])

    def literal_request(self, text):
        binding = self.literal_binding(text)
        if binding is None:
            return None
        if binding.issue:
            return self.state("clarify", binding.issue)
        if binding.keyword is not None:
            return {**self.state("keyword"), "keyword_query": binding.keyword}
        return self.executor.query(binding.plan)

    @staticmethod
    def state(status, reason=None):
        return {"version": "discovery.v2", "status": status, "reason": reason, "source": "local",
                "plan": None, "person_id": None, "people_ids": {}, "constraints": [], "issues": [], "results": None}

    def interpret(self, question):
        _safe(question, 600)
        literal = self.literal_request(question)
        if literal is not None:
            return literal
        if is_extended_request(question):
            plan, leftover, issue = parse_extended(question)
            if plan is not None and not leftover and not issue:
                return self.executor.query(plan)
            return self.state("unsupported", issue or "incomplete_request")
        values, text, issue = local_plan(question)
        reason = unsupported_reason(question) or issue
        if reason or remaining(text):
            return self.state("unsupported", reason) if reason else self.state("keyword")
        try:
            fields = {key: value for key, value in values.items() if key in {"view", "sort", "direction"}}
            if values.get("country"):
                fields["countries"] = [values["country"]]
            if values.get("genre"):
                fields["genres"] = [values["genre"]]
            if values.get("person"):
                fields["people"] = [SearchPerson(name=values["person"], role=values.get("person_role", "any"))]
            if values.get("decade"):
                fields.update(year_min=values["decade"], year_max=values["decade"] + 9)
            return self.executor.query(SearchPlan(version="search-plan.v2", **fields))
        except ValidationError:
            return self.state("unsupported", "invalid_request")

    def summaries(self, ids):
        with Session(self.engine) as session:
            rows = session.exec(select(LibraryFilmReadModel).where(LibraryFilmReadModel.visible.is_(True),
                LibraryFilmReadModel.film_id.in_(ids))).all()
            return {row.film_id: row.payload for row in rows}
