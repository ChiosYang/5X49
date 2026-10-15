"""Explicit, read-only review/CI verification before a targeted ledger release."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

from app.evaluation.ask_budget import BudgetLedger, BudgetStop

RELEASE_AUTHORIZATION = "I_AUTHORIZE_RECONCILED_REVIEW_HOLD_RELEASE"
REPOSITORY = "ChiosYang/5X49"


def verify_review_approval(approval, *, repo_root):
    reviewed = approval.get("reviewed_head")
    run_id = approval.get("ci_run_id")
    if (approval.get("version") != "ask-review-approval.v1" or approval.get("decision") != "approved"
            or not isinstance(reviewed, str) or re.fullmatch(r"[0-9a-f]{40}", reviewed) is None
            or type(run_id) is not int or run_id <= 0
            or not isinstance(approval.get("review_ref"), str)
            or re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", approval["review_ref"]) is None
            or not isinstance(approval.get("attempt_id"), str) or not approval["attempt_id"]
            or not isinstance(approval.get("reconciliation_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", approval["reconciliation_sha256"]) is None):
        raise BudgetStop("review_approval_evidence_invalid")

    def git(*args):
        return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=True).stdout.strip()

    try:
        current = git("rev-parse", "HEAD")
        if git("status", "--porcelain=v1"):
            raise BudgetStop("unreviewed_worktree_changes")
        git("merge-base", "--is-ancestor", reviewed, current)
        changed = git("diff", "--name-only", reviewed, current).splitlines()
        if any(not path.startswith("docs/") for path in changed):
            raise BudgetStop("unreviewed_code_changes")
    except subprocess.CalledProcessError:
        raise BudgetStop("reviewed_head_not_verified") from None
    source = f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}"
    try:
        request = urllib.request.Request(source, headers={"User-Agent": "5X49-evaluation-review", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            ci = json.load(response)
    except Exception:
        raise BudgetStop("review_ci_evidence_unavailable") from None
    if (ci.get("id") != run_id or ci.get("head_sha") != reviewed or ci.get("status") != "completed"
            or type(ci.get("run_attempt")) is not int or ci["run_attempt"] <= 0
            or ci.get("conclusion") != "success" or ci.get("repository", {}).get("full_name") != REPOSITORY
            or ci.get("path") != ".github/workflows/ci.yml"
            or ci.get("event") != "pull_request"
            or not any(pr.get("number") == 28 for pr in ci.get("pull_requests", []))):
        raise BudgetStop("review_ci_evidence_mismatch")
    if git("rev-parse", "HEAD") != current or git("status", "--porcelain=v1"):
        raise BudgetStop("worktree_changed_during_review_verification")
    return {"version": "ask-review-release.v1", "decision": "approved", "reviewed_head": reviewed,
            "current_head": current, "ci_head": ci["head_sha"], "ci_run_id": run_id,
            "ci_run_attempt": ci["run_attempt"],
            "ci_conclusion": "success", "ci_source": source, "review_ref": approval["review_ref"],
            "attempt_id": approval["attempt_id"], "reconciliation_sha256": approval["reconciliation_sha256"],
            "approval_sha256": hashlib.sha256(json.dumps(approval, sort_keys=True).encode()).hexdigest()}


def release_review_hold(approval_path: Path, *, authorization, ledger_path: Path, repo_root: Path):
    if authorization != RELEASE_AUTHORIZATION:
        raise BudgetStop("explicit_review_release_authorization_required")
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    evidence = verify_review_approval(approval, repo_root=repo_root)
    if not ledger_path.is_file():
        raise BudgetStop("historical_ledger_missing")
    ledger = BudgetLedger(ledger_path)
    applied = ledger.release_review(evidence["attempt_id"], reconciliation_sha256=evidence["reconciliation_sha256"], evidence=evidence)
    return {"version": "ask-review-release.v1", "evidence_class": "audited_review_hold_release",
            "applied": applied, "review_released": True, "paid_requests_in_run": 0,
            "strict_json_validated": False, "review_evidence": evidence, "ledger": ledger.summary()}
