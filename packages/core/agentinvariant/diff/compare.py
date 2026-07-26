"""朴素 Behavior Diff:比较 Baseline 与 Candidate 在同一场景下的运行。

分类规则是设计文档 9.3 场景级判定算法的最小子集(无 Contract Engine 时,
以场景声明的成功判据 + 阻断违规近似):

  REGRESSION       基线成功而候选失败
  IMPROVEMENT      基线失败而候选成功
  NEUTRAL_CHANGE   两边均成功,仅路径 / 非关键输出变化
  NO_CHANGE        行为一致
  REVIEW_REQUIRED  其余情况(如两边均失败但方式不同)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..tracing.recorder import TraceRecorder


@dataclass
class RunResult:
    version: str
    final_output: str
    recorder: TraceRecorder
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "success": self.success,
            "final_output": self.final_output,
            "tool_sequence": self.recorder.tool_sequence,
            "violations": self.recorder.violations,
            "trace": self.recorder.to_dict(),
        }


def compare_runs(scenario_id: str, baseline: RunResult, candidate: RunResult) -> dict[str, Any]:
    base_seq = baseline.recorder.tool_sequence
    cand_seq = candidate.recorder.tool_sequence

    if baseline.success and not candidate.success:
        outcome = "REGRESSION"
    elif not baseline.success and candidate.success:
        outcome = "IMPROVEMENT"
    elif baseline.success and candidate.success:
        outcome = "NO_CHANGE" if base_seq == cand_seq and baseline.final_output == candidate.final_output else "NEUTRAL_CHANGE"
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
            "new_violations": [
                v for v in candidate.recorder.violations
                if v["violation"] not in {b["violation"] for b in baseline.recorder.violations}
            ],
        },
    }
