"""测试报告页：单次测试单的执行结果统计、质量结论与多格式导出。"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from excel_export import run_report_workbook
import store
from styles import (DANGER, PLOTLY_CONFIG, PRIMARY, SUCCESS, WARNING, banner,
                    kpi_card, page_header, result_styler, style_chart)


def render() -> None:
    page_header("测试报告", "单次测试单的执行统计、模块/优先级下钻与发布建议")
    runs = store.list_runs()
    if not runs:
        st.info("还没有测试单。先去「测试执行」创建并记录执行结果。")
        from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
        st.page_link(PAGES["execution"], label="▶️ 前往测试执行")
        return

    run = _pick_run(runs)
    rows = store.run_cases(run["id"])
    if not rows:
        st.warning("该测试单没有用例（相关用例可能已被删除）。")
        return

    _kpi_band(run)
    _conclusion(run, rows)
    _charts(run, rows)
    _issue_list(run, rows)
    _exports(run)


def _pick_run(runs: list[dict]) -> dict:
    """默认定位最近一个已完成的测试单。"""
    default = 0
    for i, r in enumerate(runs):
        if r["status"] == "done":
            default = i
            break
    labels = [f"RUN-{r['id']:04d} · {r['name']} · "
              f"{'🟢 进行中' if r['status'] == 'in_progress' else '✅ 已完成'}" for r in runs]
    idx = st.selectbox("选择测试单", range(len(labels)), index=default,
                       format_func=lambda i: labels[i], key="report_pick")
    return runs[idx]


def _kpi_band(run: dict) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        kpi_card("用例总数", run["total"], f"已执行 {run['executed']} 条")
    with c2:
        kpi_card("通过", run["passed"], accent=SUCCESS)
    with c3:
        kpi_card("失败", run["failed"], accent=DANGER)
    with c4:
        kpi_card("阻塞", run["blocked"], accent=WARNING)
    with c5:
        kpi_card("未执行", run["pending"], accent="#64748B")
    with c6:
        rate = f"{run['pass_rate']:.1%}" if run["executed"] else "—"
        kpi_card("通过率", rate, accent=SUCCESS if run["pass_rate"] >= 0.9 else WARNING)


def _conclusion(run: dict, rows: list[dict]) -> None:
    bad = [r for r in rows if r["result"] in ("失败", "阻塞")]
    p0_bad = [r for r in bad if r["priority"] == "P0"]
    if not bad and run["pending"] == 0:
        banner("ok", "✅ 全部通过，可发布",
               f"RUN-{run['id']:04d} 共 {run['total']} 条用例全部执行通过，未发现阻塞或失败问题。")
    elif p0_bad:
        banner("bad", "⛔ 存在 P0 问题，不建议发布",
               f"{len(p0_bad)} 条 P0 用例失败或阻塞（"
               + "、".join(r["case_id"] for r in p0_bad[:5])
               + "），修复后需回归 P0 场景。")
    elif bad:
        banner("warn", "⚠️ 存在非 P0 问题，修复后可回归发布",
               f"{len(bad)} 条用例失败/阻塞，集中在："
               + "、".join(sorted({r['module'] for r in bad})) + "。")
    else:
        banner("warn", "⏳ 执行未完成",
               f"还有 {run['pending']} 条用例未执行，结论以完成执行后的数据为准。")


def _charts(run: dict, rows: list[dict]) -> None:
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown("##### 结果分布")
        counts = pd.DataFrame([{"结果": label, "数量": run[key] or 0} for label, key in
                               (("通过", "passed"), ("失败", "failed"), ("阻塞", "blocked"),
                                ("跳过", "skipped"), ("未执行", "pending"))])
        counts = counts[counts["数量"] > 0]
        fig = style_chart(px.pie(counts, names="结果", values="数量", hole=0.58,
                                 color="结果",
                                 color_discrete_map={"通过": "#16A34A", "失败": "#DC2626",
                                                     "阻塞": "#D97706", "跳过": "#94A3B8",
                                                     "未执行": "#CBD5E1"}),
                          height=300)
        st.plotly_chart(fig, use_container_width=True, key="pie_result",
                        config=PLOTLY_CONFIG)

    with c2:
        st.markdown("##### 优先级通过率")
        prio_rows = []
        for p in ("P0", "P1", "P2"):
            prows = [r for r in rows if r["priority"] == p]
            if not prows:
                continue
            exe = sum(1 for r in prows if r["result"] != "未执行")
            ok = sum(1 for r in prows if r["result"] == "通过")
            prio_rows.append({"优先级": p, "通过率": ok / exe if exe else 0.0,
                              "明细": f"{ok}/{exe}"})
        if prio_rows:
            fig = style_chart(px.bar(pd.DataFrame(prio_rows), x="优先级", y="通过率",
                                     color="优先级", text="明细",
                                     color_discrete_map={"P0": "#DC2626", "P1": "#D97706",
                                                         "P2": "#94A3B8"}),
                              height=300, legend=None)
            fig.update_layout(yaxis_tickformat=".0%", yaxis_range=[0, 1.05])
            st.plotly_chart(fig, use_container_width=True, key="bar_prio",
                            config=PLOTLY_CONFIG)

    st.markdown("##### 模块 × 结果")
    mod = pd.DataFrame([{"模块": r["module"], "结果": r["result"]} for r in rows])
    fig = style_chart(px.histogram(mod, x="模块", color="结果", barmode="stack",
                                   color_discrete_map={"通过": "#16A34A", "失败": "#DC2626",
                                                       "阻塞": "#D97706", "跳过": "#94A3B8",
                                                       "未执行": "#CBD5E1"}),
                      height=300)
    fig.update_layout(bargap=0.35)  # 单模块时柱子不再横贯全宽
    st.plotly_chart(fig, use_container_width=True, key="bar_module",
                    config=PLOTLY_CONFIG)


def _issue_list(run: dict, rows: list[dict]) -> None:
    issues = [r for r in rows if r["result"] in ("失败", "阻塞")]
    st.markdown(f"##### 问题清单（失败 / 阻塞，共 {len(issues)} 条）")
    if not issues:
        st.caption("本测试单无失败或阻塞问题 🎉")
        return
    df = pd.DataFrame([{"用例ID": r["case_id"], "模块": r["module"], "标题": r["title"],
                        "优先级": r["priority"], "类型": r["result"],
                        "备注": r["note"] or "—"} for r in issues])
    st.dataframe(result_styler(df, "类型"), width="stretch", hide_index=True, height=260)

    # 执行失败 → 缺陷登记（企业闭环：报告里发现的问题可跟踪）
    existing = {d["source_case_id"] for d in store.list_defects()
                if d["source_case_id"]}
    fresh = [r for r in issues if r["case_id"] not in existing]
    if not fresh:
        st.caption("✅ 本单失败/阻塞用例均已登记缺陷，可在「缺陷管理」跟踪修复进度。")
        return
    with st.popover(f"🐞 将失败用例登记为缺陷（{len(fresh)} 条未登记）"):
        st.caption("登记后可在「缺陷管理」页跟踪 修复 → 验证关闭 全流程。")
        options = [f'{r["case_id"]} · {r["title"]}（{r["result"]}）' for r in fresh]
        pick = st.selectbox("选择用例", options, key="rep_def_pick")
        severity = st.selectbox("严重程度", list(store._SEVERITIES), index=1,
                                key="rep_def_sev")
        if st.button("登记缺陷", type="primary"):
            r = fresh[options.index(pick)]
            did = store.create_defect(
                title=f"[{r['module']}] {r['title']}", module=r["module"],
                severity=severity,
                description=f"来源：RUN-{run['id']:04d} 执行「{r['result']}」；{r['note'] or ''}",
                source_case_id=r["case_id"], run_id=run["id"])
            st.toast(f"缺陷 {did} 已登记")
            st.rerun()


@st.cache_data(show_spinner=False)
def _export_run_excel(version: int, run_id: int) -> bytes:
    """执行报表 Excel：version 作为缓存盐，数据未变时零重建。"""
    run = store.get_run(run_id)
    if run is None:
        return b""
    return run_report_workbook(run, store.run_cases(run_id))


@st.cache_data(show_spinner=False)
def _export_run_md(version: int, run_id: int) -> bytes:
    run = store.get_run(run_id)
    if run is None:
        return b""
    return _run_markdown(run, store.run_cases(run_id)).encode("utf-8")


def _exports(run: dict) -> None:
    st.markdown("##### 导出")
    v = store.version()
    rid = run["id"]
    d1, d2 = st.columns(2)
    d1.download_button("下载执行报表.xlsx（汇总+明细+问题清单）",
                       data=_export_run_excel(v, rid),
                       file_name=f"RUN-{rid:04d}_执行报表.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    d2.download_button("下载 report.md",
                       data=_export_run_md(v, rid),
                       file_name=f"RUN-{rid:04d}_执行报告.md",
                       mime="text/markdown", use_container_width=True)


def _run_markdown(run: dict, rows: list[dict]) -> str:
    """执行报告 Markdown 渲染（仅报告页使用，不影响 pipeline.report_markdown）。"""
    lines = [f"# 测试执行报告 · RUN-{run['id']:04d}", ""]
    lines += [f"- 名称：{run['name']}", f"- 环境：{run['env']}",
              f"- 状态：{'已完成' if run['status'] == 'done' else '进行中'}",
              f"- 通过率：{run['pass_rate']:.1%}（通过 {run['passed']} / 失败 {run['failed']}"
              f" / 阻塞 {run['blocked']} / 跳过 {run['skipped']} / 未执行 {run['pending']}）", ""]
    lines += ["| 用例ID | 模块 | 标题 | 优先级 | 结果 | 备注 |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['case_id']} | {r['module']} | {r['title']} | {r['priority']} "
               f"| {r['result']} | {r['note']} |" for r in rows]
    return "\n".join(lines)
