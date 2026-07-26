"""agentinvariant CLI(POC 版,标准库 argparse;正式版换 Typer)。

    agentinvariant gate --result .agentinvariant/report.json --config gate.yaml

退出码:0 = 允许发布,1 = 阻止发布,2 = 输入错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gate import GateConfig, evaluate_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentinvariant")
    sub = parser.add_subparsers(dest="command", required=True)

    gate_cmd = sub.add_parser("gate", help="根据行为回归报告执行发布门禁")
    gate_cmd.add_argument("--result", required=True, help="compare 产出的 report.json 路径")
    gate_cmd.add_argument("--config", required=True, help="release gate YAML 配置路径")

    args = parser.parse_args(argv)

    if args.command == "gate":
        result_path, config_path = Path(args.result), Path(args.config)
        for p in (result_path, config_path):
            if not p.exists():
                print(f"文件不存在: {p}", file=sys.stderr)
                return 2
        report = json.loads(result_path.read_text(encoding="utf-8"))
        gate_result = evaluate_gate(report, GateConfig.from_yaml(config_path))
        print(json.dumps(gate_result, ensure_ascii=False, indent=2))
        return 0 if gate_result["passed"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
