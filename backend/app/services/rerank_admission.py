"""Model-bound admission and an OFFLINE ranking-only shortlist proposal.

Native scores are not probabilities and absolute scales do not transfer across
models. A separated head is ordering evidence, not proof of relevance/no-answer.
"""
from dataclasses import dataclass
import math

from app.services.semantic_search import SemanticError

LEGACY_MODEL = "nvidia/nemotron-3.5-rerank-8b:free"
VOYAGE_MODEL = "voyageai/rerank-3"


def profile(model):
    if model == LEGACY_MODEL:
        return "legacy-native.v1"
    if model == VOYAGE_MODEL:
        return "ranking-only.v1"
    return "unreviewed"


def validate_scores(scores):
    if not isinstance(scores, dict) or len(scores) > 20 or any(not isinstance(key, str)
            or type(value) not in (int, float) or not math.isfinite(value)
            or not 0 <= value <= 1 for key, value in scores.items()):
        raise SemanticError("search_rerank_invalid")


@dataclass(frozen=True)
class ShortlistProposal:
    ids: tuple[str, ...]
    reason: str
    relevance_calibrated: bool = False
    noanswer_determined: bool = False


def separated_head(scores, *, maximum=5):
    """Offline only: select a unique gap accounting for >half the score range.

    This structural criterion is invariant under positive affine rescaling;
    there is no model-specific absolute threshold. Flat/singleton lists, tied
    splits and a broad head exceeding the cap cannot establish a shortlist.
    Never use an empty proposal as a correct no-answer or publish it as an
    admitted result. Calibration needs independent positive AND negative data.
    """
    validate_scores(scores)
    if type(maximum) is not int or not 1 <= maximum <= 20:
        raise SemanticError("search_policy_invalid")
    ranked = sorted(scores, key=lambda key: (-scores[key], key))
    if len(ranked) < 2:
        return ShortlistProposal((), "insufficient_comparison")
    span = scores[ranked[0]] - scores[ranked[-1]]
    if span <= 0:
        return ShortlistProposal((), "flat_scores")
    splits = [i for i in range(1, len(ranked))
              if scores[ranked[i-1]] - scores[ranked[i]] > span * (.5 + 1e-12)]
    if len(splits) != 1:
        return ShortlistProposal((), "no_dominant_separation")
    cut = splits[0]
    if cut > maximum:
        return ShortlistProposal((), "head_exceeds_cap")
    return ShortlistProposal(tuple(ranked[:cut]), "separated_rank_head_only")


def admitted_ids(candidates, scores, *, model, threshold, maximum):
    """Retain the known native contract; unfamiliar scales fail explicitly."""
    validate_scores(scores)
    if profile(model) != "legacy-native.v1":
        raise SemanticError("search_rerank_uncalibrated")
    if (type(maximum) is not int or not 1 <= maximum <= 20
            or type(threshold) not in (int, float) or not 0 < threshold < 1):
        raise SemanticError("search_policy_invalid")
    accepted = [c for c in candidates if c.film_id in scores
                and scores[c.film_id] >= threshold]
    # Missing scores are local evidence, never a zero native relevance score.
    accepted += [c for c in candidates if c.film_id not in scores and c.admitted]
    accepted.sort(key=lambda c: (c.film_id not in scores, -scores.get(c.film_id, 0), -c.rrf, c.film_id))
    return [c.film_id for c in accepted[:maximum]]
