"""POC-1 验证:工具截获与五种执行模式。"""

import json

from langchain_core.tools import tool

from agentinvariant.fixtures import FixtureStore
from agentinvariant.runtime import ExecutionMode, ToolPolicy, virtualize
from agentinvariant.tracing import TraceRecorder

CALLS = []


@tool
def dangerous_refund(order_id: str) -> str:
    """执行退款。"""
    CALLS.append(order_id)
    return json.dumps({"refunded": order_id})


def make(policies, store=None):
    recorder = TraceRecorder()
    tools = virtualize([dangerous_refund], policies, recorder, store)
    return tools[0], recorder


def test_unconfigured_tool_defaults_to_blocked():
    CALLS.clear()
    vt, recorder = make({})
    result = vt.invoke({"order_id": "o1"})
    assert "阻断" in result
    assert CALLS == []  # 真实工具从未执行
    assert recorder.violations and recorder.violations[0]["tool"] == "dangerous_refund"


def test_mock_mode_returns_preset_result():
    CALLS.clear()
    vt, recorder = make({"dangerous_refund": ToolPolicy(mode=ExecutionMode.MOCK, mock_result={"refunded": "fake"})})
    assert json.loads(vt.invoke({"order_id": "o1"})) == {"refunded": "fake"}
    assert CALLS == []
    assert recorder.tool_sequence == ["dangerous_refund"]


def test_record_then_replay_roundtrip(tmp_path):
    CALLS.clear()
    store = FixtureStore(tmp_path / "fx.json")
    vt, _ = make({"dangerous_refund": ToolPolicy(mode=ExecutionMode.RECORD)}, store)
    live = vt.invoke({"order_id": "o1"})
    assert CALLS == ["o1"] and len(store) == 1

    vt2, _ = make({"dangerous_refund": ToolPolicy(mode=ExecutionMode.REPLAY)}, store)
    assert vt2.invoke({"order_id": "o1"}) == live  # Fixture 命中
    assert CALLS == ["o1"]  # 未再次真实执行

    miss = vt2.invoke({"order_id": "o999"})
    assert "无法回放" in miss  # Fixture 未命中要显式报告,不静默放行


def test_fixture_key_is_arg_order_insensitive(tmp_path):
    store = FixtureStore(tmp_path / "fx.json")
    store.save("t", {"a": 1, "b": 2}, "r")
    hit, result = store.lookup("t", {"b": 2, "a": 1})
    assert hit and result == "r"


def test_argument_guard_blocks_and_records_violation():
    CALLS.clear()
    guard = lambda args: "禁止退款" if args.get("order_id") == "bad" else None
    vt, recorder = make({"dangerous_refund": ToolPolicy(mode=ExecutionMode.LIVE, argument_guard=guard)})
    assert "违反策略" in vt.invoke({"order_id": "bad"})
    assert CALLS == []
    assert recorder.violations[0]["violation"] == "禁止退款"
    vt.invoke({"order_id": "ok"})
    assert CALLS == ["ok"]
