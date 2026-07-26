# 生产级 AI Agent 变更回归与发布保障系统

**产品与技术设计方案（最终基线版）**

> 定位：执行虚拟化 × 行为契约 × 版本回归 × 发布门禁

| 文档版本 | v1.0 |
| --- | --- |
| 文档日期 | 2026 年 7 月 |
| 项目阶段 | 设计基线 / 编码前 |
| 项目名称 | 待定（不建议直接使用 AgentGuard / AgentDiff） |

**核心目标：让团队在部署 Agent 变更前，知道会破坏什么。**

## 目录

0. 本次最终调整说明

1. 执行摘要

2. 市场与生态研究结论

3. 产品定位、边界与目标用户

4. 典型场景与用户工作流

5. 产品原则与核心概念

6. 总体架构设计

7. 核心功能设计

8. 数据模型与 Trace 规范

9. 行为契约与差异判定

10. 与 Langfuse、LangSmith、Phoenix 的组合方式

11. 安全、隐私与威胁模型

12. MVP 范围与验收标准

13. 阶段路线图与实施计划

14. 仓库结构与技术选型

15. 关键风险与决策记录

附录 A. 配置示例

附录 B. 术语表

附录 C. 研究来源

## 0. 本次最终调整说明

> 最终结论：项目可以独立使用，也可以作为 Langfuse、LangSmith、Phoenix 等观测与评测平台的下游执行保障层。最终方案不再以替代这些平台为目标。

| 调整项 | 原先设想 | 最终调整 |
| --- | --- | --- |
| 产品关系 | 替代 LangSmith / 做开源内网版 | 独立内核 + 平台适配器，优先组合使用 |
| 核心壁垒 | Trace、评测、工具回放全部自建 | 聚焦执行虚拟化、业务契约、行为变更分析、发布门禁 |
| Trace 体系 | 自定义事件协议 | 兼容 OpenTelemetry / OpenInference，仅增加项目扩展字段 |
| 测试判定 | 新旧路径尽量一致 | 结果契约 + 过程不变量 + 资源预算，不要求完整路径相同 |
| 沙箱定位 | 通用 API 沙箱作为唯一差异点 | 支持企业自有工具、生产 Trace 资产化和版本发布闭环；可接入外部沙箱 |
| 首版产品 | 先搭完整 Web 平台 | 先完成本地 CLI/SDK 垂直闭环，随后接 Web 和平台集成 |
| 项目命名 | AgentGuard / AgentDiff | 均已有同名或近似项目，先使用描述性工作代号 |

为什么需要这些调整：

- Langfuse 的核心平台可免费自托管，Phoenix 也可完整本地部署，因此“可私有化”本身不足以形成产品壁垒。

- LangSmith 已具备数据集、实验、回归比较和在线/离线评测；复制这些能力会造成正面重复建设。

- Agent-Diff 已经在 Slack、Linear、Box、Google Calendar 等第三方 API 的沙箱副本和状态差异评估上形成明确实现，因此本项目必须重点服务任意企业自有工具和真实 Agent 版本变更，而不是只做预制 SaaS 沙箱。

- AgentGuard、AgentDiff 等名称已经被多个产品或研究项目使用，正式开源前应单独完成命名检索。

## 1. 执行摘要

项目定义：一个面向生产级 AI Agent 的执行虚拟化、行为回归和发布门禁引擎。

它解决的不是“Agent 回答是否好看”，而是下面这个工程问题：

> 核心问题：当模型、Prompt、工作流节点、工具 Schema、权限策略、知识库、记忆或运行时发生变化后，如何在不触发真实副作用的条件下，判断候选版本是否破坏了既有业务场景。

项目需要对一次 Agent 变更给出四类答案：

1. 业务结果是否仍然正确，是否出现历史成功场景回归。

2. 关键过程是否违反业务不变量，例如跳过权限检查、审批、风控或幂等控制。

3. 数据库写入、退款、邮件、消息、工单等副作用是否符合预期且没有真实执行。

4. 延迟、Token、成本、工具次数、失败率是否满足发布阈值。

```text
生产 Trace / 测试场景
        ↓
Baseline Agent ─┐
                ├─ 固定工具环境 → 行为契约 → Behavior Diff → Release Gate
Candidate Agent ┘
        ↓
HTML / JSON / JUnit / OTLP
        ↓
GitHub Actions / Jenkins / Langfuse / LangSmith / Phoenix
```

最终产品关系：

| 系统 | 主要职责 |
| --- | --- |
| Langfuse / LangSmith / Phoenix | 生产 Trace、数据集、实验管理、评测、可视化、团队协作 |
| 本项目核心引擎 | 安全执行、工具虚拟化、状态与过程契约、行为差异、发布准入 |
| CI/CD 系统 | 根据发布门禁结果阻止合并、部署或升级 |

## 2. 市场与生态研究结论

