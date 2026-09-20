"""用例库页：测试资产检索、批量操作（建单/停用/删除）、单条编辑与手工新建。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from excel_export import library_workbook
from methods import METHODS
import store
from styles import page_header, priority_styler


def render() -> None:
    page_header("用例库", "团队测试资产：检索筛选、圈选建单、编辑维护")

    cases = _toolbar_and_query()
    if not cases:
        st.info("用例库为空。先去「用例生成」采纳 AI 产出，或在下方新建手工用例。")
        _new_case_expander()
        return

    selected_ids = _case_table(cases)
    if selected_ids:
        _batch_actions(selected_ids)

    _case_detail(cases)
    _new_case_expander()


def _toolbar_and_query() -> list[dict]:
    """筛选工具栏 → store 查询。"""
    f1, f2, f3, f4, f5 = st.columns([2, 1.4, 1.2, 1, 1])
    keyword = f1.text_input("🔍 关键字（标题/模块/标签）", key="lib_kw")
    sel_method = f2.multiselect("方法", list(METHODS), key="lib_method")
    sel_prio = f3.multiselect("优先级", ["P0", "P1", "P2"], key="lib_prio")
    source = f4.selectbox("来源", ["全部", "AI", "手工"], key="lib_source")
    status = f5.selectbox("状态", ["启用", "停用", "全部"], key="lib_status")

    return store.list_cases(
        keyword=keyword.strip(),
        method=sel_method or None,
        priority=sel_prio or None,
        source={"全部": None, "AI": "ai", "手工": "manual"}[source],
        status={"启用": "active", "停用": "deprecated", "全部": "all"}[status])


def _case_table(cases: list[dict]) -> list[str]:
    """主表格（多选行）→ 返回选中的用例 ID。"""
    rows = [{"ID": c["id"], "模块": c["module"], "标题": c["title"], "方法": c["method"],
             "优先级": c["priority"], "来源": "AI" if c["source"] == "ai" else "手工",
             "标签": c["tags"], "状态": "启用" if c["status"] == "active" else "停用"}
            for c in cases]
    df = pd.DataFrame(rows)
    event = st.dataframe(priority_styler(df), width="stretch", hide_index=True, height=480,
                         on_select="rerun", selection_mode="multi-row", key="lib_table")
    st.caption(f"共 {len(cases)} 条 · 点击行首复选框可多选")
    return [rows[i]["ID"] for i in event.selection.rows]


def _batch_actions(ids: list[str]) -> None:
    a1, a2, a3, a4, a5 = st.columns([2.2, 1.2, 1.2, 1, 2])
    with a1.popover(f"➕ 新建测试单（含选中 {len(ids)} 条）", use_container_width=True):
        name = st.text_input("测试单名称", value=f"回归 {datetime.now():%m-%d %H:%M}", key="mk_run_name")
        env = st.selectbox("环境", ["测试环境", "预发环境", "生产环境"], key="mk_run_env")
        if st.button("创建并前往执行", type="primary", use_container_width=True):
            run_id = store.create_run(name=name, env=env, case_ids=ids)
            st.session_state.enter_run_id = run_id
            st.toast(f"测试单 RUN-{run_id:04d} 已创建")
            from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
            st.switch_page(PAGES["execution"])
    with a2.popover(f"⏸ 停用（{len(ids)} 条）", use_container_width=True):
        st.caption("停用后不在默认列表与建单圈选中出现，可随时恢复。")
        if st.button("确认停用", use_container_width=True):
            store.set_case_status(ids, "deprecated")
            st.toast(f"已停用 {len(ids)} 条用例")
            st.rerun()
    with a3.popover(f"🗑 删除（{len(ids)} 条）", use_container_width=True):
        st.warning("将同时移除相关执行记录，不可恢复。")
        if st.checkbox("我确认删除", key="del_confirm") and st.button("确认删除", type="primary",
                                                                    use_container_width=True):
            store.delete_cases(ids)
            st.toast(f"已删除 {len(ids)} 条用例")
            st.rerun()
    a4.download_button("⬇️ Excel", data=library_workbook(
        store.list_cases(status="all")), file_name="用例库.xlsx",
        use_container_width=True,
        help="导出当前用例库全部用例（含停用）")
    with a5:
        from nav import PAGES  # 延迟导入：避免 nav → views → nav 循环
        st.page_link(PAGES["execution"], label="▶️ 前往测试执行", use_container_width=True)


def _case_detail(cases: list[dict]) -> None:
    st.subheader("用例详情与编辑")
    options = [f'{c["id"]} · {c["title"]}' for c in cases]
    pick = st.selectbox("定位用例", options, key="lib_pick", index=None,
                        placeholder="选择一条用例查看 / 编辑")
    if pick is None:
        return
    case = cases[options.index(pick)]

    d1, d2 = st.columns([1, 1.4], gap="medium")
    with d1:
        meta = (f'<div class="banner"><div class="t">{case["id"]} · {case["title"]}</div>'
                f'<div class="d">模块：{case["module"]} ｜ 方法：{case["method"]} ｜ '
                f'来源：{"AI" if case["source"] == "ai" else "手工"}'
                + (f' ｜ 标签：{case["tags"]}' if case["tags"] else "") + "<br>"
                f'前置条件：{case["precondition"] or "—"}</div></div>')
        st.markdown(meta, unsafe_allow_html=True)
        st.markdown("**步骤**\n" + case["steps"].replace("\n", "  \n"))
        st.markdown("**预期结果**\n" + (case["expected"] or "—"))
        if case["testpoint_id"]:
            st.caption(f"🔗 追溯测试点：{case['testpoint_id']}")

    with d2:
        with st.form(f"edit_{case['id']}", border=True):
            st.markdown("**编辑用例**")
            t1, t2 = st.columns(2)
            title = t1.text_input("标题", value=case["title"])
            module = t2.text_input("模块", value=case["module"])
            t3, t4, t5 = st.columns(3)
            priority = t3.selectbox("优先级", ["P0", "P1", "P2"],
                                    index=["P0", "P1", "P2"].index(case["priority"]))
            method = t4.selectbox("方法", list(METHODS) + ["手工"],
                                  index=(list(METHODS) + ["手工"]).index(case["method"]))
            tags = t5.text_input("标签（逗号分隔）", value=case["tags"])
            precondition = st.text_area("前置条件", value=case["precondition"])
            steps = st.text_area("步骤（每行一步）", value=case["steps"], height=140)
            expected = st.text_area("预期结果", value=case["expected"], height=90)
            if st.form_submit_button("💾 保存修改", type="primary", use_container_width=True):
                store.update_case(case["id"], title=title, module=module, priority=priority,
                                  method=method, tags=tags.strip(), precondition=precondition,
                                  steps=steps, expected=expected)
                st.toast(f"{case['id']} 已保存")
                st.rerun()


def _new_case_expander() -> None:
    with st.expander("➕ 新建手工用例", expanded=False):
        with st.form("new_case", border=False):
            t1, t2 = st.columns(2)
            title = t1.text_input("标题*", placeholder="如：验证验证码为空时的登录提示")
            module = t2.text_input("模块*", placeholder="如：登录")
            t3, t4, t5 = st.columns(3)
            priority = t3.selectbox("优先级", ["P0", "P1", "P2"], index=1)
            method = t4.selectbox("方法", ["手工"] + list(METHODS))
            tags = t5.text_input("标签（逗号分隔）")
            precondition = st.text_area("前置条件", placeholder="如：已打开登录页")
            steps = st.text_area("步骤（每行一步）", placeholder="1. …\n2. …")
            expected = st.text_area("预期结果", placeholder="如：登录成功，跳转首页")
            submitted = st.form_submit_button("保存新用例", type="primary", use_container_width=True)
        if submitted:
            if not title.strip() or not module.strip():
                st.error("标题与模块为必填项")
            else:
                cid = store.add_case(module=module.strip(), title=title.strip(),
                                     priority=priority, method=method,
                                     precondition=precondition, steps=steps,
                                     expected=expected, tags=tags.strip())
                st.toast(f"手工用例 {cid} 已创建")
                st.rerun()
