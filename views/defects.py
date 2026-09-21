"""缺陷管理页：失败问题登记 → 状态流转（打开/修复中/已解决/已关闭）→ 与用例、测试单双向追溯。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import store
from styles import (DANGER, DEFECT_STATUS_COLORS, PRIMARY, SEVERITY_COLORS,
                    SUCCESS, WARNING, guide_steps, kpi_card, page_header,
                    pill_styler)


def render() -> None:
    page_header("缺陷管理", "失败问题全程跟踪：登记 → 修复 → 验证关闭，与用例 / 测试单双向关联")
    guide_steps(["从报告页或手工登记缺陷", "跟进修复流转状态", "回归验证后关闭"])

    _kpi_band()
    defects = _toolbar_and_query()

    if defects:
        selected = _defect_table(defects)
        if selected:
            _actions(selected)
    else:
        st.info("暂无缺陷记录。执行中发现失败用例后，可从下方「从失败用例创建」一键登记，"
                "或手工新建。")

    _create_from_failure()
    _new_defect_expander()


def _kpi_band() -> None:
    stats = store.defect_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi_card("缺陷总数", stats["total"], f"待处理 {stats['打开'] + stats['修复中']} 个",
                 accent=PRIMARY)
    with c2:
        kpi_card("打开", stats["打开"], "待确认 / 分派", accent=DANGER)
    with c3:
        kpi_card("修复中", stats["修复中"], "开发处理中", accent=WARNING)
    with c4:
        kpi_card("已解决", stats["已解决"], "待回归验证", accent="#2563EB")
    with c5:
        kpi_card("已关闭", stats["已关闭"], "回归验证通过", accent=SUCCESS)


def _toolbar_and_query() -> list[dict]:
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1.2])
    keyword = f1.text_input("🔍 关键字（标题/模块/描述/来源用例）", key="def_kw")
    status = f2.selectbox("状态", ["全部", *store._DEFECT_STATUSES], key="def_status")
    severity = f3.selectbox("严重程度", ["全部", *store._SEVERITIES], key="def_severity")
    module = f4.text_input("模块", key="def_module")

    defects = store.list_defects(
        keyword=keyword.strip(),
        status=None if status == "全部" else status,
        severity=None if severity == "全部" else severity,
        module=module.strip())
    if defects:
        st.caption(f"共 {len(defects)} 条缺陷")
    return defects


def _defect_table(defects: list[dict]) -> list[str]:
    rows = [{"ID": d["id"], "标题": d["title"], "模块": d["module"],
             "严重程度": d["severity"], "状态": d["status"], "处理人": d["assignee"] or "—",
             "来源用例": d["source_case_id"] or "—", "创建时间": d["created_at"]}
            for d in defects]
    df = pd.DataFrame(rows)
    event = st.dataframe(
        pill_styler(df, {"严重程度": SEVERITY_COLORS, "状态": DEFECT_STATUS_COLORS}),
        width="stretch", hide_index=True, height=380,
        on_select="rerun", selection_mode="multi-row", key="def_table")
    return [rows[i]["ID"] for i in event.selection.rows]


def _actions(ids: list[str]) -> None:
    a1, a2, a3 = st.columns([1.6, 1.6, 1])
    with a1.popover(f"🔄 状态流转（已选 {len(ids)} 条）", use_container_width=True):
        st.caption("打开 → 修复中 → 已解决 → 已关闭；验证不通过可重新打开。")
        new_status = st.selectbox("目标状态", list(store._DEFECT_STATUSES), key="def_flow")
        new_assignee = st.text_input("处理人（可选，批量指派）", key="def_flow_assignee",
                                     placeholder="如：刘畅")
        if st.button("确认流转", type="primary", use_container_width=True):
            for did in ids:
                store.update_defect(did, status=new_status,
                                    assignee=new_assignee.strip() or None)
            st.toast(f"已把 {len(ids)} 条缺陷置为「{new_status}」")
            st.rerun()
    with a2.popover(f"🗑 删除（已选 {len(ids)} 条）", use_container_width=True):
        st.warning("删除后不可恢复。")
        if st.checkbox("我确认删除", key="def_del_confirm") and st.button(
                "确认删除", type="primary", use_container_width=True):
            store.delete_defects(ids)
            st.toast(f"已删除 {len(ids)} 条缺陷")
            st.rerun()
    with a3:
        from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
        st.page_link(PAGES["execution"], label="↩️ 回归执行", use_container_width=True)


def _create_from_failure() -> None:
    """从执行失败的用例一键登记缺陷（预填模块/标题/来源）。"""
    with st.expander("🐞 从失败用例创建缺陷", expanded=False):
        runs = store.list_runs()
        if not runs:
            st.caption("还没有测试单，先去「测试执行」完成一轮执行。")
            return
        labels = [f"RUN-{r['id']:04d} · {r['name']}" for r in runs]
        run = runs[st.selectbox("选择测试单", range(len(labels)),
                                format_func=lambda i: labels[i], key="def_run_pick")]
        failures = [r for r in store.run_cases(run["id"])
                    if r["result"] in ("失败", "阻塞")]
        if not failures:
            st.caption("该测试单没有失败 / 阻塞用例 🎉")
            return

        with st.form("defect_from_failure", border=False):
            options = [f'{r["case_id"]} · {r["title"]}（{r["result"]}）' for r in failures]
            pick = st.selectbox("失败用例", options, key="def_failure_pick")
            c1, c2 = st.columns(2)
            severity = c1.selectbox("严重程度", list(store._SEVERITIES), index=1)
            assignee = c2.text_input("处理人", key="def_assignee", placeholder="如：刘畅")
            description = st.text_area("缺陷描述（复现步骤 / 实际 vs 预期）",
                                       height=90, key="def_desc")
            submitted = st.form_submit_button("登记缺陷", type="primary",
                                              use_container_width=True)
        if submitted:
            r = failures[options.index(pick)]
            did = store.create_defect(
                title=f"[{r['module']}] {r['title']}",
                module=r["module"], severity=severity,
                description=description.strip() or f"来源：RUN-{run['id']:04d} 执行「{r['result']}」；{r['note'] or ''}",
                source_case_id=r["case_id"], run_id=run["id"],
                assignee=assignee.strip())
            st.toast(f"缺陷 {did} 已登记")
            st.rerun()


def _new_defect_expander() -> None:
    with st.expander("➕ 手工新建缺陷", expanded=False):
        with st.form("new_defect", border=False):
            t1, t2 = st.columns([2, 1])
            title = t1.text_input("标题*", placeholder="如：登录页验证码为空仍可提交")
            module = t2.text_input("模块", placeholder="如：登录")
            c1, c2 = st.columns(2)
            severity = c1.selectbox("严重程度", list(store._SEVERITIES), index=1)
            assignee = c2.text_input("处理人", key="def_manual_assignee",
                                     placeholder="如：刘畅")
            description = st.text_area("描述", height=90, key="def_manual_desc")
            submitted = st.form_submit_button("创建缺陷", type="primary",
                                              use_container_width=True)
        if submitted:
            if not title.strip():
                st.error("标题为必填项")
            else:
                did = store.create_defect(title=title.strip(), module=module.strip(),
                                          severity=severity, description=description.strip(),
                                          assignee=assignee.strip())
                st.toast(f"缺陷 {did} 已创建")
                st.rerun()
