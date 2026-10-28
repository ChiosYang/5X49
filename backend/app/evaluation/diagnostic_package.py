"""Read-only, standard-library loader for the diagnostic v3 draft contract."""
from __future__ import annotations

import hashlib
import io
import json
import math
import stat
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

VERSION = "5x49-diagnostic-v3.0-draft"
FILES = frozenset({"manifest.json", "validation-report.json", "source-draft.zh.md",
    "input/frozen-index.jsonl", "input/questions-only.json", "input/questions-only.jsonl",
    "input/result-template.json", "judging/answer-key.json", "judging/scoring-spec.json",
    "judging/scoring-rules.md", "evidence/candidate-evidence.json"})
STAGES = ("lexical_ids", "semantic_ids", "fused_ids", "filtered_ids", "reranked_ids", "displayed_ids")
GAINS = {0: 0, 1: 0, 2: 3, 3: 7}
FORMULAS = {
    "recall_at_20": "count(intersection(first20(fused_ids), relevant_ids)) / len(relevant_ids)",
    "precision_at_5": "count(intersection(first5(displayed_ids), relevant_ids)) / 5",
    "p5_ceiling_normalized": "count(intersection(first5(displayed_ids), relevant_ids)) / min(5,len(relevant_ids))",
    "ndcg_at_5": "sum_i_1_to_5(gain(grade(displayed_i))/log2(i+1)) / ideal_DCG_over_all_24_candidates; missing positions gain 0",
    "answerable_hit_at_5": "int(any(grade(id)>=2 for id in first5(displayed_ids)))",
    "false_empty": "int(observed_behavior == empty) on answerable queries",
    "noanswer_false_positive": "int(len(displayed_ids)>0) on noanswer controls",
    "noanswer_correct": "int(observed_behavior == empty and len(displayed_ids)==0)",
    "clarification_score": "human 0..2 according to per-query rubric; report each and total/6",
}


