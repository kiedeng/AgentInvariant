# 行为契约规范(v0.1)

> 状态:随 v0.1 实现冻结。设计动机见 [design-baseline.md](design-baseline.md) 第 5.1、7.5、9 章。

## 1. 通用结构

契约在场景的 `contracts:` 列表中声明,每条规则:

```yaml
- type: <规则类型>
  severity: blocker | warning   # 默认 blocker
  <规则特有字段>...
```

- **blocker** 失败 → 该次运行判为失败(进入 Diff 分类);
- **warning** 失败 → 仅在报告中记录证据,不影响成败;
- 运行超时(`[TIMEOUT]`)无条件判失败,与契约无关。

评估上下文:工具事件序列(含被阻断的尝试)、最终回答文本、运行耗时、
运行前后状态快照(需配置 StateProvider)。

## 2. 规则参考

### 过程不变量

| 类型 | 字段 | 语义 |
| --- | --- | --- |
| `tool_called` | `tool` | 工具至少被调用(尝试)一次 |
| `tool_not_called` | `tool` | 工具从未被调用(尝试) |
| `happens_before` | `before`, `after` | `after` 的每次调用前必须已发生 `before`;`after` 未发生则空洞通过 |
| `max_occurrences` | `tool`, `max` | 调用(尝试)次数上限;重复副作用检测的主要手段 |
| `argument_constraint` | `tool`, `matcher` | 每次调用参数须通过命名匹配器 |
| `no_policy_violation` | — | 运行中不得出现 blocked / 守卫违规(常用 warning 取证) |

### 结果 / 状态契约

| 类型 | 字段 | 语义 |
| --- | --- | --- |
| `result_constraint` | `tool`, `field`, `equals` | 工具最后一次成功结果的字段值断言 |
| `output_contains` / `output_not_contains` | `value` | 最终回答文本包含 / 不包含子串 |
| `state_constraint` | `field`(点路径), `equals` | 运行后状态断言,如 `approval_rates.0.rate` |
| `state_unchanged` | — | 运行前后规范化状态完全一致(只读场景强断言) |

状态类规则在未配置 StateProvider 时**显式失败**,不静默通过。

### 资源预算

| 类型 | 字段 | 语义 |
| --- | --- | --- |
| `max_steps` | `max` | 工具调用总步数上限 |
| `max_latency_ms` | `max` | 运行耗时上限;超时中断的运行无耗时记录,判失败 |

### 参数匹配器注册表

| 名称 | 语义 |
| --- | --- |
| `sql_readonly` | SQL 必须以 SELECT 开头 |
| `no_sensitive_fields` | 参数不得包含身份证 / password / ssn 等敏感 Token |

匹配器同时可用作 runtime 守卫(`policies.<tool>.guard`,执行前阻断)与
`argument_constraint` 契约(事后取证)——同一规则,两个执行点。

## 3. 判定优先级与设计约束

1. 契约优先,不以 Baseline 路径为真理:候选用更少步骤完成同样正确的结果
   是改进或中性变化,不是失败;
2. Baseline 也接受同一套契约评估——历史上就违反业务规则的 Baseline 场景
   会判失败,使修复类变更被正确识别为 IMPROVEMENT;
3. 新引入的业务规则建议先以 `warning` 上线取证,团队确认后再升级为 `blocker`;
4. 所有内置规则均为确定性检查;语义评分(LLM Judge 等)只能作为外部补充,
   不参与门禁硬判定。
