# Changelog

## v0.1.0 (2026-07-26)

首个可用版本:本地 CLI/SDK 垂直闭环(设计基线阶段 1 MVP Core + 部分阶段 2/3 能力)。

### 核心引擎

- **执行虚拟化**:任意 LangChain/LangGraph 工具的非侵入式截获;live / mock /
  replay / blocked / record 五种模式;未声明策略的工具默认 blocked;
  副作用等级声明;执行前参数守卫;mock/replay 延迟模拟。
- **Fixture**:参数规范化 exact 匹配、动态字段忽略、record/replay 闭环、
  未命中显式报错。
- **Contract Engine**:13 个确定性内置规则(过程不变量 / 结果与状态契约 /
  资源预算),blocker/warning 两级 severity,匹配器注册表
  (sql_readonly、no_sensitive_fields)。
- **State Provider**:运行前后业务状态快照(SQLite 实现 + 协议接口),
  动态字段规范化,state_constraint / state_unchanged 规则。
- **Behavior Diff**:REGRESSION / IMPROVEMENT / NEUTRAL_CHANGE / NO_CHANGE /
  REVIEW_REQUIRED 场景级分类;工具序列、输出、状态、违规差异。
- **Runner**:YAML 项目配置与数据集加载,场景级工具策略覆盖,超时隔离,
  重复运行聚合(pass_rate)。
- **Release Gate**:YAML 阈值 -> 结构化决策与退出码(0/1/2)。
- **报告**:JSON / JUnit XML / 静态 HTML。
- **OTLP 导出**:gen_ai.* + agent.release.* 语义 Span,隐私默认不导出内容,
  兼容 Phoenix / Langfuse / 通用 Collector。

### CLI

- `agentinvariant record | compare | gate`。

### 示例与文档

- 金融 SQL Agent V1/V2 示例:16 个场景(越权、简称误拒回归、多轮追问、
  超时、工具异常、Prompt 注入、敏感字段、重复邮件、fail-closed 等)。
- 规范文档:trace-replay-spec、behavior-contract-spec、diff-gate-spec。
- GitHub Actions CI:单元测试 + 示例回归演示(断言门禁阻止发布)。

### 已知限制

- 示例使用确定性脚本模型;真实 LLM 集成测试需 API Key,不在离线 CI 内。
- Fixture 仅 exact 匹配,尚无 Schema 版本绑定与脱敏管道。
- 超时隔离基于线程,进程级隔离在路线图中。
- 仅 Python Callable + LangGraph Adapter(设计决策 D-06)。