### 2.1 已经成熟或正在快速成熟的能力

| 能力类别 | 代表平台 | 成熟度判断 |
| --- | --- | --- |
| Trace 与可观测 | Langfuse、LangSmith、Phoenix | 较成熟，不应重复搭建完整平台 |
| 数据集与实验 | LangSmith、Langfuse、Phoenix、Braintrust | 较成熟，可作为上游或结果接收方 |
| LLM / Agent 评测 | Promptfoo、DeepEval、LangSmith | 竞争激烈，不作为主定位 |
| 生产问题转回归案例 | LangSmith、Langfuse 等 | 已有基础闭环，但执行环境仍需用户自行构造 |
| API 沙箱与状态差异 | Agent-Diff | 已出现清晰实现，尤其针对预制第三方 SaaS API |
| 任意企业工具版本回归 | 分散在内部工程和小型框架中 | 仍缺统一、轻量、可组合的发布保障层 |

### 2.2 现有平台能力边界

- LangSmith 可以从历史生产 Trace 或人工案例创建数据集，执行候选版本，比较实验结果并查看回归和改善。

- Langfuse 和 Phoenix 都能自托管，具备 Trace、数据集、实验和评测，因此本项目不能以“本地可部署的观测平台”自居。

- OpenTelemetry 和 OpenInference 已经提供 Agent、Workflow、模型、工具调用、Token 等语义约定，项目应复用而不是另建封闭格式。

- Agent-Diff 通过第三方 API 副本和状态差异契约验证结果，说明“结果状态契约”比严格匹配推理路径更可靠。

### 2.3 仍然值得解决的工程空缺

- 将企业自有 Python 工具、MCP 工具、内部 HTTP API 快速切换为 live、mock、replay、blocked 模式。

- 从生产 Trace 自动生成可脱敏、可版本化的工具 Fixture，而不是手工维护大量 Mock。

- 同时验证最终状态、关键流程不变量和资源预算，而不是只输出一个语义评分。

- 比较完整 Agent 版本：代码、Graph、Prompt、工具 Schema、模型和策略配置共同变化时，定位受影响场景。

- 将结果作为 CI 发布门禁，同时把 Trace 与评分导回现有观测平台。

- 在内网或断网环境中以 CLI/SDK 独立运行，不强迫用户部署另一套大型平台。

## 3. 产品定位、边界与目标用户

### 3.1 产品定位

> 一句话定位：生产级 AI Agent 的变更回归与发布保障执行层。

英文描述建议：

```text
A local-first execution virtualization and release assurance engine for production AI agents.
```

核心宣传语建议：

```text
Know what breaks before deploying an agent change.
```

### 3.2 目标用户

| 用户 | 典型需求 | 优先级 |
| --- | --- | --- |
| Agent 开发工程师 | 修改流程、Prompt、工具后做本地回归 | P0 |
| AI 平台 / 架构团队 | 统一多个项目的发布门禁和工具安全测试 | P0 |
| 金融、政务等内网团队 | 不上传 Trace，避免真实副作用 | P0 |
| 使用 Langfuse / LangSmith 的团队 | 补齐安全执行和发布准入 | P1 |
| 模型评测研究者 | 比较模型在固定业务环境中的行为 | P2 |

### 3.3 明确不做的内容

- 不负责开发、编排或托管 Agent。

- 不做完整的线上 Trace 查询和可观测后台。

- 不做 Prompt 管理中心和标注平台。

- 不以 LLM-as-a-Judge 或答案质量评测为主产品。

- 不保证模型执行完全确定性，只固定外部环境并检查契约。

- 不在首版承担自动灰度、自动回滚和生产流量路由。

## 4. 典型场景与用户工作流

| 变更类型 | 需要保障的内容 |
| --- | --- |
| 新增权限节点 | 验证合法请求是否误拦截、越权请求是否漏拦截、多轮上下文是否丢失。 |
| 更换模型 | 在相同输入和工具环境下比较任务成功率、参数正确率、规则违规、成本和延迟。 |
| 修改工具 Schema | 验证参数兼容性、默认值、类型、枚举值和模型理解是否发生回归。 |
| 调整 Prompt | 发现查询时间范围、确认逻辑、回答格式和工具选择的隐性变化。 |
| 修改重试与异常处理 | 检查是否重复执行支付、邮件、退款等副作用工具。 |
| 升级 Agent SDK | 检查流式事件、Tool Call 解析、状态恢复和异常类型是否变化。 |
| 知识库或记忆变更 | 比较召回、上下文继承和最终业务状态，但不把语义评分作为唯一判据。 |

### 4.1 标准用户流程

```text
1. 从人工案例、生产 Trace 或现有 Dataset 选择场景
2. 注册 Baseline 与 Candidate Agent 版本
3. 为工具配置 live / mock / replay / blocked
4. 定义结果契约、过程不变量和资源预算
5. 批量执行两个版本
6. 生成每个场景的行为差异和总体回归报告
7. 执行 Release Gate
8. 将结果写入 CI，并可导出到 Langfuse / LangSmith / Phoenix
```

