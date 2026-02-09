"""
NFO File Scanner for tinyMediaManager (TMM) scraped movies.
Parses .nfo XML files to extract rich metadata.
"""
import os
import glob
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


class NFOScanner:
    """Scans a directory for TMM-scraped movie folders and parses .nfo files."""

    def __init__(self, media_dir: str):
        self.media_dir = Path(media_dir)

    def scan(self) -> list[dict]:
        """Scan all subdirectories for .nfo files and parse them."""
        movies = []
        
        if not self.media_dir.exists():
            print(f"❌ Media directory not found: {self.media_dir}")
            return movies
        
        for folder in self.media_dir.iterdir():
            if not folder.is_dir() or folder.name.startswith('.'):
                continue
            
            # Find .nfo files in the folder
            nfo_files = list(folder.glob("*.nfo"))
            if nfo_files:
                movie_data = self.parse_nfo(nfo_files[0], folder)
                if movie_data:
                    movies.append(movie_data)
                    print(f"  ✅ Parsed: {movie_data['title']} ({movie_data['year']})")
        
        print(f"\n📚 Total movies scanned: {len(movies)}")
        return movies

    def parse_nfo(self, nfo_path: Path, folder: Path) -> Optional[dict]:
        """Parse a single .nfo XML file and return standardized movie dict."""
        try:
            tree = ET.parse(nfo_path)
            root = tree.getroot()
            
            # Extract core fields
            title = root.findtext('originaltitle') or root.findtext('title') or "Unknown"
            title_cn = root.findtext('title') or title
            year = int(root.findtext('year') or 0)
            tmdb_id = root.findtext('tmdbid')
            imdb_id = root.findtext('id')
            plot = root.findtext('plot') or root.findtext('outline') or ""
            runtime = int(root.findtext('runtime') or 0)
            
            # Genres (multiple <genre> tags)
            genres = [g.text for g in root.findall('genre') if g.text]
            
            # Director
            director = root.findtext('director') or ""
            
            # Ratings
            imdb_rating = None
            for rating in root.findall('.//rating'):
                if rating.get('name') == 'imdb':
                    val = rating.findtext('value')
                    if val:
                        imdb_rating = float(val)
                        break
            
            # Actors (top 5)
            actors = []
            for actor in root.findall('actor')[:5]:
                name = actor.findtext('name')
                role = actor.findtext('role')
                if name:
                    actors.append({"name": name, "role": role or ""})
            
            # Image paths (local files)
            folder_name = folder.name
            poster_local = self._find_image(folder, "-poster")
            fanart_local = self._find_image(folder, "-fanart")
            
            # Also get TMDB URLs as fallback
            poster_url = None
            for thumb in root.findall('thumb'):
                if thumb.get('aspect') == 'poster' and thumb.text:
                    poster_url = thumb.text
                    break
            
            fanart_url = None
            fanart_elem = root.find('fanart/thumb')
            if fanart_elem is not None and fanart_elem.text:
                fanart_url = fanart_elem.text
            
            # Generate unique ID
            # 1. Prioritize TMDB ID (cleanest URL)
            if tmdb_id:
                movie_id = f"{tmdb_id}_{year}"
            # 2. Fallback to IMDB ID
            elif imdb_id:
                movie_id = f"{imdb_id}_{year}"
            # 3. Fallback to Title (sanitize strictly)
            else:
                # Remove special chars, keep only alphanumeric, underscore, hyphen
                safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in title)
                safe_title = safe_title.replace(' ', '_')
                movie_id = f"{safe_title}_{year}"
            
            # Find video file
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv']
            video_file = None
            for ext in video_extensions:
                videos = list(folder.glob(f"*{ext}"))
                if videos:
                    video_file = videos[0].name
                    break
            
            return {
                "id": movie_id,
                "title": title,
                "title_cn": title_cn,
                "year": year,
                "tmdb_id": tmdb_id,
                "imdb_id": imdb_id,
                "plot": plot,
                "runtime": runtime,
                "genres": genres,
                "director": director,
                "imdb_rating": imdb_rating,
                "actors": actors,
                # Local paths (relative to media mount point)
                "poster_local": f"/media/{folder_name}/{poster_local}" if poster_local else None,
                "backdrop_local": f"/media/{folder_name}/{fanart_local}" if fanart_local else None,
                # TMDB CDN fallbacks
                "poster_path": self._extract_tmdb_path(poster_url),
                "backdrop_path": self._extract_tmdb_path(fanart_url),
                # Folder info
                "folder_name": folder_name,
                "video_file": video_file,
                "nfo_source": "tmm"
            }
            
        except ET.ParseError as e:
            print(f"  ❌ XML Parse Error in {nfo_path}: {e}")
            return None
        except Exception as e:
            print(f"  ❌ Error parsing {nfo_path}: {e}")
            return None

    def _find_image(self, folder: Path, suffix: str) -> Optional[str]:
        """Find an image file with the given suffix (-poster, -fanart, etc.)."""
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            matches = list(folder.glob(f"*{suffix}{ext}"))
            if matches:
                return matches[0].name
        return None

    def _extract_tmdb_path(self, url: Optional[str]) -> Optional[str]:
        """Extract TMDB path from full URL for use with image.tmdb.org prefix."""
        if not url:
            return None
        # URL format: https://image.tmdb.org/t/p/original/xxx.jpg
        # We want to extract: /xxx.jpg
        if "image.tmdb.org" in url:
            parts = url.split("/original")
            if len(parts) > 1:
                return parts[1]
        return None


# Test scanner if run directly
if __name__ == "__main__":
    import json
    test_dir = "/Users/alicolia/Projects/movies-nfo-test"
    scanner = NFOScanner(test_dir)
    movies = scanner.scan()
    print(json.dumps(movies[:2], indent=2, ensure_ascii=False))
