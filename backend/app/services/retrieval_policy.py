"""Opt-in offline recall / ordering / admission. No provider or application wiring.

Caller supplies content vectors and the current SQL-eligible IDs. Intent modes
are explicit caller annotations, not an automatic natural-language interpreter.
Keep semantic_search.py intact so the frozen historical experiment can replay.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
import re

from app.contracts.structured_metadata import normalize_metadata_text
from app.services.semantic_search import (ContentDocument, ProviderSpec, SemanticError,
    _eligible, _hash, _safe, _tokens, _vector, corpus_revision)

VERSION = "retrieval-policy.offline.v2.1"
# Search scaffolding contributes negligibly to ordering, never to admission.
GENERIC_EN = frozenset("a an the and or of in on with to from at by for as is are was were "
    "be been it its their they them his her this that these those which who how what "
    "when where can could would should find search show give looking look please "
    "film films movie movies story stories about featuring during into through".split())
GENERIC_ZH = frozenset(("电影", "影片", "故事", "寻找", "搜索", "推荐", "一部", "一些", "一段", "有关", "关于"))
FUNCTION_ZH = frozenset("的了与和在中里地于以为并而是个这那们着及后前将把让来去")
SPLIT = re.compile(r"\b(?:and|while|with|where|under|featuring)\b|[，,;；。]|并且|以及|同时|而且|和|与", re.I)


@dataclass(frozen=True)
class RetrievalPolicy:
    candidate_k: int = 20
    k1: float = 1.2
    b: float = .75
    rrf_k: int = 60
    theme_strong: float = .42
    theme_supported: float = .28
    theme_coverage: float = .12
    factual_similarity: float = .32
    factual_coverage: float = .30
    clause_coverage: float = .25
    literal_coverage: float = .70
    reference_similarity: float = .45
    anchor_bundle_bm25: float = 3.

    def __post_init__(self):
        if type(self.candidate_k) is not int or not 1 <= self.candidate_k <= 100:
            raise SemanticError("invalid_candidate_bound")
        if type(self.rrf_k) is not int or not 1 <= self.rrf_k <= 1000:
            raise SemanticError("invalid_retrieval_policy")
        for name, value in asdict(self).items():
            if name in {"candidate_k", "rrf_k"}:
                continue
            maximum = 3 if name in {"k1", "anchor_bundle_bm25"} else 1
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= maximum:
                raise SemanticError("invalid_retrieval_policy")
        if self.theme_supported > self.theme_strong:
            raise SemanticError("invalid_retrieval_policy")

    @property
    def fingerprint(self):
        return _hash([VERSION, asdict(self)])


def _stem(word):
    # Deliberately small morphology, not translation or identity normalization.
    if word in GENERIC_EN:
        return word
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def features(text):
    """Words + CJK word-like bigrams and weak character fallback, without a model."""
    text = normalize_metadata_text(text)
    counts = Counter("w:" + _stem(w) for w in re.findall(r"[a-z0-9]+", text))
    # Split generic spans before n-grams: 电影故事 must not create the spurious
    # substantive bridge 影故, or acquire admission through character overlap.
    cjk_text = re.sub("|".join(sorted(GENERIC_ZH)), " ", text)
    for run in re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+", cjk_text):
        counts.update("c:" + c for c in run if c not in FUNCTION_ZH)
        counts.update("b:" + run[i:i + 2] for i in range(len(run) - 1)
                      if not set(run[i:i + 2]) & FUNCTION_ZH)
    return counts


def weight(term):
    value = term[2:]
    if term.startswith("c:"):
        return .15
    if value in GENERIC_EN or value in GENERIC_ZH:
        return .02
    return 1.


def substantive(terms):
    return {term for term in terms if weight(term) >= 1}


def anchor_count(query, matched):
    """Overlapping CJK n-grams are one literal span, not independent evidence."""
    text = normalize_metadata_text(query)
    spans = [(m.start(), m.end(), "w:" + _stem(m.group())) for m in re.finditer(r"[a-z0-9]+", text)
             if "w:" + _stem(m.group()) in matched]
    for term in matched:
        if term.startswith("b:"):
            spans.extend((m.start(), m.start() + len(term[2:]), term) for m in
                         re.finditer("(?=" + re.escape(term[2:]) + ")", text))
    groups, end = [], -1
    for start, stop, term in sorted(spans):
        if start > end:
            groups.append(set())
        groups[-1].add(term)
        end = max(end, stop)
    # Repeating an English word or the same CJK span adds no new evidence.
    independent = []
    for group in groups:
        separate = []
        for old in independent:
            if old & group:
                group |= old
            else:
                separate.append(old)
        independent = [*separate, group]
    return len(independent)


@dataclass(frozen=True)
class LexicalEvidence:
    bm25: float
    coverage: float
    matched: tuple[str, ...]
    anchors: int
    clause_coverages: tuple[float, ...]
    exact_identity: bool


class LexicalIndex:
    def __init__(self, texts, identities, policy):
        self.policy, self.identities = policy, identities
        self.terms = {key: features(text) for key, text in texts.items()}
        self.df = Counter(term for terms in self.terms.values() for term in terms)
        self.lengths = {key: sum(weight(t) * n for t, n in terms.items())
                        for key, terms in self.terms.items()}
        self.average_length = sum(self.lengths.values()) / max(1, len(self.lengths)) or 1

    def idf(self, term):
        n, df = len(self.terms), self.df[term]
        return math.log1p((n - df + .5) / (df + .5))

    def coverage(self, wanted, actual):
        wanted = substantive(wanted)
        # Stable arithmetic across process hash seeds, especially at admission
        # boundaries; set iteration must not make .25 flip by a rounding bit.
        denominator = sum(self.idf(t) for t in sorted(wanted))
        return sum(self.idf(t) for t in sorted(wanted & actual)) / denominator if denominator else 0.

    def evidence(self, query, key):
        wanted, actual = features(query), self.terms[key]
        normalization = self.policy.k1 * (1 - self.policy.b + self.policy.b *
            self.lengths[key] / self.average_length)
        value = sum(weight(t) * self.idf(t) * (actual[t] * (self.policy.k1 + 1)) /
                    (actual[t] + normalization) for t in wanted if actual[t])
        clauses = [features(part) for part in SPLIT.split(query)]
        clauses = [part for part in clauses if substantive(part)]
        matched = tuple(sorted(substantive(wanted) & set(actual)))
        return LexicalEvidence(value, self.coverage(wanted, set(actual)),
            matched, anchor_count(query, matched),
            tuple(self.coverage(part, set(actual)) for part in clauses),
            normalize_metadata_text(query) in self.identities[key])


@dataclass(frozen=True)
class Candidate:
    film_id: str
    cosine: float | None
    lexical: LexicalEvidence
    shared_terms: int
    rrf: float
    admitted: bool
    reason: str


@dataclass(frozen=True)
class RetrievalResult:
    candidates: tuple[Candidate, ...]
    dense_ids: tuple[str, ...]
    lexical_ids: tuple[str, ...]
    mode: str
    stage: str
    strategy: str
    eligible_count: int
    policy_fingerprint: str

    @property
    def displayed_ids(self):
        return [row.film_id for row in self.candidates if row.admitted]


class RetrievalIndex:
    """Bounded in-memory index of explicit, already authorized content/vectors.

    No SQL, provider, snapshot writes, environment lookup or network operation.
    Current eligible IDs must be recomputed by the existing SQL executor each use.
    """
    def __init__(self, documents, vectors, spec: ProviderSpec, policy=None):
        self.revision = corpus_revision(documents)
        self.policy, self.spec = policy or RetrievalPolicy(), spec
        if not isinstance(self.policy, RetrievalPolicy) or not isinstance(spec, ProviderSpec):
            raise SemanticError("invalid_retrieval_policy")
        self.documents = {doc.film_id: doc for doc in documents}
        if not isinstance(vectors, dict) or set(vectors) != set(self.documents):
            raise SemanticError("invalid_vector_identities")
        self.vectors = {key: _vector(value, spec.dimensions) for key, value in vectors.items()}
        self.texts = {key: " ".join(doc.chunks) for key, doc in self.documents.items()}
        self.identities = {key: {normalize_metadata_text(n) for n in (doc.title, *doc.aliases)}
                           for key, doc in self.documents.items()}
        self.lexical = LexicalIndex(self.texts, self.identities, self.policy)
        self.legacy_terms = {key: _tokens(text) for key, text in self.texts.items()}

    def _admit(self, evidence, cosine, mode, strategy):
        p = self.policy
        if evidence.exact_identity and mode != "reference":
            return True, "exact_identity"
        meaningful = len(evidence.matched)
        clauses = bool(evidence.clause_coverages) and min(evidence.clause_coverages) >= p.clause_coverage
        bundle = evidence.anchors >= 2 and evidence.bm25 >= p.anchor_bundle_bm25
        if mode == "reference":
            if strategy == "lexical":
                ok = evidence.coverage >= p.theme_coverage and bundle
            else:
                ok = cosine is not None and cosine >= p.reference_similarity
            return ok, "reference_content" if ok else "reference_insufficient_evidence"
        if mode == "exploratory":
            if cosine is not None and cosine >= p.theme_strong:
                return True, "theme_semantic_support"
            if (cosine is not None and cosine >= p.theme_supported
                    and evidence.coverage > 0 and meaningful):
                # Broad themes may be paraphrases: one real lexical anchor plus
                # semantic support is evidence, not a claim of full fact coverage.
                return True, "theme_semantic_anchor"
            if evidence.coverage >= p.literal_coverage and meaningful >= 2:
                return True, "theme_substantive_literal"
            if bundle and evidence.coverage >= p.theme_coverage:
                return True, "theme_lexical_anchor_bundle"
            return False, "theme_insufficient_evidence"
        # Literal evidence can stand alone, but rank/one generic token cannot.
        if clauses and meaningful >= 2 and evidence.coverage >= p.literal_coverage:
            return True, "factual_substantive_literal"
        if clauses and bundle and evidence.coverage >= p.clause_coverage:
            return True, "factual_lexical_anchor_bundle"
        if (clauses and evidence.anchors >= 2 and evidence.coverage >= p.factual_coverage
                and cosine is not None and cosine >= p.factual_similarity):
            return True, "factual_combined_support"
        return False, "factual_incomplete_evidence"

    def search(self, question, *, eligible_ids, query_vector=None, reference_id=None,
               mode="factual", strategy="hybrid", stage="admission"):
        question = _safe(question, 600)
        if (not isinstance(mode, str) or mode not in {"factual", "exploratory"}
                or not isinstance(strategy, str) or strategy not in {"dense", "lexical", "hybrid"}):
            raise SemanticError("invalid_retrieval_mode")
        if not isinstance(stage, str) or stage not in {"candidates", "lexical", "admission"}:
            raise SemanticError("invalid_retrieval_stage")
        eligible = _eligible(eligible_ids) & set(self.documents)
        if reference_id is not None:
            if not isinstance(reference_id, str) or reference_id not in self.documents:
                raise SemanticError("reference_missing_content")
            topic, vector, mode = self.texts[reference_id], self.vectors[reference_id], "reference"
            eligible.discard(reference_id)
        else:
            topic = question
            vector = None if strategy == "lexical" or query_vector is None else _vector(query_vector, self.spec.dimensions)
            if strategy != "lexical" and vector is None and eligible:
                raise SemanticError("missing_query_vector")
        words = _tokens(topic)
        meaningful_query = bool(substantive(features(topic)))
        evidence = {key: self.lexical.evidence(topic, key) for key in eligible}
        cosine = {key: max(-1., min(1., sum(a * b for a, b in zip(vector, self.vectors[key]))))
                  for key in eligible} if vector is not None and strategy != "lexical" else {}
        shared = {key: len(words & self.legacy_terms[key]) for key in eligible}
        lexical = {key: evidence[key].bm25 if stage != "candidates" else shared[key] for key in eligible}
        k = self.policy.candidate_k
        dense_ids = sorted(cosine, key=lambda key: (-cosine[key], key))[:k] if strategy != "lexical" else []
        lexical_ids = sorted((key for key in lexical if lexical[key] > 0),
                             key=lambda key: (-lexical[key], key))[:k] if strategy != "dense" else []
        exact = sorted(key for key in eligible if evidence[key].exact_identity and mode != "reference")[:k]
        fused = {key: 0. for key in exact}
        for ids in (dense_ids, lexical_ids):
            for rank, key in enumerate(ids, 1):
                fused[key] = fused.get(key, 0) + 1 / (self.policy.rrf_k + rank)
        rows = []
        for key in sorted(fused, key=lambda key: (key not in exact, -fused[key], key)):
            if stage == "admission":
                admitted, reason = self._admit(evidence[key], cosine.get(key), mode, strategy)
                if mode != "reference" and not meaningful_query and not evidence[key].exact_identity:
                    admitted, reason = False, "generic_only_query"
            else:
                admitted = (strategy != "lexical" and cosine.get(key, -1) >= .35 or
                            strategy != "dense" and (shared[key] if stage == "candidates" else lexical[key]) > 0)
                reason = "legacy_display_gate" if admitted else "candidate_only"
            rows.append(Candidate(key, cosine.get(key), evidence[key], shared[key],
                                  fused[key], bool(admitted), reason))
        return RetrievalResult(tuple(rows), tuple(dense_ids), tuple(lexical_ids), mode,
            stage, strategy, len(eligible), self.policy.fingerprint)
