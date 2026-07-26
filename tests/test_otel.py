"""OTLP 导出:Span 结构、gen_ai/agent.release 属性、隐私默认。"""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentinvariant.tracing.otel import export_report

REPORT = {
    "project": "finance-agent",
    "comparisons": [
        {
            "scenario_id": "finance-001",
            "outcome": "NEUTRAL_CHANGE",
            "baseline": {
                "version": "v1", "success": True, "final_output": "答案", "duration_ms": 12.5,
                "contracts": [{"rule": "output_contains", "passed": True, "severity": "blocker"}],
                "trace": [
                    {"tool": "execute_sql", "mode": "replay", "effect": "WRITE_REVERSIBLE",
                     "args": {"sql": "SELECT 1"}, "result": {"rows": []}, "violation": None, "error": None},
                ],
            },
            "candidate": {
                "version": "v2", "success": True, "final_output": "答案", "duration_ms": 15.0,
                "contracts": [],
                "trace": [
                    {"tool": "check_permission", "mode": "live", "effect": "READ_ONLY",
                     "args": {"user_id": "u1"}, "result": {"allowed": True}, "violation": None, "error": None},
                    {"tool": "send_email", "mode": "blocked", "effect": "EXTERNAL_COMMUNICATION",
                     "args": {}, "result": None, "violation": "tool blocked by policy", "error": "blocked"},
                ],
            },
        },
    ],
}


def test_export_report_span_structure_and_privacy_default():
    exporter = InMemorySpanExporter()
    count = export_report(REPORT, exporter, service_name="finance-agent")
    spans = exporter.get_finished_spans()
    assert count == len(spans) == 2 + 3  # 2 个 invoke_agent + 3 个 execute_tool

    agent_spans = [s for s in spans if s.name == "invoke_agent"]
    tool_spans = [s for s in spans if s.name == "execute_tool"]
    roles = {s.attributes["agent.release.run_role"] for s in agent_spans}
    assert roles == {"baseline", "candidate"}
    assert all(s.attributes["agent.release.scenario_id"] == "finance-001" for s in agent_spans)

    blocked = next(s for s in tool_spans if s.attributes["gen_ai.tool.name"] == "send_email")
    assert blocked.attributes["agent.release.execution_mode"] == "blocked"
    assert blocked.attributes["agent.release.tool_effect"] == "EXTERNAL_COMMUNICATION"
    assert blocked.attributes["agent.release.violation"] == "tool blocked by policy"

    # 隐私默认:不导出参数与结果内容
    for s in tool_spans:
        assert "gen_ai.tool.call.arguments" not in s.attributes
        assert "gen_ai.tool.call.result" not in s.attributes

    # 工具 Span 归属于对应的 invoke_agent 根 Span
    parent_ids = {s.parent.span_id for s in tool_spans}
    agent_ids = {s.context.span_id for s in agent_spans}
    assert parent_ids <= agent_ids


def test_export_report_with_content_recording():
    exporter = InMemorySpanExporter()
    export_report(REPORT, exporter, record_content=True)
    tool_spans = [s for s in exporter.get_finished_spans() if s.name == "execute_tool"]
    sql_span = next(s for s in tool_spans if s.attributes["gen_ai.tool.name"] == "execute_sql")
    assert "SELECT 1" in sql_span.attributes["gen_ai.tool.call.arguments"]
