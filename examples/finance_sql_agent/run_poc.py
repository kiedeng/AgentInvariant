"""POC 端到端流程:record -> compare(含契约)-> report(JSON/JUnit/HTML)-> gate。

用法:
    python -m examples.finance_sql_agent.run_poc
    # 退出码即门禁结论:0 允许发布,1 阻止发布

阶段 A(record):用 V1 在模拟测试环境 live 运行,录制 execute_sql Fixture。
阶段 B(compare):V1/V2 在 execute_sql=replay、send_email=blocked、
check_permission=live 的策略下运行同一批场景;每次运行用 Contract Engine
判定成败,再做 Behavior Diff 分类。
全程 send_email 永不真实执行(EXTERNAL_COMMUNICATION 默认阻断)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agentinvariant.contracts import ContractContext, blocker_failed, evaluate_contracts
from agentinvariant.contracts.matchers import sql_readonly
from agentinvariant.diff import RunResult, compare_runs
from agentinvariant.fixtures import FixtureStore
from agentinvariant.gate import GateConfig, evaluate_gate
from agentinvariant.reports import write_html, write_junit
from agentinvariant.runtime import ExecutionMode, ToolEffect, ToolPolicy, virtualize
from agentinvariant.tracing import TraceRecorder

from .agents import build_agent_v1, build_agent_v2, run_agent
from .scenarios import SCENARIOS
from .tools import ALL_TOOLS, SENT_EMAILS

OUT_DIR = Path(".agentinvariant")
FIXTURE_PATH = OUT_DIR / "fixtures" / "finance_sql_agent.json"
GATE_CONFIG = Path(__file__).parent / "gate.yaml"


def _policies(execute_sql_mode: ExecutionMode) -> dict[str, ToolPolicy]:
    return {
        "check_permission": ToolPolicy(mode=ExecutionMode.LIVE, effect=ToolEffect.READ_ONLY),
        "execute_sql": ToolPolicy(
            mode=execute_sql_mode,
            effect=ToolEffect.WRITE_REVERSIBLE,
            argument_guard=sql_readonly,  # 与契约同源的不变量,执行前阻断
        ),
        "send_email": ToolPolicy(mode=ExecutionMode.BLOCKED, effect=ToolEffect.EXTERNAL_COMMUNICATION),
    }


def _run_version(builder, version: str, scenario: dict, mode: ExecutionMode, store: FixtureStore) -> RunResult:
    recorder = TraceRecorder()
    tools = virtualize(ALL_TOOLS, _policies(mode), recorder, store)
    agent = builder(tools)
    output = run_agent(agent, scenario)

    checks = evaluate_contracts(scenario["contracts"], ContractContext(recorder.events, output))
    return RunResult(
        version=version,
        final_output=output,
        recorder=recorder,
        success=not blocker_failed(checks),
        contracts=[c.to_dict() for c in checks],
    )


def main() -> tuple[dict, dict]:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.unlink(missing_ok=True)
    store = FixtureStore(FIXTURE_PATH)

    print("== 阶段 A:record(V1 live 运行,录制 execute_sql Fixture)==")
    for scenario in SCENARIOS:
        _run_version(build_agent_v1, "v1-record", scenario, ExecutionMode.RECORD, store)
    print(f"已录制 {len(store)} 条 Fixture -> {FIXTURE_PATH}\n")

    print("== 阶段 B:compare(execute_sql=replay, send_email=blocked, 契约判定)==")
    comparisons = []
    for scenario in SCENARIOS:
        baseline = _run_version(build_agent_v1, "v1", scenario, ExecutionMode.REPLAY, store)
        candidate = _run_version(build_agent_v2, "v2", scenario, ExecutionMode.REPLAY, store)
        comparisons.append(compare_runs(scenario["id"], baseline, candidate))

    report = {
        "baseline": "finance-agent v1 (无权限节点)",
        "candidate": "finance-agent v2 (新增权限节点)",
        "summary": {
            outcome: sum(1 for c in comparisons if c["outcome"] == outcome)
            for outcome in ("REGRESSION", "IMPROVEMENT", "NEUTRAL_CHANGE", "NO_CHANGE", "REVIEW_REQUIRED")
        },
        "real_emails_sent": len(SENT_EMAILS),
        "comparisons": comparisons,
    }

    gate_result = evaluate_gate(report, GateConfig.from_yaml(GATE_CONFIG))

    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    junit_path = write_junit(report, OUT_DIR / "junit.xml")
    html_path = write_html(report, gate_result, OUT_DIR / "report.html")

    for c in comparisons:
        print(f"  {c['scenario_id']}  {c['outcome']:<15}"
              f" baseline={'OK ' if c['baseline']['success'] else 'FAIL'}"
              f" candidate={'OK ' if c['candidate']['success'] else 'FAIL'}"
              f" 工具序列 {c['baseline']['tool_sequence']} -> {c['candidate']['tool_sequence']}")
    print(f"\n汇总: {report['summary']}")
    print(f"真实发出的邮件数: {report['real_emails_sent']} (必须为 0)")
    print(f"报告: {report_path} | {junit_path} | {html_path}")
    print(f"Release Gate: {'PASS 允许发布' if gate_result['passed'] else 'FAIL 阻止发布'}")
    for reason in gate_result["reasons"]:
        print(f"  - {reason}")
    return report, gate_result


if __name__ == "__main__":
    _, gate_result = main()
    sys.exit(0 if gate_result["passed"] else 1)
