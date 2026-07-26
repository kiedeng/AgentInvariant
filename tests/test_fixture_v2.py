"""Fixture v2:Schema 版本绑定、过期检测、敏感字段脱敏。"""

import json

from langchain_core.tools import tool

from agentinvariant.fixtures import FixtureStore
from agentinvariant.fixtures.store import MASK_PLACEHOLDER, mask_sensitive, schema_hash_of
from agentinvariant.runtime import ExecutionMode, ToolPolicy, virtualize
from agentinvariant.tracing import TraceRecorder


def test_schema_hash_stable_and_sensitive_to_change():
    a = schema_hash_of({"properties": {"x": {"type": "string"}}})
    b = schema_hash_of({"properties": {"x": {"type": "string"}}})
    c = schema_hash_of({"properties": {"x": {"type": "integer"}}})
    assert a == b != c


def test_lookup_detects_stale_schema(tmp_path):
    store = FixtureStore(tmp_path / "fx.json")
    store.save("q", {"a": 1}, "old-result", schema_hash="sha256:v1")

    hit, result, reason = store.lookup("q", {"a": 1}, schema_hash="sha256:v1")
    assert hit and result == "old-result"

    hit, _, reason = store.lookup("q", {"a": 1}, schema_hash="sha256:v2")
    assert not hit and reason.startswith("fixture_stale")

    # 旧格式 Fixture(无 schema_hash)向后兼容:不判过期
    store.save("legacy", {"a": 1}, "r", schema_hash=None)
    hit, _, _ = store.lookup("legacy", {"a": 1}, schema_hash="sha256:any")
    assert hit


def test_mask_sensitive_recursive():
    value = {"user": {"id_card": "110101...", "name": "张三"}, "rows": [{"password": "p"}]}
    masked = mask_sensitive(value, ("id_card", "password"))
    assert masked["user"]["id_card"] == MASK_PLACEHOLDER
    assert masked["rows"][0]["password"] == MASK_PLACEHOLDER
    assert masked["user"]["name"] == "张三"


def test_store_masks_on_save_but_key_still_matches(tmp_path):
    store = FixtureStore(tmp_path / "fx.json", mask_fields=("token",))
    store.save("api", {"token": "secret-123", "q": "x"}, {"token": "secret-456", "data": 1})

    # 磁盘上不出现明文
    raw = (tmp_path / "fx.json").read_text(encoding="utf-8")
    assert "secret-123" not in raw and "secret-456" not in raw

    # 用原始参数仍能命中(键在脱敏前计算)
    hit, result, _ = store.lookup("api", {"token": "secret-123", "q": "x"})
    assert hit and result == {"token": MASK_PLACEHOLDER, "data": 1}


def test_replay_reports_stale_fixture_to_model(tmp_path):
    @tool
    def query(a: str) -> str:
        """查询。"""
        return "live"

    store = FixtureStore(tmp_path / "fx.json")
    store.save("query", {"a": "1"}, "recorded", schema_hash="sha256:old-schema")

    recorder = TraceRecorder()
    vt = virtualize([query], {"query": ToolPolicy(mode=ExecutionMode.REPLAY)}, recorder, store)[0]
    out = json.loads(vt.invoke({"a": "1"}))
    assert "过期" in out["error"]
    assert recorder.events[0].error.startswith("fixture_stale")
