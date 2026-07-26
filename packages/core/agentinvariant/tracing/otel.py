"""OTel 导出:把回归运行以 GenAI 语义约定 Span 发送到 OTLP 后端。

Span 结构(设计基线 8.2):
  invoke_agent (每个场景 × 每个版本一条根 Span)
  └── execute_tool (每次工具调用一条子 Span)

属性使用 gen_ai.* 语义约定 + agent.release.* 项目扩展字段。
隐私默认:record_content=False 时不导出参数与结果内容,只导出结构字段。

Phoenix / Langfuse / 通用 Collector 均可通过 OTLP HTTP 端点接收,例如:
  agentinvariant compare --config ... --otlp-endpoint http://localhost:6006/v1/traces
"""

from __future__ import annotations

import json
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter

_MAX_CONTENT_CHARS = 4000


def _content(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:_MAX_CONTENT_CHARS]


def build_exporter(endpoint: str) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=endpoint)


def export_report(
    report: dict[str, Any],
    exporter: SpanExporter,
    service_name: str = "agentinvariant",
    record_content: bool = False,
) -> int:
    """把 compare 报告导出为 OTel Span,返回导出的 Span 数量。"""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("agentinvariant")

    span_count = 0
    for comparison in report["comparisons"]:
        for role in ("baseline", "candidate"):
            run = comparison[role]
            with tracer.start_as_current_span("invoke_agent") as agent_span:
                span_count += 1
                agent_span.set_attribute("gen_ai.operation.name", "invoke_agent")
                agent_span.set_attribute("gen_ai.agent.name", report.get("project", ""))
                agent_span.set_attribute("gen_ai.agent.version", run["version"])
                agent_span.set_attribute("agent.release.run_role", role)
                agent_span.set_attribute("agent.release.scenario_id", comparison["scenario_id"])
                agent_span.set_attribute("agent.release.outcome", comparison["outcome"])
                agent_span.set_attribute("agent.release.success", run["success"])
                if run["duration_ms"] is not None:
                    agent_span.set_attribute("agent.release.duration_ms", run["duration_ms"])
                agent_span.set_attribute(
                    "agent.release.contract_result",
                    json.dumps(
                        [{"rule": c["rule"], "passed": c["passed"], "severity": c["severity"]}
                         for c in run["contracts"]],
                        ensure_ascii=False,
                    ),
                )
                if record_content:
                    agent_span.set_attribute("gen_ai.response.text", _content(run["final_output"]))

                for event in run["trace"]:
                    with tracer.start_as_current_span("execute_tool") as tool_span:
                        span_count += 1
                        tool_span.set_attribute("gen_ai.operation.name", "execute_tool")
                        tool_span.set_attribute("gen_ai.tool.name", event["tool"])
                        tool_span.set_attribute("agent.release.execution_mode", event["mode"])
                        tool_span.set_attribute("agent.release.tool_effect", event["effect"])
                        if event["violation"]:
                            tool_span.set_attribute("agent.release.violation", event["violation"])
                        if event["error"]:
                            tool_span.set_attribute("error.type", event["error"])
                        if record_content:
                            tool_span.set_attribute("gen_ai.tool.call.arguments", _content(event["args"]))
                            tool_span.set_attribute("gen_ai.tool.call.result", _content(event["result"]))

    provider.force_flush()
    provider.shutdown()
    return span_count
