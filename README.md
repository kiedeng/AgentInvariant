# AgentInvariant

生产级 AI Agent 的变更回归与发布保障引擎。

> **Know what breaks before deploying an agent change.**
> 在部署 Agent 变更(模型、Prompt、工作流、工具 Schema、权限策略)之前,
> 在不触发真实副作用的条件下,判断候选版本是否破坏了既有业务场景。

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

## 它做什么

```text
生产 Trace / 测试场景
        ↓
Baseline Agent ─┐
                ├─ 工具虚拟化(live/mock/replay/blocked) → 行为契约 → Behavior Diff → Release Gate
Candidate Agent ┘
        ↓
JSON / JUnit / HTML 报告 + OTLP(Phoenix / Langfuse)
        ↓
GitHub Actions / Jenkins 以退出码阻止发布
```

对一次 Agent 变更给出四类答案:

1. **业务结果**是否仍然正确,是否出现历史成功场景回归;
2. **关键过程**是否违反业务不变量(跳过鉴权、重复副作用、写库越界);
3. **副作用**(邮件、退款、写 SQL)是否符合预期且从未真实执行;
4. **预算**(耗时、步数)是否满足发布阈值。

完整产品与架构设计见 [docs/design-baseline.md](docs/design-baseline.md);
实现规范见 [trace-replay](docs/trace-replay-spec.md)、
[behavior-contract](docs/behavior-contract-spec.md)、
[diff-gate](docs/diff-gate-spec.md)。

## 快速开始

```bash
pip install -e ".[dev]"

# 运行内置金融 SQL Agent 示例(V1 无权限节点 -> V2 新增权限节点)
agentinvariant record  --config examples/finance_sql_agent/agentinvariant.yaml
agentinvariant compare --config examples/finance_sql_agent/agentinvariant.yaml
# 退出码 1:示例内置了一个真实回归,门禁按设计阻止发布

pytest   # 29 个测试
```

示例输出(16 个场景):

```text
finance-002    IMPROVEMENT     越权查询:V1 放行(旧缺陷),V2 正确拦截
finance-003    REGRESSION      部门简称:V2 权限检查在标准化之前,误拒合法请求 ← 抓到了
finance-006    IMPROVEMENT     多轮"那重庆呢":跨部门追问被 V2 拦截
finance-009    REVIEW_REQUIRED 慢 SQL 超时:两侧都失败,需人工确认
finance-013    IMPROVEMENT     "再发一次":V1 重复发送邮件缺陷被 max_occurrences 抓出
finance-015    IMPROVEMENT     权限服务宕机:V1 泄漏数据,V2 fail-closed
...
汇总: REGRESSION: 1 · IMPROVEMENT: 4 · NEUTRAL_CHANGE: 10 · REVIEW_REQUIRED: 1
Release Gate: FAIL 阻止发布
  - 新增回归 1 个(允许 0): ['finance-003']
  - 候选成功率 88% 低于阈值 95%
```

全程零真实副作用:`send_email` 被阻断、`UPDATE` 被 `sql_readonly` 守卫拦截、
`execute_sql` 从 Fixture 回放。

## 接入你自己的 Agent

**1. 提供入口函数**(Agent 代码零改动,只需接收工具列表):

```python
# my_project/adapter.py
def run_baseline(tools, scenario) -> str:
    agent = build_my_agent(tools)          # 你现有的构建逻辑
    return invoke_langgraph(agent, [scenario["input"]])
```

**2. 声明项目配置** `agentinvariant.yaml`:

```yaml
name: my-agent
baseline:  {entrypoint: "my_project.adapter:run_baseline", version: v1.3.0}
candidate: {entrypoint: "my_project.adapter:run_candidate", version: v1.4.0}
tools: my_project.tools:ALL_TOOLS
dataset: datasets/scenarios.yaml
gate: gate.yaml
policies:                       # 未声明的工具一律 blocked
  query_db:   {mode: replay, guard: sql_readonly}
  send_email: {mode: blocked, effect: EXTERNAL_COMMUNICATION}
```

**3. 用契约声明业务期望**(场景 YAML):

```yaml
- id: refund-001
  input: 给订单 A1 退款
  contracts:
    - {type: happens_before, before: check_approval, after: execute_refund}
    - {type: max_occurrences, tool: execute_refund, max: 1}
    - {type: state_constraint, field: orders.0.status, equals: REFUNDED}
```

**4. 接入 CI**:`agentinvariant compare` 的退出码即发布决策(0 放行 / 1 阻止),
JUnit 报告可直接进测试面板,HTML 报告供人工审查。

**不想手写契约?** 先跑一次,再从实际行为生成草稿:

```bash
agentinvariant scaffold --result .agentinvariant/report.json --out contracts-draft.yaml
# 草稿全部是 warning 级,人工确认后把关键规则升级为 blocker
```

## 与观测平台组合

本项目不替代 Langfuse / LangSmith / Phoenix,而是作为它们的下游执行保障层:

```bash
agentinvariant compare --config agentinvariant.yaml \
    --otlp-endpoint http://localhost:6006/v1/traces   # Phoenix
```

Trace 采用 OpenTelemetry GenAI 语义(`gen_ai.*`)+ 项目扩展字段
(`agent.release.*`);隐私默认不导出 Prompt、参数与结果内容。

## 仓库结构

```text
packages/core/agentinvariant/
├── runtime/    工具执行虚拟化:五种模式、默认 blocked、参数守卫、延迟模拟
├── fixtures/   Fixture 存储:参数规范化、record/replay 闭环
├── contracts/  Contract Engine:13 个内置规则 + 匹配器注册表
├── state/      StateProvider:运行前后业务状态快照(SQLite 实现)
├── diff/       Behavior Diff 与场景级判定
├── gate/       Release Gate:YAML 阈值 -> 结构化决策
├── reports/    JUnit XML / 静态 HTML 报告器
├── tracing/    Trace 记录 + OTLP 导出(gen_ai.* 语义)
├── adapters/   LangGraph 多轮调用辅助
├── runner.py   Experiment Runner:超时隔离、重复运行、场景级策略覆盖
├── config.py   项目 / 数据集 YAML 配置
└── cli.py      record / compare / gate 命令
examples/finance_sql_agent/   金融 SQL Agent 示例(16 场景 + 配置全套)
docs/                         设计基线 + 三份实现规范
tests/                        29 个测试
```

## 当前边界(诚实声明)

- 示例用**确定性脚本模型**替代真实 LLM:离线、零成本、可复现;验证的是
  截获机制与消息回路。真实 LLM 下的行为验证需要带 API Key 的集成测试。
- Fixture 仅 exact 匹配(已含 Schema 版本绑定、过期检测与敏感字段脱敏);
  subset/custom matcher 与静态加密在路线图中。
- 超时隔离基于线程;进程级隔离在路线图中。
- Adapter 仅 Python Callable + LangGraph(设计决策 D-06);
  `adapters.create_tool_agent` 已兼容 `langchain.agents.create_agent`(v1)
  并在其缺失时回退到 `langgraph.prebuilt`。
- 命名检索(设计决策 D-07):PyPI 上 `agentinvariant` 已确认可用(2026-07);
  商标层面的检索未做,商业化使用前请自行确认。

## 路线图

见 [docs/design-baseline.md](docs/design-baseline.md) 第 13 章:
阶段 2(开源 v0.1 文档与插件接口)→ 阶段 3(Langfuse / LangSmith / Phoenix
双向 Adapter)→ 阶段 4(Web 平台)→ 阶段 5(Shadow 与持续回归)。

## 贡献与许可

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。
本项目以 [MIT License](LICENSE) 开源。
