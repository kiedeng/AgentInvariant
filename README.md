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

在 POC 之上,已完成设计基线 M3/M4 里程碑的最小实现:

| 模块 | 能力 |
| --- | --- |
| Contract Engine | 10 个确定性内置规则:tool_called / tool_not_called / happens_before / max_occurrences / argument_constraint / result_constraint / output_contains / output_not_contains / no_policy_violation / max_steps,支持 blocker/warning 两级 severity |
| Release Gate | YAML 阈值配置(回归数、成功率、待审数、违规数),`agentinvariant gate` CLI 返回 0/1/2 退出码,可直接接入 CI |
| 报告 | JSON + JUnit XML(CI 测试面板)+ 静态 HTML(人读的差异与证据表) |

### 运行 POC

```bash
pip install -e ".[dev]"
python -m examples.finance_sql_agent.run_poc   # 端到端演示,退出码即门禁结论
pytest                                          # 19 个验证测试

# 单独执行门禁(CI 用法)
agentinvariant gate --result .agentinvariant/report.json \
                    --config examples/finance_sql_agent/gate.yaml
```

演示输出(金融 SQL Agent,V1 → V2 新增权限检查节点):

```text
finance-001  NEUTRAL_CHANGE  合法查询:权限节点加入后仍成功,路径变化为中性
finance-002  IMPROVEMENT     越权查询:V1 放行(旧缺陷),V2 正确拦截
finance-003  REGRESSION      部门简称:V2 权限检查在标准化之前,误拒合法请求 ← 抓到了
finance-004  NEUTRAL_CHANGE  邮件请求:send_email 被 blocked,两版本均优雅降级
finance-005  NEUTRAL_CHANGE  诱导写库:sql_readonly 不变量阻断 UPDATE,留下违规证据

真实发出的邮件数: 0 (必须为 0)
Release Gate: FAIL 阻止发布
  - 新增回归 1 个(允许 0): ['finance-003']
  - 候选成功率 80% 低于阈值 95%
```

这对应设计文档 12.4 验收标准 1、2、3、5、6 的最小实现:零真实副作用、发现权限误拒回归、发现 SQL 写操作、门禁在有回归时以非零退出码失败并给出可读原因、生成 HTML/JSON/JUnit 三种报告。

## 仓库结构

```text
packages/core/agentinvariant/
├── runtime/    工具执行虚拟化:VirtualTool、五种模式、默认 blocked、参数守卫
├── fixtures/   Fixture 存储:参数规范化、exact 匹配、record/replay 闭环
├── tracing/    运行内 Trace 记录(正式版将替换为 OTel/OpenInference)
├── contracts/  Contract Engine:10 个内置规则 + 参数匹配器注册表
├── diff/       Behavior Diff 与场景级判定(9.3 判定算法子集)
├── gate/       Release Gate:YAML 阈值 -> 结构化决策
├── reports/    JUnit XML / 静态 HTML 报告器
└── cli.py      agentinvariant gate 命令(退出码 0/1/2)
examples/finance_sql_agent/   金融 SQL Agent V1/V2 演示(脚本化确定性模型 + gate.yaml)
tests/                        19 个验证测试
docs/design-baseline.md       产品与架构设计基线
```

## POC 期间的已知简化与发现

- **脚本化模型替代真实 LLM**:POC 验证的是消息回路与截获机制的机械可行性;真实 LLM 下"注入 Fixture 后能否继续合理推理"需要后续带 API Key 的集成测试。
- **`create_react_agent` 已在 LangGraph v1.0 标记废弃**(迁移至 `langchain.agents.create_agent`):正式版 Adapter 层需同时兼容两者——这正是 Adapter 层存在的理由。
- Trace 为内存态简化结构,尚未接 OTel;Diff 为朴素分类,尚无 Contract Engine;参数守卫(`sql_readonly`)是 argument_constraint 不变量的最小预览,正式版归 Contract Engine。
- 场景仅 5 个,正式 MVP 需按设计文档 12.3 扩至 20~30 个。

## 下一步(按设计文档 13.2 里程碑)

1. 冻结《Trace、Fixture 与执行虚拟化详细规范》(以已长出的接口为基础)。
2. State Provider 与 state_constraint 规则(SQLite 前后快照 + 动态字段规范化)。
3. OTel/OpenInference Trace 替换内存记录器,OTLP 导出到 Phoenix/Langfuse。
4. 场景 YAML 化加载(当前为 Python 字典)与场景扩至 20~30 个(多轮、超时、注入)。
5. 正式命名检索(AgentInvariant 作为候选)与包名确定。
