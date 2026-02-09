from sqlmodel import Session
from app.database import engine
from app.models import Movie
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

            # Update status to processing
            movie.analysis_status = "processing"
            session.add(movie)
            session.commit()
            session.refresh(movie)
            
            try:
                # Call AI Service
                # Prefer title_cn for Chinese context analysis if available, 
                # but historian.get_movie_metadata usually expects English or Original Title for TMDB search.
                # However, our historian uses `movie_name` to search TMDB. 
                # If we pass title_cn, TMDB search usually works fine.
                search_query = movie.title_cn or movie.title
                
                result = self.historian.analyze_genealogy(search_query, tmdb_id=movie.tmdb_id)
                
                if result:
                    movie.analysis_data = result
                    movie.micro_genre = result.get("micro_genre")
                    movie.analysis_status = "completed"
                    logger.info(f"Analysis completed for: {movie.title}")
                else:
                    movie.analysis_status = "failed"
                    logger.error(f"Analysis failed (no result) for: {movie.title}")
            
            except Exception as e:
                movie.analysis_status = "failed"
                logger.error(f"Analysis error for {movie.title}: {e}")
            
            session.add(movie)
            session.commit()

analysis_service = AnalysisService()
