"""Explicit, evidence-backed identity correction of a NEW public corpus version.

No name matching, network, source writes, query labels or library mutation. The
operator reviews the external credit evidence; this validator binds that review
to exact source IDs and every affected film before producing a derived corpus.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.evaluation.search_corpus import CorpusFilm
from app.services.semantic_search import SemanticError, _hash


class CreditEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    film_id: str = Field(strict=True, pattern=r"^film_[a-f0-9]{32}$")
    source_ref: str = Field(strict=True, min_length=1, max_length=100)
    film_qid: str = Field(strict=True, pattern=r"^Q[1-9][0-9]*$")
    director_qid: str = Field(strict=True, pattern=r"^Q[1-9][0-9]*$")
    reference: str = Field(strict=True, min_length=1, max_length=300)
    retrieved: date


class PersonLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(strict=True, pattern=r"^person_(?:[a-f0-9]{16}|[a-f0-9]{32})$")
    target_id: str = Field(strict=True, pattern=r"^Q[1-9][0-9]*$")
    evidence: list[CreditEvidence] = Field(min_length=1, max_length=100)


class IdentityOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["public-person-identity-overlay.v1"]
    parent_sha256: str = Field(strict=True, pattern=r"^[a-f0-9]{64}$")
    verification: Literal["reviewed-source-credit-links"]
    links: list[PersonLink] = Field(min_length=1, max_length=100)


def derive_identity_corpus(raw: bytes, manifest):
    """Return a separate payload/model tuple; callers own any new DB/output.

Evidence URLs are attestations, not fetched or automatically trusted as truth.
Each crosswalk needs source review; syntax validation cannot certify an external
claim. Existing authoritative IDs cannot be rewritten or inferred from names.
"""
    try:
        overlay = IdentityOverlay.model_validate(manifest)
        if sha256(raw).hexdigest() != overlay.parent_sha256:
            raise ValueError
        original = json.loads(raw)
        if not isinstance(original, dict) or any(k in original for k in ("queries", "cases", "qrels", "gold", "identity_overlay")):
            raise ValueError
        films = tuple(CorpusFilm.model_validate(f) for f in original["films"])
        by_id = {f.id: f for f in films}
        source_refs = {s["id"] for s in original["sources"]}
        if len(by_id) != len(films):
            raise ValueError
        people = {p for f in films if f.directors.status == "accepted" for p in f.directors.value}
        mapping = {}
        for link in overlay.links:
            if link.source_id in mapping or link.source_id not in people or link.target_id not in people:
                raise ValueError
            affected = {f.id for f in films if link.source_id in f.directors.value}
            evidence_ids = [e.film_id for e in link.evidence]
            if (set(evidence_ids) != affected or len(evidence_ids) != len(affected)
                    or len({e.film_qid for e in link.evidence}) != len(affected)):
                raise ValueError
            for evidence in link.evidence:
                film = by_id[evidence.film_id]
                if (evidence.director_qid != link.target_id
                        or evidence.reference != f"https://www.wikidata.org/wiki/{evidence.film_qid}#P57"
                        or evidence.source_ref not in source_refs
                        or evidence.source_ref not in film.directors.sources):
                    raise ValueError
                names = next(f["director_names"] for f in original["films"] if f["id"] == film.id)
                if names["status"] != "accepted" or len(names["value"]) != len(film.directors.value):
                    raise ValueError
            mapping[link.source_id] = link.target_id
    except (KeyError, TypeError, ValueError, ValidationError):
        raise SemanticError("search_identity_overlay_invalid") from None

    derived = deepcopy(original)
    fingerprint = _hash(overlay.model_dump(mode="json"))
    origin = "identity-overlay:" + fingerprint
    changes = []
    for film in derived["films"]:
        values = film["directors"].get("value") or []
        if not any(p in mapping for p in values):
            continue
        film["source_director_ids"] = list(values)
        # Duplicate credits of an explicitly linked identity become one person;
        # retain every original key in source_director_ids and the manifest.
        merged = {}
        for person, name in zip(values, film["director_names"]["value"]):
            merged.setdefault(mapping.get(person, person), name)
        film["directors"]["value"] = list(merged)
        film["directors"]["sources"] = list(dict.fromkeys([*film["directors"]["sources"], origin]))
        film["director_names"]["value"] = list(merged.values())
        film["directors"]["reason"] += " Explicit reviewed cross-source identity overlay; source IDs retained."
        changes.append(film["id"])
    derived["version"] = original["version"] + "+person-identities.v1"
    derived["identity_overlay"] = {"version": overlay.version, "parent_sha256": overlay.parent_sha256,
        "manifest_sha256": fingerprint, "manifest": overlay.model_dump(mode="json"), "changed_films": changes}
    derived["sources"].append({"id": origin, "kind": "reviewed-identity-crosswalk",
                               "references": sorted({e.reference for link in overlay.links for e in link.evidence})})
    return derived, tuple(CorpusFilm.model_validate(f) for f in derived["films"])
