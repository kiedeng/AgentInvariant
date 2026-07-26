"""静态 HTML 报告:开发者无需打开代码即可理解的行为差异摘要。

POC 用标准库字符串模板;正式版按设计基线 14.1 换用 Jinja2。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

_OUTCOME_COLORS = {
    "REGRESSION": "#c62828",
    "IMPROVEMENT": "#2e7d32",
    "NEUTRAL_CHANGE": "#616161",
    "NO_CHANGE": "#9e9e9e",
    "REVIEW_REQUIRED": "#e65100",
}

_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>AgentInvariant 行为回归报告</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; color: #212121; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: .5rem .7rem; text-align: left; vertical-align: top; font-size: .9rem; }}
  th {{ background: #f5f5f5; }}
  .outcome {{ font-weight: 700; color: #fff; padding: .15rem .5rem; border-radius: .25rem; display: inline-block; }}
  .fail {{ color: #c62828; }} .pass {{ color: #2e7d32; }} .warn {{ color: #e65100; }}
  code {{ background: #f5f5f5; padding: 0 .25rem; }}
  .gate {{ padding: .8rem 1rem; border-radius: .4rem; color: #fff; font-weight: 700;
           background: {gate_color}; margin: 1rem 0; }}
</style>
<h1>AgentInvariant 行为回归报告</h1>
<p>Baseline: <b>{baseline}</b> → Candidate: <b>{candidate}</b></p>
<div class="gate">Release Gate: {gate_text}</div>
<p>{summary_line} · 真实副作用(邮件)发出数: <b>{emails}</b></p>
<table>
<tr><th>场景</th><th>结论</th><th>Baseline</th><th>Candidate</th><th>工具序列变化</th><th>契约与违规证据</th></tr>
{rows}
</table>
"""

_ROW = """<tr>
<td><b>{sid}</b></td>
<td><span class="outcome" style="background:{color}">{outcome}</span></td>
<td class="{b_cls}">{b_mark}<br>{b_out}</td>
<td class="{c_cls}">{c_mark}<br>{c_out}</td>
<td><code>{b_seq}</code><br>→ <code>{c_seq}</code></td>
<td>{evidence}</td>
</tr>"""


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _evidence(c: dict[str, Any]) -> str:
    lines: list[str] = []
    for side in ("baseline", "candidate"):
        for chk in c[side].get("contracts", []):
            if not chk["passed"]:
                cls = "fail" if chk["severity"] == "blocker" else "warn"
                lines.append(f'<span class="{cls}">[{side}] {_esc(chk["description"])} — {_esc(chk["detail"])}</span>')
        for v in c[side].get("violations", []):
            lines.append(f'<span class="warn">[{side}] {_esc(v["tool"])} 策略违规: {_esc(v["violation"])}</span>')
    return "<br>".join(lines) or "—"


def write_html(report: dict[str, Any], gate_result: dict[str, Any], path: str | Path) -> Path:
    rows = []
    for c in report["comparisons"]:
        rows.append(_ROW.format(
            sid=_esc(c["scenario_id"]),
            color=_OUTCOME_COLORS.get(c["outcome"], "#616161"),
            outcome=_esc(c["outcome"]),
            b_cls="pass" if c["baseline"]["success"] else "fail",
            c_cls="pass" if c["candidate"]["success"] else "fail",
            b_mark="✔ 成功" if c["baseline"]["success"] else "✘ 失败",
            c_mark="✔ 成功" if c["candidate"]["success"] else "✘ 失败",
            b_out=_esc(c["baseline"]["final_output"]),
            c_out=_esc(c["candidate"]["final_output"]),
            b_seq=_esc(" → ".join(c["baseline"]["tool_sequence"]) or "(无工具调用)"),
            c_seq=_esc(" → ".join(c["candidate"]["tool_sequence"]) or "(无工具调用)"),
            evidence=_evidence(c),
        ))

    summary = report["summary"]
    page = _PAGE.format(
        baseline=_esc(report["baseline"]),
        candidate=_esc(report["candidate"]),
        gate_color="#2e7d32" if gate_result["passed"] else "#c62828",
        gate_text="PASS 允许发布" if gate_result["passed"] else
                  "FAIL 阻止发布 — " + _esc("; ".join(gate_result["reasons"])),
        summary_line=" · ".join(f"{k}: {v}" for k, v in summary.items() if v),
        emails=report.get("real_emails_sent", "N/A"),
        rows="\n".join(rows),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
