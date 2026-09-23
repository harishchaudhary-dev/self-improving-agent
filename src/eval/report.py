import json
import sys
from pathlib import Path


def compare(before_path, after_path):
    before = json.loads(Path(before_path).read_text())
    after = json.loads(Path(after_path).read_text())
    b_by_id = {r["scenario_id"]: r for r in before["results"]}
    a_by_id = {r["scenario_id"]: r for r in after["results"]}

    print(f"{'Scenario':<28} {'Before':>8} {'After':>8} {'Delta':>8}  Status")
    print("-" * 70)
    regressions = []
    improvements = []
    for sid in b_by_id:
        b, a = b_by_id[sid], a_by_id.get(sid)
        if not a:
            continue
        delta = a["score"] - b["score"]
        status = ""
        if delta < 0:
            status = "REGRESSION"
            regressions.append(sid)
        elif delta > 0:
            status = "improved"
            improvements.append(sid)
        else:
            status = "unchanged"
        print(f"{sid:<28} {b['score']:>8} {a['score']:>8} {delta:>+8.1f}  {status}")

    print("-" * 70)
    print(f"Overall: {before['overall_score']} -> {after['overall_score']} "
          f"({after['overall_score'] - before['overall_score']:+.1f})")
    print(f"Pass rate: {before['pass_rate']}% -> {after['pass_rate']}%")
    print(f"Policy version: {before['policy_version']} -> {after['policy_version']}")

    if regressions:
        print(f"\n⚠️  REGRESSIONS DETECTED in: {regressions} -- loop should NOT be considered closed cleanly.")
    else:
        print(f"\n✅ No regressions. Improved: {improvements or 'none (already passing)'}")
    return {"regressions": regressions, "improvements": improvements}


if __name__ == "__main__":
    compare(sys.argv[1], sys.argv[2])
