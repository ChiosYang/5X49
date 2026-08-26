import logging
from typing import Any

from pydantic import ValidationError
from sqlmodel import Session

from app.database import engine
from app.services.analysis_evidence import evidence_retriever
from app.services.analysis_runtime import (
    AnalysisRuntimeError,
    AnalysisSubjectMismatch,
    analysis_runtime_persistence,
)
from app.services.historian import FilmHistorian, analysis_prompt_snapshot
from app.services.metadata.tmdb import TMDBClient
from app.services.settings import get_language


logger = logging.getLogger("analysis")


class AnalysisExecutionError(RuntimeError):
    pass


class AnalysisService:
    def __init__(
        self,
        *,
        database_engine=None,
        historian=None,
        tmdb=None,
        evidence=None,
    ):
        self._database_engine = database_engine
        self.historian = historian if historian is not None else FilmHistorian()
        self.tmdb = tmdb if tmdb is not None else TMDBClient()
        self.evidence = evidence if evidence is not None else evidence_retriever

    @property
    def database_engine(self):
        # Keep the module-level engine fallback so existing tests and production
        # startup can replace it without reconstructing the singleton.
        return self._database_engine or engine

    def analyze_movie(self, movie_id: str, ctx: Any | None = None) -> dict:
        try:
            configuration = self.historian.analysis_configuration()
            job_id = self._job_id(ctx, movie_id)
            with Session(self.database_engine) as session:
                start = analysis_runtime_persistence.start(
                    session,
                    movie_id=movie_id,
                    job_id=job_id,
                    provider=configuration.provider,
                    model=configuration.model,
                    prompt_version=analysis_prompt_snapshot(configuration),
                )
                session.commit()
        except Exception as exc:
            category, code, message, _review = self._safe_failure(exc, False)
            logger.error(
                "Analysis could not start movie_id=%s category=%s code=%s exception=%s",
                movie_id,
                category,
                code,
                exc.__class__.__name__,
            )
            raise AnalysisExecutionError(message) from None

        if start.cached:
            try:
                with Session(self.database_engine) as session:
                    completed = analysis_runtime_persistence.restore_cached_projection(
                        session,
                        start=start,
                        job_id=job_id,
                    )
                    session.commit()
                return self._result(movie_id, completed, cached=True)
            except Exception as exc:
                logger.error(
                    "Cached analysis projection failed movie_id=%s exception=%s",
                    movie_id,
                    exc.__class__.__name__,
                )
                raise AnalysisExecutionError("Analysis persistence failed") from None

        try:
            self._raise_if_cancelled(ctx)
            generation = self.historian.analyze_v2(
                start.analysis_input,
                configuration=configuration,
            )
            self._raise_if_cancelled(ctx)
            if generation.output.subject_film_id != start.film_id:
                raise AnalysisSubjectMismatch("Analysis output subject does not match input")

            remote_targets, remote_failures = self._prepare_tmdb_targets(
                generation.output,
                ctx,
            )
            with Session(self.database_engine) as session:
                evidence_candidates = analysis_runtime_persistence.evidence_candidates(
                    session,
                    generation.output,
                    remote_targets,
                )
            evidence_batch = self.evidence.verify(evidence_candidates)
            self._raise_if_cancelled(ctx)

            with Session(self.database_engine) as session:
                completed = analysis_runtime_persistence.complete(
                    session,
                    start=start,
                    output=generation.output,
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                    estimated_cost=generation.estimated_cost,
                    currency=generation.currency,
                    remote_targets=remote_targets,
                    remote_failures=remote_failures,
                    evidence_batch=evidence_batch,
                    job_id=job_id,
                )
                session.commit()
            return self._result(movie_id, completed, cached=False)
        except Exception as exc:
            cancelled = exc.__class__.__name__ == "JobCancelled"
            category, code, message, review = self._safe_failure(exc, cancelled)
            try:
                with Session(self.database_engine) as session:
                    analysis_runtime_persistence.fail(
                        session,
                        start=start,
                        job_id=job_id,
                        error_category=category,
                        error_code=code,
                        error_message=message,
                        cancelled=cancelled,
                        create_output_review=review,
                    )
                    session.commit()
            except Exception:
                logger.error("Failed to persist analysis failure state code=%s", code)
            logger.error(
                "Analysis failed movie_id=%s category=%s code=%s exception=%s",
                movie_id,
                category,
                code,
                exc.__class__.__name__,
            )
            if cancelled:
                raise
            raise AnalysisExecutionError(message) from None

    def _prepare_tmdb_targets(self, output, ctx) -> tuple[dict[str, dict], dict[str, str]]:
        with Session(self.database_engine) as session:
            missing = analysis_runtime_persistence.missing_tmdb_targets(session, output)
        if not missing:
            return {}, {}
        if not self.tmdb.is_configured():
            return {}, {key: "unresolved_reference" for key in missing}
        language = "zh-CN" if get_language() == "zh" else "en-US"
        details_by_id: dict[int, dict] = {}
        failures_by_id: dict[int, str] = {}
        for provider_id in sorted(set(missing.values())):
            self._raise_if_cancelled(ctx)
            try:
                details_by_id[provider_id] = self.tmdb.movie_details(
                    provider_id,
                    language=language,
                )
            except Exception:
                failures_by_id[provider_id] = "unresolved_reference"
        remote = {
            candidate_key: details_by_id[provider_id]
            for candidate_key, provider_id in missing.items()
            if provider_id in details_by_id
        }
        failures = {
            candidate_key: failures_by_id[provider_id]
            for candidate_key, provider_id in missing.items()
            if provider_id in failures_by_id
        }
        return remote, failures

    @staticmethod
    def _safe_failure(exc: Exception, cancelled: bool) -> tuple[str, str, str, bool]:
        if cancelled:
            return "cancelled", "analysis_cancelled", "Analysis cancelled", False
        if isinstance(exc, (ValidationError, AnalysisSubjectMismatch, ValueError)):
            return "validation", "analysis_output_invalid", "Analysis output was invalid", True
        if isinstance(exc, AnalysisRuntimeError):
            return exc.error_category, exc.error_code, "Analysis could not be completed", False
        module = exc.__class__.__module__.casefold()
        if "openai" in module or "httpx" in module:
            return "provider", "analysis_provider_failed", "Analysis provider request failed", False
        return "persistence", "analysis_persistence_failed", "Analysis persistence failed", False

    @staticmethod
    def _job_id(ctx: Any | None, movie_id: str) -> str:
        value = getattr(ctx, "job_id", None)
        return str(value) if value else f"manual-analysis-{movie_id}"[:160]

    @staticmethod
    def _raise_if_cancelled(ctx: Any | None) -> None:
        if ctx is not None and hasattr(ctx, "raise_if_cancelled"):
            ctx.raise_if_cancelled()

    @staticmethod
    def _result(movie_id: str, completed, *, cached: bool) -> dict:
        return {
            "status": "success",
            "movie_id": movie_id,
            "cached": cached,
            "assertions": completed.assertions,
            "evidence": completed.evidence,
            "reviews": completed.reviews,
        }


analysis_service = AnalysisService()


__all__ = ["AnalysisExecutionError", "AnalysisService", "analysis_service"]
