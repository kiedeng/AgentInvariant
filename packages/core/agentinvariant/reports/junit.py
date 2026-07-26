"""JUnit XML 报告:每个场景一个 testcase,REGRESSION 记为 failure。

让 GitHub Actions / Jenkins / GitLab CI 的测试面板直接展示回归场景。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

FAILING_OUTCOMES = {"REGRESSION"}


def write_junit(report: dict[str, Any], path: str | Path) -> Path:
    comparisons = report["comparisons"]
    failures = sum(1 for c in comparisons if c["outcome"] in FAILING_OUTCOMES)

    suite = ET.Element(
        "testsuite",
        name="agentinvariant.behavior-diff",
        tests=str(len(comparisons)),
        failures=str(failures),
        errors="0",
    )
    for c in comparisons:
        case = ET.SubElement(suite, "testcase", classname=report.get("candidate", "candidate"),
                             name=f"{c['scenario_id']} [{c['outcome']}]")
        if c["outcome"] in FAILING_OUTCOMES:
            failed_contracts = [
                chk for chk in c["candidate"].get("contracts", [])
                if not chk["passed"] and chk["severity"] == "blocker"
            ]
            detail = "; ".join(f"{chk['description']}: {chk['detail']}" for chk in failed_contracts) \
                or f"候选输出: {c['candidate']['final_output']}"
            failure = ET.SubElement(case, "failure", message=f"{c['scenario_id']} 出现行为回归")
            failure.text = detail

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path
