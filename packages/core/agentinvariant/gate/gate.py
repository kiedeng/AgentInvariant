"""Release Gate:把 Behavior Diff 报告变成机器可执行的发布决策。

输入:compare 产出的报告 dict + YAML 阈值配置。
输出:结构化 GateResult;CLI 层据此返回退出码(0 放行 / 1 阻断),
供 GitHub Actions / Jenkins 直接消费(设计基线 7.7)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class GateConfig(BaseModel):
    max_new_regressions: int = 0
    max_review_required: int | None = None
    min_candidate_success_rate: float = 0.0
    # 候选版本运行中允许的策略违规(blocked 尝试 / 守卫拦截)上限;None 表示不限制
    max_candidate_violations: int | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GateConfig":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(data.get("release_gate", data))


def evaluate_gate(report: dict[str, Any], config: GateConfig) -> dict[str, Any]:
    comparisons = report["comparisons"]
    summary = report["summary"]

    regressions = summary.get("REGRESSION", 0)
    review_required = summary.get("REVIEW_REQUIRED", 0)
    candidate_successes = sum(1 for c in comparisons if c["candidate"]["success"])
    success_rate = candidate_successes / len(comparisons) if comparisons else 1.0
    candidate_violations = sum(len(c["candidate"]["violations"]) for c in comparisons)

    reasons: list[str] = []
    if regressions > config.max_new_regressions:
        failing = [c["scenario_id"] for c in comparisons if c["outcome"] == "REGRESSION"]
        reasons.append(f"新增回归 {regressions} 个(允许 {config.max_new_regressions}): {failing}")
    if config.max_review_required is not None and review_required > config.max_review_required:
        reasons.append(f"待人工确认场景 {review_required} 个(允许 {config.max_review_required})")
    if success_rate < config.min_candidate_success_rate:
        reasons.append(f"候选成功率 {success_rate:.0%} 低于阈值 {config.min_candidate_success_rate:.0%}")
    if config.max_candidate_violations is not None and candidate_violations > config.max_candidate_violations:
        reasons.append(f"候选版本策略违规 {candidate_violations} 次(允许 {config.max_candidate_violations})")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "metrics": {
            "regressions": regressions,
            "review_required": review_required,
            "candidate_success_rate": round(success_rate, 4),
            "candidate_violations": candidate_violations,
            "scenario_count": len(comparisons),
        },
    }
