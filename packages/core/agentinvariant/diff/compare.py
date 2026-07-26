"""Behavior Diff:比较 Baseline 与 Candidate 在同一场景下的运行。

分类规则是设计文档 9.3 场景级判定算法的实现(成功与否由 Contract Engine
的 blocker 规则判定,状态由 StateProvider 快照):

  REGRESSION       基线成功而候选失败
  IMPROVEMENT      基线失败而候选成功
  NEUTRAL_CHANGE   两边均成功,仅路径 / 非关键输出变化
  NO_CHANGE        行为一致
  REVIEW_REQUIRED  其余情况(如两边均失败但方式不同)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..tracing.recorder import TraceRecorder


@dataclass
class RunResult:
    version: str
    final_output: str
    recorder: TraceRecorder
    success: bool
    contracts: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float | None = None
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    repetitions: int = 1
    pass_rate: float = 1.0
    timed_out: bool = False
    error: str | None = None  # Agent 运行时异常(已捕获为失败运行)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "success": self.success,
            "final_output": self.final_output,
            "duration_ms": round(self.duration_ms, 1) if self.duration_ms is not None else None,
            "timed_out": self.timed_out,
            "error": self.error,
            "repetitions": self.repetitions,
            "pass_rate": self.pass_rate,
            "tool_sequence": self.recorder.tool_sequence,
            "violations": self.recorder.violations,
            "contracts": self.contracts,
            "state_after": self.state_after,
            "trace": self.recorder.to_dict(),
        }


def _state_diff(baseline: RunResult, candidate: RunResult) -> list[str]:
    if baseline.state_after is None or candidate.state_after is None:
        return []
    keys = set(baseline.state_after) | set(candidate.state_after)
    return sorted(
        k for k in keys
        if baseline.state_after.get(k) != candidate.state_after.get(k)
    )


def compare_runs(scenario_id: str, baseline: RunResult, candidate: RunResult) -> dict[str, Any]:
    base_seq = baseline.recorder.tool_sequence
    cand_seq = candidate.recorder.tool_sequence
    state_changed_keys = _state_diff(baseline, candidate)

    if baseline.success and not candidate.success:
        outcome = "REGRESSION"
    elif not baseline.success and candidate.success:
        outcome = "IMPROVEMENT"
    elif baseline.success and candidate.success:
        identical = (
            base_seq == cand_seq
            and baseline.final_output == candidate.final_output
            and not state_changed_keys
        )
        outcome = "NO_CHANGE" if identical else "NEUTRAL_CHANGE"
    else:
        outcome = "REVIEW_REQUIRED"

    return {
        "scenario_id": scenario_id,
        "outcome": outcome,
        "baseline": baseline.to_dict(),
        "candidate": candidate.to_dict(),
        "diff": {
            "tools_added": [t for t in cand_seq if t not in base_seq],
            "tools_removed": [t for t in base_seq if t not in cand_seq],
            "output_changed": baseline.final_output != candidate.final_output,
            "state_changed_keys": state_changed_keys,
            "new_violations": [
                v for v in candidate.recorder.violations
                if v["violation"] not in {b["violation"] for b in baseline.recorder.violations}
            ],
        },
    }
