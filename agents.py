"""Agent 抽象与实现：需求分析 / 用例生成 / 用例评审 三个智能体。

- Mock*Agent：规则化实现，离线、确定性、可复现（演示 + CI + 单测）。
- LLM*Agent：接入真实大模型（Qwen/DeepSeek/硅基流动，OpenAI 兼容接口），
  通过环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 配置。
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import List

from methods import METHODS
from models import Review, TestCase, TestPoint

# ---------------- PRD 解析（规则化，供 Mock 使用） ----------------

_FIELD_RANGE = re.compile(r"^([一-龥A-Za-z]+)\s*[：:]\s*(\d+)\s*[-~至]\s*(\d+)\s*位(.{0,20})")
_FIELD_FIXED = re.compile(r"^([一-龥A-Za-z]+)\s*[：:]\s*(\d+)\s*位(.{0,20})")


def _parse_constraints(prd_text: str) -> List[dict]:
    fields = []
    for line in prd_text.splitlines():
        line = line.strip()
        m = _FIELD_RANGE.match(line)
        if m:
            name, lo, hi, cons = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        else:
            m = _FIELD_FIXED.match(line)
            if not m:
                continue
            name, lo, hi, cons = m.group(1), int(m.group(2)), int(m.group(2)), m.group(3)
        fields.append({"name": name, "min": lo, "max": hi, "constraint": cons.strip("，,。、")})
    return fields


def _parse_module(prd_text: str) -> str:
    m = re.search(r"【功能】\s*(.+)", prd_text)
    return m.group(1).strip() if m else "功能模块"


def _kind(constraint: str) -> str:
    return "digit" if ("数字" in constraint and "字母" not in constraint) else "alnum"


def _sample(n: int, kind: str) -> str:
    n = max(n, 1)
    return ("1" * n) if kind == "digit" else ("a1" * ((n + 1) // 2))[:n]


# ---------------- 抽象接口 ----------------

class AnalyzerAgent(ABC):
    @abstractmethod
    def analyze(self, prd_text: str) -> List[TestPoint]: ...


class GeneratorAgent(ABC):
    @abstractmethod
    def generate(self, points: List[TestPoint]) -> List[TestCase]: ...


class ReviewerAgent(ABC):
    @abstractmethod
    def review(self, cases: List[TestCase], points: List[TestPoint]) -> Review: ...


# ---------------- Mock：规则化实现（离线确定性） ----------------

class MockAnalyzerAgent(AnalyzerAgent):
    def analyze(self, prd_text: str) -> List[TestPoint]:
        fields = _parse_constraints(prd_text)
        module = _parse_module(prd_text)
        points: List[TestPoint] = []

        def add(desc, method, priority, **meta):
            pid = len(points) + 1
            points.append(TestPoint(id=f"TP{pid:03d}", module=module,
                                    description=desc, method=method, priority=priority, meta=meta))

        # 场景法（模块级主/异常流程）
        add("正常登录成功主流程", "场景法", "P0")
        add("密码错误登录失败分支", "场景法", "P1")
        if "锁定" in prd_text:
            add("连续输错触发账号锁定", "场景法", "P0")
        if "记住" in prd_text:
            add("勾选记住登录状态，7 天内免登录", "场景法", "P2")

        # 等价类 + 边界值（逐字段）
        for f in fields:
            name, lo, hi, cons = f["name"], f["min"], f["max"], f["constraint"]
            kind = _kind(cons)
            mid = (lo + hi) // 2
            add(f"{name}有效等价类（符合 {lo}-{hi} 位规则）", "等价类", "P1", field=name, value=_sample(mid, kind), valid=True)
            add(f"{name}无效等价类-空值", "等价类", "P1", field=name, value="（空）", valid=False)
            add(f"{name}无效等价类-超短（<{lo} 位）", "等价类", "P2", field=name, value=_sample(lo - 1, kind), valid=False)
            add(f"{name}无效等价类-超长（>{hi} 位）", "等价类", "P2", field=name, value=_sample(hi + 1, kind), valid=False)
            add(f"{name}无效等价类-非法字符", "等价类", "P2", field=name, value="!@#$%^&*()", valid=False)
            add(f"{name}下边界 {lo} 位", "边界值", "P1", field=name, value=_sample(lo, kind), valid=True)
            add(f"{name}下边界-1（{lo - 1} 位）", "边界值", "P2", field=name, value=_sample(lo - 1, kind), valid=False)
            add(f"{name}上边界 {hi} 位", "边界值", "P1", field=name, value=_sample(hi, kind), valid=True)
            add(f"{name}上边界+1（{hi + 1} 位）", "边界值", "P2", field=name, value=_sample(hi + 1, kind), valid=False)

        # 错误猜测
        add("用户名含 SQL 注入/XSS 特殊字符", "错误猜测", "P1", field="用户名", value="' OR '1'='1", valid=False)
        add("大小写敏感性与首尾空格处理", "错误猜测", "P2", field="用户名", value=" Abc123 ", valid=False)
        return points


class MockGeneratorAgent(GeneratorAgent):
    def generate(self, points: List[TestPoint]) -> List[TestCase]:
        return [
            TestCase(
                id=f"TC{i:03d}", module=p.module, title=p.description,
                precondition="账号已注册且未锁定；已打开登录页",
                steps=self._steps(p), expected=self._expected(p),
                priority=p.priority, method=p.method, testpoint_id=p.id,
            )
            for i, p in enumerate(points, 1)
        ]

    def _steps(self, p: TestPoint) -> str:
        if p.method == "场景法":
            if "锁定" in p.description:
                return "1.连续 5 次输入错误密码\n2.第 6 次输入正确密码并登录"
            if "记住" in p.description:
                return "1.输入正确账号密码并勾选「记住登录」\n2.登录成功后关闭浏览器\n3.重新打开页面"
            if "失败" in p.description:
                return "1.输入正确用户名\n2.输入错误密码\n3.点击登录"
            return "1.输入正确用户名、密码、验证码\n2.点击登录"
        field = p.meta.get("field", "输入框")
        value = p.meta.get("value", "测试值")
        return f"1.在{field}输入框输入「{value}」\n2.其余字段填合法值\n3.点击登录"

    def _expected(self, p: TestPoint) -> str:
        if p.meta.get("valid"):
            return "登录成功，跳转首页"
        if p.method == "场景法":
            if "锁定" in p.description:
                return "账号锁定 30 分钟，提示稍后再试"
            if "记住" in p.description:
                return "7 天内免登录，直接进入系统"
            if "失败" in p.description:
                return "登录失败，提示「账号或密码错误」"
            return "登录成功，跳转首页"
        return "登录失败，页面给出对应校验提示，不提交请求"


class MockReviewerAgent(ReviewerAgent):
    def review(self, cases: List[TestCase], points: List[TestPoint]) -> Review:
        methods = {c.method for c in cases}
        checks = []

        def check(criterion, passed, note=""):
            checks.append({"criterion": criterion, "passed": passed, "note": note})

        # 1. 方法覆盖
        for m in METHODS:
            check(f"覆盖「{m}」方法", m in methods, "已覆盖" if m in methods else f"缺少{m}类用例")
        # 2. 结构完整性
        bad = [c.id for c in cases if not (c.precondition and c.steps and c.expected)]
        check("用例结构完整（前置/步骤/预期）", not bad, "全部完整" if not bad else f"{len(bad)} 条不完整")
        # 3. 优先级标注
        no_prio = [c.id for c in cases if not c.priority]
        check("优先级标注（P0/P1/P2）", not no_prio, "全部标注" if not no_prio else f"{len(no_prio)} 条缺失")
        # 4. 可追溯性
        orphan = [c.id for c in cases if not c.testpoint_id]
        check("用例可追溯到测试点", not orphan, "全部可追溯" if not orphan else f"{len(orphan)} 条无来源")
        # 5. 边界值完整性
        has_upper_plus = any("上边界+1" in c.title for c in cases)
        check("边界值覆盖上下界±1", has_upper_plus, "已覆盖" if has_upper_plus else "缺少边界±1")

        score = round(sum(1 for c in checks if c["passed"]) / len(checks) * 100)
        suggestions = [
            "可补充并发登录、验证码过期、跨端（移动端/Web）等场景",
            "可将 P0/P1 关键用例接入自动化（Pytest/Playwright）做回归",
            "建议按风险等级对 P0/P1 用例做冒烟优先执行",
        ]
        return Review(score=score, checks=checks, suggestions=suggestions)


# ---------------- LLM：接入真实大模型（OpenAI 兼容接口） ----------------

class _LLMClient:
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("EVAL_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct")

    def call(self, system: str, user: str) -> str:
        from openai import OpenAI  # 延迟导入，mock 模式无需安装

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        r = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return r.choices[0].message.content


def _parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    for i, ch in enumerate(text):
        if ch in "{[":
            return json.loads(text[i:])
    raise ValueError(f"无法从模型输出解析 JSON: {text[:120]}")


class LLMAnalyzerAgent(AnalyzerAgent):
    def __init__(self, llm: _LLMClient | None = None):
        self.llm = llm or _LLMClient()

    def analyze(self, prd_text: str) -> List[TestPoint]:
        user = f"""请基于以下 PRD 提炼测试点，显式运用四种方法：{'、'.join(METHODS)}。
