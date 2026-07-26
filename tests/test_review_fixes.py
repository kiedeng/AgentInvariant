"""PR #1 审查意见的回归测试(Codex review 指出的缺陷)。"""

import textwrap

from agentinvariant.cli import main as cli_main
from agentinvariant.contracts import ContractContext, parse_rule
from agentinvariant.tracing import TraceRecorder

from tests._entrypoints import reset_provider
from tests.test_runner import LEGAL_QUERY, make_project

from agentinvariant.runner import ExperimentRunner


def test_result_constraint_non_object_json_fails_instead_of_crashing():
    """工具结果是合法 JSON 但不是对象(数组/字符串/数字/null)时判失败。"""
    rule = parse_rule({"type": "result_constraint", "tool": "t", "field": "x", "equals": 1})
    for raw in ('[1, 2]', '"text"', "42", "null"):
        recorder = TraceRecorder()
        recorder.record("t", {}, "mock").result = raw
        check = rule.evaluate(ContractContext(events=recorder.events, final_output=""))
        assert not check.passed, raw  # 不抛 AttributeError


def test_state_unchanged_detects_removed_key():
    before = {"orders": [{"id": 1}], "audit_log": [{"id": 9}]}
    after = {"orders": [{"id": 1}]}  # audit_log 整个被删除
    rule = parse_rule({"type": "state_unchanged"})
    check = rule.evaluate(ContractContext(events=[], final_output="",
                                          state_before=before, state_after=after))
    assert not check.passed and "audit_log" in check.detail


def test_agent_exception_becomes_failed_run_not_crash(tmp_path):
    """候选版本运行时异常应成为 REGRESSION 进入门禁,而不是中断整个比较。"""
    config = make_project(tmp_path, LEGAL_QUERY)
    config = config.model_copy(update={
        "candidate": config.candidate.model_copy(update={"entrypoint": "tests._entrypoints:raise_boom"}),
    })
    runner = ExperimentRunner(config)
    runner.record()
    report, gate_result = runner.compare()  # 不抛异常

    comparison = report["comparisons"][0]
    assert comparison["outcome"] == "REGRESSION"
    assert comparison["baseline"]["success"]
    assert not comparison["candidate"]["success"]
    assert "boom" in comparison["candidate"]["error"]
    assert "[ERROR]" in comparison["candidate"]["final_output"]
    assert not gate_result["passed"]


def test_state_provider_reset_called_before_each_run(tmp_path):
    config = make_project(tmp_path, LEGAL_QUERY,
                          extra="state_provider: tests._entrypoints:reset_provider")
    runner = ExperimentRunner(config)
    runner.record()
    reset_provider.resets = 0
    runner.compare()
    # Baseline 与 Candidate 各一次运行,每次运行前 reset 一次
    assert reset_provider.resets == 2


def test_cli_invalid_config_returns_input_error_code(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: [unclosed", encoding="utf-8")  # YAML 语法错误
    assert cli_main(["record", "--config", str(bad)]) == 2
    assert cli_main(["compare", "--config", str(bad)]) == 2

    incomplete = tmp_path / "incomplete.yaml"
    incomplete.write_text("name: x\n", encoding="utf-8")  # 缺必填字段
    assert cli_main(["compare", "--config", str(incomplete)]) == 2

    unresolvable = tmp_path / "unresolvable.yaml"
    unresolvable.write_text(textwrap.dedent("""
        name: x
        baseline: {entrypoint: "no.such.module:fn"}
        candidate: {entrypoint: "no.such.module:fn"}
        tools: no.such.module:TOOLS
        dataset: nope.yaml
    """), encoding="utf-8")
    assert cli_main(["compare", "--config", str(unresolvable)]) == 2
