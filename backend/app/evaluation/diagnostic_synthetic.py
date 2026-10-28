"""Wholly synthetic fixture factory: no real titles, queries or relevance labels."""
import copy
import json
from pathlib import Path

from app.evaluation.diagnostic_package import FORMULAS, VERSION, sha256


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def fixture():
    films = [{"id": f"toy-{i:02}", "key": f"candidate-{i:02}", "year": 2000 + i,
              "directors": [f"Toy Director {i}"], "document_text": f"Synthetic document {i}",
              "document_text_sha256": sha256(f"Synthetic document {i}".encode())} for i in range(24)]
    questions, answers, template = [], [], []
    for category in ("plot", "theme", "similar"):
        for n in range(8):
            qid = f"toy-{category}-{n + 1}"
            behavior = "ranked" if n < 5 else "empty" if n < 7 else "clarify"
            question = {"query_id": qid, "category": category, "query": f"Synthetic {category} input {n + 1}"}
            questions.append(question)
            reference = "toy-00" if category == "similar" and behavior != "clarify" else None
            judgments = []
            for film in films:
                grade = None if behavior == "clarify" else {"toy-01": 3, "toy-02": 2, "toy-03": 1}.get(film["id"], 0) if behavior == "ranked" else 0
                reason = "excluded_reference" if film["id"] == reference else "hard_constraint_failed" if behavior == "empty" else "synthetic_label"
                judgments.append({"film_id": film["id"], "film_key": film["key"], "grade": grade,
                    "acceptable_grade_range_for_review": None if grade is None else [grade, grade],
                    "is_named_hard_negative": behavior == "ranked" and film["id"] == "toy-03",
                    "judgment_status": "not_applicable_until_clarified" if behavior == "clarify" else "constraint_verified" if behavior == "empty" else "provisional_interpretive",
                    "reason_code": reason})
            answers.append({**question, "expected_behavior": behavior, "reference_id": reference,
                "constraint_filter": {"field": "year", "op": "lte", "value": 1900} if behavior == "empty" else None,
                "clarification_rubric": {"scoring": {"0": "guess", "1": "question", "2": "specific question"}} if behavior == "clarify" else None,
                "judgments": judgments, "relevant_ids": ["toy-01", "toy-02"] if behavior == "ranked" else [],
                "grade3_ids": ["toy-01"] if behavior == "ranked" else []})
            template.append({"query_id": qid, "run_status": None, "observed_behavior": None, "fused_ids": [], "displayed_ids": [],
                             "clarification_text": "", "human_clarification_score": None, "human_review_note": ""})
    files = {"input/frozen-index.jsonl": b"".join(encoded(f).replace(b"\n", b"") + b"\n" for f in films),
        "input/questions-only.json": encoded({"version": VERSION, "queries": questions}),
        "input/questions-only.jsonl": b"".join(json.dumps(q).encode() + b"\n" for q in questions),
        "input/result-template.json": encoded({"version": VERSION, "status": "TEMPLATE_NOT_RESULTS", "runs": template}),
        "judging/answer-key.json": encoded({"version": VERSION, "pair_count": 576, "binary_relevant_min_grade": 2, "queries": answers}),
        "judging/scoring-spec.json": encoded({"version": VERSION, "status": "proposal_not_calibrated", "candidate_count": 24,
            "relevant_grade_min": 2, "gain_by_grade": {"0": 0, "1": 0, "2": 3, "3": 7}, "metrics": FORMULAS, "formal_definition_file": "scoring-rules.md"}),
        "judging/scoring-rules.md": b"Synthetic scoring-contract fixture; no real data.\n",
        "evidence/candidate-evidence.json": encoded({"version": VERSION, "films": films}),
        "validation-report.json": encoded({"status": "SYNTHETIC_ONLY"}), "source-draft.zh.md": b"Synthetic fixture only.\n"}
    seal(files)
    return files


def seal(files):
    files["manifest.json"] = encoded({"version": VERSION, "candidate_count": 24, "query_count": 24,
        "status": "synthetic_draft_not_human_gold", "files": {name: {"sha256": sha256(data), "bytes": len(data)}
        for name, data in files.items() if name != "manifest.json"}})


def write_fixture(path: Path, files=None):
    for name, data in (files or fixture()).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def simulated_results(package):
    runs = []
    for qid, answer in package.answers.items():
        runs.append({"query_id": qid, "run_status": "ok", "observed_behavior": answer["expected_behavior"],
            "fused_ids": list(package.index), "displayed_ids": ["toy-01", "toy-02"] if answer["expected_behavior"] == "ranked" else [],
            "clarification_text": "Which synthetic preference do you mean?" if answer["expected_behavior"] == "clarify" else "",
            "human_clarification_score": 2 if answer["expected_behavior"] == "clarify" else None,
            "human_review_note": "SIMULATED rubric score, not human adjudication" if answer["expected_behavior"] == "clarify" else ""})
    return {"version": VERSION, "status": "SIMULATED_RESULTS", "manifest_sha256": package.binding, "runs": copy.deepcopy(runs)}


def main(argv=None):
    import argparse
    from app.evaluation.diagnostic_package import load_package
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    package_path=args.output/"package"
    write_fixture(package_path)
    data=simulated_results(load_package(package_path))
    (args.output/"ideal-results.json").write_bytes(encoded(data))
    faulty=copy.deepcopy(data)
    faulty["runs"][0]["displayed_ids"]=["toy-04","toy-02","toy-01"]
    faulty["runs"][16]["displayed_ids"]=["toy-00","toy-01","toy-02"]
    faulty["runs"][5].update(observed_behavior="ranked",displayed_ids=["toy-01"])
    (args.output/"faulty-results.json").write_bytes(encoded(faulty))
    print(json.dumps({"status":"SIMULATED_FIXTURES_ONLY","output":str(args.output)}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
