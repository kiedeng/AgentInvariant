"""Fixture 存储:记录工具的 (参数 -> 结果),供 replay 模式注入。

v0.2 能力(设计基线 7.4):
- exact 匹配 + 参数规范化(键排序、忽略动态字段);
- Schema 版本绑定:Fixture 记录录制时的工具 args_schema 哈希,
  replay 时 Schema 变化 → 显式判过期,不静默匹配新参数;
- 敏感字段脱敏:save 时按键名掩码参数与结果中的值;
- 录制时间戳,供过期策略与重录提示使用。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MASK_PLACEHOLDER = "***MASKED***"


def canonicalize(args: dict[str, Any], ignore_fields: tuple[str, ...] = ()) -> str:
    filtered = {k: v for k, v in args.items() if k not in ignore_fields}
    return json.dumps(filtered, ensure_ascii=False, sort_keys=True)


def schema_hash_of(schema: Any) -> str:
    """计算工具参数 Schema 的稳定哈希。schema 可为 dict 或 pydantic 模型。"""
    if schema is None:
        payload = "null"
    elif isinstance(schema, dict):
        payload = json.dumps(schema, ensure_ascii=False, sort_keys=True, default=str)
    else:
        payload = json.dumps(schema.model_json_schema(), ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def mask_sensitive(value: Any, mask_fields: tuple[str, ...]) -> Any:
    """递归掩码字典中键名命中 mask_fields 的值。"""
    if not mask_fields:
        return value
    if isinstance(value, dict):
        return {
            k: MASK_PLACEHOLDER if k in mask_fields else mask_sensitive(v, mask_fields)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive(v, mask_fields) for v in value]
    return value


class FixtureStore:
    """一个 Fixture 集合,持久化为单个 JSON 文件。"""

    def __init__(
        self,
        path: str | Path,
        ignore_fields: tuple[str, ...] = ("request_id", "trace_id", "timestamp"),
        mask_fields: tuple[str, ...] = (),
    ) -> None:
        self.path = Path(path)
        self.ignore_fields = ignore_fields
        self.mask_fields = tuple(mask_fields)
        self._entries: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self._entries = json.loads(self.path.read_text(encoding="utf-8"))

    def _hash_for_key(self, value: Any) -> Any:
        """键中的敏感字段值以哈希代替:可确定性匹配,磁盘不落明文。"""
        if isinstance(value, dict):
            return {
                k: ("sha256:" + hashlib.sha256(
                        json.dumps(v, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest()[:12]) if k in self.mask_fields else self._hash_for_key(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._hash_for_key(v) for v in value]
        return value

    def _key(self, tool: str, args: dict[str, Any]) -> str:
        keyed_args = self._hash_for_key(args) if self.mask_fields else args
        return f"{tool}::{canonicalize(keyed_args, self.ignore_fields)}"

    def save(self, tool: str, args: dict[str, Any], result: Any, schema_hash: str | None = None) -> None:
        # 注意:键用原始参数计算(否则 replay 查不到),存储内容做脱敏
        self._entries[self._key(tool, args)] = {
            "tool": tool,
            "args": mask_sensitive(args, self.mask_fields),
            "result": mask_sensitive(result, self.mask_fields),
            "schema_hash": schema_hash,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def lookup(
        self,
        tool: str,
        args: dict[str, Any],
        schema_hash: str | None = None,
    ) -> tuple[bool, Any, str | None]:
        """返回 (命中, 结果, 未命中原因)。Schema 不匹配视为过期,不静默命中。"""
        entry = self._entries.get(self._key(tool, args))
        if entry is None:
            return False, None, "fixture_miss"
        recorded = entry.get("schema_hash")
        if schema_hash and recorded and recorded != schema_hash:
            return False, None, f"fixture_stale: 工具 Schema 已变化(录制 {recorded},当前 {schema_hash}),请重新 record"
        return True, entry["result"], None

    def __len__(self) -> int:
        return len(self._entries)
