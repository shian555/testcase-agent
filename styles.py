"""设计系统：企业蓝白风格的样式令牌与页面级组件。

设计令牌同时供 CSS 与 Python（plotly/openpyxl）使用，保证网页、图表、Excel 导出同色系。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

# ---- 设计令牌（与 .streamlit/config.toml 的 primaryColor 一致）----
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1E40AF"
BG = "#F8FAFC"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
SUCCESS = "#16A34A"
WARNING = "#D97706"
DANGER = "#DC2626"

# 优先级 / 执行结果 → (浅底色, 深字色)：表格 Styler、Excel、图表共用
PRIORITY_COLORS = {"P0": ("#FEE2E2", "#B91C1C"), "P1": ("#FEF3C7", "#B45309"),
                   "P2": ("#E2E8F0", "#475569")}
RESULT_COLORS = {"通过": ("#DCFCE7", "#15803D"), "失败": ("#FEE2E2", "#B91C1C"),
                 "阻塞": ("#FEF3C7", "#B45309"), "跳过": ("#E2E8F0", "#475569"),
                 "未执行": ("#F8FAFC", "#94A3B8")}
CHART_SEQUENCE = [PRIMARY, SUCCESS, WARNING, DANGER, "#8B5CF6", "#0EA5E9", MUTED]

_CSS = f"""
<style>
/* 全局画布：浅灰底 + 白色侧栏 */
.stApp {{ background: {BG}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{
    background: {CARD}; border-right: 1px solid {BORDER};
}}
[data-testid="stSidebar"] * {{ color: {TEXT}; }}

/* 统一页面标题组件 */
.page-header {{ margin-bottom: .25rem; }}
.page-header h2 {{
    font-weight: 700; color: {TEXT}; margin: 0 0 .15rem 0;
    letter-spacing: .01em;
}}
.page-header p {{ color: {MUTED}; font-size: .9rem; margin: 0; }}
.page-header hr {{
    border: none; border-top: 1px solid {BORDER}; margin: .6rem 0 1rem 0;
}}

/* KPI 卡片：白卡 + 主色左边条 */
.kpi-card {{
    background: {CARD}; border: 1px solid {BORDER}; border-left: 4px solid {PRIMARY};
    border-radius: 12px; padding: .9rem 1.1rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
}}
.kpi-label {{ color: {MUTED}; font-size: .82rem; margin-bottom: .2rem; }}
.kpi-value {{ color: {TEXT}; font-size: 1.65rem; font-weight: 700; line-height: 1.2; }}
.kpi-delta {{ color: {MUTED}; font-size: .78rem; margin-top: .25rem; }}

/* 结果横幅 / 详情卡 */
.banner {{
    border-radius: 12px; padding: .9rem 1.1rem; margin: .5rem 0;
    border: 1px solid {BORDER}; background: {CARD};
    box-shadow: 0 1px 3px rgba(15, 23, 42, .08); color: {TEXT};
}}
.banner.ok    {{ border-left: 4px solid {SUCCESS}; }}
.banner.warn  {{ border-left: 4px solid {WARNING}; }}
.banner.bad   {{ border-left: 4px solid {DANGER}; }}
.banner .t {{ font-weight: 700; }}
.banner .d {{ font-size: .9rem; color: {MUTED}; }}

/* 圆角 pill（仅用于 HTML 卡片视图；表格内用色块单元格） */
.pill {{
    display: inline-block; padding: .1rem .6rem; border-radius: 999px;
    font-size: .78rem; font-weight: 600;
}}

/* Tab 栏与输入控件精修 */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0; padding: 6px 14px;
}}
.stTabs [aria-selected="true"] {{ color: {PRIMARY}; }}
div[data-baseweb="input"] input, div[data-baseweb="select"] > div,
div[data-baseweb="textarea"] {{
    border-radius: 8px !important;
}}
.stButton > button {{ border-radius: 8px; }}
.stButton > button[kind="primary"] {{
    box-shadow: 0 1px 2px rgba(37, 99, 235, .35);
}}
</style>
"""


def inject_css() -> None:
    """应用启动时注入一次全局样式（app.py 在 set_page_config 之后调用）。"""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, desc: str = "") -> None:
    """每页统一开头：标题 + 副标题 + 分隔线，是企业感最强的一个信号。"""
    st.markdown(
        f'<div class="page-header"><h2>{title}</h2>'
        + (f"<p>{desc}</p>" if desc else "")
        + "<hr></div>",
        unsafe_allow_html=True)


def kpi_card(label: str, value, delta: str = "", accent: str = PRIMARY) -> None:
    """KPI 指标卡（比原生 st.metric 更接近商业看板）。"""
    st.markdown(
        f'<div class="kpi-card" style="border-left-color:{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        + (f'<div class="kpi-delta">{delta}</div>' if delta else "")
        + "</div>",
        unsafe_allow_html=True)


def banner(kind: str, title: str, desc: str = "") -> None:
    """结论横幅：kind ∈ ok / warn / bad。"""
    st.markdown(
        f'<div class="banner {kind}"><div class="t">{title}</div>'
        + (f'<div class="d">{desc}</div>' if desc else "")
        + "</div>",
        unsafe_allow_html=True)


def pill(text: str, bg: str, fg: str) -> str:
    """行内彩色 pill 的 HTML 片段。"""
    return f'<span class="pill" style="background:{bg};color:{fg}">{text}</span>'


def priority_styler(df: pd.DataFrame, column: str = "优先级") -> pd.io.formats.style.Styler:
    """表格优先级列上色（st.dataframe 的 Styler 仅支持 background/color 两属性）。"""
    def _paint(v):
        bg, fg = PRIORITY_COLORS.get(v, ("", ""))
        return f"background-color:{bg};color:{fg}" if bg else ""
    return df.style.map(_paint, subset=[column])


def result_styler(df: pd.DataFrame, column: str = "结果") -> pd.io.formats.style.Styler:
    """表格执行结果列上色。"""
    def _paint(v):
        bg, fg = RESULT_COLORS.get(v, ("", ""))
        return f"background-color:{bg};color:{fg}" if bg else ""
    return df.style.map(_paint, subset=[column])