## 5. 产品原则与核心概念

| 原则 | 说明 |
| --- | --- |
| 独立内核 | 不依赖任何观测平台即可运行。 |
| 可组合 | 可导入、导出或联动 Langfuse、LangSmith、Phoenix。 |
| 契约优先 | 优先检查业务结果和不变量，不要求完整路径相同。 |
| 副作用默认安全 | 不可逆工具默认 blocked，可逆写操作默认 mock。 |
| 标准优先 | 使用 OpenTelemetry / OpenInference 语义。 |
| 证据优先 | 输出结构化差异和证据，不夸大自动根因推断。 |
| 本地优先 | CLI/SDK 能在离线环境完成核心流程。 |
| 渐进接入 | 从装饰器、Adapter 或 OTLP 导入中选择最低接入成本方式。 |

### 5.1 三类契约

| 契约 | 回答的问题 | 示例 |
| --- | --- | --- |
| 结果 / 状态契约 | 任务最终是否完成正确？ | 工单已创建；退款状态正确；报表包含指定区域 |
| 过程不变量 | 执行过程中有没有违反硬规则？ | SQL 前必须鉴权；高额退款前必须审批 |
| 资源预算 | 代价是否可以接受？ | P95 延迟、Token、成本、最大步骤数 |

### 5.2 三种回放含义

| 类型 | 含义 | 项目承诺 |
| --- | --- | --- |
| 输入重放 | 相同用户输入重新执行候选版本 | 支持 |
| 环境回放 | 工具返回、错误、延迟和外部状态固定 | 核心能力 |
| 完整确定性回放 | 模型与所有内部调度完全一致 | 不承诺 |

## 6. 总体架构设计

```text
┌────────────────────────────────────────────────────────────┐
│ CLI / CI / Python SDK                                     │
│ record · import · compare · replay · gate · report         │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ Scenario & Experiment Runner                               │
│ Baseline Runner │ Candidate Runner │ Repetition │ Isolation │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ Agent Adapter Layer                                       │
│ Python Callable │ LangGraph │ Future: OpenAI Agents / MCP   │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ Execution Virtualization                                  │
│ Tool Router │ Live │ Mock │ Replay │ Blocked │ Sandbox      │
└───────────────────────────┬────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────┐
│ OTEL / OpenInference Trace + State Snapshot                │
└───────────────┬───────────────────────────────┬────────────┘
                │                               │
┌───────────────▼──────────────┐  ┌────────────▼─────────────┐
│ Contract Engine             │  │ Behavior / State Diff     │
│ Result · Invariant · Budget │  │ Alignment · Classification│
└───────────────┬──────────────┘  └────────────┬─────────────┘
                └──────────────────┬────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────┐
│ Release Gate & Report                                      │
│ HTML │ JSON │ JUnit │ OTLP │ Platform Adapters             │
└────────────────────────────────────────────────────────────┘
```

### 6.1 分层说明

| 层 | 职责 | 是否核心 |
| --- | --- | --- |
| Adapter | 把不同 Agent 调用方式转换为统一 RunContext | 是 |
| Execution Virtualization | 截获工具、注入 Fixture、阻止副作用 | 核心壁垒 |
| Trace / State | 记录可观察行为与业务状态快照 | 是 |
| Contract Engine | 检查结果、不变量和预算 | 核心壁垒 |
| Diff Engine | 对齐新旧行为、状态和指标 | 核心壁垒 |
| Release Gate | 形成可机器执行的发布决策 | 是 |
| Platform Adapter | 连接 Langfuse、LangSmith、Phoenix | 可选扩展 |
| Web UI | 管理与可视化 | 后续产品化 |

## 7. 核心功能设计

### 7.1 Agent 版本指纹

一个 Agent 版本由以下组合共同确定：

- 源代码 Git Commit 与依赖锁文件。

- 模型、供应商、温度、推理参数和路由配置。

- System Prompt、模板和 Prompt 版本。

- 工作流 Graph / 节点及其配置。

- 工具定义、描述、Schema 和副作用类型。

- 权限、Guardrail、审批和重试策略。

- 知识库、语义层和记忆配置版本。

```yaml
agent:
  name: finance-agent
  version: 1.4.0
source:
  git_commit: 82db392
model:
  provider: openai-compatible
  name: deepseek-v4
prompt:
  hash: sha256:...
workflow:
  hash: sha256:...
tools:
  schema_hash: sha256:...
policy:
  hash: sha256:...
```

### 7.2 Trace 与生产案例导入

- 原生 SDK 录制：Python 装饰器和 LangGraph Adapter。

- OTLP / OpenInference 导入：从 Phoenix、Langfuse 或通用 Collector 获取 Trace。

