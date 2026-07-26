"""确定性脚本模型:模拟一个会调用工具的 LLM。

POC/示例用它替代真实模型,原因:
1. 离线、零成本、完全可复现;
2. 要验证的是"工具截获 + Fixture 注入后推理能否继续",脚本模型会真实地
   读取 ToolMessage 内容并据此分支(权限拒绝则拒答、SQL 出错则道歉、
   邮件被阻断则在答案中说明),等价于验证了消息回路的机械可行性。

真实 LLM 下的行为验证属于带 API Key 的集成测试,不在离线 CI 范围内。

内置的"版本差异"(供回归演示):
- V1 无权限检查;V2 先鉴权,但鉴权用未标准化的部门简称(隐性缺陷);
- V1 在用户说"再发一次"时会重复发送邮件(历史缺陷),V2 已修复。
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

DEPT_PATTERN = re.compile(r"(信贷部|市场部|重庆分部|信贷|市场|重庆)")
_ALIAS_FULL = {"信贷": "信贷部", "市场": "市场部", "重庆": "重庆分部"}
MONTH_PATTERN = re.compile(r"(\d{1,2})月")
DEFAULT_MONTH = "2026-06"  # “上个月”


def _extract_department(query: str, fallback: str) -> tuple[str, str]:
    """返回 (原始提及, 标准化全名)。"""
    m = DEPT_PATTERN.search(query)
    raw = m.group(1) if m else fallback
    return raw, _ALIAS_FULL.get(raw, raw)


def _extract_month(query: str) -> str:
    m = MONTH_PATTERN.search(query)
    return f"2026-{int(m.group(1)):02d}" if m else DEFAULT_MONTH


def _parse_json(content: Any) -> dict:
    try:
        return json.loads(content if isinstance(content, str) else str(content))
    except (json.JSONDecodeError, TypeError):
        return {}


class ScriptedFinanceModel(BaseChatModel):
    """按固定策略产生 tool_calls 的假模型。

    require_permission=False 模拟 V1(直接查数),True 模拟 V2(先鉴权)。
    """

    require_permission: bool = False
    _call_counter: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-finance-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedFinanceModel":
        return self

    def _next_id(self) -> str:
        self._call_counter += 1
        return f"call_{self._call_counter}"

    def _tool_call(self, name: str, args: dict) -> ChatResult:
        msg = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": self._next_id()}])
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _answer(self, text: str) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        # 场景上下文以 JSON 首行注入第一条 HumanMessage(多轮时后续轮次为纯文本)
        humans = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
        first_human, last_human = messages[humans[0]], messages[humans[-1]]
        ctx_line, _, _ = str(first_human.content).partition("\n")
        ctx = _parse_json(ctx_line)
        query = str(last_human.content)
        if last_human is first_human:
            query = str(first_human.content).partition("\n")[2] or query

        user_id = ctx.get("user_id", "unknown")
        # V2 的隐性缺陷:权限检查用原始提及(可能是简称),SQL 用标准化全名。
        raw_dept, department = _extract_department(query, ctx.get("department_name", ""))
        month = _extract_month(query)

        # 只看最后一轮用户输入之后的工具结果(多轮场景下不复用上一轮的鉴权)
        turn_tools = [m for m in messages[humans[-1]:] if isinstance(m, ToolMessage)]
        tool_results: dict[str, dict] = {m.name: _parse_json(m.content) for m in turn_tools}
        email_attempts = sum(1 for m in turn_tools if m.name == "send_email")

        wants_update = any(k in query for k in ("更新", "修改为", "改成"))
        wants_email = "邮件" in query
        wants_email_again = "再发" in query

        # 1. V2 首先鉴权(注意:传入的是未标准化的 raw_dept —— 这就是待发现的缺陷)
        if self.require_permission and "check_permission" not in tool_results:
            return self._tool_call("check_permission", {"user_id": user_id, "department": raw_dept})

        if self.require_permission:
            perm = tool_results["check_permission"]
            if "error" in perm:
                return self._answer("权限服务不可用,无法继续查询。")
            if not perm.get("allowed"):
                return self._answer(f"你无权查询 {raw_dept} 的数据,请求已拒绝。")

        # 2. 执行 SQL(查询 / 敏感字段 / 用户要求的更新)
        if "execute_sql" not in tool_results:
            if wants_update:
                sql = f"UPDATE approval_rates SET rate = 1.0 WHERE department = '{department}'"
            elif "身份证" in query:
                sql = f"SELECT id_card, name FROM employees WHERE department = '{department}'"
            else:
                sql = (
                    "SELECT department, month, rate FROM approval_rates "
                    f"WHERE department = '{department}' AND month = '{month}'"
                )
            return self._tool_call("execute_sql", {"sql": sql})

        sql_result = tool_results["execute_sql"]
        if "error" in sql_result:
            return self._answer(f"操作未完成:{sql_result['error']}")

        # 3. 需要时发送邮件;V1 历史缺陷:用户说“再发一次”会重复发送
        email_target = 2 if (wants_email_again and not self.require_permission) else 1
        if wants_email and email_attempts < email_target:
            return self._tool_call(
                "send_email",
                {"to": f"{user_id}@example.com", "subject": "审批通过率报告", "body": "见附件"},
            )

        # 4. 汇总回答
        if wants_update:
            return self._answer(f"已完成更新,影响 {sql_result.get('rows_affected')} 行。")

        rows = sql_result.get("rows", [])
        if not rows:
            answer = f"{department} 在 {month} 没有数据。"
        else:
            answer = f"{rows[0][0]} {rows[0][1]} 审批通过率为 {rows[0][2]:.0%}。"
        if wants_email:
            email_result = tool_results["send_email"]
            answer += " 报告邮件已发送。" if email_result.get("sent") else f" 邮件未能发送({email_result.get('error', '未知原因')})。"
        return self._answer(answer)
