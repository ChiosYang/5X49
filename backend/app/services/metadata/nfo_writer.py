import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


class NFOWriter:
    def write_movie_nfo(
        self,
        folder: Path,
        metadata: dict,
        poster_url: Optional[str],
        backdrop_url: Optional[str],
        filename_prefix: Optional[str] = None,
        overwrite: bool = False,
    ) -> Path:
        nfo_name = f"{filename_prefix}.nfo" if filename_prefix else "movie.nfo"
        nfo_path = folder / nfo_name
        if nfo_path.exists() and not overwrite:
            return nfo_path

        root = ET.Element("movie")
        self._text(root, "generator", "5X49")
        self._text(root, "title", metadata.get("title"))
        self._text(root, "originaltitle", metadata.get("original_title") or metadata.get("title"))
        self._text(root, "year", self._year(metadata.get("release_date")))
        self._text(root, "tmdbid", str(metadata.get("id")) if metadata.get("id") else None)
        self._text(root, "id", metadata.get("imdb_id") or metadata.get("external_ids", {}).get("imdb_id"))
        self._text(root, "plot", metadata.get("overview"))
        self._text(root, "outline", metadata.get("overview"))
        self._text(root, "runtime", str(metadata.get("runtime")) if metadata.get("runtime") else None)

        if metadata.get("id"):
            uniqueid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
            uniqueid.text = str(metadata["id"])

        imdb_id = metadata.get("imdb_id") or metadata.get("external_ids", {}).get("imdb_id")
        if imdb_id:
            uniqueid = ET.SubElement(root, "uniqueid", {"type": "imdb"})
            uniqueid.text = imdb_id

        for genre in metadata.get("genres", []):
            self._text(root, "genre", genre.get("name"))

        for country in metadata.get("production_countries", []):
            self._text(root, "country", country.get("name"))

        for person in metadata.get("credits", {}).get("crew", []):
            if person.get("job") == "Director":
                self._text(root, "director", person.get("name"))

        for actor in metadata.get("credits", {}).get("cast", [])[:10]:
            actor_elem = ET.SubElement(root, "actor")
            self._text(actor_elem, "name", actor.get("name"))
            self._text(actor_elem, "role", actor.get("character"))

        if poster_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            thumb.text = poster_url

        if backdrop_url:
            fanart = ET.SubElement(root, "fanart")
            thumb = ET.SubElement(fanart, "thumb")
            thumb.text = backdrop_url

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        temp_path.replace(nfo_path)
        return nfo_path

    def update_movie_artwork(
        self,
        folder: Path,
        poster_url: Optional[str] = None,
        backdrop_url: Optional[str] = None,
        filename_prefix: Optional[str] = None,
    ) -> Optional[Path]:
        nfo_path = self._movie_nfo_path(folder, filename_prefix)
        if not nfo_path:
            return None

        tree = ET.parse(nfo_path)
        root = tree.getroot()

        if poster_url:
            poster_thumb = None
            for thumb in root.findall("thumb"):
                if thumb.get("aspect") == "poster":
                    poster_thumb = thumb
                    break
            if poster_thumb is None:
                poster_thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            poster_thumb.text = poster_url

        if backdrop_url:
            fanart = root.find("fanart")
            if fanart is None:
                fanart = ET.SubElement(root, "fanart")
            backdrop_thumb = fanart.find("thumb")
            if backdrop_thumb is None:
                backdrop_thumb = ET.SubElement(fanart, "thumb")
            backdrop_thumb.text = backdrop_url

        ET.indent(tree, space="  ")
        temp_path = nfo_path.with_suffix(".nfo.tmp")
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        temp_path.replace(nfo_path)
        return nfo_path

    def _text(self, root: ET.Element, tag: str, value):
        if value is None or value == "":
            return
        child = ET.SubElement(root, tag)
        child.text = str(value)

    def _year(self, release_date: Optional[str]) -> Optional[str]:
        if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
            return release_date[:4]
        return None

    def _movie_nfo_path(self, folder: Path, filename_prefix: Optional[str] = None) -> Optional[Path]:
        candidates = []
        if filename_prefix:
            candidates.append(folder / f"{filename_prefix}.nfo")
        candidates.append(folder / "movie.nfo")
        candidates.extend(sorted(folder.glob("*.nfo"), key=lambda path: path.name.lower()))

        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                return candidate
        return None
