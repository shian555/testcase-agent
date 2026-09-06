"""编排：PRD → 测试点 → 用例 → 评审 → 报告。"""
from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from agents import AnalyzerAgent, GeneratorAgent, ReviewerAgent
from models import Review, TestCase, TestPoint


def run(analyzer: AnalyzerAgent, generator: GeneratorAgent, reviewer: ReviewerAgent, prd_text: str):
    points = analyzer.analyze(prd_text)
    cases = generator.generate(points)
    review = reviewer.review(cases, points)
    return points, cases, review


def export(points, cases, review: Review, outdir) -> None:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Markdown 报告
    lines = ["# AI 测试用例生成报告", ""]
    lines.append(f"- 测试点：{len(points)} 个")
    lines.append(f"- 测试用例：{len(cases)} 条")
    lines.append(f"- 评审得分：{review.score}/100")
    lines.append("")
    lines.append("## 评审结果")
    for c in review.checks:
        lines.append(f"- [{'x' if c['passed'] else ' '}] {c['criterion']}：{c['note']}")
    lines.append("")
    lines.append("## 评审建议")
    for s in review.suggestions:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## 测试用例")
    lines.append("| ID | 模块 | 标题 | 方法 | 优先级 | 前置条件 | 步骤 | 预期结果 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in cases:
        steps = c.steps.replace("\n", "<br>")
        lines.append(f"| {c.id} | {c.module} | {c.title} | {c.method} | {c.priority} | {c.precondition} | {steps} | {c.expected} |")
    (outdir / "report.md").write_text("\n".join(lines), encoding="utf-8")

    # CSV（utf-8-sig 让 Excel 直接打开不乱码）
    with open(outdir / "test_cases.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = ["id", "module", "title", "method", "priority", "precondition", "steps", "expected", "testpoint_id"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cases:
            w.writerow({k: v for k, v in asdict(c).items() if k in fields})
