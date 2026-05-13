from typing import Optional

import requests

from app.services.settings import get_tmdb_api_key


class TMDBClient:
    base_url = "https://api.themoviedb.org/3"
    image_base_url = "https://image.tmdb.org/t/p"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def search_movies(self, query: str, year: Optional[int] = None, language: str = "zh-CN") -> list[dict]:
        self._require_api_key()
        api_key = self._api_key()
        params = {
            "api_key": api_key,
            "query": query,
            "language": language,
            "include_adult": "false",
        }
        if year:
            params["year"] = str(year)

        data = self._get("/search/movie", params=params)
        return data.get("results", [])

    def movie_details(self, tmdb_id: int, language: str = "zh-CN") -> dict:
        self._require_api_key()
        api_key = self._api_key()
        return self._get(
            f"/movie/{tmdb_id}",
            params={
                "api_key": api_key,
                "language": language,
                "append_to_response": "credits,external_ids,images",
                "include_image_language": self._image_languages(language),
            },
        )

    def configuration(self) -> dict:
        self._require_api_key()
        return self._get("/configuration", params={"api_key": self._api_key()})

    def image_url(self, path: Optional[str], size: str = "original") -> Optional[str]:
        if not path:
            return None
        return f"{self.image_base_url}/{size}{path}"

    def _get(self, path: str, params: dict) -> dict:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def _api_key(self) -> Optional[str]:
        return self.api_key or get_tmdb_api_key()

    def _require_api_key(self):
        if not self._api_key():
            raise RuntimeError("TMDB_API_KEY is not configured")

    def _image_languages(self, language: str) -> str:
        lang = (language or "zh-CN").split("-")[0]
        fallback = "en" if lang != "en" else "zh"
        return f"{lang},null,{fallback}"
