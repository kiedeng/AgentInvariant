"""端到端演示:record -> compare -> report -> gate(基于通用 ExperimentRunner)。

用法:
    python -m examples.finance_sql_agent.run_poc
    # 退出码即门禁结论:0 允许发布,1 阻止发布

等价的 CLI 用法:
    agentinvariant record  --config examples/finance_sql_agent/agentinvariant.yaml
    agentinvariant compare --config examples/finance_sql_agent/agentinvariant.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

from agentinvariant.config import ProjectConfig
from agentinvariant.runner import ExperimentRunner

from .tools import SENT_EMAILS

CONFIG_PATH = Path(__file__).parent / "agentinvariant.yaml"


def main(output_dir: str | None = None) -> tuple[dict, dict]:
    config = ProjectConfig.from_yaml(CONFIG_PATH)
    if output_dir is not None:
        config = config.model_copy(update={
            "output_dir": output_dir,
            "fixtures": str(Path(output_dir) / "fixtures" / "finance.json"),
        })
    config.path(config.fixtures).unlink(missing_ok=True)
    runner = ExperimentRunner(config)

    print("== 阶段 A:record(V1 live 运行,录制 replay 工具 Fixture)==")
    count = runner.record()
    print(f"已录制 {count} 条 Fixture -> {config.path(config.fixtures)}\n")

    print("== 阶段 B:compare(execute_sql=replay, send_email=blocked, 契约判定)==")
    report, gate_result = runner.compare()
    paths = runner.write_reports(report, gate_result)
    report["real_emails_sent"] = len(SENT_EMAILS)

    for c in report["comparisons"]:
        print(f"  {c['scenario_id']:<14} {c['outcome']:<15}"
              f" baseline={'OK ' if c['baseline']['success'] else 'FAIL'}"
              f" candidate={'OK ' if c['candidate']['success'] else 'FAIL'}")
    print(f"\n汇总: {report['summary']}")
    print(f"真实发出的邮件数: {len(SENT_EMAILS)} (必须为 0)")
    print("报告: " + " | ".join(str(p) for p in paths.values()))
    print(f"Release Gate: {'PASS 允许发布' if gate_result['passed'] else 'FAIL 阻止发布'}")
    for reason in gate_result["reasons"]:
        print(f"  - {reason}")
    return report, gate_result


if __name__ == "__main__":
    _, gate_result = main()
    sys.exit(0 if gate_result["passed"] else 1)
