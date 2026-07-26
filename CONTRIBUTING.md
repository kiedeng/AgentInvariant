# 贡献指南 / Contributing

感谢你对 AgentInvariant 的兴趣。项目处于早期(v0.2.x),欢迎 Issue 与 PR。

## 开发环境

```bash
pip install -e ".[dev]"
pytest                      # 全量测试必须通过
python -m examples.finance_sql_agent.run_poc   # 端到端演示(预期退出码 1)
```

要求 Python 3.11+。CI 会在 3.11 / 3.12 上运行同样的检查。

## 提交约定

- 一个 PR 解决一件事;附带测试(修 bug 先写复现测试);
- 行为契约、Fixture、门禁语义的改动需同步更新 `docs/` 下对应规范;
- 破坏性变更(规则语义、报告格式、CLI 参数)需在 CHANGELOG 标注。

## 设计边界(提 Issue / PR 前请读)

核心设计决策见 [docs/design-baseline.md](docs/design-baseline.md) 第 15 章,
其中几条硬边界:

- 不做观测平台(Trace 后台、Prompt 管理);与 Langfuse/LangSmith/Phoenix 组合而非替代;
- 内置契约规则必须**确定性**;LLM 评分只能作为外部补充,不进门禁硬判定;
- 工具虚拟化默认安全:未声明策略的工具一律 blocked,不可逆副作用默认不得 live;
- 内核不硬编码任何具体业务或 SaaS 服务,一切经插件接口(Adapter / StateProvider / Matcher)。

## 发布流程(维护者)

发版只需要一个标签,其余全自动(`.github/workflows/release.yml`):

```bash
git checkout main && git pull
git tag -a vX.Y.Z -m "AgentInvariant vX.Y.Z"
git push origin vX.Y.Z
```

工作流会构建 wheel/sdist、对构建产物做 CLI 冒烟验证,并创建附带产物的
GitHub Release。发版前请确认 `pyproject.toml` 的 version 与 CHANGELOG 已更新。

可选的 PyPI 自动发布默认关闭;启用方式:在 PyPI 项目设置中添加
Trusted Publisher(指向本仓库的 `release.yml`),再在仓库
Settings → Actions → Variables 中设 `PYPI_PUBLISH=true`。无需在仓库
存放任何 API Token。

## 安全问题

安全漏洞请勿公开提 Issue,直接联系仓库维护者。
