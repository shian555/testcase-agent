"""数据模型：测试点 / 测试用例 / 评审结果。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestPoint:
    id: str
    module: str
    description: str
    method: str
    priority: str
    meta: dict = field(default_factory=dict)


@dataclass
class TestCase:
    id: str
    module: str
    title: str
    precondition: str
    steps: str
    expected: str
    priority: str
    method: str
    testpoint_id: str


@dataclass
class Review:
    score: int
    checks: list = field(default_factory=list)       # [{criterion, passed, note}]
    suggestions: list = field(default_factory=list)