PRD：
{prd_text}

只输出 JSON 数组，每项含字段：id, module, description, method(等价类/边界值/场景法/错误猜测), priority(P0/P1/P2)。"""
        data = _parse_json(self.llm.call("你是资深测试分析师，擅长从需求提炼测试点。", user))
        return [TestPoint(id=d.get("id", f"TP{i + 1:03d}"), module=d.get("module", "功能模块"),
                          description=d.get("description", ""), method=d.get("method", "场景法"),
                          priority=d.get("priority", "P2"), meta={}) for i, d in enumerate(data)]


class LLMGeneratorAgent(GeneratorAgent):
    def __init__(self, llm: _LLMClient | None = None):
        self.llm = llm or _LLMClient()

    def generate(self, points: List[TestPoint]) -> List[TestCase]:
        pts = [{"id": p.id, "module": p.module, "description": p.description, "method": p.method, "priority": p.priority} for p in points]
        user = f"""把以下测试点转成可执行测试用例。
测试点：{json.dumps(pts, ensure_ascii=False)}

只输出 JSON 数组，每项含字段：id, module, title, precondition, steps, expected, priority, method, testpoint_id。"""
        data = _parse_json(self.llm.call("你是测试用例设计工程师，输出规范、可执行的用例。", user))
        return [TestCase(id=d.get("id", f"TC{i + 1:03d}"), module=d.get("module", "功能模块"),
                         title=d.get("title", ""), precondition=d.get("precondition", ""),
                         steps=d.get("steps", ""), expected=d.get("expected", ""),
                         priority=d.get("priority", "P2"), method=d.get("method", "场景法"),
                         testpoint_id=d.get("testpoint_id", "")) for i, d in enumerate(data)]


class LLMReviewerAgent(ReviewerAgent):
    def __init__(self, llm: _LLMClient | None = None):
        self.llm = llm or _LLMClient()

    def review(self, cases: List[TestCase], points: List[TestPoint]) -> Review:
        cs = [{"id": c.id, "title": c.title, "method": c.method, "priority": c.priority,
               "has_precondition": bool(c.precondition), "has_steps": bool(c.steps),
               "has_expected": bool(c.expected), "testpoint_id": c.testpoint_id} for c in cases]
        user = f"""请按以下 5 项标准评审测试用例集：方法覆盖（等价类/边界值/场景法/错误猜测）、结构完整性、优先级标注、可追溯性、边界值完整性。
用例集：{json.dumps(cs, ensure_ascii=False)}

只输出 JSON：{{"score": 0-100 的整数, "checks": [{{"criterion": str, "passed": bool, "note": str}}], "suggestions": [str]}}。"""
        d = _parse_json(self.llm.call("你是资深测试架构师，负责用例评审。", user))
        return Review(score=int(d.get("score", 0)), checks=d.get("checks", []), suggestions=d.get("suggestions", []))
