"""argument_constraint 的内置参数匹配器。

匹配器签名:fn(args: dict) -> str | None,返回 None 放行,返回字符串为违规原因。
既可用于 Contract Engine 事后检查,也可作为 runtime ToolPolicy.argument_guard
在执行前阻断(同一规则,两个执行点)。
"""

from __future__ import annotations

from typing import Any, Callable

Matcher = Callable[[dict[str, Any]], str | None]


def sql_readonly(args: dict[str, Any]) -> str | None:
    sql = str(args.get("sql", "")).strip().upper()
    return None if sql.startswith("SELECT") else "SQL 仅允许 SELECT(sql_readonly)"


_SENSITIVE_TOKENS = ("身份证", "ID_CARD", "PASSWORD", "SSN", "PHONE_NUMBER")


def no_sensitive_fields(args: dict[str, Any]) -> str | None:
    text = str(args).upper()
    hits = [t for t in _SENSITIVE_TOKENS if t.upper() in text]
    return f"参数涉及敏感字段: {hits}(no_sensitive_fields)" if hits else None


MATCHERS: dict[str, Matcher] = {
    "sql_readonly": sql_readonly,
    "no_sensitive_fields": no_sensitive_fields,
}


def get_matcher(name: str) -> Matcher:
    if name not in MATCHERS:
        raise KeyError(f"未知的参数匹配器: {name},可用: {sorted(MATCHERS)}")
    return MATCHERS[name]
