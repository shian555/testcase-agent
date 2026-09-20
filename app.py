"""Streamlit 可视化 Demo：粘贴 PRD → 一键生成测试用例 → 在线查看 / 筛选 / 下载。

用法：
    python -m streamlit run app.py
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from agents import (LLMAnalyzerAgent, LLMGeneratorAgent, LLMReviewerAgent,
                    MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent)
from methods import METHODS
from pipeline import cases_csv, report_markdown

st.set_page_config(page_title="AI 测试用例生成 Agent", page_icon="🧪", layout="wide")


def get_agents(mode: str):
    """按模式返回三个 Agent：mock=规则版（离线、确定性、可复现），real=接真实大模型。"""
    if mode == "mock":
        return MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent()
    return LLMAnalyzerAgent(), LLMGeneratorAgent(), LLMReviewerAgent()


# ---------------- 侧边栏：模式 + 方法论说明 ----------------

with st.sidebar:
    st.header("⚙️ 运行模式")
    mode = st.radio("Agent 实现", ["mock", "real"], horizontal=True,
                    help="mock：规则化实现，离线可复现；real：接真实大模型（需设 LLM_API_KEY 等环境变量）")
    st.divider()
    st.subheader("📐 注入的测试方法论")
    for m, desc in METHODS.items():
        st.markdown(f"**{m}**：{desc}")
    st.divider()
    st.markdown("[GitHub 仓库](https://github.com/shian555/testcase-agent)")

# ---------------- 主区：输入 → 生成 → 展示 ----------------

st.title("🧪 AI 测试用例生成 Agent")
st.caption("多 Agent 流水线：PRD 解析 → 测试点提炼 → 用例生成 → 独立评审打分")

default_prd = Path("data/sample_prd.txt").read_text(encoding="utf-8")
prd_text = st.text_area("① 输入 PRD（产品需求文档）", value=default_prd, height=170)

# URL 带 ?auto=1 时自动执行（用于分享链接 / 录屏 / 自动截图）
auto_run = st.query_params.get("auto") == "1"

clicked = st.button("🚀 ② 生成测试用例", type="primary", disabled=not prd_text.strip())

if clicked or auto_run:
    if mode == "real" and not (os.getenv("LLM_API_KEY") or os.getenv("EVAL_API_KEY")):
        st.error("real 模式需要先设置环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（详见 README）")
        st.stop()

    # 流水线逐步执行，真实展示三个 Agent 的衔接（复用 pipeline.run 的同款调用顺序）
    with st.status("Agent 流水线执行中…", expanded=True) as status:
        analyzer, generator, reviewer = get_agents(mode)

        st.write("🔍 **AnalyzerAgent**：解析 PRD，按方法学提炼测试点…")
        points = analyzer.analyze(prd_text)
        st.write(f"　└ ✅ 产出测试点 **{len(points)}** 个")

        st.write("🛠️ **GeneratorAgent**：把测试点转成可执行用例…")
        cases = generator.generate(points)
        st.write(f"　└ ✅ 产出用例 **{len(cases)}** 条")

        st.write("⚖️ **ReviewerAgent**：按 5 项标准独立评审打分…")
        review = reviewer.review(cases, points)
        st.write(f"　└ ✅ 评审得分 **{review.score}/100**")

        status.update(label="✅ 流水线执行完成", state="complete", expanded=False)

    # ---- 总览指标 ----
    st.success(f"生成完成：测试点 {len(points)} 个 · 用例 {len(cases)} 条 · 评审得分 {review.score}/100")
    m1, m2, m3 = st.columns(3)
    m1.metric("测试点", len(points))
    m2.metric("测试用例", len(cases))
    m3.metric("评审得分", f"{review.score}/100")
    st.progress(review.score / 100,
                text=f"评审得分 {review.score}/100（mock 模式满分是规则保证的设计结果；real 模式才会暴露真实问题）")

    # ---- 分页签展示 ----
    tab_points, tab_cases, tab_review, tab_download = st.tabs(
        ["📋 测试点", "🧾 测试用例", "⚖️ 评审详情", "⬇️ 下载"])

    with tab_points:
        rows = [{"ID": p.id, "模块": p.module, "测试点": p.description,
                 "方法": p.method, "优先级": p.priority} for p in points]
        st.dataframe(rows, width="stretch", hide_index=True)

    with tab_cases:
        f1, f2 = st.columns(2)
        sel_methods = f1.multiselect("按方法筛选", list(METHODS), default=list(METHODS))
        sel_prio = f2.multiselect("按优先级筛选", ["P0", "P1", "P2"], default=["P0", "P1", "P2"])
        shown = [c for c in cases if c.method in sel_methods and c.priority in sel_prio]
        st.caption(f"显示 {len(shown)} / {len(cases)} 条")
        rows = [{"ID": c.id, "模块": c.module, "标题": c.title, "方法": c.method,
                 "优先级": c.priority, "前置条件": c.precondition,
                 "步骤": c.steps, "预期结果": c.expected} for c in shown]
        st.dataframe(rows, width="stretch", hide_index=True, height=460)

    with tab_review:
        st.subheader("评审检查项")
        for c in review.checks:
            icon = "✅" if c["passed"] else "❌"
            st.markdown(f"- {icon} **{c['criterion']}**：{c.get('note', '')}")
        st.subheader("改进建议")
        for s in review.suggestions:
            st.markdown(f"- {s}")

    with tab_download:
        d1, d2 = st.columns(2)
        d1.download_button("下载 test_cases.csv（Excel 可直接打开）",
                           data=cases_csv(cases).encode("utf-8-sig"),
                           file_name="test_cases.csv", mime="text/csv")
        d2.download_button("下载 report.md",
                           data=report_markdown(points, cases, review).encode("utf-8"),
                           file_name="report.md", mime="text/markdown")
        with st.expander("在线预览 Markdown 报告"):
            st.markdown(report_markdown(points, cases, review))

else:
    st.info("👆 在上方输入（或保留示例）PRD，点击「生成测试用例」查看三个 Agent 的完整流水线输出。")