- 平台 Adapter：从 LangSmith Dataset、Langfuse Dataset 等拉取输入和元数据。

- 导入时完成字段脱敏、Fixture 提取、工具副作用分类和数据版本标记。

### 7.3 工具执行虚拟化

| 模式 | 行为 | 适用工具 |
| --- | --- | --- |
| live | 真实执行并记录结果 | 只读数据库、测试环境查询 |
| mock | 返回场景预设结果 | 错误注入、边界条件、写操作 |
| replay | 根据历史 Fixture 返回结果 | 生产问题复现、版本公平比较 |
| blocked | 不执行并记录策略违规 | 退款、支付、外发消息、危险命令 |
| sandbox | 在隔离环境执行 | 代码、Shell、浏览器或容器任务；后续阶段 |

工具必须声明副作用等级：

```text
READ_ONLY
WRITE_REVERSIBLE
WRITE_IRREVERSIBLE
EXTERNAL_COMMUNICATION
CODE_EXECUTION
```

> 默认安全策略：不可逆写操作、外部通信和代码执行在测试中默认不得 live；必须显式授权。

### 7.4 Fixture Store

- 保存规范化后的工具参数、结果、错误、延迟和来源 Trace。

- Fixture 必须绑定工具 Schema 版本，避免旧 Fixture 静默匹配新参数。

- 支持 exact、canonicalized、subset 和 custom matcher；MVP 先实现 exact 与 custom。

- 敏感字段可哈希、掩码或用合成值替换。

- 对动态字段提供忽略规则，例如 request_id、timestamp、trace_id。

### 7.5 Contract Engine

| 规则类型 | 示例 |
| --- | --- |
| tool_called / tool_not_called | 必须调用权限工具；不得调用写 SQL 工具 |
| happens_before | check_permission 必须早于 execute_sql |
| max_occurrences | send_email 最多一次 |
| argument_constraint | SQL 仅允许 SELECT；金额必须等于订单可退款金额 |
| result_constraint | 权限结果必须 allowed=true 后才能继续 |
| state_constraint | 最终工单状态为 CREATED |
| no_duplicate_side_effect | 幂等键相同的副作用不得重复 |
| budget | 最大步骤、Token、成本和延迟 |

### 7.6 Behavior / State Diff

Diff 不应只比较工具调用数组，而要同时比较：

- 最终业务输出和结构化状态。

- 节点、模型、工具和异常 Span。

- 工具参数的规范化差异。

- 副作用的新增、删除、重复和状态变化。

- 契约规则的通过、失败和严重级别变化。

- Token、成本、延迟、步骤数和重试数。

差异分类：

```text
REGRESSION       原来通过，现在失败或违反硬规则
IMPROVEMENT      原来失败，现在通过
EXPECTED_CHANGE  配置声明为预期变化
NEUTRAL_CHANGE   路径变化但契约与预算均满足
REVIEW_REQUIRED  系统无法可靠判定，需要人工确认
```

### 7.7 Release Gate

```yaml
release_gate:
  max_new_regressions: 0
  max_blocker_violations: 0
  min_success_rate: 0.95
  max_p95_latency_increase_percent: 20
  max_cost_increase_percent: 15
  require_manual_review_for:
    - WRITE_IRREVERSIBLE
    - EXTERNAL_COMMUNICATION
```

> 机器可执行：Release Gate 必须返回标准退出码和结构化 JSON，使 GitHub Actions、Jenkins、GitLab CI 能直接阻止发布。

## 8. 数据模型与 Trace 规范

### 8.1 核心对象

```text
Project
├── AgentVersion
├── Dataset
│   └── Scenario
├── BehaviorContract
├── FixtureSet
├── Experiment
│   ├── BaselineRun
│   └── CandidateRun
├── Trace / Span
├── StateSnapshot
├── ScenarioComparison
└── ReleaseGateResult
```

### 8.2 Trace 标准

内部以 OpenTelemetry Span 为主，优先复用 GenAI / OpenInference 属性，并增加少量扩展字段。

| 字段 | 用途 |
| --- | --- |
| gen_ai.agent.name / version | Agent 名称与版本 |
| gen_ai.operation.name | invoke_agent、invoke_workflow、execute_tool 等 |
| gen_ai.tool.name | 工具名称 |
| gen_ai.tool.call.arguments / result | 结构化工具参数与结果 |
| gen_ai.usage.* | Token 统计 |
| agent.release.run_role | baseline / candidate / shadow |
| agent.release.scenario_id | 场景标识 |
| agent.release.tool_effect | 副作用等级 |
| agent.release.execution_mode | live / mock / replay / blocked / sandbox |
| agent.release.contract_result | 契约检查结果 |

> 隐私要求：Prompt、工具参数和工具结果可能包含 PII 或商业敏感数据。录制默认必须支持关闭内容、字段白名单、截断、哈希和脱敏。

