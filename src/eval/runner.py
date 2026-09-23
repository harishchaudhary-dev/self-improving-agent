import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent import Agent, MockBackend, load_policies
from src.tools import ClinicDB
from src.eval.scenarios import SCENARIOS
from src.eval.judge import score_scenario


def make_backend(mode):
    if mode == "real":
        from src.agent import AnthropicBackend
        return AnthropicBackend()
    return MockBackend()


def run_scenario(scenario, backend):
    db = ClinicDB()
    agent = Agent(backend=backend, db=db)
    tool_log_all = []
    for turn in scenario["turns"]:
        _, tool_log = agent.user_turn(turn)
        tool_log_all.append(tool_log)
    result = score_scenario(scenario, agent.transcript, tool_log_all)
    result["transcript"] = [t.to_dict() for t in agent.transcript]
    return result


def run_all(mode="mock", out_path=None):
    backend = make_backend(mode)
    results = [run_scenario(s, backend) for s in SCENARIOS]
    summary = {
        "policy_version": load_policies()["version"],
        "mode": mode,
        "overall_score": round(sum(r["score"] for r in results) / sum(r["max"] for r in results) * 100, 1),
        "pass_rate": round(100 * sum(r["passed"] for r in results) / len(results), 1),
        "results": results,
    }
    if out_path:
        Path(out_path).write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--out", default="results/run.json")
    args = ap.parse_args()
    summary = run_all(args.mode, args.out)
    print(f"Overall score: {summary['overall_score']}  Pass rate: {summary['pass_rate']}%  "
          f"(policy v{summary['policy_version']})")
    for r in summary["results"]:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{flag}] {r['scenario_id']:<28} {r['score']}/{r['max']}")
        if not r["passed"]:
            for reason in r["reasons"]:
                print(f"         - {reason}")
