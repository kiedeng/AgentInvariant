"""Release Gate 阈值判定与 CLI 退出码。"""

import json

from agentinvariant.cli import main as cli_main
from agentinvariant.gate import GateConfig, evaluate_gate


def make_report(outcomes: list[str], candidate_success: list[bool]) -> dict:
    return {
        "baseline": "v1",
        "candidate": "v2",
        "summary": {o: outcomes.count(o) for o in set(outcomes)},
        "comparisons": [
            {
                "scenario_id": f"s-{i}",
                "outcome": outcome,
                "baseline": {"success": True, "violations": []},
                "candidate": {"success": ok, "violations": []},
            }
            for i, (outcome, ok) in enumerate(zip(outcomes, candidate_success))
        ],
    }


def test_gate_blocks_on_regression():
    report = make_report(["REGRESSION", "NO_CHANGE"], [False, True])
    result = evaluate_gate(report, GateConfig(max_new_regressions=0))
    assert not result["passed"]
    assert "s-0" in result["reasons"][0]


def test_gate_passes_within_thresholds():
    report = make_report(["NO_CHANGE", "IMPROVEMENT"], [True, True])
    result = evaluate_gate(report, GateConfig(max_new_regressions=0, min_candidate_success_rate=0.95))
    assert result["passed"] and result["reasons"] == []


def test_gate_blocks_on_low_success_rate():
    report = make_report(["NO_CHANGE", "REVIEW_REQUIRED"], [True, False])
    result = evaluate_gate(report, GateConfig(min_candidate_success_rate=0.9))
    assert not result["passed"]


def test_cli_gate_exit_codes(tmp_path):
    report = make_report(["NO_CHANGE"], [True])
    result_path = tmp_path / "report.json"
    result_path.write_text(json.dumps(report), encoding="utf-8")
    config_path = tmp_path / "gate.yaml"
    config_path.write_text("release_gate:\n  max_new_regressions: 0\n", encoding="utf-8")

    assert cli_main(["gate", "--result", str(result_path), "--config", str(config_path)]) == 0

    bad_report = make_report(["REGRESSION"], [False])
    result_path.write_text(json.dumps(bad_report), encoding="utf-8")
    assert cli_main(["gate", "--result", str(result_path), "--config", str(config_path)]) == 1

    assert cli_main(["gate", "--result", str(tmp_path / "nope.json"), "--config", str(config_path)]) == 2
