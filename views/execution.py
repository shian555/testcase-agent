"""测试执行页：圈选用例建测试单 → 逐条记录执行结果 → 标记完成。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from excel_export import run_report_workbook
from methods import METHODS
import store
from styles import RESULT_COLORS, page_header, pill, result_styler

_RESULTS = ["未执行", "通过", "失败", "阻塞", "跳过"]


@st.cache_data(show_spinner=False)
def _export_run_excel(version: int, run_id: int) -> bytes:
    """执行报表 Excel：version 为缓存盐，数据未变时跳过重建（拖慢每次重渲染的元凶）。"""
    run = store.get_run(run_id)
    if run is None:
        return b""
    return run_report_workbook(run, store.run_cases(run_id))


def render() -> None:
    page_header("测试执行", "从用例库圈选用例创建测试单，逐条记录执行结果")
    runs = store.list_runs()
    _create_run_expander(runs)

    if not runs:
        st.info("还没有测试单。先创建一个：展开上方「新建测试单」，圈选用例后创建。")
        return

    run = _pick_run(runs)
    _run_panel(run)


def _create_run_expander(runs: list[dict]) -> None:
    with st.expander("➕ 新建测试单", expanded=not runs):
        pool = store.list_cases(status="active")
        if not pool:
            st.warning("用例库为空，先去「用例生成」采纳用例或新建手工用例。")
            return

        f1, f2, f3, f4 = st.columns([2, 1.3, 1.2, 1])
        keyword = f1.text_input("🔍 筛选用例（标题/模块/标签）", key="mk_kw")
        sel_prio = f2.multiselect("优先级", ["P0", "P1", "P2"], key="mk_prio")
        sel_method = f3.multiselect("方法", list(METHODS), key="mk_method")
        st.caption(f"用例库共 {len(pool)} 条 active 用例")

        picked = store.list_cases(keyword=keyword.strip(), priority=sel_prio or None,
                                  method=sel_method or None)
        rows = [{"选择": False, "ID": c["id"], "模块": c["module"], "标题": c["title"],
                 "优先级": c["priority"], "方法": c["method"]} for c in picked]
        df = pd.DataFrame(rows)
        sel = st.data_editor(df, key="mk_picker", hide_index=True, width="stretch", height=300,
                             column_config={
                                 "选择": st.column_config.CheckboxColumn("选择", default=False),
                                 "ID": st.column_config.TextColumn("ID", disabled=True),
                                 "模块": st.column_config.TextColumn("模块", disabled=True),
                                 "标题": st.column_config.TextColumn("标题", disabled=True, width="medium"),
                                 "优先级": st.column_config.TextColumn("优先级", disabled=True),
                                 "方法": st.column_config.TextColumn("方法", disabled=True),
                             })
        chosen_ids = [r["ID"] for _, r in sel.iterrows() if r["选择"]]
        st.caption(f"已圈选 **{len(chosen_ids)}** 条用例")

        t1, t2, t3 = st.columns([2, 1, 1.4])
        name = t1.text_input("测试单名称*", value=f"回归 {datetime.now():%m-%d %H:%M}", key="mk_name")
        env = t2.selectbox("环境", ["测试环境", "预发环境", "生产环境"], key="mk_env")
        note = t3.text_input("备注", key="mk_note")
        st.button("创建测试单", type="primary",
                  disabled=not (name.strip() and chosen_ids), use_container_width=True,
                  key="mk_submit", help="至少填写名称并圈选用例")
        if st.session_state.get("mk_submit"):
            run_id = store.create_run(name=name.strip(), env=env, note=note.strip(),
                                      case_ids=chosen_ids)
            st.toast(f"测试单 RUN-{run_id:04d} 已创建")
            st.rerun()


def _pick_run(runs: list[dict]) -> dict:
    """测试单选择器：优先定位新建/指定要进入的单。"""
    enter = st.session_state.pop("enter_run_id", None)
    default = 0
    if enter:
        for i, r in enumerate(runs):
            if r["id"] == enter:
                default = i
                break
    labels = [f"RUN-{r['id']:04d} · {r['name']} · "
              f"{'🟢 进行中' if r['status'] == 'in_progress' else '✅ 已完成'}" for r in runs]
    idx = st.selectbox("选择测试单", range(len(labels)), index=default,
                       format_func=lambda i: labels[i], key="run_pick")
    return runs[idx]


def _run_panel(run: dict) -> None:
    rid = run["id"]
    st.subheader(f"RUN-{rid:04d} · {run['name']}")
    st.caption(f"环境：{run['env']} ｜ 状态：{'进行中' if run['status'] == 'in_progress' else '已完成'}"
               f" ｜ 创建：{run['created_at']}" + (f" ｜ 备注：{run['note']}" if run["note"] else ""))

    total = run["total"]
    st.progress((total - run["pending"]) / total if total else 0.0,
                text=f"执行进度 {total - run['pending']} / {total} · 通过率 "
                     f"{run['pass_rate']:.1%}" if total else "没有用例")

    k1, k2, k3, k4, k5 = st.columns(5)
    for col, label, key in ((k1, "通过", "passed"), (k2, "失败", "failed"),
                            (k3, "阻塞", "blocked"), (k4, "跳过", "skipped"),
                            (k5, "未执行", "pending")):
        bg, fg = RESULT_COLORS[label]
        col.markdown(pill(f"{label} {run[key]}", bg, fg) if key != "pending" else
                     f'<span class="pill" style="background:#F1F5F9;color:#64748B">未执行 {run[key]}</span>',
                     unsafe_allow_html=True)

    rows = store.run_cases(rid)
    df = pd.DataFrame([{"用例ID": r["case_id"], "标题": r["title"], "优先级": r["priority"],
                        "结果": r["result"], "备注": r["note"]} for r in rows])
    ed = st.data_editor(df, key=f"editor_{rid}", hide_index=True, width="stretch", height=420,
                        column_config={
                            "用例ID": st.column_config.TextColumn("用例ID", disabled=True, width="small"),
                            "标题": st.column_config.TextColumn("标题", disabled=True, width="medium"),
                            "优先级": st.column_config.TextColumn("优先级", disabled=True),
                            "结果": st.column_config.SelectboxColumn("结果", options=_RESULTS,
                                                                     required=True),
                            "备注": st.column_config.TextColumn("备注（失败原因 / 缺陷号）", width="large"),
                        })

    c1, c2, c3 = st.columns([1.4, 1.2, 1.6])
    c1.button("💾 保存执行结果", type="primary", use_container_width=True, key="save_results")
    if st.session_state.get("save_results"):
        for _, r in ed.iterrows():
            store.set_result(rid, r["用例ID"], r["结果"], r["备注"])
        st.toast("执行结果已保存")
        st.rerun()

    done_disabled = run["pending"] > 0 or run["status"] == "done"
    c2.button("✅ 标记完成", disabled=done_disabled, use_container_width=True,
              key="finish_run",
              help="全部用例执行完毕后可标记完成" if done_disabled else None)
    if st.session_state.get("finish_run"):
        store.finish_run(rid)
        st.toast(f"RUN-{rid:04d} 已标记完成")
        st.rerun()

    c3.download_button("⬇️ 导出执行报表（Excel）", use_container_width=True,
                       data=_export_run_excel(store.version(), rid),
                       file_name=f"RUN-{rid:04d}_执行报表.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("🔍 查看用例详情（前置 / 步骤 / 预期）"):
        options = [f'{r["case_id"]} · {r["title"]}' for r in rows]
        if options:
            pick = st.selectbox("选择用例", options, key=f"detail_{rid}")
            r = rows[options.index(pick)]
            st.markdown(f"**前置条件**：{r['precondition'] or '—'}")
            st.markdown("**步骤**\n" + r["steps"].replace("\n", "  \n"))
            st.markdown(f"**预期结果**：{r['expected'] or '—'}")
