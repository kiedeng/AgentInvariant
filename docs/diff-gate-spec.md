# Behavior Diff 与 Release Gate 规范(v0.1)

> 状态:随 v0.1 实现冻结。设计动机见 [design-baseline.md](design-baseline.md) 第 7.6、7.7、9.3 章。

## 1. 场景级判定

每个场景比较 Baseline 与 Candidate 各一次运行(`repeat > 1` 时聚合,见 §3):

```text
if baseline_success and not candidate_success: REGRESSION
elif not baseline_success and candidate_success: IMPROVEMENT
elif both success:
    NO_CHANGE       若工具序列、最终输出、运行后状态全部一致
    NEUTRAL_CHANGE  否则(路径 / 非关键输出变化,契约均满足)
else: REVIEW_REQUIRED   # 两侧均失败,需人工确认
```

`success` 由 Contract Engine 判定:无 blocker 契约失败且未超时。

## 2. 比较报告(report.json)

```json
{
  "project": "finance-agent",
  "baseline": "finance-agent v1.3.0",
  "candidate": "finance-agent v1.4.0",
  "summary": {"REGRESSION": 1, "IMPROVEMENT": 4, "NEUTRAL_CHANGE": 10, "NO_CHANGE": 0, "REVIEW_REQUIRED": 1},
  "comparisons": [
    {
      "scenario_id": "finance-003",
      "outcome": "REGRESSION",
      "baseline":  { "success": true,  "final_output": "...", "tool_sequence": [...],
                     "contracts": [...], "violations": [...], "state_after": {...},
                     "duration_ms": 12.5, "timed_out": false, "repetitions": 1, "pass_rate": 1.0,
                     "trace": [...] },
      "candidate": { "...同上..." },
      "diff": {
        "tools_added": ["check_permission"],
        "tools_removed": [],
        "output_changed": true,
        "state_changed_keys": [],
        "new_violations": []
      }
    }
  ]
}
```

约束:

- 每个 REGRESSION 必须能在 `candidate.contracts` 中找到失败的 blocker 规则(证据优先);
- `state_changed_keys` 为两版本运行后规范化状态不一致的键(需 StateProvider);
- 报告是自包含的:门禁、JUnit、HTML 都只从该 JSON 派生。

## 3. 重复运行聚合

`runner.repeat = N` 时每侧运行 N 次:

- `success` = 全部 N 次成功(硬规则任何一次违反即失败,设计基线 9.4);
- `pass_rate` = 成功次数 / N,随报告输出;
- Trace / 输出取第一次运行作为代表。

## 4. Release Gate

```yaml
release_gate:
  max_new_regressions: 0            # REGRESSION 数上限
  max_review_required: 1            # REVIEW_REQUIRED 数上限(null 不限制)
  min_candidate_success_rate: 0.95  # 候选成功场景占比下限
  max_candidate_violations: null    # 候选侧策略违规次数上限(null 不限制)
```

输出:

```json
{"passed": false,
 "reasons": ["新增回归 1 个(允许 0): ['finance-003']", "候选成功率 88% 低于阈值 95%"],
 "metrics": {"regressions": 1, "review_required": 1, "candidate_success_rate": 0.875,
             "candidate_violations": 4, "scenario_count": 16}}
```

退出码约定(CI 消费):

| 码 | 含义 |
| --- | --- |
| 0 | 门禁通过,允许发布 |
| 1 | 门禁失败,阻止发布 |
| 2 | 输入错误(缺文件、配置非法) |

## 5. CLI 工作流

```bash
agentinvariant record  --config agentinvariant.yaml   # Baseline 录制 Fixture
agentinvariant compare --config agentinvariant.yaml \
    [--otlp-endpoint http://localhost:6006/v1/traces]  # 比较 + 报告 + 门禁
agentinvariant gate --result .agentinvariant/report.json --config gate.yaml  # 单独复验门禁
agentinvariant scaffold --result .agentinvariant/report.json \
    --out contracts-draft.yaml [--side baseline]       # 从实际行为生成契约草稿
```

`scaffold` 生成的草稿全部为 `severity: warning`,须人工审查后把关键规则
升级为 blocker —— 草稿绝不自动成为门禁硬规则(设计基线 15.1 风险缓解)。

产物目录(`output_dir`,默认 `.agentinvariant/`,建议 gitignore):
`report.json`、`gate.json`、`junit.xml`、`report.html`、`fixtures/`。
