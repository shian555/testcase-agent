"""设置页：LLM 运行环境、数据管理（演示数据/备份/清空）、方法论与关于。"""
from __future__ import annotations

import os

import streamlit as st

from methods import METHODS
import store
from styles import page_header


def render() -> None:
    page_header("设置", "运行环境、数据管理与方法论说明")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        _llm_section()
    with c2:
        _data_section()

    with st.expander("📐 注入的测试方法论"):
        for m, desc in METHODS.items():
            st.markdown(f"- **{m}**：{desc}")

    with st.expander("ℹ️ 关于本平台"):
        st.markdown(
            "AI 智能测试平台 —— 基于 LLM 的测试用例生成多 Agent 系统（"
            "AnalyzerAgent → GeneratorAgent → ReviewerAgent），"
            "覆盖「生成 → 采纳入库 → 测试执行 → 质量报告」完整业务闭环。")
        st.markdown("- 技术栈：Python · Streamlit · SQLite · Plotly · OpenAI 兼容接口")
        st.page_link("https://github.com/shian555/testcase-agent", label="GitHub 仓库")
        st.caption("云端演示环境数据存于容器内 SQLite，重部署后会重置；重要数据请及时备份。")


def _llm_section() -> None:
    st.markdown("##### 🤖 LLM 运行环境（real 模式）")
    key = os.getenv("LLM_API_KEY") or os.getenv("EVAL_API_KEY") or ""
    base = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = os.getenv("LLM_MODEL", "qwen2.5-7b-instruct")
    masked = f"已配置（****{key[-4:]}）" if key else "未配置（可继续使用 mock 模式）"
    st.markdown(
        f"- LLM_API_KEY：{masked}\n"
        f"- LLM_BASE_URL：`{base}`\n"
        f"- LLM_MODEL：`{model}`")
    if st.button("测试连接", use_container_width=True):
        if not key:
            st.error("未检测到 LLM_API_KEY，无法连接")
        else:
            try:
                from agents import _LLMClient
                reply = _LLMClient().call("你是连通性测试助手", "请只回复：pong")
                st.success(f"连接成功，模型返回：{reply[:50]}")
            except Exception as e:  # noqa: BLE001 —— 连接失败原因原样呈现
                st.error(f"连接失败：{e}")


def _data_section() -> None:
    st.markdown("##### 💾 数据管理")
    st.caption(f"存储位置：`{store.db_path()}`")

    b1, b2 = st.columns(2)
    b1.button("📦 填充演示数据", use_container_width=True, key="set_seed",
              help="mock 流水线跑样例 PRD 采纳入库，并创建一个已完成的回归测试单")
    if st.session_state.get("set_seed"):
        store.seed_demo()
        st.toast("演示数据已就绪")
        st.rerun()

    try:
        backup = store.backup_bytes()
        b2.download_button("⬇️ 备份数据库", data=backup, file_name="platform_backup.db",
                           mime="application/octet-stream", use_container_width=True)
    except Exception:  # noqa: BLE001 —— 库文件尚未创建时隐藏备份
        b2.caption("暂无数据可备份")

    with st.popover("🗑 清空全部数据"):
        st.warning("将删除所有用例、测试单与执行记录，不可恢复。")
        if st.checkbox("我确认清空", key="clear_confirm"):
            if st.button("确认清空", type="primary", use_container_width=True):
                store.clear_all()
                st.toast("数据已清空")
                st.rerun()