### 8.3 状态快照

对于有写操作的 Agent，仅比较 Trace 不够。需要通过 State Provider 获取运行前后状态：

```python
class StateProvider(Protocol):
    async def snapshot_before(self, scenario, context) -> dict: ...
    async def snapshot_after(self, scenario, context) -> dict: ...
    def normalize(self, state: dict) -> dict: ...
```

MVP 先提供：

- SQLite / PostgreSQL 查询快照示例。

- Python 自定义 StateProvider。

- JSON 状态快照。

## 9. 行为契约与差异判定

### 9.1 判定优先级

1. 阻断级业务不变量。

2. 最终状态和业务结果。

3. 副作用正确性与幂等性。

4. 错误、补偿和恢复行为。

5. 资源预算。

6. 路径、文本和非关键参数差异。

### 9.2 为什么不能严格匹配完整路径

> 示例：候选版本可能用 3 次工具调用完成旧版本 5 次调用的任务。如果最终状态正确、权限和审批均未跳过，则应视为改进或中性变化，而不是失败。

### 9.3 场景级判定算法（初版）

```text
if blocker_invariant_failed:
    outcome = REGRESSION
elif baseline_success and not candidate_success:
    outcome = REGRESSION
elif state_contract_failed or side_effect_contract_failed:
    outcome = REGRESSION
elif budget_exceeded_beyond_gate:
    outcome = REGRESSION
elif not baseline_success and candidate_success:
    outcome = IMPROVEMENT
elif only_noncritical_path_changed:
    outcome = NEUTRAL_CHANGE
else:
    outcome = REVIEW_REQUIRED
```

### 9.4 非确定性处理

- 支持单场景重复运行 N 次，计算通过率、规则违规率和成本分布。

- 对于模型输出文本，不默认使用完全相等；优先使用结构化结果或外部 Evaluator。

- 硬不变量任何一次违反都可配置为阻断。

- 对随机性高的场景，发布门禁使用统计阈值而不是单次快照。

- 允许接入 Promptfoo、DeepEval、LangSmith Evaluator 作为补充评分。

## 10. 与 Langfuse、LangSmith、Phoenix 的组合方式

### 10.1 总体关系

```text
Langfuse / LangSmith / Phoenix
生产 Trace、数据集、实验资产、评测和团队协作
                    ↓ 输入 / 导入
本项目核心引擎
安全执行、Fixture、状态契约、过程不变量、Behavior Diff、Release Gate
                    ↓ 输出 / 导出
CI/CD + 原观测平台
```

### 10.2 三种部署模式

| 模式 | 结构 | 适用情况 |
| --- | --- | --- |
| 独立模式 | CLI + SQLite/JSONL + HTML | 离线、个人项目、轻量 CI |
| 开源组合 | 本项目 + Langfuse 或 Phoenix | 企业私有化、完整可观测和团队协作 |
| 商业组合 | 本项目 + LangSmith / Braintrust | 已采购平台，需要补齐执行安全和门禁 |

### 10.3 Langfuse Adapter

- 导入 Trace、Dataset Item、运行元数据和 Score。

- 将生产 Trace 转为 Scenario 和 Fixture。

- 将回归结果写回为 Score、Metadata 或独立 Trace。

- 通过 OTLP 或 SDK 发送测试运行 Trace。

- 不复制 Langfuse 的 Prompt、数据集和 Trace 管理 UI。

### 10.4 LangSmith Adapter

- 从 Dataset 获取测试输入和 reference outputs。

- 以 Target Function 或外部 Runner 方式运行候选版本。

- 将契约结果作为 Evaluator / Feedback Key 写入 Experiment。

- 将本项目生成的行为差异摘要作为实验 Metadata。

- 在 LangSmith 继续完成实验对比和人工审查。

### 10.5 Phoenix Adapter

- 通过 OTLP 原生发送 Trace。

- 利用 OpenInference Instrumentation 降低框架接入成本。

- 将本项目运行结果与 Phoenix 数据集、实验和评测组合。

- 在完全离线环境中使用 Phoenix 作为观测 UI。

### 10.6 与 Agent-Diff 的关系

| 维度 | Agent-Diff | 本项目 |
| --- | --- | --- |
| 主要目标 | 模型评测、训练和第三方 API 任务基准 | 生产 Agent 版本变更回归与发布保障 |
| 环境 | Slack、Linear、Box、Calendar 等 API 副本 | 任意企业自有工具、数据库、MCP 和内部 API |
| 判定重点 | 环境 State Diff | State Contract + 过程不变量 + 资源预算 + 版本比较 |
| 数据来源 | 预制模板与任务集 | 生产 Trace、历史失败、人工业务案例 |
| 交付形式 | 评测环境与 Benchmark | CLI/CI 门禁与平台适配层 |
| 组合可能 | 可作为特定第三方 API 的 Sandbox Provider | 可接入其环境作为一个执行后端 |

