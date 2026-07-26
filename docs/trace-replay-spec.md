# Trace、Fixture 与执行虚拟化规范(v0.1)

> 状态:随 v0.1 实现冻结。上游产品设计见 [design-baseline.md](design-baseline.md) 第 7、8 章。

## 1. 执行虚拟化

### 1.1 接入契约

Agent 代码对虚拟化零感知。测试引擎在构建 Agent 前包装工具列表:

```python
from agentinvariant.runtime import virtualize

tools = virtualize(raw_tools, policies, recorder, fixture_store)
agent = build_agent(tools)   # Agent 构建函数只接收工具列表
```

Agent 入口(Python Callable Adapter)契约:

```python
def entrypoint(tools: list[BaseTool], scenario: dict) -> str:
    """执行一个场景,返回最终回答文本。"""
```

### 1.2 执行模式

| 模式 | 行为 | 失败语义 |
| --- | --- | --- |
| `live` | 真实执行内层工具 | 异常向上抛出 |
| `mock` | 返回策略预设结果(可带 `latency_ms` 模拟延迟) | — |
| `replay` | 按参数规范化键查 Fixture | 未命中返回错误 JSON,不静默放行 |
| `blocked` | 不执行,记录 `violation` | 返回错误 JSON,Agent 可优雅降级 |
| `record` | 真实执行并把结果写入 FixtureStore | 同 live |

**默认安全策略**:未在 policies 中显式声明的工具一律 `blocked`。

### 1.3 ToolPolicy 字段

```yaml
tool_name:
  mode: live | mock | replay | blocked   # record 由引擎在 record 阶段自动切换
  effect: READ_ONLY | WRITE_REVERSIBLE | WRITE_IRREVERSIBLE | EXTERNAL_COMMUNICATION | CODE_EXECUTION
  result: <mock 返回值>
  latency_ms: 0
  guard: <matchers 注册表名称>    # 执行前参数守卫,违规即阻断
```

场景级 `tools:` 覆盖与项目级 `policies:` 做浅合并(场景字段优先)。
`record` 阶段引擎只把 `replay` 模式切换为 `record`,其余模式不变。

### 1.4 阻断与守卫的返回格式

被阻断的调用返回给模型的内容为 JSON 字符串:

```json
{"error": "工具 send_email 已被测试策略阻断,未真实执行。"}
{"error": "工具 execute_sql 参数违反策略: SQL 仅允许 SELECT(sql_readonly),未执行。"}
```

约定错误文案包含「未真实执行 / 未执行」,场景契约可据此断言。

## 2. Trace 事件模型

每次运行持有独立 `TraceRecorder`;每次工具调用(含被阻断的尝试)产生一条事件:

```json
{
  "index": 0,
  "tool": "execute_sql",
  "args": {"sql": "SELECT ..."},
  "mode": "replay",
  "result": {"rows": []},
  "error": null,
  "violation": null,
  "effect": "WRITE_REVERSIBLE"
}
```

语义:

- `index`:运行内严格递增,`happens_before` 等次序规则以此为准;
- `violation` 非空表示策略违规(blocked 尝试或守卫拦截);
- **被阻断的调用也是事件**:`tool_called` / `max_occurrences` 统计的是“尝试”。

## 3. Fixture 规范

- 存储:单 JSON 文件一个 Fixture 集;键为 `tool::canonicalize(args)`;
- 规范化:参数键排序 + 剔除 `ignore_fields`(默认 `request_id` / `trace_id` / `timestamp`);
- 匹配:v0.1 仅 exact(规范化后全等);未命中显式报错;
- 录制:`record` 阶段由 Baseline 真实执行产出,Baseline/Candidate 共享同一 Fixture 集,保证版本比较公平。

**待后续版本**:Schema 版本绑定与过期检测、subset/custom matcher、字段脱敏管道。

## 4. OTLP 导出

Span 结构:每场景 × 每版本一条 `invoke_agent` 根 Span,每条工具事件一条 `execute_tool` 子 Span。

| 属性 | 示例 |
| --- | --- |
| `gen_ai.operation.name` | `invoke_agent` / `execute_tool` |
| `gen_ai.agent.name` / `gen_ai.agent.version` | `finance-agent` / `v1.4.0` |
| `gen_ai.tool.name` | `execute_sql` |
| `agent.release.run_role` | `baseline` / `candidate` |
| `agent.release.scenario_id` | `finance-003` |
| `agent.release.outcome` | `REGRESSION` |
| `agent.release.execution_mode` | `replay` |
| `agent.release.tool_effect` | `WRITE_REVERSIBLE` |
| `agent.release.violation` | 违规原因(如有) |
| `agent.release.contract_result` | 契约结果摘要 JSON |

**隐私默认**:`record_content: false` 时不导出回答文本、工具参数与结果;
开启后内容截断到 4000 字符。端点通过 `otlp.endpoint` 或 `--otlp-endpoint` 指定,
Phoenix / Langfuse / 通用 Collector 的 OTLP HTTP 端点均可接收。
