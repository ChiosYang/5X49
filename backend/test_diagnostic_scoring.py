import copy
import io
import json
import math
import socket
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.evaluation import diagnostic as d
from app.evaluation import diagnostic_package as p
from app.evaluation.diagnostic_synthetic import encoded, fixture, seal, simulated_results, write_fixture


class DiagnosticScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "package"
        write_fixture(self.root)
        self.package = p.load_package(self.root)
        self.data = simulated_results(self.package)

    def ranked(self, category="plot"):
        return next(r for r in self.data["runs"] if r["query_id"] == f"toy-{category}-1")

    def row(self, report, qid="toy-plot-1"):
        return next(r for r in report["cases"] if r["query_id"] == qid)

    def mutate_package(self, member, callback):
        files = fixture()
        value = p.decode(files[member]);callback(value);files[member] = encoded(value);seal(files)
        write_fixture(self.root, files)
        return p.load_package(self.root)

    def test_ideal_manual_counts_and_separate_denominators(self):
        r = d.score(self.package, self.data)
        self.assertTrue(r["diagnostic_complete"])
        self.assertTrue(r["simulation"])
        self.assertFalse(r["official_aggregate_valid"])
        self.assertEqual(r["acceptance"], "not_assessed")
        self.assertEqual(r["ranking"]["expected"], 15)
        self.assertEqual(r["empty"]["expected"], 6)
        self.assertEqual(r["clarification"]["expected"], 3)
        self.assertEqual(r["ranking"]["macro"]["precision_at_5"], .4)
        self.assertEqual(r["ranking"]["macro"]["ndcg_at_5"], 1)
        self.assertEqual(r["ranking"]["numerators"]["answerable_hit_at_5"], 15)
        self.assertEqual(r["empty"]["numerators"]["noanswer_correct"], 6)
        self.assertEqual(r["clarification"]["total"], 6)
        self.assertTrue(all(v["expected"] == 5 for v in r["by_category"].values()))

    def test_wrong_order_hand_calculated_discount(self):
        self.ranked()["displayed_ids"] = ["toy-02", "toy-01"]
        metrics = self.row(d.score(self.package, self.data))["metrics"]
        # Hand calculation: (3 + 7/log2(3))/(7 + 3/log2(3)).
        self.assertAlmostEqual(metrics["ndcg_at_5"], 0.8339912323981488)
        self.assertEqual(metrics["precision_at_5"], .4)

    def test_single_relevant_answer_ceiling_is_one_not_five(self):
        def change(a):
            q=a["queries"][0];q["judgments"][2].update(grade=0,acceptable_grade_range_for_review=[0,0]);q["relevant_ids"]=["toy-01"]
        package=self.mutate_package("judging/answer-key.json",change)
        report=d.score(package,simulated_results(package));m=self.row(report)["metrics"]
        self.assertEqual(m["precision_at_5"],.2)
        self.assertEqual(m["p5_ceiling_normalized"],1)
        self.assertEqual(m["ndcg_at_5"],1)

    def test_answerable_with_zero_ideal_is_invalid_package(self):
        def change(a):
            q=a["queries"][0]
            for j in q["judgments"]:j.update(grade=0,acceptable_grade_range_for_review=[0,0])
            q.update(relevant_ids=[],grade3_ids=[])
        with self.assertRaises(p.InvalidInput):self.mutate_package("judging/answer-key.json",change)

    def test_short_list_keeps_fixed_five_denominator(self):
        self.ranked()["displayed_ids"] = ["toy-01"]
        m = self.row(d.score(self.package, self.data))["metrics"]
        self.assertEqual(m["precision_at_5"], .2)
        self.assertEqual(m["p5_ceiling_normalized"], .5)
        self.assertAlmostEqual(m["ndcg_at_5"], 0.7871546029909718)

    def test_wrong_film_keeps_original_slot(self):
        self.ranked()["displayed_ids"] = ["toy-04", "toy-01", "toy-02"]
        row = self.row(d.score(self.package, self.data))
        self.assertEqual([s["gain"] for s in row["display_slots"]], [0, 7, 3])
        self.assertAlmostEqual(row["metrics"]["ndcg_at_5"], 0.6653152460429406)

    def test_grade_one_has_zero_gain_and_named_exposure(self):
        self.ranked()["displayed_ids"] = ["toy-03"]
        m = self.row(d.score(self.package, self.data))["metrics"]
        self.assertEqual(m["ndcg_at_5"], 0)
        self.assertEqual(m["named_hard_negative_exposure_at_5"], 1)

    def test_reference_zero_gain_not_compacted(self):
        self.ranked("similar")["displayed_ids"] = ["toy-00", "toy-01", "toy-02"]
        r = d.score(self.package, self.data)
        row = self.row(r, "toy-similar-1")
        self.assertEqual(row["display_slots"][0]["gain"], 0)
        self.assertEqual(row["hard_constraint_violations"][0]["position"], 1)
        self.assertAlmostEqual(row["metrics"]["ndcg_at_5"], 0.6653152460429406)
        self.assertEqual(r["hard_constraint_violation_count"], 1)

    def test_duplicate_is_invalid_and_preserves_occupied_rank(self):
        self.ranked()["displayed_ids"] = ["toy-01", "toy-01", "toy-02"]
        r = d.score(self.package, self.data);row = self.row(r)
        self.assertFalse(r["diagnostic_complete"])
        self.assertIn("duplicate_candidate", [e["code"] for e in r["contract_errors"]])
        self.assertEqual([s["gain"] for s in row["display_slots"]], [7, 0, 3])
        self.assertEqual(row["metrics"]["precision_at_5"], .4)
        self.assertEqual(r["ranking"]["measured"], 14)
        self.assertIsNone(r["ranking"]["macro"])

    def test_unknown_candidate_is_unscored_not_zero(self):
        for stage in ("fused_ids", "displayed_ids", "lexical_ids"):
            with self.subTest(stage=stage):
                data = copy.deepcopy(self.data);data["runs"][0][stage] = ["outside-package"]
                r = d.score(self.package, data)
                self.assertIsNone(self.row(r)["metrics"])
                self.assertFalse(r["diagnostic_complete"])

    def test_unknown_slot_stays_unknown_and_known_reference_still_reported(self):
        self.ranked("similar")["displayed_ids"]=["outside-package","toy-00","toy-01"]
        r=d.score(self.package,self.data);row=self.row(r,"toy-similar-1")
        self.assertIsNone(row["metrics"])
        self.assertIsNone(row["display_slots"][0]["gain"])
        self.assertEqual(row["hard_constraint_violations"][0]["position"],2)

    def test_boolean_gain_and_positive_ineligible_label_are_rejected(self):
        def change(s):s["gain_by_grade"]["0"]=False
        with self.assertRaises(p.InvalidInput):self.mutate_package("judging/scoring-spec.json",change)
        def conflict(a):a["queries"][0]["constraint_filter"]={"field":"year","op":"lte","value":1900}
        with self.assertRaises(p.InvalidInput):self.mutate_package("judging/answer-key.json",conflict)

    def test_missing_duplicate_and_unknown_questions(self):
        for mode in ("missing", "duplicate", "unknown"):
            with self.subTest(mode=mode):
                data = copy.deepcopy(self.data)
                if mode == "missing":data["runs"].pop(0)
                elif mode == "duplicate":data["runs"].append(copy.deepcopy(data["runs"][0]))
                else:data["runs"][0]["query_id"] = "absent-query"
                r = d.score(self.package, data)
                self.assertFalse(r["diagnostic_complete"])
                self.assertIsNone(r["ranking"]["macro"])
                self.assertIn(mode + "_query", [e["code"] for e in r["contract_errors"]])

    def test_illegal_scores_and_nonfinite_values(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, "0.7"):
            with self.subTest(value=value):
                data = copy.deepcopy(self.data);data["runs"][0]["scores"] = {"displayed_ids": [value, .2]}
                with self.assertRaises(p.InvalidInput):d.score(self.package, data)
        with self.assertRaises(p.InvalidInput):p.decode(b'{"score":NaN}')
        with self.assertRaises(p.InvalidInput):p.decode(b'{"score":1e999}')
        with self.assertRaises(p.InvalidInput):p.decode(b'{"score":1,"score":2}')

    def test_score_and_stage_mapping_checks(self):
        for extra in ({"scores": {"displayed_ids": [.2]}}, {"scores": {"other": []}},
                      {"latency_ms": {"total": -1}}, {"stage_status": {"bogus": "ok"}}, {"run_status": "success"}):
            data = copy.deepcopy(self.data);data["runs"][0].update(extra)
            with self.subTest(extra=extra), self.assertRaises(p.InvalidInput):d.score(self.package, data)

    def test_empty_false_positive_and_constraint_violation(self):
        run = next(r for r in self.data["runs"] if r["query_id"] == "toy-plot-6")
        run.update(observed_behavior="ranked", displayed_ids=["toy-01"])
        r = d.score(self.package, self.data);row = self.row(r, "toy-plot-6")
        self.assertEqual(row["metrics"], {"noanswer_false_positive": 1, "noanswer_correct": 0})
        self.assertEqual(r["empty"]["numerators"]["noanswer_false_positive"], 1)
        self.assertEqual(r["hard_constraint_violation_count"], 1)

    def test_error_empty_never_counts_as_correct_refusal(self):
        for qid in ("toy-plot-1", "toy-plot-6"):
            with self.subTest(qid=qid):
                data = copy.deepcopy(self.data);run = next(r for r in data["runs"] if r["query_id"] == qid)
                run.update(run_status="error", observed_behavior="empty", displayed_ids=[], error="synthetic timeout")
                r = d.score(self.package, data);row = self.row(r, qid)
                self.assertIsNone(row["metrics"])
                self.assertFalse(r["diagnostic_complete"])

    def test_false_empty_unnecessary_clarification_and_wrong_empty_behavior(self):
        self.ranked().update(observed_behavior="empty", displayed_ids=[])
        self.ranked("theme").update(observed_behavior="clarify", displayed_ids=[], clarification_text="Which one?")
        run = next(r for r in self.data["runs"] if r["query_id"] == "toy-theme-6")
        run.update(observed_behavior="clarify", clarification_text="Which one?")
        r = d.score(self.package, self.data)
        self.assertEqual(r["ranking"]["numerators"]["false_empty"], 1)
        self.assertEqual(r["ranking"]["numerators"]["unnecessary_clarification"], 1)
        self.assertEqual(self.row(r, "toy-theme-6")["metrics"]["noanswer_correct"], 0)
        self.assertEqual(self.row(r, "toy-theme-6")["metrics"]["noanswer_false_positive"], 0)

    def test_clarification_guess_is_zero_even_with_supplied_two(self):
        run = next(r for r in self.data["runs"] if r["query_id"] == "toy-plot-8")
        run.update(observed_behavior="ranked", displayed_ids=["toy-01"])
        row = self.row(d.score(self.package, self.data), "toy-plot-8")
        self.assertEqual(row["clarification_score"], 0)
        self.assertIsNone(row["metrics"])

    def test_clarification_needs_manual_review_not_keyword_matching(self):
        run = next(r for r in self.data["runs"] if r["query_id"] == "toy-plot-8")
        run.update(human_clarification_score=None, human_review_note="")
        r = d.score(self.package, self.data)
        self.assertIsNone(r["clarification"]["total"])
        self.assertEqual(r["clarification"]["partial_total"], 4)
        self.assertFalse(r["diagnostic_complete"])
        run["human_clarification_score"] = 2
        with self.assertRaises(p.InvalidInput):d.score(self.package, self.data)

    def test_behavior_empty_with_ids_is_invalid(self):
        self.ranked()["observed_behavior"] = "empty"
        r = d.score(self.package, self.data)
        self.assertFalse(r["diagnostic_complete"])
        self.assertIn("behavior_contains_recommendations", [e["code"] for e in r["contract_errors"]])

    def test_unjudged_rankable_label_is_not_imputed_zero(self):
        def change(a):
            j = a["queries"][0]["judgments"][4];j.update(grade=None, acceptable_grade_range_for_review=None)
        package = self.mutate_package("judging/answer-key.json", change)
        data = simulated_results(package);r = d.score(package, data)
        self.assertIsNone(self.row(r)["metrics"])
        self.assertEqual(r["ranking"]["measured"], 14)

    def test_package_rejects_unknown_label_and_identity_conflicts(self):
        def label(a):a["queries"][0]["judgments"][4]["grade"] = 4
        def identity(a):a["queries"][0]["judgments"][4]["film_id"] = "unknown"
        def status(a):a["queries"][0]["judgments"][4]["judgment_status"] = "human_gold"
        for change in (label, identity, status):
            with self.subTest(change=change.__name__), self.assertRaises(p.InvalidInput):self.mutate_package("judging/answer-key.json", change)

    def test_binding_versions_and_schema_fail_closed(self):
        for change in ({"version": "future"}, {"manifest_sha256": "wrong"}, {"status": "passed"}, {"extra": []}):
            data = copy.deepcopy(self.data);data.update(change)
            with self.subTest(change=change), self.assertRaises(p.InvalidInput):d.score(self.package, data)
        for member in ("run_status", "displayed_ids"):
            data = copy.deepcopy(self.data);del data["runs"][0][member]
            with self.assertRaises(p.InvalidInput):d.score(self.package, data)

    def test_manifest_and_index_tampering(self):
        (self.root / "input/frozen-index.jsonl").write_bytes(b"{}\n")
        with self.assertRaises(p.InvalidInput):p.load_package(self.root)

    def test_execution_inputs_reject_answer_fields_and_populated_template(self):
        def add_answer(q):q["queries"][0]["expected_behavior"]="ranked"
        with self.assertRaises(p.InvalidInput):self.mutate_package("input/questions-only.json",add_answer)
        def populate(t):t["runs"][0]["displayed_ids"]=["toy-01"]
        with self.assertRaises(p.InvalidInput):self.mutate_package("input/result-template.json",populate)
        files=fixture();records=p.jsonl(files["input/frozen-index.jsonl"]);records[0]["grade"]=3
        files["input/frozen-index.jsonl"]=b"".join(json.dumps(x).encode()+b"\n"for x in records);seal(files);write_fixture(self.root,files)
        with self.assertRaises(p.InvalidInput):p.load_package(self.root)
        files = fixture();rows = p.jsonl(files["input/frozen-index.jsonl"]);rows[0]["document_text"] = "changed"
        files["input/frozen-index.jsonl"] = b"".join(json.dumps(x).encode() + b"\n" for x in rows);seal(files);write_fixture(self.root, files)
        with self.assertRaises(p.InvalidInput):p.load_package(self.root)

    def test_archive_safety_and_equivalence(self):
        zpath = Path(self.temp.name) / "input.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for name, data in fixture().items():z.writestr(name, data)
        self.assertEqual(p.load_package(zpath).binding, self.package.binding)
        for name in ("../escape", "C:/escape", "a\\b", "/absolute"):
            with zipfile.ZipFile(zpath, "w") as z:z.writestr(name, b"x")
            with self.subTest(name=name), self.assertRaises(p.InvalidInput):p.load_package(zpath)

    def test_archive_duplicate_symlink_and_oversized_member(self):
        import warnings
        zpath=Path(self.temp.name)/"bad.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(zpath,"w") as z:z.writestr("manifest.json",b"{}");z.writestr("manifest.json",b"{}")
        with self.assertRaises(p.InvalidInput):p.load_package(zpath)
        entry=zipfile.ZipInfo("manifest.json");entry.create_system=3;entry.external_attr=0o120777<<16
        with zipfile.ZipFile(zpath,"w") as z:z.writestr(entry,b"target")
        with self.assertRaises(p.InvalidInput):p.load_package(zpath)
        with zipfile.ZipFile(zpath,"w",compression=zipfile.ZIP_DEFLATED) as z:z.writestr("manifest.json",b"x"*20_000_001)
        with self.assertRaises(p.InvalidInput):p.load_package(zpath)

    def test_failed_required_stage_cannot_be_a_complete_run(self):
        self.ranked()["stage_status"]={"fused_ids":"error"}
        r=d.score(self.package,self.data)
        self.assertFalse(r["diagnostic_complete"])
        self.assertEqual(r["ranking"]["measured"],14)
        self.assertEqual(r["stage_summary"]["fused_ids"]["measured"],14)

    def test_missing_telemetry_is_not_guessed_as_stage_success(self):
        r=d.score(self.package,self.data)
        self.assertEqual(r["stage_summary"]["fused_ids"]["measured"],15)
        self.assertEqual(r["stage_summary"]["reranked_ids"]["measured"],0)
        self.assertIsNone(r["stage_summary"]["reranked_ids"]["partial_macro_recall_at_20"])

    def test_cli_subprocess_has_no_database_search_or_provider_imports(self):
        result_path=Path(self.temp.name)/"result.json";result_path.write_bytes(encoded(self.data))
        code='''import sys
def guard(event,args):
 if event in {"socket.connect","socket.getaddrinfo","subprocess.Popen"}:raise AssertionError(event)
sys.addaudithook(guard)
from app.evaluation.diagnostic import main
status=main(["score","--package",sys.argv[1],"--results",sys.argv[2]])
assert not any(n in sys.modules for n in ("app.database","app.main","app.services.discovery_search","openai","httpx"))
raise SystemExit(status)
'''
        run=subprocess.run([sys.executable,"-B","-c",code,str(self.root),str(result_path)],capture_output=True,text=True,encoding="utf-8",check=False)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertTrue(json.loads(run.stdout)["simulation"])

    def test_stage_metrics_missing_logs_are_unavailable(self):
        row = self.row(d.score(self.package, self.data))
        self.assertIn("reranked_ids", row["stage_evidence"]["unavailable"])
        self.assertEqual(set(row["stage_evidence"]["stages"]), {"fused_ids", "displayed_ids"})
        self.ranked().update(filtered_ids=["toy-04"], reranked_ids=["toy-04", "toy-01", "toy-02"], displayed_ids=[])
        row = self.row(d.score(self.package, self.data))
        self.assertIn("relevant_removed_at_filter_stage", row["stage_evidence"]["observations"])
        self.assertIn("relevant_removed_at_display_stage", row["stage_evidence"]["observations"])

    def test_fused_recall_is_not_final_ranking_recall(self):
        self.ranked()["fused_ids"] = ["toy-04"]
        self.ranked()["displayed_ids"] = ["toy-01", "toy-02"]
        m = self.row(d.score(self.package, self.data))["metrics"]
        self.assertEqual(m["recall_at_20"], 0)
        self.assertEqual(m["ndcg_at_5"], 1)

    def test_recall_cutoff_boundary(self):
        rest = [fid for fid in self.package.index if fid not in {"toy-01", "toy-02"}]
        self.ranked()["fused_ids"] = rest[:19] + ["toy-01", "toy-02"]
        m = self.row(d.score(self.package, self.data))["metrics"]
        self.assertEqual(m["recall_at_20"], .5)

    def test_fifth_slot_boundary_and_ndcg_noanswer_undefined(self):
        self.ranked()["displayed_ids"] = ["toy-04", "toy-05", "toy-06", "toy-07", "toy-01", "toy-02"]
        r = d.score(self.package, self.data);m = self.row(r)["metrics"]
        self.assertEqual(m["precision_at_5"], .2)
        self.assertAlmostEqual(m["ndcg_at_5"], (7 / math.log2(6)) / (7 + 3 / math.log2(3)))
        self.assertNotIn("ndcg_at_5", self.row(r, "toy-plot-6")["metrics"])

    def test_reproducible_order_and_input_immutability(self):
        before = copy.deepcopy(self.data)
        r1 = d.score(self.package, self.data)
        data = copy.deepcopy(self.data);data["runs"].reverse()
        self.assertEqual(r1, d.score(self.package, data))
        self.assertEqual(before, self.data)
        self.assertEqual(r1, d.score(self.package, self.data))

    def test_bad_prefix_cannot_improve_discount_and_tail_does_not_change_top5(self):
        before = self.row(d.score(self.package, self.data))["metrics"]["ndcg_at_5"]
        self.ranked()["displayed_ids"].insert(0, "toy-04")
        after = self.row(d.score(self.package, self.data))["metrics"]["ndcg_at_5"]
        self.assertLess(after, before)
        self.ranked()["displayed_ids"] = ["toy-01", "toy-02", "toy-04", "toy-05", "toy-06"]
        a = self.row(d.score(self.package, self.data))["metrics"]
        self.ranked()["displayed_ids"].append("toy-07")
        self.assertEqual(a, self.row(d.score(self.package, self.data))["metrics"])

    def test_no_network_or_subprocess_and_template_not_run(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess")):
            template = d.bound_template(self.package)
            r = d.score(self.package, template)
            self.assertEqual(r["run_counts"], {"not_run": 24})
            self.assertIsNone(r["ranking"]["macro"])
            self.assertEqual(r["empty"]["measured"], 0)

    def test_freeze_register_preserves_intervals_without_human_claim(self):
        def change(a):a["queries"][0]["judgments"][1]["acceptable_grade_range_for_review"] = [1, 3]
        package = self.mutate_package("judging/answer-key.json", change)
        register = p.review_register(package)
        pair = next(r for r in register["pairs"] if r["query_id"] == "toy-plot-1" and r["film_id"] == "toy-01")
        self.assertEqual(pair["acceptable_grade_range_for_review"], [1, 3])
        self.assertEqual(pair["status"], "needs_human_review")
        self.assertFalse(register["human_adjudication"])
        self.assertEqual(register["label_changes"], [])

    def test_cli_json_summary_exit_and_input_protection(self):
        result_path = Path(self.temp.name) / "results.json";result_path.write_bytes(encoded(self.data))
        out = Path(self.temp.name) / "report.json";summary = Path(self.temp.name) / "report.txt"
        before = {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(d.main(["score", "--package", str(self.root), "--results", str(result_path), "--output", str(out), "--summary", str(summary)]), 0)
        self.assertIn("SIMULATED", summary.read_text())
        with redirect_stderr(io.StringIO()):
            self.assertEqual(d.main(["score", "--package", str(self.root), "--results", str(result_path), "--output", str(result_path)]), 2)
            self.assertEqual(d.main(["template", "--package", str(self.root), "--output", str(self.root / "oops")]), 2)
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
