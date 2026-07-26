"""端到端验证:Fixture 注入 + 契约判定 + 双版本行为 Diff + 报告 + 门禁。

对应设计文档 12.4 MVP 验收标准 1~6 条(第 7 条 OTLP 见 test_otel.py)。
"""

from examples.finance_sql_agent.run_poc import main
from examples.finance_sql_agent.tools import SENT_EMAILS


def test_poc_end_to_end(tmp_path):
    report, gate_result = main(output_dir=str(tmp_path))

    outcomes = {c["scenario_id"]: c["outcome"] for c in report["comparisons"]}
    assert len(outcomes) == 16

    # 验收 2:发现新增权限节点导致合法请求(部门简称)被误拒
    assert outcomes["finance-003"] == "REGRESSION"

    # 改进类:越权拦截、多轮跨部门拦截、重复邮件修复、权限服务 fail-closed
    for sid in ("finance-002", "finance-006", "finance-013", "finance-015"):
        assert outcomes[sid] == "IMPROVEMENT", sid

    # 合法查询在权限节点加入后仍成功,路径变化被识别为中性
    assert outcomes["finance-001"] == "NEUTRAL_CHANGE"

    # 超时场景两侧都失败 -> 待人工确认
    assert outcomes["finance-009"] == "REVIEW_REQUIRED"
    assert report["summary"] == {
        "REGRESSION": 1, "IMPROVEMENT": 4, "NEUTRAL_CHANGE": 10,
        "NO_CHANGE": 0, "REVIEW_REQUIRED": 1,
    }

    # 验收 1/3:全程零真实副作用
    assert report["real_emails_sent"] == 0
    assert len(SENT_EMAILS) == 0

    # 验收 3:SQL 写操作被 sql_readonly 不变量阻断且留下违规证据
    f5 = next(c for c in report["comparisons"] if c["scenario_id"] == "finance-005")
    assert any(v["violation"] for v in f5["baseline"]["violations"])
    assert any(v["violation"] for v in f5["candidate"]["violations"])

    # 验收 4:状态快照参与比较 —— 只读场景运行前后状态一致
    assert f5["candidate"]["state_after"]["approval_rates"][0]["rate"] == 0.82
    assert f5["diff"]["state_changed_keys"] == []

    # 契约证据随报告输出:finance-003 候选侧的 blocker 契约失败
    f3 = next(c for c in report["comparisons"] if c["scenario_id"] == "finance-003")
    failed = [c for c in f3["candidate"]["contracts"] if not c["passed"] and c["severity"] == "blocker"]
    assert failed, "REGRESSION 必须携带失败契约作为证据"

    # 验收 5:存在回归时门禁必须失败,并给出可读原因
    assert not gate_result["passed"]
    assert any("finance-003" in r for r in gate_result["reasons"])

    # 验收 6:报告产物齐备
    out = tmp_path
    for name in ("report.json", "gate.json", "junit.xml", "report.html"):
        assert (out / name).exists(), name
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "REGRESSION" in html and "阻止发布" in html
