"""契约草稿生成:suggest_contracts 与 scaffold CLI。"""

import json

import yaml

from agentinvariant.cli import main as cli_main
from agentinvariant.contracts import evaluate_contracts, ContractContext
from agentinvariant.contracts.scaffold import scaffold_from_report, suggest_contracts
from agentinvariant.tracing import TraceRecorder


def test_suggest_contracts_from_sequence():
    contracts = suggest_contracts(["check_permission", "execute_sql", "execute_sql"])
    by_type = {}
    for c in contracts:
        by_type.setdefault(c["type"], []).append(c)

    assert {c["tool"] for c in by_type["tool_called"]} == {"check_permission", "execute_sql"}
    occ = {c["tool"]: c["max"] for c in by_type["max_occurrences"]}
    assert occ == {"check_permission": 1, "execute_sql": 2}
    hb = by_type["happens_before"][0]
    assert (hb["before"], hb["after"]) == ("check_permission", "execute_sql")
    assert by_type["max_steps"][0]["max"] == 5  # 3 步 + 2 余量
    assert all(c["severity"] == "warning" for c in contracts)  # 草稿绝不自动成为硬规则


def test_suggested_contracts_are_valid_and_pass_on_own_trace():
    """草稿必须是合法规则,且对生成它的那次运行自身全部通过。"""
    recorder = TraceRecorder()
    for tool in ("check_permission", "execute_sql"):
        recorder.record(tool, {}, "mock")
    ctx = ContractContext(events=recorder.events, final_output="ok")

    checks = evaluate_contracts(suggest_contracts(recorder.tool_sequence), ctx)
    assert checks and all(c.passed for c in checks)


def test_scaffold_cli_writes_reviewed_draft(tmp_path):
    report = {
        "comparisons": [
            {"scenario_id": "s-1",
             "baseline": {"tool_sequence": ["a", "b"]},
             "candidate": {"tool_sequence": ["a"]}},
        ],
    }
    result_path = tmp_path / "report.json"
    result_path.write_text(json.dumps(report), encoding="utf-8")
    out_path = tmp_path / "draft.yaml"

    assert cli_main(["scaffold", "--result", str(result_path), "--out", str(out_path)]) == 0
    text = out_path.read_text(encoding="utf-8")
    assert text.startswith("# 契约草稿")

    draft = yaml.safe_load(text)
    assert draft["s-1"]["observed_tool_sequence"] == ["a", "b"]
    assert any(c["type"] == "happens_before" for c in draft["s-1"]["contracts"])

    # candidate 侧
    assert cli_main(["scaffold", "--result", str(result_path), "--out", str(out_path), "--side", "candidate"]) == 0
    draft = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert draft["s-1"]["observed_tool_sequence"] == ["a"]