class InvalidInput(ValueError):
    """Malformed, unsupported or incorrectly bound evaluation input."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidInput(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise InvalidInput(f"non-finite JSON number: {value}")


def finite_tree(value: Any) -> None:
    if isinstance(value, float):
        require(math.isfinite(value), "non-finite number")
    elif isinstance(value, dict):
        for child in value.values():
            finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            finite_tree(child)


def decode(data: bytes) -> Any:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
        finite_tree(value)
        return value
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInput(f"invalid UTF-8 JSON: {exc}") from None


def jsonl(data: bytes) -> list:
    return [decode(line) for line in data.splitlines() if line.strip()]


def safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return (bool(name) and not p.is_absolute() and "\\" not in name and ":" not in name
            and all(part not in {"", ".", ".."} for part in name.split("/")))


def read_members(path: Path, archive_bytes: bytes | None = None) -> dict[str, bytes]:
    if path.is_dir():
        result = {}
        require({p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()} == FILES,
                "unexpected/missing directory members")
        for name in FILES:
            item = path.joinpath(*name.split("/"))
            require(item.is_file() and not item.is_symlink(), f"missing/unsafe package member: {name}")
            require(item.resolve().is_relative_to(path.resolve()), "member escapes package")
            require(item.stat().st_size <= 20_000_000, "package member too large")
            result[name] = item.read_bytes()
        return result
    require(path.is_file() and path.stat().st_size <= 100_000_000, "missing/oversize package")
    result = {}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes) if archive_bytes is not None else path) as archive:
            total = 0
            for entry in archive.infolist():
                if entry.is_dir():
                    require(safe_name(entry.filename.rstrip("/")), "unsafe archive directory")
                    continue
                require(safe_name(entry.filename), "unsafe archive member path")
                require(not stat.S_ISLNK(entry.external_attr >> 16), "archive symlink")
                require(entry.filename not in result, "duplicate archive member")
                total += entry.file_size
                require(entry.file_size <= 20_000_000 and total <= 100_000_000, "oversize archive")
                result[entry.filename] = archive.read(entry)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise InvalidInput(f"invalid archive: {exc}") from None
    require(set(result) == FILES, "unexpected/missing archive members")
    return result


@dataclass(frozen=True)
class Package:
    members: dict[str, bytes]
    manifest: dict
    index: dict[str, dict]
    questions: dict[str, dict]
    answers: dict[str, dict]
    spec: dict
    original_archive_sha256: str | None = None

    @property
    def binding(self) -> str:
        return sha256(self.members["manifest.json"])


def unique_map(rows: Any, key: str, label: str) -> dict:
    require(isinstance(rows, list) and all(isinstance(r, dict) for r in rows), f"invalid {label} rows")
    keys = [r.get(key) for r in rows]
    require(all(isinstance(k, str) and k.strip() for k in keys), f"invalid {label} ID")
    require(len(keys) == len(set(keys)), f"duplicate {label} ID")
    return dict(zip(keys, rows))


def load_package(path: Path) -> Package:
    archive_bytes = None
    if path.is_file():
        require(path.stat().st_size <= 100_000_000, "oversize package")
        archive_bytes = path.read_bytes()
    files = read_members(path, archive_bytes)
    manifest = decode(files["manifest.json"])
    require(isinstance(manifest, dict) and manifest.get("version") == VERSION, "unsupported package version")
    declared = manifest.get("files")
    require(isinstance(declared, dict) and set(declared) == FILES - {"manifest.json"}, "invalid manifest members")
    for name, metadata in declared.items():
        require(isinstance(metadata, dict) and type(metadata.get("bytes")) is int, "invalid manifest length")
        require(metadata["bytes"] == len(files[name]) and metadata.get("sha256") == sha256(files[name]), f"hash/length mismatch: {name}")
    spec = decode(files["judging/scoring-spec.json"])
    require(isinstance(spec, dict) and spec.get("version") == VERSION, "unsupported rules version")
    require(spec.get("status") == "proposal_not_calibrated", "unsupported rule calibration state")
    require(spec.get("candidate_count") == 24 and type(spec.get("relevant_grade_min")) is int
            and spec["relevant_grade_min"] == 2, "unsupported relevance contract")
    require(spec.get("gain_by_grade") == {str(k): v for k, v in GAINS.items()}, "unsupported gains")
    require(all(type(v) is int for v in spec["gain_by_grade"].values()), "invalid gain number type")
    require(spec.get("metrics") == FORMULAS and spec.get("formal_definition_file") == "scoring-rules.md", "unsupported metric formulas")
    require(manifest.get("candidate_count") == manifest.get("query_count") == 24, "wrong package counts")
    index = unique_map(jsonl(files["input/frozen-index.jsonl"]), "id", "candidate")
    query_file = decode(files["input/questions-only.json"])
    answer_file = decode(files["judging/answer-key.json"])
    require(isinstance(query_file, dict) and isinstance(answer_file, dict), "invalid question/answer schema")
    require(query_file.get("version") == answer_file.get("version") == VERSION, "question/answer version mismatch")
    questions = unique_map(query_file.get("queries"), "query_id", "question")
    answers = unique_map(answer_file.get("queries"), "query_id", "answer")
    require(len(index) == len(questions) == len(answers) == 24 and set(questions) == set(answers), "wrong IDs/counts")
    require(jsonl(files["input/questions-only.jsonl"]) == list(questions.values()), "question JSON/JSONL mismatch")
    require(Counter(q.get("category") for q in questions.values()) == {"plot": 8, "theme": 8, "similar": 8}, "wrong categories")
    require(answer_file.get("pair_count") == 576 and answer_file.get("binary_relevant_min_grade") == 2, "wrong judgment contract")
    for film in index.values():
        require(set(film) <= {"id", "key", "title_en", "titles", "year", "directors", "document_text", "document_text_sha256"}, "unsupported/judging field in frozen index")
        require(isinstance(film.get("key"), str), "invalid candidate key")
        require(isinstance(film.get("document_text"), str) and film.get("document_text_sha256") == sha256(film["document_text"].encode("utf-8")), "index text hash mismatch")
        require(type(film.get("year")) is int and isinstance(film.get("directors"), list)
                and all(isinstance(d, str) for d in film["directors"]), "invalid candidate facts")
    for qid, answer in answers.items():
        question = questions[qid]
        require(set(question) == {"query_id", "category", "query"}, "unexpected labels in execution questions")
        require(isinstance(question.get("query"), str) and bool(question["query"].strip()), "invalid question text")
        require(answer.get("query") == question["query"] and answer.get("category") == question["category"], "answer/question mismatch")
        behavior = answer.get("expected_behavior")
        require(behavior in {"ranked", "empty", "clarify"}, "unknown expected behavior")
        judgments = unique_map(answer.get("judgments"), "film_id", "judgment")
        require(set(judgments) == set(index), "incomplete judgments")
        reference = answer.get("reference_id")
        require(reference is None or reference in index, "unknown reference")
        relevant = set()
        for fid, judgment in judgments.items():
            grade, interval = judgment.get("grade"), judgment.get("acceptable_grade_range_for_review")
            require(judgment.get("judgment_status") in {"proposed_source_based", "proposed_factual_match",
                    "constraint_verified", "not_applicable_until_clarified", "provisional_interpretive"}, "unknown judgment status")
            require(grade is None or type(grade) is int and grade in GAINS, "unknown label")
            require(type(judgment.get("is_named_hard_negative")) is bool, "invalid hard-negative marker")
            require(judgment.get("film_key") == index[fid].get("key"), "judgment identity mismatch")
            if grade is None:
                require(interval is None or isinstance(interval, list) and len(interval) == 2, "invalid unjudged interval")
            else:
                require(isinstance(interval, list) and len(interval) == 2
                        and all(type(n) is int and n in GAINS for n in interval)
                        and interval[0] <= grade <= interval[1], "invalid review interval")
                if grade >= 2:
                    relevant.add(fid)
            if judgment["is_named_hard_negative"]:
                require(grade is not None and grade <= 1, "hard negative has positive grade")
            if fid == reference or judgment.get("reason_code") in {"hard_constraint_failed", "excluded_reference"}:
                require(grade == 0, "hard constraint has nonzero/unknown grade")
        require(set(answer.get("relevant_ids", [])) == relevant, "relevant IDs disagree with grades")
        require(set(answer.get("grade3_ids", [])) == {fid for fid, j in judgments.items() if j["grade"] == 3}, "grade3 IDs disagree")
        if behavior == "ranked":
            require(bool(relevant), "answerable question without relevant candidates")
        for fid, film in index.items():
            if not eligible(film, answer):
                require(judgments[fid]["grade"] == 0, "ineligible candidate has nonzero/unknown grade")
        if behavior == "empty":
            require(not relevant and answer.get("constraint_filter") is not None, "invalid empty control")
            require(not [fid for fid, film in index.items() if eligible(film, answer)], "empty control has eligible candidate")
        if behavior == "clarify":
            require(all(j["grade"] is None for j in judgments.values()) and isinstance(answer.get("clarification_rubric"), dict), "invalid clarification labels/rubric")
    for category in {"plot", "theme", "similar"}:
        require(Counter(a["expected_behavior"] for a in answers.values() if a["category"] == category)
                == {"ranked": 5, "empty": 2, "clarify": 1}, "wrong category behavior counts")
    require(len({film["key"] for film in index.values()}) == 24, "duplicate candidate key")
    template = decode(files["input/result-template.json"])
    require(isinstance(template, dict) and template.get("version") == VERSION and template.get("status") == "TEMPLATE_NOT_RESULTS", "invalid package result template")
    template_runs = unique_map(template.get("runs"), "query_id", "template question")
    require(set(template_runs) == set(questions), "template question mismatch")
    require(all(r.get("run_status") is None and r.get("observed_behavior") is None
                and r.get("displayed_ids") == [] and r.get("fused_ids") == [] for r in template_runs.values()), "template is already populated")
    return Package(files, manifest, index, questions, answers, spec,
                   sha256(archive_bytes) if archive_bytes is not None else None)


def eligible(film: dict, answer: dict) -> bool:
    if film["id"] == answer.get("reference_id"):
        return False
    clause = answer.get("constraint_filter")
    if clause is None:
        return True
    require(isinstance(clause, dict) and set(clause) == {"field", "op", "value"}, "unsupported constraint schema")
    field, op, value = clause["field"], clause["op"], clause["value"]
    if field == "year":
        if op == "between_inclusive":
            require(isinstance(value, list) and len(value) == 2 and all(type(v) is int for v in value) and value[0] <= value[1], "invalid year range")
            return value[0] <= film["year"] <= value[1]
        require(op in {"lte", "gte"} and type(value) is int, "unsupported year constraint")
        return film["year"] <= value if op == "lte" else film["year"] >= value
    require(field == "directors" and op == "contains" and isinstance(value, str), "unsupported constraint")
    return value in film["directors"]


def review_register(package: Package) -> dict:
    rows = []
    for qid, answer in sorted(package.answers.items()):
        for judgment in answer["judgments"]:
            grade = judgment["grade"]
            state = ("not_applicable_until_clarified" if answer["expected_behavior"] == "clarify" else
                     "machine_checkable_constraint" if judgment.get("judgment_status") == "constraint_verified" else "needs_human_review")
            rows.append({"query_id": qid, "film_id": judgment["film_id"], "proposed_grade": grade,
                         "acceptable_grade_range_for_review": judgment["acceptable_grade_range_for_review"],
                         "status": state, "source_judgment_status": judgment.get("judgment_status"),
                         "reason": "Preserve source proposal; no human adjudication performed"})
    return {"version": "diagnostic-review-register.v1", "base_version": VERSION,
            "manifest_sha256": package.binding, "label_changes": [], "human_adjudication": False,
            "summary": dict(Counter(r["status"] for r in rows)), "pairs": rows}
