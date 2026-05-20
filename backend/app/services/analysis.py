from sqlmodel import Session
from app.database import engine
from app.models import Movie
from app.services.event_store import event_store
from app.services.historian import FilmHistorian
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analysis")

class AnalysisService:
    def __init__(self):
        self.historian = FilmHistorian()

    def analyze_movie(self, movie_id: str):
        """
        Background task to analyze a movie using FilmHistorian.
        Updates the database with the results.
        """
        logger.info(f"Starting analysis for movie: {movie_id}")
        
        with Session(engine) as session:
            movie = session.get(Movie, movie_id)
            if not movie:
                logger.error(f"Movie not found: {movie_id}")
                return

            if movie.analysis_status == "completed":
                logger.info(f"Movie already analyzed: {movie_id}")
                return

            title = movie.title
            title_cn = movie.title_cn
            tmdb_id = movie.tmdb_id

        _, projected = event_store.append_and_project(
            "AnalysisStarted",
            "movie",
            movie_id,
            {"movie_id": movie_id, "title": title, "tmdb_id": tmdb_id},
        )
        if not projected:
            logger.error(f"Movie not found during analysis projection: {movie_id}")
            return
            
        try:
            # Prefer title_cn for Chinese context analysis if available.
            search_query = title_cn or title
            result = self.historian.analyze_genealogy(search_query, tmdb_id=tmdb_id)

            if result:
                micro_genre, micro_genre_definition = self._parse_micro_genre(result)
                event_store.append_and_project(
                    "AnalysisCompleted",
                    "movie",
                    movie_id,
                    {
                        "movie_id": movie_id,
                        "analysis_data": result,
                        "micro_genre": micro_genre,
                        "micro_genre_definition": micro_genre_definition,
                    },
                )
                logger.info(f"Analysis completed for: {title}")
                return

            event_store.append_and_project(
                "AnalysisFailed",
                "movie",
                movie_id,
                {"movie_id": movie_id, "message": "No result"},
            )
            logger.error(f"Analysis failed (no result) for: {title}")

        except Exception as e:
            event_store.append_and_project(
                "AnalysisFailed",
                "movie",
                movie_id,
                {"movie_id": movie_id, "message": str(e)},
            )
            logger.error(f"Analysis error for {title}: {e}")

    def _parse_micro_genre(self, result: dict) -> tuple[str | None, str | None]:
        raw_micro_genre = result.get("micro_genre", "")
        if not raw_micro_genre:
            return None, None
        if " - " in raw_micro_genre:
            name, definition = raw_micro_genre.split(" - ", 1)
            return name.strip(), definition.strip()
        return raw_micro_genre.strip(), None

analysis_service = AnalysisService()
