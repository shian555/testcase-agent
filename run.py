"""CLI 入口。

用法：
    python run.py                          # 默认 mock + 示例 PRD
    python run.py --mode real --prd data/sample_prd.txt   # 接真实 LLM（需设 LLM_API_KEY 等）
"""
from __future__ import annotations

import argparse
from pathlib import Path

from agents import (LLMAnalyzerAgent, LLMGeneratorAgent, LLMReviewerAgent,
                    MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent)
from pipeline import export, run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--prd", default="data/sample_prd.txt")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    prd_text = Path(args.prd).read_text(encoding="utf-8")

    if args.mode == "mock":
        points, cases, review = run(MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent(), prd_text)
    else:
        points, cases, review = run(LLMAnalyzerAgent(), LLMGeneratorAgent(), LLMReviewerAgent(), prd_text)

    export(points, cases, review, Path(args.out))
    print(f"测试点 {len(points)} 个 | 用例 {len(cases)} 条 | 评审 {review.score}/100")
    print(f"报告已写出：{args.out}/report.md  {args.out}/test_cases.csv")


if __name__ == "__main__":
    main()
