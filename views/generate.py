"""用例生成页：PRD → 测试点 → 用例 → 评审 三 Agent 流水线 + 采纳入库（人机协同）。"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import (LLMAnalyzerAgent, LLMGeneratorAgent, LLMReviewerAgent,
                    MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent)
from excel_export import generation_workbook
from methods import METHODS
from pipeline import cases_csv, report_markdown
import store
from styles import guide_steps, page_header, priority_styler


def _get_agents(mode: str):
    """按模式返回三个 Agent：mock=规则版（离线、确定性、可复现），real=接真实大模型。"""
    if mode == "mock":
        return MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent()
    return LLMAnalyzerAgent(), LLMGeneratorAgent(), LLMReviewerAgent()


@st.cache_data(show_spinner=False)
def _export_generation_excel(n_points: int, n_cases: int, score: int, case_ids: tuple) -> bytes:
    """生成报告 Excel：以批次规模 + 用例 ID 序列为缓存盐，翻页不再重复构建。"""
    return generation_workbook(st.session_state.gen_points, st.session_state.gen_cases,
                               st.session_state.gen_review)


def render() -> None:
    page_header("用例生成", "粘贴 PRD，三 Agent 流水线产出测试点与用例，人工勾选采纳后沉淀入用例库")
    guide_steps(["粘贴 PRD 文档", "点击「开始生成」", "评审后勾选采纳入库", "导出报告归档"])

    with st.expander("📐 注入的测试方法论", expanded=False):
        st.markdown("　".join(f"**{m}**" for m in METHODS))
        for m, desc in METHODS.items():
            st.markdown(f"- **{m}**：{desc}")

    left, right = st.columns([2, 3], gap="medium")

    with left:
        default_prd = (Path(__file__).resolve().parents[1] / "data" / "sample_prd.txt").read_text(encoding="utf-8")
        prd_text = st.text_area("① 输入 PRD（产品需求文档）", value=default_prd, height=300, key="prd_text")
        st.button("🚀 ② 开始生成", type="primary", use_container_width=True,
                  disabled=not prd_text.strip(), key="run_pipeline")
        clicked = st.session_state.run_pipeline
        auto_run = st.query_params.get("auto") == "1"  # 截图 / 分享链接自动执行钩子

    with right:
        if clicked or auto_run:
            _run_pipeline(prd_text)
        if "gen_points" in st.session_state:
            _render_results()
        else:
            st.info("👈 在左侧输入（或保留示例）PRD，点击「开始生成」，查看三个 Agent 的完整流水线输出。\n\n"
                    "生成结果可通过「采纳入库」沉淀为团队用例资产，再圈选建测试单执行。")


def _run_pipeline(prd_text: str) -> None:
    mode = st.session_state.get("mode", "mock")
    if mode == "real" and not (os.getenv("LLM_API_KEY") or os.getenv("EVAL_API_KEY")):
        st.error("real 模式需要先设置环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（见设置页）")
        return

    with st.status("Agent 流水线执行中…", expanded=True) as status:
        analyzer, generator, reviewer = _get_agents(mode)

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

    st.session_state.gen_points = points
    st.session_state.gen_cases = cases
    st.session_state.gen_review = review
    st.session_state.pop("gen_adopted", None)   # 新批次：重置采纳状态与编辑器
    st.session_state.pop("adopt_df", None)


def _render_results() -> None:
    points = st.session_state.gen_points
    cases = st.session_state.gen_cases
    review = st.session_state.gen_review

    st.success(f"生成完成：测试点 {len(points)} 个 · 用例 {len(cases)} 条 · 评审得分 {review.score}/100")
    st.progress(review.score / 100,
                text=f"评审得分 {review.score}/100（mock 模式满分是规则保证的设计结果；real 模式才暴露真实问题）")

    tab_points, tab_cases, tab_review, tab_adopt, tab_export = st.tabs(
        ["📋 测试点", "🧾 用例", "⚖️ 评审详情", "✅ 采纳入库", "⬇️ 导出"])

    with tab_points:
        df = pd.DataFrame([{"ID": p.id, "模块": p.module, "测试点": p.description,
                            "方法": p.method, "优先级": p.priority} for p in points])
        st.dataframe(priority_styler(df), width="stretch", hide_index=True, height=380)

    with tab_cases:
        f1, f2 = st.columns(2)
        sel_methods = f1.multiselect("按方法筛选", list(METHODS), default=list(METHODS),
                                     key="gen_case_methods")
        sel_prio = f2.multiselect("按优先级筛选", ["P0", "P1", "P2"], default=["P0", "P1", "P2"],
                                  key="gen_case_prios")
        shown = [c for c in cases if c.method in sel_methods and c.priority in sel_prio]
        st.caption(f"显示 {len(shown)} / {len(cases)} 条")
        df = pd.DataFrame([{"ID": c.id, "模块": c.module, "标题": c.title, "方法": c.method,
                            "优先级": c.priority, "前置条件": c.precondition,
                            "步骤": c.steps, "预期结果": c.expected} for c in shown])
        st.dataframe(priority_styler(df), width="stretch", hide_index=True, height=430)

    with tab_review:
        st.markdown("##### 评审检查项")
        for c in review.checks:
            st.markdown(f"- {'✅' if c['passed'] else '❌'} **{c['criterion']}**：{c.get('note', '')}")
        st.markdown("##### 改进建议")
        for s in review.suggestions:
            st.markdown(f"- 💡 {s}")

    with tab_adopt:
        _adopt_tab(cases, review)

    with tab_export:
        d1, d2, d3 = st.columns(3)
        d1.download_button("下载 test_cases.csv（Excel 可直接打开）",
                           data=cases_csv(cases).encode("utf-8-sig"),
                           file_name="test_cases.csv", mime="text/csv",
                           use_container_width=True)
        d2.download_button("下载 report.md",
                           data=report_markdown(points, cases, review).encode("utf-8"),
                           file_name="report.md", mime="text/markdown",
                           use_container_width=True)
        d3.download_button("下载生成报告.xlsx（格式化）",
                           data=_export_generation_excel(len(points), len(cases),
                                                         review.score,
                                                         tuple(c.id for c in cases)),
                           file_name="用例生成报告.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
        with st.expander("在线预览 Markdown 报告"):
            st.markdown(report_markdown(points, cases, review))


def _adopt_tab(cases, review) -> None:
    """采纳入库：人工编辑 + 勾选 → 写入 gen_batches + cases（人机协同闭环）。"""
    if "gen_adopted" in st.session_state:
        batch_id, n = st.session_state.gen_adopted
        st.success(f"本批已采纳 **{n}** 条用例入用例库（批次 {batch_id[:14]}…）。"
                   "可在用例库中检索编辑，或圈选创建测试单。")
        from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
        c1, c2 = st.columns(2)
        c1.page_link(PAGES["library"], label="📚 前往用例库", use_container_width=True)
        c2.page_link(PAGES["execution"], label="▶️ 前往测试执行", use_container_width=True)
        return

    if "adopt_df" not in st.session_state:
        st.session_state.adopt_df = pd.DataFrame([{
            "采纳": False, "ID": c.id, "模块": c.module, "标题": c.title,
            "优先级": c.priority, "方法": c.method, "前置条件": c.precondition,
            "步骤": c.steps, "预期结果": c.expected,
        } for c in cases])

    q1, q2, q3, q4 = st.columns(4)
    if q1.button("全选", use_container_width=True):
        st.session_state.adopt_df["采纳"] = True
        st.session_state.pop("adopt_editor", None)
        st.rerun()
    if q2.button("全选 P0", use_container_width=True):
        df = st.session_state.adopt_df
        df.loc[df["优先级"] == "P0", "采纳"] = True
        st.session_state.pop("adopt_editor", None)
        st.rerun()
    if q3.button("清空勾选", use_container_width=True):
        st.session_state.adopt_df["采纳"] = False
        st.session_state.pop("adopt_editor", None)
        st.rerun()
    dedup = q4.checkbox("跳过库中同模块同名用例", value=True, key="adopt_dedup")

    ed = st.data_editor(
        st.session_state.adopt_df,
        key="adopt_editor",
        hide_index=True,
        width="stretch",
        height=400,
        column_config={
            "采纳": st.column_config.CheckboxColumn("采纳", help="勾选后可批量入库", default=False),
            "ID": st.column_config.TextColumn("ID", disabled=True),
            "方法": st.column_config.TextColumn("方法", disabled=True, width="medium"),
            "标题": st.column_config.TextColumn("标题", width="medium"),
            "优先级": st.column_config.SelectboxColumn("优先级", options=["P0", "P1", "P2"],
                                                       required=True),
            "前置条件": st.column_config.TextColumn("前置条件", width="large"),
            "步骤": st.column_config.TextColumn("步骤", width="large"),
            "预期结果": st.column_config.TextColumn("预期结果", width="large"),
        })

    n = int(ed["采纳"].sum())
    st.button(f"✅ 采纳勾选的 {n} 条用例入用例库", type="primary", use_container_width=True,
              disabled=n == 0, key="adopt_submit")
    if st.session_state.adopt_submit:
        mode = st.session_state.get("mode", "mock")
        items = [{"module": r["模块"], "title": r["标题"], "priority": r["优先级"],
                  "method": r["方法"], "precondition": r["前置条件"], "steps": r["步骤"],
                  "expected": r["预期结果"], "testpoint_id": ""} for _, r in ed[ed["采纳"]].iterrows()]
        batch_id, ids = store.adopt_batch(st.session_state.get("prd_text", ""), mode,
                                          review.score, items, dedup=dedup)
        st.session_state.gen_adopted = (batch_id, len(ids))
        st.session_state.pop("adopt_df", None)
        st.rerun()
