"""State Provider:获取运行前后的业务状态快照(设计基线 8.3)。

对有写操作的 Agent,仅比较 Trace 不够 —— 需要证明业务状态本身
未被破坏(或按预期变化)。快照经 normalize 移除动态字段后参与:
1. state_constraint 契约(候选运行后的状态断言);
2. Baseline/Candidate 的 state diff(报告证据)。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StateProvider(Protocol):
    def snapshot(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """返回当前业务状态快照。运行前后各调用一次。"""
        ...

    def normalize(self, state: dict[str, Any]) -> dict[str, Any]:
        """移除时间戳、自增 ID 等动态字段,使快照可稳定比较。"""
        ...


class SqliteStateProvider:
    """用一组命名 SQL 查询对 SQLite 库做快照。

    queries: {"名称": "SELECT ..."};每个查询结果为行列表。
    ignore_fields: normalize 时按键名整体剔除。
    """

    def __init__(
        self,
        connection_factory,
        queries: dict[str, str],
        ignore_fields: tuple[str, ...] = (),
    ) -> None:
        self._connection_factory = connection_factory
        self.queries = queries
        self.ignore_fields = ignore_fields

    def snapshot(self, scenario: dict[str, Any]) -> dict[str, Any]:
        conn: sqlite3.Connection = self._connection_factory()
        state: dict[str, Any] = {}
        for name, sql in self.queries.items():
            cursor = conn.execute(sql)
            columns = [c[0] for c in cursor.description]
            state[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return state

    def normalize(self, state: dict[str, Any]) -> dict[str, Any]:
        def strip(rows: Any) -> Any:
            if not isinstance(rows, list):
                return rows
            return [
                {k: v for k, v in row.items() if k not in self.ignore_fields}
                for row in rows
            ]

        return {name: strip(rows) for name, rows in state.items()}


def state_get(state: dict[str, Any], dotted_path: str) -> Any:
    """按点路径取状态字段,列表段支持数字索引:如 "approval_rates.0.rate"。"""
    node: Any = state
    for part in dotted_path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node
