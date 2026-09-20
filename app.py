"""AI 智能测试平台入口：全局样式 + 侧边栏 + 多页导航。

页面在 views/ 包中实现（每个模块只暴露 render()，无顶层 st 调用）；
Page 对象集中定义在 nav.py，供导航与视图内跳转共用。
"""
import streamlit as st

from nav import ORDER, PAGES
from styles import inject_css

st.set_page_config(page_title="AI 智能测试平台", page_icon="🧪", layout="wide")
inject_css()

with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="logo">🧪</div><div>'
        '<div class="n">AI 智能测试平台</div>'
        '<div class="d">AI-POWERED TEST PLATFORM</div></div></div>',
        unsafe_allow_html=True)
    st.caption("多 Agent 用例生成 · 用例库 · 测试执行 · 质量报告")
    st.divider()
    st.radio("Agent 运行模式", ["mock", "real"], horizontal=True, key="mode",
             help="mock：规则化离线实现，确定性可复现；real：接真实大模型（需 LLM_API_KEY，见设置页）")
    st.divider()
    st.page_link("https://github.com/shian555/testcase-agent", label="GitHub 仓库", icon="🔗")
    st.caption("💾 用例与执行数据存于本地 SQLite；云端演示环境重部署后会重置，可在设置页备份数据库。")

page = st.navigation([PAGES[key] for key in ORDER])
page.run()
