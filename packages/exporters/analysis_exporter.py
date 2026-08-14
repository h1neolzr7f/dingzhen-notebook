"""JSON/Markdown export for deterministic P3 analysis reports."""

from __future__ import annotations

import json
from pathlib import Path

from packages.analysis import AnalysisReport


def render_analysis_markdown(report: AnalysisReport) -> str:
    data = report.to_dict()
    accuracy = "未知" if data["accuracy"] is None else f"{data['accuracy']:.2%}"
    lines = [
        "---",
        "schema_version: 1",
        f"paper_id: {json.dumps(data['paper_id'], ensure_ascii=False)}",
        f"title: {json.dumps(data['title'], ensure_ascii=False)}",
        f"verified: {str(data['verified']).lower()}",
        "---",
        "",
        "# 学习分析",
        "",
        f"- 总题数：{data['total']}",
        f"- 已作答：{data['answered']}",
        f"- 正确：{data['correct']}",
        f"- 错误：{data['wrong']}",
        f"- 未知：{data['unknown']}",
        f"- 正确率：{accuracy}",
        f"- 待校对：{data['review_count']}",
        "",
        "## 模块统计",
        "",
        "| 模块 | 总题数 | 已作答 | 正确 | 错误 | 正确率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, metric in data["module_stats"].items():
        rate = "未知" if metric["accuracy"] is None else f"{metric['accuracy']:.2%}"
        lines.append(f"| {key} | {metric['total']} | {metric['answered']} | {metric['correct']} | {metric['wrong']} | {rate} |")
    lines += ["", "## 知识点统计", ""]
    for key, metric in data["knowledge_stats"].items():
        rate = "未知" if metric["accuracy"] is None else f"{metric['accuracy']:.2%}"
        lines.append(f"- {key}：{metric['correct']}/{metric['answered']}（{rate}）")
    lines += ["", "## 错因标签", ""]
    lines.extend(f"- {key}：{value}" for key, value in data["error_stats"].items()) or lines.append("- 暂无")
    lines += ["", "## 状态边界", "", "`verified: false` 或待校对题目均不应被解释为已核验的粉笔结论。", ""]
    return "\n".join(lines)


def export_analysis_json(report: AnalysisReport, destination: str | Path) -> Path:
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def export_analysis_markdown(report: AnalysisReport, destination: str | Path) -> Path:
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_analysis_markdown(report), encoding="utf-8")
    return output


__all__ = ["export_analysis_json", "export_analysis_markdown", "render_analysis_markdown"]
