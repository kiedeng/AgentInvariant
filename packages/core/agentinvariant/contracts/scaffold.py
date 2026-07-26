"""契约草稿生成:从一次运行报告推导每个场景的契约建议。

缓解设计基线 15.1 的首要产品风险 ——「用户可能不愿意编写行为契约」:
以 Baseline 的实际行为为底,生成确定性规则草稿,由人工确认后把关键规则
升级为 blocker。草稿默认全部 warning,绝不自动成为门禁硬规则。

生成规则:
- tool_called + max_occurrences:每个实际调用过的工具;
- happens_before:按各工具首次出现的先后顺序,相邻工具两两生成;
- max_steps:实际步数 + 2 的余量;
- output_contains:留空待人工填写(文本断言太脆,不自动生成)。
"""

from __future__ import annotations

from typing import Any


def suggest_contracts(tool_sequence: list[str], step_margin: int = 2) -> list[dict[str, Any]]:
    """根据一次运行的工具序列生成契约草稿(全部 warning)。"""
    suggestions: list[dict[str, Any]] = []

    first_seen: list[str] = []
    counts: dict[str, int] = {}
    for tool in tool_sequence:
        counts[tool] = counts.get(tool, 0) + 1
        if tool not in first_seen:
            first_seen.append(tool)

    for tool in first_seen:
        suggestions.append({"type": "tool_called", "tool": tool, "severity": "warning"})
        suggestions.append({"type": "max_occurrences", "tool": tool, "max": counts[tool], "severity": "warning"})

    for before, after in zip(first_seen, first_seen[1:]):
        suggestions.append({"type": "happens_before", "before": before, "after": after, "severity": "warning"})

    suggestions.append({"type": "max_steps", "max": len(tool_sequence) + step_margin, "severity": "warning"})
    return suggestions


def scaffold_from_report(report: dict[str, Any], side: str = "baseline") -> dict[str, Any]:
    """对报告中的每个场景生成契约草稿。

    返回 {scenario_id: {"observed_tool_sequence": [...], "contracts": [...]}}。
    """
    if side not in ("baseline", "candidate"):
        raise ValueError(f"side 必须是 baseline 或 candidate,得到 {side!r}")
    draft: dict[str, Any] = {}
    for comparison in report["comparisons"]:
        run = comparison[side]
        draft[comparison["scenario_id"]] = {
            "observed_tool_sequence": run["tool_sequence"],
            "contracts": suggest_contracts(run["tool_sequence"]),
        }
    return draft


DRAFT_HEADER = """\
# 契约草稿:由 agentinvariant scaffold 从 {side} 实际行为生成。
# 全部规则默认 severity: warning —— 请人工审查后:
#   1. 删除不代表业务意图的规则;
#   2. 把必须守住的规则升级为 severity: blocker;
#   3. 补充 output_contains / state_constraint 等结果契约。
"""
