"""页面注册表：st.Page 对象集中定义。

app.py 用它挂载导航；视图内跳转（st.page_link / st.switch_page）必须传
Page 对象——1.40+ 不接受 url_path 字符串，故集中一处、按 key 共享。
"""
import streamlit as st

import views.dashboard
import views.defects
import views.execution
import views.generate
import views.library
import views.reports
import views.settings

PAGES = {
    "dashboard": st.Page(views.dashboard.render, title="工作台",
                         icon=":material/dashboard:", default=True),
    "generate": st.Page(views.generate.render, title="用例生成",
                        icon=":material/auto_awesome:", url_path="generate"),
    "library": st.Page(views.library.render, title="用例库",
                       icon=":material/library_books:", url_path="library"),
    "execution": st.Page(views.execution.render, title="测试执行",
                         icon=":material/play_circle:", url_path="execution"),
    "reports": st.Page(views.reports.render, title="测试报告",
                       icon=":material/description:", url_path="reports"),
    "defects": st.Page(views.defects.render, title="缺陷管理",
                       icon=":material/bug_report:", url_path="defects"),
    "settings": st.Page(views.settings.render, title="设置",
                        icon=":material/settings:", url_path="settings"),
}

ORDER = ["dashboard", "generate", "library", "execution", "reports", "defects", "settings"]
