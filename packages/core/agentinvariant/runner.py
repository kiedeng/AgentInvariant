"""Experiment Runner:record / compare 的通用执行引擎。

职责(设计基线 6.1 Scenario & Experiment Runner 层):
- 按项目配置解析 Agent 入口、工具、数据集、策略与 StateProvider;
- 每次运行独立 TraceRecorder 与虚拟化工具集(状态不串扰);
- 场景级工具策略覆盖(A.2 场景配置语义);
- 超时隔离与重复运行;
- 运行前后状态快照,契约判定,Behavior Diff,报告与门禁。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, Callable

from .config import ProjectConfig, load_dataset, parse_policy, resolve_object
from .contracts import ContractContext, blocker_failed, evaluate_contracts
from .diff import RunResult, compare_runs
from .fixtures import FixtureStore
from .gate import GateConfig, evaluate_gate
from .reports import write_html, write_junit
from .runtime import ExecutionMode, ToolPolicy, virtualize
from .tracing import TraceRecorder


class ExperimentRunner:
    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.baseline_fn: Callable = resolve_object(config.baseline.entrypoint)
        self.candidate_fn: Callable = resolve_object(config.candidate.entrypoint)
        self.tools = resolve_object(config.tools)
        self.scenarios = load_dataset(config.path(config.dataset))
        self.state_provider = resolve_object(config.state_provider) if config.state_provider else None
        self.store = FixtureStore(
            config.path(config.fixtures),
            mask_fields=tuple(config.fixture_mask_fields),
        )

    # ---- 策略 ----

    def _policies_for(self, scenario: dict[str, Any], record: bool) -> dict[str, ToolPolicy]:
        merged: dict[str, ToolPolicy] = {}
        overrides = scenario.get("tools", {})
        for name in set(self.config.policies) | set(overrides):
            spec = {**self.config.policies.get(name, {}), **overrides.get(name, {})}
            policy = parse_policy(spec)
            if record and policy.mode is ExecutionMode.REPLAY:
                # record 阶段:replay 工具切换为真实执行并录制 Fixture
                policy = policy.model_copy(update={"mode": ExecutionMode.RECORD})
            merged[name] = policy
        return merged

    # ---- 单次运行 ----

    def _invoke_with_timeout(self, fn: Callable, tools: list, scenario: dict[str, Any], timeout_s: float) -> tuple[str, bool]:
        # 不用 with:上下文管理器会等待卡住的线程结束,超时隔离就失效了
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(fn, tools, scenario)
        try:
            result = str(future.result(timeout=timeout_s)), False
        except FutureTimeout:
            result = f"[TIMEOUT] 运行超过 {timeout_s}s 被中断。", True
        pool.shutdown(wait=False, cancel_futures=True)
        return result

    def _run_once(self, fn: Callable, version: str, scenario: dict[str, Any], record: bool) -> RunResult:
        recorder = TraceRecorder()
        tools = virtualize(self.tools, self._policies_for(scenario, record), recorder, self.store)
        timeout_s = scenario.get("runner", {}).get("timeout_s", self.config.runner.timeout_s)

        state_before = None
        if self.state_provider is not None:
            state_before = self.state_provider.normalize(self.state_provider.snapshot(scenario))

        started = time.perf_counter()
        output, timed_out = self._invoke_with_timeout(fn, tools, scenario, timeout_s)
        duration_ms = None if timed_out else (time.perf_counter() - started) * 1000

        state_after = None
        if self.state_provider is not None:
            state_after = self.state_provider.normalize(self.state_provider.snapshot(scenario))

        ctx = ContractContext(
            events=recorder.events,
            final_output=output,
            duration_ms=duration_ms,
            state_before=state_before,
            state_after=state_after,
        )
        checks = evaluate_contracts(scenario["contracts"], ctx)
        return RunResult(
            version=version,
            final_output=output,
            recorder=recorder,
            success=not blocker_failed(checks) and not timed_out,
            contracts=[c.to_dict() for c in checks],
            duration_ms=duration_ms,
            state_before=state_before,
            state_after=state_after,
            timed_out=timed_out,
        )

    def _run_repeated(self, fn: Callable, version: str, scenario: dict[str, Any]) -> RunResult:
        repeat = max(1, self.config.runner.repeat)
        runs = [self._run_once(fn, version, scenario, record=False) for _ in range(repeat)]
        primary = runs[0]
        primary.repetitions = repeat
        primary.pass_rate = sum(1 for r in runs if r.success) / repeat
        # 硬规则:任何一次失败都视为失败(设计基线 9.4)
        primary.success = all(r.success for r in runs)
        return primary

    # ---- 阶段 ----

    def record(self) -> int:
        """用 Baseline 真实执行并录制 replay 工具的 Fixture,返回 Fixture 数。"""
        for scenario in self.scenarios:
            self._run_once(self.baseline_fn, self.config.baseline.version, scenario, record=True)
        return len(self.store)

    def compare(self) -> tuple[dict[str, Any], dict[str, Any]]:
        comparisons = []
        for scenario in self.scenarios:
            baseline = self._run_repeated(self.baseline_fn, self.config.baseline.version, scenario)
            candidate = self._run_repeated(self.candidate_fn, self.config.candidate.version, scenario)
            comparisons.append(compare_runs(scenario["id"], baseline, candidate))

        report = {
            "project": self.config.name,
            "baseline": f"{self.config.name} {self.config.baseline.version}",
            "candidate": f"{self.config.name} {self.config.candidate.version}",
            "summary": {
                outcome: sum(1 for c in comparisons if c["outcome"] == outcome)
                for outcome in ("REGRESSION", "IMPROVEMENT", "NEUTRAL_CHANGE", "NO_CHANGE", "REVIEW_REQUIRED")
            },
            "comparisons": comparisons,
        }
        gate_result = evaluate_gate(report, self._gate_config())
        return report, gate_result

    def _gate_config(self) -> GateConfig:
        gate = self.config.gate
        if gate is None:
            return GateConfig()
        if isinstance(gate, dict):
            return GateConfig.model_validate(gate.get("release_gate", gate))
        return GateConfig.from_yaml(self.config.path(gate))

    # ---- 报告 ----

    def write_reports(self, report: dict[str, Any], gate_result: dict[str, Any]) -> dict[str, Path]:
        out = self.config.path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        json_path = out / "report.json"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        gate_path = out / "gate.json"
        gate_path.write_text(json.dumps(gate_result, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "json": json_path,
            "gate": gate_path,
            "junit": write_junit(report, out / "junit.xml"),
            "html": write_html(report, gate_result, out / "report.html"),
        }
