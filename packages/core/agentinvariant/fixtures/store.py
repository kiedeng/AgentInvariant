"""Fixture 存储:记录工具的 (参数 -> 结果),供 replay 模式注入。

POC 实现 exact 匹配 + 参数规范化(键排序、忽略动态字段)。
正式版需绑定工具 Schema 版本、支持 subset/custom matcher 与脱敏
(见 docs/design-baseline.md 7.4)。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonicalize(args: dict[str, Any], ignore_fields: tuple[str, ...] = ()) -> str:
    filtered = {k: v for k, v in args.items() if k not in ignore_fields}
    return json.dumps(filtered, ensure_ascii=False, sort_keys=True)


class FixtureStore:
    """一个 Fixture 集合,持久化为单个 JSON 文件。"""

    def __init__(self, path: str | Path, ignore_fields: tuple[str, ...] = ("request_id", "trace_id", "timestamp")) -> None:
        self.path = Path(path)
        self.ignore_fields = ignore_fields
        self._entries: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self._entries = json.loads(self.path.read_text(encoding="utf-8"))

    def _key(self, tool: str, args: dict[str, Any]) -> str:
        return f"{tool}::{canonicalize(args, self.ignore_fields)}"

    def save(self, tool: str, args: dict[str, Any], result: Any) -> None:
        self._entries[self._key(tool, args)] = {"tool": tool, "args": args, "result": result}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def lookup(self, tool: str, args: dict[str, Any]) -> tuple[bool, Any]:
        entry = self._entries.get(self._key(tool, args))
        if entry is None:
            return False, None
        return True, entry["result"]

    def __len__(self) -> int:
        return len(self._entries)
