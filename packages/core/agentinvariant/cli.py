"""agentinvariant CLI。

    agentinvariant record  --config agentinvariant.yaml
    agentinvariant compare --config agentinvariant.yaml [--otlp-endpoint URL]
    agentinvariant gate    --result .agentinvariant/report.json --config gate.yaml

退出码:0 = 通过 / 完成,1 = 门禁阻止发布,2 = 输入错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ProjectConfig
from .gate import GateConfig, evaluate_gate


def _load_project(path_str: str) -> ProjectConfig | None:
    path = Path(path_str)
    if not path.exists():
        print(f"配置文件不存在: {path}", file=sys.stderr)
        return None
    return ProjectConfig.from_yaml(path)


def cmd_record(args: argparse.Namespace) -> int:
    from .runner import ExperimentRunner

    config = _load_project(args.config)
    if config is None:
        return 2
    runner = ExperimentRunner(config)
    count = runner.record()
    print(f"record 完成:{count} 条 Fixture -> {config.path(config.fixtures)}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from .runner import ExperimentRunner

    config = _load_project(args.config)
    if config is None:
        return 2
    runner = ExperimentRunner(config)
    report, gate_result = runner.compare()
    paths = runner.write_reports(report, gate_result)

    for c in report["comparisons"]:
        print(f"  {c['scenario_id']:<14} {c['outcome']:<15}"
              f" baseline={'OK ' if c['baseline']['success'] else 'FAIL'}"
              f" candidate={'OK ' if c['candidate']['success'] else 'FAIL'}")
    print(f"\n汇总: {report['summary']}")
    print("报告: " + " | ".join(str(p) for p in paths.values()))

    endpoint = args.otlp_endpoint or (config.otlp.endpoint if config.otlp.enabled else None)
    if endpoint:
        from .tracing.otel import build_exporter, export_report

        spans = export_report(
            report, build_exporter(endpoint),
            service_name=config.name, record_content=config.otlp.record_content,
        )
        print(f"OTLP: 已导出 {spans} 个 Span -> {endpoint}")

    print(f"Release Gate: {'PASS 允许发布' if gate_result['passed'] else 'FAIL 阻止发布'}")
    for reason in gate_result["reasons"]:
        print(f"  - {reason}")
    return 0 if gate_result["passed"] else 1


def cmd_gate(args: argparse.Namespace) -> int:
    result_path, config_path = Path(args.result), Path(args.config)
    for p in (result_path, config_path):
        if not p.exists():
            print(f"文件不存在: {p}", file=sys.stderr)
            return 2
    report = json.loads(result_path.read_text(encoding="utf-8"))
    gate_result = evaluate_gate(report, GateConfig.from_yaml(config_path))
    print(json.dumps(gate_result, ensure_ascii=False, indent=2))
    return 0 if gate_result["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    # entrypoint/tools 等 dotted-path 相对当前工作目录解析(约定:在项目根目录运行)
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    parser = argparse.ArgumentParser(prog="agentinvariant")
    sub = parser.add_subparsers(dest="command", required=True)

    record_cmd = sub.add_parser("record", help="Baseline 真实执行并录制 replay 工具的 Fixture")
    record_cmd.add_argument("--config", required=True, help="项目配置 YAML 路径")
    record_cmd.set_defaults(fn=cmd_record)

    compare_cmd = sub.add_parser("compare", help="运行 Baseline/Candidate 并产出行为差异报告与门禁结论")
    compare_cmd.add_argument("--config", required=True, help="项目配置 YAML 路径")
    compare_cmd.add_argument("--otlp-endpoint", default=None, help="OTLP HTTP Trace 端点(如 Phoenix/Langfuse)")
    compare_cmd.set_defaults(fn=cmd_compare)

    gate_cmd = sub.add_parser("gate", help="根据已生成的报告单独执行发布门禁")
    gate_cmd.add_argument("--result", required=True, help="compare 产出的 report.json 路径")
    gate_cmd.add_argument("--config", required=True, help="release gate YAML 配置路径")
    gate_cmd.set_defaults(fn=cmd_gate)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
