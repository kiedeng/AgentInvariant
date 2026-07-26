"""项目与数据集配置(附录 A 配置示例的实现)。

项目配置 agentinvariant.yaml:
    project: {name}
    baseline:  {entrypoint: "module:fn", version}
    candidate: {entrypoint: "module:fn", version}
    tools: "module:ALL_TOOLS"
    dataset: datasets/finance.yaml
    fixtures: .agentinvariant/fixtures.json
    policies: {tool_name: {mode, effect, guard, result, latency_ms}}
    state_provider: "module:provider"        # 可选
    gate: gate.yaml                          # 路径或内联 dict
    runner: {timeout_s, repeat}
    otlp: {enabled, endpoint, record_content}

entrypoint 契约(Python Callable Adapter,设计基线 D-06):
    fn(tools: list[BaseTool], scenario: dict) -> str   # 返回最终回答文本

相对路径均相对配置文件所在目录解析。
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .contracts.matchers import get_matcher
from .runtime import ExecutionMode, ToolEffect, ToolPolicy


def resolve_object(dotted_path: str) -> Any:
    """解析 "package.module:attr" 形式的对象引用。"""
    module_path, _, attr = dotted_path.partition(":")
    if not attr:
        raise ValueError(f"对象引用必须为 'module:attr' 形式,得到: {dotted_path!r}")
    module = importlib.import_module(module_path)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(f"{module_path} 中不存在 {attr}") from exc


def parse_policy(spec: dict[str, Any]) -> ToolPolicy:
    """把 YAML 工具策略转换为 ToolPolicy。guard 为 matchers 注册表中的名称。"""
    return ToolPolicy(
        mode=ExecutionMode(spec.get("mode", "blocked")),
        effect=ToolEffect(spec.get("effect", "READ_ONLY")),
        mock_result=spec.get("result"),
        latency_ms=spec.get("latency_ms", 0),
        argument_guard=get_matcher(spec["guard"]) if spec.get("guard") else None,
    )


class AgentSpec(BaseModel):
    entrypoint: str
    version: str = ""


class RunnerConfig(BaseModel):
    timeout_s: float = 60.0
    repeat: int = 1


class OtlpConfig(BaseModel):
    enabled: bool = False
    endpoint: str | None = None
    # 隐私默认:不导出 Prompt / 参数 / 结果内容(设计基线 8.2)
    record_content: bool = False


class ProjectConfig(BaseModel):
    name: str
    baseline: AgentSpec
    candidate: AgentSpec
    tools: str
    dataset: str
    fixtures: str = ".agentinvariant/fixtures.json"
    policies: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state_provider: str | None = None
    gate: str | dict[str, Any] | None = None
    output_dir: str = ".agentinvariant"
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    otlp: OtlpConfig = Field(default_factory=OtlpConfig)

    base_dir: Path = Field(default_factory=Path)

    def path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else self.base_dir / p

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProjectConfig":
        path = Path(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "project" in data and isinstance(data["project"], dict):
            data = {**data, **data.pop("project")}
        return cls.model_validate({**data, "base_dir": path.parent})


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    scenarios = data["scenarios"] if isinstance(data, dict) else data
    seen: set[str] = set()
    for s in scenarios:
        for key in ("id", "input", "contracts"):
            if key not in s:
                raise ValueError(f"场景缺少必填字段 {key}: {s.get('id', s)}")
        if s["id"] in seen:
            raise ValueError(f"场景 id 重复: {s['id']}")
        seen.add(s["id"])
    return scenarios
