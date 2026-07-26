"""Contract Engine:确定性行为契约规则(设计基线 7.5 的 MVP 子集)。

10 个内置规则类型,均为纯确定性检查(无 LLM 评分):

  tool_called / tool_not_called   工具必须 / 不得被调用(含被阻断的尝试)
  happens_before                  after 的每次调用前必须已发生 before
  max_occurrences                 工具调用次数上限
  argument_constraint             参数满足命名匹配器(如 sql_readonly)
  result_constraint               工具最后一次结果的字段值约束
  output_contains / output_not_contains  最终回答文本约束
  no_policy_violation             运行中不得出现策略 / 守卫违规
  max_steps                       预算:工具调用总步数上限

severity: blocker(失败即运行失败)/ warning(仅记录证据)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ..tracing.recorder import ToolCallEvent
from .matchers import get_matcher


@dataclass
class ContractContext:
    events: list[ToolCallEvent]
    final_output: str
    duration_ms: float | None = None
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None

    def calls_of(self, tool: str) -> list[ToolCallEvent]:
        return [e for e in self.events if e.tool == tool]


class ContractCheck(BaseModel):
    rule: str
    description: str
    severity: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _result_as_dict(event: ToolCallEvent) -> dict[str, Any]:
    result = event.result
    if isinstance(result, dict):
        return result
    try:
        decoded = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return {}
    # 工具结果可能是合法 JSON 但不是对象(数组/字符串/数字/null):
    # 按字段断言一律判失败而不是抛 AttributeError
    return decoded if isinstance(decoded, dict) else {}


class Rule(BaseModel):
    type: str
    severity: str = "blocker"

    def evaluate(self, ctx: ContractContext) -> ContractCheck:  # pragma: no cover
        raise NotImplementedError

    def _check(self, passed: bool, description: str, detail: str = "") -> ContractCheck:
        return ContractCheck(
            rule=self.type, description=description, severity=self.severity,
            passed=passed, detail=detail,
        )


class ToolCalled(Rule):
    type: str = "tool_called"
    tool: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        calls = ctx.calls_of(self.tool)
        return self._check(bool(calls), f"必须调用 {self.tool}", f"实际调用 {len(calls)} 次")


class ToolNotCalled(Rule):
    type: str = "tool_not_called"
    tool: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        calls = ctx.calls_of(self.tool)
        return self._check(not calls, f"不得调用 {self.tool}", f"实际调用 {len(calls)} 次")


class HappensBefore(Rule):
    type: str = "happens_before"
    before: str
    after: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        desc = f"{self.after} 之前必须已调用 {self.before}"
        before_indexes = [e.index for e in ctx.calls_of(self.before)]
        for event in ctx.calls_of(self.after):
            if not any(i < event.index for i in before_indexes):
                return self._check(False, desc, f"第 {event.index} 步调用 {self.after} 时 {self.before} 尚未发生")
        return self._check(True, desc)


class MaxOccurrences(Rule):
    type: str = "max_occurrences"
    tool: str
    max: int

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        count = len(ctx.calls_of(self.tool))
        return self._check(count <= self.max, f"{self.tool} 最多调用 {self.max} 次", f"实际 {count} 次")


class ArgumentConstraint(Rule):
    type: str = "argument_constraint"
    tool: str
    matcher: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        fn = get_matcher(self.matcher)
        desc = f"{self.tool} 参数须满足 {self.matcher}"
        for event in ctx.calls_of(self.tool):
            reason = fn(event.args)
            if reason:
                return self._check(False, desc, f"第 {event.index} 步违规: {reason}, args={event.args}")
        return self._check(True, desc)


class ResultConstraint(Rule):
    type: str = "result_constraint"
    tool: str
    field: str
    equals: Any

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        desc = f"{self.tool} 最后一次结果 {self.field} == {self.equals!r}"
        calls = [e for e in ctx.calls_of(self.tool) if e.result is not None]
        if not calls:
            return self._check(False, desc, f"{self.tool} 无成功结果")
        actual = _result_as_dict(calls[-1]).get(self.field)
        return self._check(actual == self.equals, desc, f"实际值 {actual!r}")


class OutputContains(Rule):
    type: str = "output_contains"
    value: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        return self._check(self.value in ctx.final_output, f"最终回答包含 {self.value!r}",
                           f"实际回答: {ctx.final_output[:80]}")


class OutputNotContains(Rule):
    type: str = "output_not_contains"
    value: str

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        return self._check(self.value not in ctx.final_output, f"最终回答不含 {self.value!r}",
                           f"实际回答: {ctx.final_output[:80]}")


class NoPolicyViolation(Rule):
    type: str = "no_policy_violation"

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        violations = [e for e in ctx.events if e.violation]
        return self._check(not violations, "运行中不得出现策略违规",
                           "; ".join(f"{e.tool}: {e.violation}" for e in violations))


class MaxSteps(Rule):
    type: str = "max_steps"
    max: int

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        return self._check(len(ctx.events) <= self.max, f"工具调用总步数不超过 {self.max}",
                           f"实际 {len(ctx.events)} 步")


class MaxLatencyMs(Rule):
    type: str = "max_latency_ms"
    max: float

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        desc = f"运行耗时不超过 {self.max}ms"
        if ctx.duration_ms is None:
            return self._check(False, desc, "运行未记录耗时(可能超时被中断)")
        return self._check(ctx.duration_ms <= self.max, desc, f"实际 {ctx.duration_ms:.0f}ms")


class StateConstraint(Rule):
    """运行后的业务状态字段断言,如 approval_rates.0.rate == 0.82。"""

    type: str = "state_constraint"
    field: str
    equals: Any

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        from ..state.provider import state_get

        desc = f"运行后状态 {self.field} == {self.equals!r}"
        if ctx.state_after is None:
            return self._check(False, desc, "未配置 StateProvider,无法取状态快照")
        actual = state_get(ctx.state_after, self.field)
        return self._check(actual == self.equals, desc, f"实际值 {actual!r}")


class StateUnchanged(Rule):
    """运行前后业务状态必须一致(只读场景的强断言)。"""

    type: str = "state_unchanged"

    def evaluate(self, ctx: ContractContext) -> ContractCheck:
        desc = "运行前后业务状态一致"
        if ctx.state_before is None or ctx.state_after is None:
            return self._check(False, desc, "未配置 StateProvider,无法取状态快照")
        # 取两侧键的并集:整个状态集合被删除同样是状态变化
        keys = set(ctx.state_before) | set(ctx.state_after)
        changed = sorted(k for k in keys if ctx.state_before.get(k) != ctx.state_after.get(k))
        return self._check(not changed, desc, f"发生变化的状态键: {changed}" if changed else "")


_RULE_TYPES: dict[str, type[Rule]] = {
    cls.model_fields["type"].default: cls
    for cls in (
        ToolCalled, ToolNotCalled, HappensBefore, MaxOccurrences, ArgumentConstraint,
        ResultConstraint, OutputContains, OutputNotContains, NoPolicyViolation, MaxSteps,
        MaxLatencyMs, StateConstraint, StateUnchanged,
    )
}


def parse_rule(spec: dict[str, Any]) -> Rule:
    rule_type = spec.get("type")
    if rule_type not in _RULE_TYPES:
        raise ValueError(f"未知契约规则类型: {rule_type},可用: {sorted(_RULE_TYPES)}")
    return _RULE_TYPES[rule_type].model_validate(spec)


def evaluate_contracts(specs: list[dict[str, Any]], ctx: ContractContext) -> list[ContractCheck]:
    return [parse_rule(spec).evaluate(ctx) for spec in specs]


def blocker_failed(checks: list[ContractCheck]) -> bool:
    return any(not c.passed and c.severity == "blocker" for c in checks)
