"""Contract Engine 内置规则的确定性验证。"""

import pytest

from agentinvariant.contracts import ContractContext, blocker_failed, evaluate_contracts, parse_rule
from agentinvariant.tracing import TraceRecorder


def ctx_with(calls: list[tuple[str, dict]], output: str = "", results: dict | None = None) -> ContractContext:
    recorder = TraceRecorder()
    for tool, args in calls:
        event = recorder.record(tool, args, "mock")
        if results and tool in results:
            event.result = results[tool]
    return ContractContext(recorder.events, output)


def check(spec: dict, ctx: ContractContext) -> bool:
    return parse_rule(spec).evaluate(ctx).passed


def test_tool_called_and_not_called():
    ctx = ctx_with([("check_permission", {})])
    assert check({"type": "tool_called", "tool": "check_permission"}, ctx)
    assert not check({"type": "tool_called", "tool": "execute_sql"}, ctx)
    assert check({"type": "tool_not_called", "tool": "execute_sql"}, ctx)
    assert not check({"type": "tool_not_called", "tool": "check_permission"}, ctx)


def test_happens_before():
    spec = {"type": "happens_before", "before": "check_permission", "after": "execute_sql"}
    assert check(spec, ctx_with([("check_permission", {}), ("execute_sql", {})]))
    assert not check(spec, ctx_with([("execute_sql", {}), ("check_permission", {})]))
    # after 从未发生时空洞通过
    assert check(spec, ctx_with([("check_permission", {})]))


def test_max_occurrences_and_max_steps():
    ctx = ctx_with([("send_email", {}), ("send_email", {})])
    assert not check({"type": "max_occurrences", "tool": "send_email", "max": 1}, ctx)
    assert check({"type": "max_occurrences", "tool": "send_email", "max": 2}, ctx)
    assert not check({"type": "max_steps", "max": 1}, ctx)
    assert check({"type": "max_steps", "max": 2}, ctx)


def test_argument_constraint_sql_readonly():
    spec = {"type": "argument_constraint", "tool": "execute_sql", "matcher": "sql_readonly"}
    assert check(spec, ctx_with([("execute_sql", {"sql": "SELECT 1"})]))
    assert not check(spec, ctx_with([("execute_sql", {"sql": "UPDATE t SET a=1"})]))


def test_result_constraint_reads_last_result():
    ctx = ctx_with([("check_permission", {})], results={"check_permission": '{"allowed": true}'})
    assert check({"type": "result_constraint", "tool": "check_permission", "field": "allowed", "equals": True}, ctx)
    assert not check({"type": "result_constraint", "tool": "check_permission", "field": "allowed", "equals": False}, ctx)
    # 无结果时判失败而不是异常
    assert not check({"type": "result_constraint", "tool": "execute_sql", "field": "x", "equals": 1}, ctx)


def test_output_contains_and_not_contains():
    ctx = ctx_with([], output="审批通过率为 82%")
    assert check({"type": "output_contains", "value": "审批通过率"}, ctx)
    assert not check({"type": "output_contains", "value": "无权"}, ctx)
    assert check({"type": "output_not_contains", "value": "无权"}, ctx)


def test_no_policy_violation():
    recorder = TraceRecorder()
    event = recorder.record("send_email", {}, "blocked")
    event.violation = "tool blocked by policy"
    ctx = ContractContext(recorder.events, "")
    assert not check({"type": "no_policy_violation"}, ctx)
    assert check({"type": "no_policy_violation"}, ctx_with([]))


def test_severity_controls_blocker_failed():
    ctx = ctx_with([], output="")
    checks = evaluate_contracts(
        [
            {"type": "output_contains", "value": "缺失", "severity": "warning"},
        ],
        ctx,
    )
    assert not checks[0].passed
    assert not blocker_failed(checks)  # warning 失败不判运行失败


def test_unknown_rule_type_raises():
    with pytest.raises(ValueError, match="未知契约规则类型"):
        parse_rule({"type": "does_not_exist"})
