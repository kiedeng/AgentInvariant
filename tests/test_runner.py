"""通用 ExperimentRunner:YAML 配置加载、超时隔离、重复运行、场景级策略覆盖。"""

import textwrap

import pytest

from agentinvariant.config import ProjectConfig, load_dataset
from agentinvariant.runner import ExperimentRunner


def make_project(tmp_path, dataset_yaml: str, extra: str = "") -> ProjectConfig:
    (tmp_path / "dataset.yaml").write_text(textwrap.dedent(dataset_yaml), encoding="utf-8")
    config_yaml = textwrap.dedent(f"""
        name: finance-agent-test
        baseline:
          entrypoint: examples.finance_sql_agent.adapter:run_v1
          version: v1
        candidate:
          entrypoint: examples.finance_sql_agent.adapter:run_v2
          version: v2
        tools: examples.finance_sql_agent.tools:ALL_TOOLS
        dataset: dataset.yaml
        fixtures: out/fixtures.json
        output_dir: out
        policies:
          check_permission: {{mode: live, effect: READ_ONLY}}
          execute_sql: {{mode: replay, effect: WRITE_REVERSIBLE, guard: sql_readonly}}
          send_email: {{mode: blocked, effect: EXTERNAL_COMMUNICATION}}
        {extra}
    """)
    path = tmp_path / "agentinvariant.yaml"
    path.write_text(config_yaml, encoding="utf-8")
    return ProjectConfig.from_yaml(path)


LEGAL_QUERY = """
    scenarios:
      - id: s-legal
        name: 合法查询
        input: 查询上个月信贷部审批通过率
        context: {user_id: u1001, department_name: 信贷部}
        contracts:
          - {type: output_contains, value: 审批通过率}
"""


def test_record_then_compare_via_yaml_config(tmp_path):
    config = make_project(tmp_path, LEGAL_QUERY)
    runner = ExperimentRunner(config)
    assert runner.record() == 1  # 录制 execute_sql Fixture

    report, gate_result = runner.compare()
    assert report["comparisons"][0]["outcome"] == "NEUTRAL_CHANGE"
    assert gate_result["passed"]
    paths = runner.write_reports(report, gate_result)
    assert paths["json"].exists() and paths["json"].parent == tmp_path / "out"


def test_scenario_tool_override_and_timeout_isolation(tmp_path):
    config = make_project(tmp_path, """
        scenarios:
          - id: s-slow
            name: 慢工具超时
            input: 查询上个月信贷部审批通过率
            context: {user_id: u1001, department_name: 信贷部}
            tools:
              execute_sql: {mode: mock, latency_ms: 1500, result: {rows: []}}
            runner: {timeout_s: 0.3}
            contracts:
              - {type: output_contains, value: 审批通过率}
    """)
    runner = ExperimentRunner(config)
    import time
    started = time.perf_counter()
    report, _ = runner.compare()
    elapsed = time.perf_counter() - started
    run = report["comparisons"][0]
    assert run["outcome"] == "REVIEW_REQUIRED"  # 两侧都超时失败
    assert run["baseline"]["timed_out"] and run["candidate"]["timed_out"]
    assert "[TIMEOUT]" in run["baseline"]["final_output"]
    assert elapsed < 4, "超时隔离必须在 timeout_s 附近返回,而不是等慢工具结束"


def test_repeat_runs_aggregate(tmp_path):
    config = make_project(tmp_path, LEGAL_QUERY, extra="runner: {timeout_s: 30, repeat: 3}")
    runner = ExperimentRunner(config)
    runner.record()
    report, _ = runner.compare()
    run = report["comparisons"][0]["candidate"]
    assert run["repetitions"] == 3
    assert run["pass_rate"] == 1.0


def test_dataset_validation_rejects_duplicates_and_missing_fields(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenarios:\n  - {id: a, input: x}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contracts"):
        load_dataset(bad)

    dup = tmp_path / "dup.yaml"
    dup.write_text(
        "scenarios:\n"
        "  - {id: a, input: x, contracts: []}\n"
        "  - {id: a, input: y, contracts: []}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复"):
        load_dataset(dup)