## 11. 安全、隐私与威胁模型

### 11.1 主要风险

| 风险 | 后果 | 控制措施 |
| --- | --- | --- |
| 测试误连生产工具 | 真实退款、邮件、数据修改 | 默认阻断副作用；环境白名单；显式 live 授权 |
| Fixture 含敏感数据 | PII 或商业数据泄漏 | 脱敏、加密、字段白名单、Secret 扫描 |
| 工具参数中存在注入 | SQL / Shell / HTTP 风险 | AST 校验、Sandbox、域名与命令白名单 |
| Fixture 过期 | 错误的测试结论 | Schema 版本绑定、过期提示、重新录制策略 |
| 基线本身存在缺陷 | 把旧错误固化为正确行为 | 业务契约优先，不以 Baseline 路径为真理 |
| 并发状态污染 | 测试互相影响 | 每场景隔离状态、事务回滚、唯一命名空间 |
| 测试数据被恶意 Trace 污染 | 注入 Prompt 或危险工具结果 | Trace 视为不可信输入；解析和内容隔离 |

### 11.2 默认安全策略

- 所有工具默认为 blocked，必须按项目或场景显式开放。

- READ_ONLY 工具可 live，但需要配置允许的主机、数据库和账户。

- WRITE_* 和 EXTERNAL_COMMUNICATION 默认只允许 mock / replay。

- 代码与 Shell 工具只能在沙箱中执行。

- CI 日志默认不打印完整 Prompt、参数和结果。

- Fixture 文件支持静态加密和 Git 忽略建议。

## 12. MVP 范围与验收标准

> MVP 的定义：MVP 不是没有设计的 Demo，而是在完整架构下优先实现最关键、风险最高的垂直闭环。

### 12.1 MVP 必须实现

| 模块 | MVP 能力 |
| --- | --- |
| Python SDK | @agent_run、@virtual_tool 或等效接口 |
| Adapter | Python Callable + LangGraph |
| 工具模式 | live、mock、replay、blocked |
| Fixture | JSON/YAML 存储，exact + custom matcher |
| Trace | OTEL/OpenInference 风格本地记录 |
| State Provider | Python 自定义 + JSON / SQL 示例 |
| Scenario | YAML 输入、Fixture、Contract 和预算 |
| Runner | Baseline / Candidate 批量运行与超时隔离 |
| Contract | 10 个左右确定性内置规则 |
| Diff | 工具、参数、状态、错误和指标差异 |
| Gate | 结构化结果和非零退出码 |
| Report | HTML、JSON、JUnit XML |
| 示例 | 金融 SQL Agent V1/V2 |

### 12.2 MVP 不实现

- 多租户 Web 平台、RBAC、项目后台。

- 大规模 Trace 存储和检索。

- TypeScript SDK。

- MCP 通用代理、浏览器和容器沙箱。

- 实时生产 Shadow 流量和自动回滚。

- 自动根因分析和自动修复。

- 通用 LLM Judge 平台。

### 12.3 MVP 演示场景

```text
Baseline V1:
用户 → 指标识别 → SQL 生成 → 数据查询 → 回答

Candidate V2:
用户 → 指标识别 → 权限检查 → 部门标准化 → SQL 生成 → 数据查询 → 回答
```

至少覆盖以下 20~30 个场景：

- 合法查询、越权查询、缺少部门编码、部门简称。

- 多轮“那重庆呢”、时间范围不明确、数据为空。

- SQL 超时、工具异常、Prompt Injection、敏感字段查询。

- 请求发送报告、重复查询、重复邮件、SQL 写操作。

### 12.4 MVP 验收标准

1. 能在不真实执行邮件、写 SQL 和退款工具的情况下完成候选 Agent 全流程。

2. 能发现新增权限节点导致的合法请求误拒绝。

3. 能发现 Agent 跳过权限、重复副作用和 SQL 写操作。

4. 能比较两个版本的状态、工具、参数、错误、延迟和 Token。

5. 能根据 YAML Release Gate 返回成功或失败退出码。

6. 能生成一份开发者无需打开代码即可理解的 HTML 报告。

7. 能将 Trace 通过 OTLP 发往至少一个外部平台，优先 Phoenix 或 Langfuse。

## 13. 阶段路线图与实施计划

| 阶段 | 目标 | 主要产出 | 完成条件 |
| --- | --- | --- | --- |
| 阶段 0：设计与技术验证 | 消除最高技术风险 | 接口规范、POC、决策记录 | 工具截获、Fixture 注入、Trace 对齐均验证可行 |
| 阶段 1：MVP Core | 完成本地垂直闭环 | SDK、Runner、Contract、Diff、Gate、报告 | 金融示例满足验收标准 |
| 阶段 2：开源 v0.1 | 让外部开发者可用 | 文档、GitHub Action、插件接口、CI | 新用户按 Quickstart 独立跑通 |
| 阶段 3：生态集成 | 与现有平台组合 | Langfuse、LangSmith、Phoenix Adapter | 可完成 Trace/数据集导入和结果回写 |
| 阶段 4：平台化 | 团队协作和资产管理 | FastAPI、React、PostgreSQL | 支持项目、版本、数据集和报告管理 |
| 阶段 5：生产保障 | Shadow 与持续回归 | 采样、影子执行、告警、审批 | 支持真实发布流程试点 |

