"""工作台页：KPI 全景 + 分布图表 + 最近测试单；空库时引导填充演示数据。"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import store
from styles import (DANGER, PLOTLY_CONFIG, PRIMARY, SUCCESS, WARNING,
                    kpi_card, page_header, result_styler, style_chart)


def render() -> None:
    page_header("工作台", "测试资产、执行进度与质量全景")
    kpi = store.kpi_snapshot()

    if kpi["cases_total"] == 0 and kpi["runs_total"] == 0:
        _onboarding()
        return

    _kpi_row(kpi)
    _charts()
    _recent_runs()


def _onboarding() -> None:
    st.markdown(
        '<div class="banner"><div class="t">👋 欢迎使用 AI 智能测试平台</div>'
        '<div class="d">平台提供「用例生成 → 采纳入库 → 测试执行 → 质量报告 → 缺陷跟踪」完整闭环。'
        "当前还没有数据：可一键填充演示数据（mock 流水线跑样例 PRD 并完成一轮回归测试），"
        "或直接从用例生成开始。</div></div>",
        unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.button("📦 填充演示数据", type="primary", use_container_width=True, key="seed_demo")
    if st.session_state.get("seed_demo"):
        store.seed_demo()
        st.toast("演示数据已就绪")
        st.rerun()
    from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
    c2.page_link(PAGES["generate"], label="🤖 直接开始用例生成", use_container_width=True)
    st.caption("演示数据可随时在「设置 → 数据管理」中清空。")


def _kpi_row(kpi: dict) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("用例总数", kpi["cases_total"], "启用状态 · 含 AI 与手工")
    with c2:
        kpi_card("AI 生成占比", f"{kpi['ai_share']:.0%}", "由平台流水线采纳入库", accent=PRIMARY)
    with c3:
        kpi_card("测试单", kpi["runs_total"],
                 f"进行中 {kpi['runs_in_progress']} 个", accent="#8B5CF6")
    with c4:
        kpi_card("待处理缺陷", kpi["defects_open"], "打开 + 修复中",
                 accent=DANGER if kpi["defects_open"] else SUCCESS)
    with c5:
        last = kpi["last_pass_rate"]
        name = kpi["last_run_name"] or "暂无已完成的测试单"
        kpi_card("最近通过率", f"{last:.1%}" if last is not None else "—",
                 name[:12] + "…" if len(name) > 12 else name,  # 过长会换行撑高卡片
                 accent=SUCCESS if (last or 0) >= 0.9 else WARNING)


def _charts() -> None:
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown("##### 用例方法分布")
        stats = store.method_stats()
        if stats:
            df = pd.DataFrame([{"方法": s["method"], "数量": s["count"]} for s in stats])
            fig = style_chart(px.pie(df, names="方法", values="数量", hole=0.58),
                              height=300)  # 不指定色板 → 继承 style_chart 的企业色序
            st.plotly_chart(fig, use_container_width=True, key="dash_method",
                            config=PLOTLY_CONFIG)
        else:
            st.info("暂无用例")

    with c2:
        st.markdown("##### 优先级分布（AI / 手工）")
        stats = store.priority_stats()
        if stats:
            df = pd.DataFrame([{"优先级": s["priority"], "AI 生成": s["ai"],
                                "手工创建": s["manual"]} for s in stats])
            fig = style_chart(px.bar(df, x="优先级", y=["AI 生成", "手工创建"],
                                     text_auto=True,
                                     color_discrete_map={"AI 生成": "#2563EB",
                                                         "手工创建": "#94A3B8"}),
                              height=300)
            fig.update_layout(barmode="stack")
            st.plotly_chart(fig, use_container_width=True, key="dash_prio",
                            config=PLOTLY_CONFIG)
        else:
            st.info("暂无用例")

    st.markdown("##### 测试单通过率趋势（最近完成）")
    trend = store.trend_last_runs(10)
    if trend:
        df = pd.DataFrame([{"测试单": t["run"], "通过率": t["pass_rate"]} for t in trend])
        fig = style_chart(px.line(df, x="测试单", y="通过率", markers=True), height=280,
                          legend=None)
        fig.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, 1.05])
        st.plotly_chart(fig, use_container_width=True, key="dash_trend",
                        config=PLOTLY_CONFIG)
    else:
        st.caption("还没有已完成的测试单，通过率趋势将在完成首轮执行后呈现。")


def _recent_runs() -> None:
    st.markdown("##### 最近测试单")
    runs = store.list_runs()[:5]
    if not runs:
        st.caption("暂无测试单")
        return
    df = pd.DataFrame([{
        "测试单": f"RUN-{r['id']:04d}", "名称": r["name"], "环境": r["env"],
        "状态": "🟢 进行中" if r["status"] == "in_progress" else "✅ 已完成",
        "进度": (r["executed"] / r["total"] * 100) if r["total"] else 0,
        "通过率": f"{r['pass_rate']:.1%}" if r["executed"] else "—",
        "用例数": r["total"],
    } for r in runs])
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={
                     "进度": st.column_config.ProgressColumn("执行进度", min_value=0.0,
                                                             max_value=100.0, format="%.0f%%"),
                 })
    from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
    st.page_link(PAGES["execution"], label="▶️ 前往测试执行")
