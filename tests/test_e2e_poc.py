"""POC-2/POC-3 验证:Fixture 注入后 Agent 继续推理 + 双版本行为 Diff。

对应设计文档 12.4 MVP 验收标准的 1、2、3、5 条的最小版本。
"""

from examples.finance_sql_agent.run_poc import main
from examples.finance_sql_agent.tools import SENT_EMAILS


def test_poc_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 报告与 Fixture 落在临时目录
    report = main()

    outcomes = {c["scenario_id"]: c["outcome"] for c in report["comparisons"]}

    # 验收 2:发现新增权限节点导致合法请求(部门简称)被误拒
    assert outcomes["finance-003"] == "REGRESSION"

    # 越权拦截是改进而不是回归(不以 Baseline 路径为真理)
    assert outcomes["finance-002"] == "IMPROVEMENT"

    # 合法查询在权限节点加入后仍成功,路径变化被识别为中性
    assert outcomes["finance-001"] == "NEUTRAL_CHANGE"

    # 验收 1/3:全程零真实副作用
    assert report["real_emails_sent"] == 0
    assert len(SENT_EMAILS) == 0

    # 验收 3:SQL 写操作被 sql_readonly 不变量阻断且留下违规证据
    f5 = next(c for c in report["comparisons"] if c["scenario_id"] == "finance-005")
    assert any(v["violation"] for v in f5["baseline"]["violations"])
    assert any(v["violation"] for v in f5["candidate"]["violations"])

    # 验收 5:存在回归时门禁必须失败
    assert report["summary"]["REGRESSION"] == 1
