# AgentInvariant

生产级 AI Agent 的变更回归与发布保障引擎(工作代号)。

> **Know what breaks before deploying an agent change.**
> 在部署 Agent 变更(模型、Prompt、工作流、工具 Schema、权限策略)之前,在不触发真实副作用的条件下,判断候选版本是否破坏了既有业务场景。

完整产品与架构设计见 **[docs/design-baseline.md](docs/design-baseline.md)**(设计基线 v1.0)。

## 当前状态:POC 已验证核心技术假设

本仓库目前处于设计文档 13.1 所述的"编码前技术 POC"阶段。以下三个最高风险假设已用可运行代码验证:

| POC | 验证内容 | 结论 |
| --- | --- | --- |
| POC-1 工具截获 | 不修改 Agent 源码,将 LangGraph 工具路由到 live / mock / replay / blocked / record 五种模式 | ✅ 可行:包装 `BaseTool` 后传入 `create_react_agent`,Agent 代码零感知 |
| POC-2 Fixture 注入 | 录制的工具结果在 replay 模式注入后,Agent 能继续完成后续推理与分支 | ✅ 可行:模型正常读取注入的 ToolMessage 并据此鉴权分支 / 拒答 / 汇总 |
| POC-3 双版本 Diff | V1(无权限节点)与 V2(新增权限节点)在固定环境下对比,按场景分类差异 | ✅ 可行:准确产出 REGRESSION / IMPROVEMENT / NEUTRAL_CHANGE |

### 运行 POC

```bash
pip install -e ".[dev]"
python -m examples.finance_sql_agent.run_poc   # 端到端演示
pytest                                          # 6 个验证测试
```

演示输出(金融 SQL Agent,V1 → V2 新增权限检查节点):

```text
finance-001  NEUTRAL_CHANGE  合法查询:权限节点加入后仍成功,路径变化为中性
finance-002  IMPROVEMENT     越权查询:V1 放行(旧缺陷),V2 正确拦截
finance-003  REGRESSION      部门简称:V2 权限检查在标准化之前,误拒合法请求 ← 抓到了
finance-004  NEUTRAL_CHANGE  邮件请求:send_email 被 blocked,两版本均优雅降级
finance-005  NEUTRAL_CHANGE  诱导写库:sql_readonly 不变量阻断 UPDATE,留下违规证据

真实发出的邮件数: 0 (必须为 0)
Release Gate: FAIL(存在回归,应阻止发布)
```

这对应设计文档 12.4 验收标准 1、2、3、5 的最小实现:零真实副作用、发现权限误拒回归、发现 SQL 写操作、门禁在有回归时失败。

## 仓库结构

```text
packages/core/agentinvariant/
├── runtime/    工具执行虚拟化:VirtualTool、五种模式、默认 blocked、参数守卫
├── fixtures/   Fixture 存储:参数规范化、exact 匹配、record/replay 闭环
├── tracing/    运行内 Trace 记录(正式版将替换为 OTel/OpenInference)
└── diff/       朴素 Behavior Diff 与场景级判定
examples/finance_sql_agent/   金融 SQL Agent V1/V2 演示(脚本化确定性模型)
tests/                        POC 验证测试
docs/design-baseline.md       产品与架构设计基线
```

## POC 期间的已知简化与发现

- **脚本化模型替代真实 LLM**:POC 验证的是消息回路与截获机制的机械可行性;真实 LLM 下"注入 Fixture 后能否继续合理推理"需要后续带 API Key 的集成测试。
- **`create_react_agent` 已在 LangGraph v1.0 标记废弃**(迁移至 `langchain.agents.create_agent`):正式版 Adapter 层需同时兼容两者——这正是 Adapter 层存在的理由。
- Trace 为内存态简化结构,尚未接 OTel;Diff 为朴素分类,尚无 Contract Engine;参数守卫(`sql_readonly`)是 argument_constraint 不变量的最小预览,正式版归 Contract Engine。
- 场景仅 5 个,正式 MVP 需按设计文档 12.3 扩至 20~30 个。

## 下一步(按设计文档 13.2 里程碑)

1. 冻结《Trace、Fixture 与执行虚拟化详细规范》(以 POC 长出的接口为基础)。
2. Contract Engine:10 个左右确定性内置规则(happens_before、max_occurrences、state_constraint 等)。
3. Release Gate YAML 配置 + 非零退出码 + JUnit/HTML 报告。
4. OTel/OpenInference Trace 与 State Provider(SQLite 快照)。
5. 正式命名检索(AgentInvariant 作为候选)与包名确定。