### 13.1 编码前必须完成的技术 POC

1. LangGraph ToolNode / Tool 调用的非侵入式截获和替换。

2. 同一场景在两个 Agent 版本下隔离运行，确保状态不串扰。

3. 历史 Fixture 注入后 Agent 能继续完成后续推理。

4. 增加工作流节点后，Trace 能按逻辑名称和父子关系进行对齐。

5. 状态快照能够忽略动态字段并输出稳定 Diff。

6. OTLP Trace 能被 Phoenix 或 Langfuse 正确接收和展示。

### 13.2 建议里程碑

| 里程碑 | 范围 | 建议节奏 |
| --- | --- | --- |
| M0 | 完成产品边界、Trace、Contract、Tool Runtime 规范 | 第 1~2 周 |
| M1 | 单 Agent Trace + 工具 Mock/Replay POC | 第 3 周 |
| M2 | Baseline/Candidate Runner + State Diff | 第 4~5 周 |
| M3 | Contract Engine + Release Gate | 第 6 周 |
| M4 | HTML/JUnit 报告 + 金融示例 | 第 7 周 |
| M5 | 文档、CI、首个外部平台 Adapter | 第 8 周 |

> 说明：里程碑是建议顺序，不是承诺工期。每个阶段应以验收结果为准调整设计。

## 14. 仓库结构与技术选型

### 14.1 技术选型

| 领域 | 选型 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.12+ | Agent 生态和用户基础最匹配 |
| CLI | Typer | 类型友好、文档生成方便 |
| 数据模型 | Pydantic | Schema、校验和序列化成熟 |
| Trace | OpenTelemetry + OpenInference | 生态兼容，便于导出 |
| SQL 检查 | SQLGlot | AST 级只读与方言处理 |
| 本地存储 | SQLite + JSONL | MVP 简单、可离线 |
| 报告 | Jinja2 + 静态 HTML | 无服务即可查看 |
| 测试 | pytest | 自身引擎验证和插件生态 |
| 后续 API | FastAPI | 与你现有技术栈一致 |
| 后续 Web | React + TypeScript | 产品化阶段使用 |

### 14.2 推荐仓库结构

```text
agent-release-assurance/
├── packages/
│   ├── core/
│   │   ├── adapters/
│   │   ├── runtime/
│   │   ├── fixtures/
│   │   ├── tracing/
│   │   ├── state/
│   │   ├── contracts/
│   │   ├── diff/
│   │   ├── gate/
│   │   └── reports/
│   └── integrations/
│       ├── langfuse/
│       ├── langsmith/
│       ├── phoenix/
│       └── github_actions/
├── examples/
│   └── finance_sql_agent/
├── docs/
│   ├── product-requirements.md
│   ├── architecture.md
│   ├── trace-replay-spec.md
│   ├── behavior-contract-spec.md
│   ├── diff-gate-spec.md
│   └── threat-model.md
├── tests/
├── pyproject.toml
└── README.md
```

### 14.3 包拆分建议

```bash
pip install agent-release-core
pip install "agent-release-core[langgraph]"
pip install "agent-release-core[langfuse]"
pip install "agent-release-core[langsmith]"
pip install "agent-release-core[phoenix]"
```

正式包名需在编码前重新检索 PyPI、npm、GitHub 和商标使用情况。

## 15. 关键风险与决策记录

| 编号 | 风险 / 决策 | 当前结论 |
| --- | --- | --- |
| D-01 | 是否做 LangSmith 替代品 | 否。定位为独立执行保障层和补充组件。 |
| D-02 | 是否自建完整 Trace 后台 | 否。核心保留必要本地存储，复杂查询交给外部平台。 |
| D-03 | 是否严格复现 Agent 路径 | 否。固定环境，验证结果和不变量。 |
| D-04 | 是否以通用 API 沙箱为唯一卖点 | 否。Agent-Diff 已覆盖部分场景；重点转向企业工具、生产 Trace 和发布闭环。 |
| D-05 | 是否第一版做 Web UI | 否。CLI、SDK、HTML 报告先行。 |
| D-06 | 是否第一版支持所有框架 | 否。Python Callable + LangGraph。 |
| D-07 | 是否使用 AgentGuard / AgentDiff 名称 | 暂不使用，存在明显重名和定位冲突。 |
| D-08 | 最终差异化 | 企业工具虚拟化 + 生产案例资产化 + 状态/过程契约 + 版本行为 Diff + 发布门禁。 |

