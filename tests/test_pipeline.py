"""离线单测：验证生成链路、方法论覆盖、可追溯性与评审输出。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent  # noqa: E402
from pipeline import export, run  # noqa: E402

PRD = (ROOT / "data" / "sample_prd.txt").read_text(encoding="utf-8")


def _run():
    return run(MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent(), PRD)


def test_generates_cases_with_all_methods():
    points, cases, _ = _run()
    assert len(points) > 0
    assert len(cases) == len(points)
    methods = {c.method for c in cases}
    assert {"等价类", "边界值", "场景法", "错误猜测"} <= methods


def test_traceability():
    points, cases, _ = _run()
    point_ids = {p.id for p in points}
    assert all(c.testpoint_id in point_ids for c in cases)


def test_review_score_and_checks():
    _, _, review = _run()
    assert 0 <= review.score <= 100
    assert len(review.checks) >= 5
    assert review.score == 100  # mock 目标是理想输出


def test_export_writes_files(tmp_path):
    points, cases, review = _run()
    export(points, cases, review, tmp_path)
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "test_cases.csv").exists()
