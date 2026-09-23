"""
Runs the full improvement loop end-to-end:
  1. Reset policies.json to baseline (v1) -- so this script is repeatable.
  2. Run the eval suite -> results/baseline.json
  3. Feed failures into the improvement step -> policies.json bumped to v2+
  4. Re-run the same eval suite -> results/after.json
  5. Print a before/after diff, explicitly flagging any regression.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
POLICIES_PATH = ROOT / "data" / "policies.json"

BASELINE_POLICIES = {
    "version": 1,
    "rules": [
        "Always greet the patient and state you are a scheduling assistant, not a clinician.",
        "Never invent or guess appointment slots, patient records, or appointment IDs. Only state facts returned by a tool call."
    ],
    "changelog": [{"version": 1, "change": "Initial baseline policy set."}]
}


def main(mode="mock"):
    sys.path.insert(0, str(ROOT))
    from src.eval.runner import run_all
    from src.improve import apply_fixes_for_failures
    from src.eval.report import compare

    print("=== Step 1: reset to baseline policy ===")
    POLICIES_PATH.write_text(json.dumps(BASELINE_POLICIES, indent=2))

    print("\n=== Step 2: baseline eval run ===")
    baseline = run_all(mode, ROOT / "results" / "baseline.json")
    print(f"Baseline overall score: {baseline['overall_score']}  pass rate: {baseline['pass_rate']}%")
    for r in baseline["results"]:
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['scenario_id']:<28} {r['score']}/{r['max']}")

    failed = [r["scenario_id"] for r in baseline["results"] if not r["passed"]]
    print(f"\n=== Step 3: generate + apply improvement for failures {failed} ===")
    applied, skipped = apply_fixes_for_failures(failed)
    for a in applied:
        print(f"  + [{a['scenario']}] added rule: {a['rule']}")
    for s in skipped:
        print(f"  = [{s['scenario']}] not a prompt fix ({s['reason']}) -- already enforced elsewhere")

    print("\n=== Step 4: re-run eval with updated policy ===")
    after = run_all(mode, ROOT / "results" / "after.json")
    print(f"After overall score: {after['overall_score']}  pass rate: {after['pass_rate']}%")

    print("\n=== Step 5: before/after diff ===")
    compare(ROOT / "results" / "baseline.json", ROOT / "results" / "after.json")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "mock"
    main(mode)