### 15.1 最重要的产品风险

- 用户可能不愿意编写行为契约。应提供模板、自动建议和从 Trace 生成草稿，但不能完全依赖 LLM 自动生成。

- 不同企业工具差异很大。核心接口必须插件化，不能在内核硬编码金融或 SaaS 服务。

- Fixture 维护成本可能变高。需要 Schema 版本、录制更新、动态字段规范化和过期检测。

- 行为 Diff 容易误报。必须区分硬契约、状态结果和非关键路径差异，并允许预期变更声明。

- 已有平台可能继续扩展类似能力。项目必须保持轻量、开放标准和平台中立。

## 附录 A. 配置示例

### A.1 项目配置

```yaml
project:
  name: finance-agent-regression

baseline:
  callable: examples.finance.v1:run_agent
  version: v1.3.0

candidate:
  callable: examples.finance.v2:run_agent
  version: v1.4.0

dataset:
  path: datasets/finance.yaml

reporters:
  - html
  - json
  - junit

exporters:
  otlp:
    enabled: false
```

### A.2 场景配置

```yaml
id: finance-001
name: 查询本人部门审批通过率
input:
  message: 查询上个月本部门审批通过率
context:
  user_id: u1001
  department_name: 信贷部

tools:
  check_permission:
    mode: mock
    result:
      allowed: true
  execute_sql:
    mode: replay
    fixture: fixtures/finance-001-execute-sql.json
  send_email:
    mode: blocked

contracts:
  - type: happens_before
    before: check_permission
    after: execute_sql
    severity: blocker
  - type: argument_constraint
    tool: execute_sql
    matcher: sql_readonly
    severity: blocker
  - type: output_contains
    value: 审批通过率

budgets:
  max_steps: 8
  max_latency_ms: 12000
```

### A.3 命令行草案

```bash
# 录制一次测试环境运行并生成 Fixture
agent-release record --agent examples.finance.v1:run_agent --scenario finance-001

# 比较两个版本
agent-release compare --config agent-release.yaml

# 只检查发布门禁
agent-release gate --result .agent-release/latest/result.json

# 将 Trace 发往 Phoenix / Langfuse 等 OTLP 后端
agent-release compare --otlp-endpoint http://localhost:6006/v1/traces
```

## 附录 B. 术语表

| 术语 | 定义 |
| --- | --- |
| Baseline | 当前生产或被认可的基线 Agent 版本。 |
| Candidate | 准备发布、灰度或替换的候选版本。 |
| Scenario | 一次可重复执行的业务测试场景。 |
| Fixture | 记录或预设的工具输入、输出、错误和延迟。 |
| Tool Virtualization | 将 Agent 的工具调用路由到 live、mock、replay、blocked 或 sandbox。 |
| Behavior Contract | 对结果、过程和资源预算的可执行约束。 |
| State Diff | 比较运行前后业务环境状态变化。 |
| Behavior Diff | 比较两个 Agent 版本的可观察行为和契约结果。 |
| Release Gate | 根据阈值形成是否允许发布的机器决策。 |
| Shadow Run | 候选版本接收真实输入但不产生真实副作用的影子执行。 |

## 附录 C. 研究来源

[R1] Langfuse Self-hosting：Langfuse 可开源自托管，部分企业功能需要许可证。 [官方来源](https://langfuse.com/self-hosting)

[R2] Langfuse Open Source Handbook：核心功能与许可说明。 [官方来源](https://langfuse.com/handbook/chapters/open-source)

[R3] LangSmith Evaluation：离线评测、线上评测、数据集和生产反馈闭环。 [官方来源](https://docs.langchain.com/langsmith/evaluation)

[R4] LangSmith Compare Experiment Results：实验回归、改善和 Trace 对比。 [官方来源](https://docs.langchain.com/langsmith/compare-experiment-results)

[R5] Phoenix Self-hosting：可本地、自托管和断网部署。 [官方来源](https://arize.com/docs/phoenix/self-hosting)

[R6] Phoenix Overview：基于 OpenTelemetry 和 OpenInference 的观测、数据集和实验能力。 [官方来源](https://arize.com/docs/phoenix)

[R7] OpenTelemetry GenAI Semantic Conventions：Agent、Workflow、工具调用和 Token 等语义属性。 [官方来源](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)

[R8] OpenInference：面向 AI 应用的 OpenTelemetry 补充约定和多框架埋点。 [官方来源](https://github.com/Arize-ai/openinference)

[R9] Agent-Diff：第三方 API 沙箱、环境状态差异和确定性任务验证。 [官方来源](https://github.com/agent-diff-bench/agent-diff)

> 文档状态：本文件是编码前的产品与架构基线。下一份应产出《Trace、Fixture 与执行虚拟化详细规范》，并通过 LangGraph POC 验证后再冻结核心 API。
