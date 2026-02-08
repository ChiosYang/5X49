from fastapi import FastAPI, HTTPException
from app.services.historian import FilmHistorian
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Film Genealogy API")

# Allow Frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

historian = FilmHistorian()

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Film Genealogy Agent"}

@app.get("/analyze/{movie_name}")
def analyze_movie(movie_name: str):
    """
    Analyze a movie's genealogy (Ancestors -> Core -> Descendants)
    """
    result = historian.analyze_genealogy(movie_name)
    if not result:
        raise HTTPException(status_code=404, detail="Movie not found or analysis failed")
    return result
