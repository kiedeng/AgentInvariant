"""金融示例的真实工具实现(模拟测试环境)。

execute_sql 操作一个真实的 SQLite 库,send_email 会真实追加到发件箱 —
用来验证虚拟化层能否阻止/回放这些副作用。
"""

from __future__ import annotations

import json
import sqlite3

from langchain_core.tools import tool

USERS = {
    "u1001": {"department": "信贷部"},
    "u2002": {"department": "市场部"},
    "u3003": {"department": "重庆分部"},
}

# 真实发出的邮件会进入这里 —— POC 验收标准之一是它必须始终为空。
SENT_EMAILS: list[dict] = []

_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.execute(
            "CREATE TABLE approval_rates (department TEXT, month TEXT, rate REAL)"
        )
        _conn.executemany(
            "INSERT INTO approval_rates VALUES (?, ?, ?)",
            [
                ("信贷部", "2026-06", 0.82),
                ("市场部", "2026-06", 0.91),
                ("重庆分部", "2026-06", 0.77),
            ],
        )
        _conn.commit()
    return _conn


@tool
def check_permission(user_id: str, department: str) -> str:
    """检查用户是否有权查询指定部门的数据。"""
    user = USERS.get(user_id)
    # 注意:这里是严格全名匹配,不处理"信贷"这类简称 —— 这是 V2 引入的隐性缺陷,
    # 也是本 POC 要让 Diff 引擎抓出来的回归。
    allowed = user is not None and user["department"] == department
    return json.dumps({"allowed": allowed, "user_id": user_id, "department": department}, ensure_ascii=False)


@tool
def execute_sql(sql: str) -> str:
    """在指标库上执行 SQL 并返回结果行。"""
    cur = _db().execute(sql)
    if sql.strip().upper().startswith("SELECT"):
        rows = cur.fetchall()
        return json.dumps({"rows": rows}, ensure_ascii=False)
    _db().commit()
    return json.dumps({"rows_affected": cur.rowcount}, ensure_ascii=False)


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """向指定收件人发送邮件。"""
    SENT_EMAILS.append({"to": to, "subject": subject, "body": body})
    return json.dumps({"sent": True, "to": to}, ensure_ascii=False)


ALL_TOOLS = [check_permission, execute_sql, send_email]
