"""StateProvider 与状态类契约规则。"""

import sqlite3

from agentinvariant.contracts import ContractContext, parse_rule
from agentinvariant.state import SqliteStateProvider
from agentinvariant.state.provider import state_get


def make_provider():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("CREATE TABLE orders (id INTEGER, status TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO orders VALUES (1, 'CREATED', '2026-07-26T10:00:00')")
    conn.commit()
    return conn, SqliteStateProvider(
        connection_factory=lambda: conn,
        queries={"orders": "SELECT id, status, updated_at FROM orders ORDER BY id"},
        ignore_fields=("updated_at",),
    )


def test_snapshot_and_normalize_drops_dynamic_fields():
    conn, provider = make_provider()
    snap = provider.normalize(provider.snapshot({}))
    assert snap == {"orders": [{"id": 1, "status": "CREATED"}]}

    conn.execute("UPDATE orders SET updated_at = '2026-07-26T11:00:00'")
    conn.commit()
    assert provider.normalize(provider.snapshot({})) == snap  # 动态字段被忽略


def test_state_get_dotted_path():
    state = {"orders": [{"id": 1, "status": "CREATED"}]}
    assert state_get(state, "orders.0.status") == "CREATED"
    assert state_get(state, "orders.0.missing") is None
    assert state_get(state, "nope") is None


def test_state_constraint_and_unchanged_rules():
    before = {"orders": [{"id": 1, "status": "CREATED"}]}
    after_same = {"orders": [{"id": 1, "status": "CREATED"}]}
    after_written = {"orders": [{"id": 1, "status": "REFUNDED"}]}

    ok = ContractContext(events=[], final_output="", state_before=before, state_after=after_same)
    written = ContractContext(events=[], final_output="", state_before=before, state_after=after_written)

    constraint = parse_rule({"type": "state_constraint", "field": "orders.0.status", "equals": "CREATED"})
    assert constraint.evaluate(ok).passed
    assert not constraint.evaluate(written).passed

    unchanged = parse_rule({"type": "state_unchanged"})
    assert unchanged.evaluate(ok).passed
    check = unchanged.evaluate(written)
    assert not check.passed and "orders" in check.detail

    # 未配置 StateProvider 时显式失败而不是静默通过
    no_state = ContractContext(events=[], final_output="")
    assert not constraint.evaluate(no_state).passed
    assert not unchanged.evaluate(no_state).passed


def test_max_latency_ms_rule():
    rule = parse_rule({"type": "max_latency_ms", "max": 100})
    assert rule.evaluate(ContractContext(events=[], final_output="", duration_ms=50)).passed
    assert not rule.evaluate(ContractContext(events=[], final_output="", duration_ms=150)).passed
    # 超时中断的运行没有耗时记录,判失败
    assert not rule.evaluate(ContractContext(events=[], final_output="")).passed
