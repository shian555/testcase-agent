"""设计系统：企业蓝白风格的样式令牌与页面级组件。

设计令牌同时供 CSS 与 Python（plotly/openpyxl）使用，保证网页、图表、Excel 导出同色系。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---- 设计令牌（与 .streamlit/config.toml 的 primaryColor 一致）----
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1E40AF"
PRIMARY_LIGHT = "#EFF6FF"
BG = "#F8FAFC"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
SUCCESS = "#16A34A"
WARNING = "#D97706"
DANGER = "#DC2626"

FONT_STACK = "Segoe UI, PingFang SC, Microsoft YaHei, -apple-system, sans-serif"

# 优先级 / 执行结果 → (浅底色, 深字色)：表格 Styler、Excel、图表共用
PRIORITY_COLORS = {"P0": ("#FEE2E2", "#B91C1C"), "P1": ("#FEF3C7", "#B45309"),
                   "P2": ("#E2E8F0", "#475569")}
RESULT_COLORS = {"通过": ("#DCFCE7", "#15803D"), "失败": ("#FEE2E2", "#B91C1C"),
                 "阻塞": ("#FEF3C7", "#B45309"), "跳过": ("#E2E8F0", "#475569"),
                 "未执行": ("#F8FAFC", "#94A3B8")}
SEVERITY_COLORS = {"严重": ("#FEE2E2", "#B91C1C"), "一般": ("#FEF3C7", "#B45309"),
                   "轻微": ("#E2E8F0", "#475569")}
DEFECT_STATUS_COLORS = {"打开": ("#FEE2E2", "#DC2626"), "修复中": ("#FEF3C7", "#B45309"),
                        "已解决": ("#DBEAFE", "#1D4ED8"), "已关闭": ("#DCFCE7", "#15803D")}
CHART_SEQUENCE = [PRIMARY, "#0EA5E9", "#8B5CF6", WARNING, SUCCESS, DANGER, MUTED]

# plotly 统一配置：隐藏悬浮工具条（更干净、渲染更轻）
PLOTLY_CONFIG = {"displayModeBar": False}

_CSS = f"""
<style>
/* ---------- 全局画布 ---------- */
.stApp {{ background: {BG}; color: {TEXT};
  font-family: {FONT_STACK}; }}
[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer, [data-testid="stStatusWidget"] {{ visibility: hidden; }}
[data-testid="stSidebar"] {{
    background: {CARD}; border-right: 1px solid {BORDER};
    box-shadow: 2px 0 12px rgba(15, 23, 42, .03);
}}
[data-testid="stSidebar"] * {{ color: {TEXT}; }}
[data-testid="stSidebar"] hr {{ margin: .35rem 0; border-color: {BORDER}; }}

/* 侧边导航：圆角高亮，当前页蓝底 */
[data-testid="stSidebarNav"] {{ padding-top: .6rem; }}
[data-testid="stSidebar"] span, [data-testid="stSidebar"] a {{ font-size: .92rem; }}
[data-testid="stPageLink-NavLink"], [data-testid="stSidebarNav"] a {{
    border-radius: 10px !important; padding: .42rem .75rem !important;
    transition: background .12s ease, color .12s ease;
}}
[data-testid="stPageLink-NavLink"]:hover, [data-testid="stSidebarNav"] a:hover {{
    background: #F1F5F9;
}}
[aria-current="page"][data-testid="stPageLink-NavLink"],
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: {PRIMARY_LIGHT} !important; color: {PRIMARY_DARK} !important;
    font-weight: 600;
}}

/* 品牌块 */
.brand {{ display: flex; align-items: center; gap: .65rem; padding: .2rem 0 .4rem 0; }}
.brand .logo {{
    width: 38px; height: 38px; border-radius: 10px; flex: none;
    display: flex; align-items: center; justify-content: center; font-size: 1.15rem;
    background: linear-gradient(135deg, {PRIMARY}, {PRIMARY_DARK});
    box-shadow: 0 4px 10px rgba(37, 99, 235, .35);
}}
.brand .n {{ font-weight: 700; font-size: 1.02rem; line-height: 1.25; }}
.brand .d {{ color: {MUTED}; font-size: .72rem; letter-spacing: .04em; }}

/* ---------- 页面标题 ---------- */
.page-header {{ margin-bottom: .25rem; }}
.page-header h2 {{
    font-weight: 700; color: {TEXT}; margin: 0 0 .15rem 0;
    font-size: 1.55rem; letter-spacing: .01em;
}}
.page-header p {{ color: {MUTED}; font-size: .9rem; margin: 0; }}
.page-header hr {{
    border: none; border-top: 1px solid {BORDER}; margin: .6rem 0 1.1rem 0;
}}

/* ---------- KPI 卡片：白卡 + 顶部色条 + 悬浮上浮 ---------- */
.kpi-card {{
    position: relative; background: {CARD}; border: 1px solid {BORDER};
    border-top: 3px solid {PRIMARY}; border-radius: 13px; padding: .95rem 1.1rem 1rem 1.1rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .05), 0 6px 16px -8px rgba(15, 23, 42, .10);
    transition: transform .16s ease, box-shadow .16s ease; overflow: hidden;
}}
.kpi-card:hover {{ transform: translateY(-2px);
    box-shadow: 0 2px 4px rgba(15, 23, 42, .06), 0 12px 24px -10px rgba(15, 23, 42, .16); }}
.kpi-label {{ color: {MUTED}; font-size: .78rem; font-weight: 600;
    letter-spacing: .05em; margin-bottom: .3rem; }}
.kpi-value {{ color: {TEXT}; font-size: 1.8rem; font-weight: 700;
    line-height: 1.15; font-variant-numeric: tabular-nums; }}
.kpi-delta {{ color: {MUTED}; font-size: .76rem; margin-top: .3rem; }}

/* ---------- 横幅：着色底 + 色边（告警感更明确） ---------- */
.banner {{
    border-radius: 12px; padding: .85rem 1.1rem; margin: .5rem 0;
    border: 1px solid {BORDER}; background: {CARD}; color: {TEXT};
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}}
.banner.ok   {{ background: #F0FDF4; border-color: #BBF7D0; }}
.banner.warn {{ background: #FFFBEB; border-color: #FDE68A; }}
.banner.bad  {{ background: #FEF2F2; border-color: #FECACA; }}
.banner.ok .t   {{ color: #166534; }}
.banner.warn .t {{ color: #92400E; }}
.banner.bad .t  {{ color: #991B1B; }}
.banner .t {{ font-weight: 700; }}
.banner .d {{ font-size: .88rem; color: #475569; margin-top: .15rem; }}

/* 圆角 pill（仅用于 HTML 卡片视图；表格内用色块单元格） */
.pill {{
    display: inline-block; padding: .12rem .65rem; border-radius: 999px;
    font-size: .78rem; font-weight: 600; letter-spacing: .01em;
}}

/* ---------- 表格 / 图表卡片 ---------- */
[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}}
[data-testid="stPlotlyChart"] {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
    /* 只留水平 padding：垂直方向容器高度=图高，加 padding 会把底部 x 轴标签挤出容器被裁切 */
    padding: 0 .4rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}}
[data-testid="stPlotlyChart"] .js-plotly-plot .plotly .modebar {{ display: none; }}

/* ---------- 控件精修 ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0; padding: 7px 15px; font-size: .92rem;
}}
.stTabs [aria-selected="true"] {{ color: {PRIMARY}; font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {PRIMARY}; }}

div[data-baseweb="input"] input, div[data-baseweb="select"] > div,
div[data-baseweb="textarea"] {{
    border-radius: 9px !important;
}}
div[data-baseweb="input"] input:focus, div[data-baseweb="textarea"]:focus {{
    border-color: {PRIMARY} !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, .12) !important;
}}

.stButton > button {{ border-radius: 9px; font-weight: 500; }}
.stButton > button[kind="primary"] {{
    background: linear-gradient(180deg, {PRIMARY}, {PRIMARY_DARK});
    border: none; box-shadow: 0 2px 6px rgba(37, 99, 235, .35);
}}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.06); }}
.stButton > button[kind="secondary"] {{
    border: 1px solid {BORDER}; background: {CARD}; color: #334155;
}}
.stButton > button[kind="secondary"]:hover {{ border-color: #CBD5E1; background: #F8FAFC; }}

[data-testid="stExpander"] {{
    border: 1px solid {BORDER} !important; border-radius: 12px !important;
    background: {CARD}; box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}}
[data-testid="stExpander"] summary {{ font-weight: 600; }}

h3, h4, h5, h6 {{ letter-spacing: .01em; }}
::-webkit-scrollbar {{ width: 9px; height: 9px; }}
::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
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
    """KPI 指标卡：顶部色条区分指标归属，数值大字号等宽。"""
    st.markdown(
        f'<div class="kpi-card" style="border-top-color:{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        + (f'<div class="kpi-delta">{delta}</div>' if delta else "")
        + "</div>",
        unsafe_allow_html=True)


def banner(kind: str, title: str, desc: str = "") -> None:
    """结论横幅：kind ∈ ok / warn / bad（着色底），空串则中性白底。"""
    st.markdown(
        f'<div class="banner {kind}"><div class="t">{title}</div>'
        + (f'<div class="d">{desc}</div>' if desc else "")
        + "</div>",
        unsafe_allow_html=True)


def pill(text: str, bg: str, fg: str) -> str:
    """行内彩色 pill 的 HTML 片段。"""
    return f'<span class="pill" style="background:{bg};color:{fg}">{text}</span>'


def pill_styler(df: pd.DataFrame, paints: dict[str, dict]) -> pd.io.formats.style.Styler:
    """通用表格色块：paints = {列名: {值: (底色, 字色)}}（Styler 仅支持 background/color）。"""
    def _painter(mapping: dict):
        def _paint(v):
            bg, fg = mapping.get(v, ("", ""))
            return f"background-color:{bg};color:{fg}" if bg else ""
        return _paint
    sty = df.style
    for col, mapping in paints.items():
        sty = sty.map(_painter(mapping), subset=[col])
    return sty


def priority_styler(df: pd.DataFrame, column: str = "优先级") -> pd.io.formats.style.Styler:
    return pill_styler(df, {column: PRIORITY_COLORS})


def result_styler(df: pd.DataFrame, column: str = "结果") -> pd.io.formats.style.Styler:
    return pill_styler(df, {column: RESULT_COLORS})


def style_chart(fig: go.Figure, height: int = 300, legend: str | None = "bottom") -> go.Figure:
    """图表统一风格：透明底、浅网格、小字号、图例水平置底（企业看板一致性）。"""
    fig.update_layout(
        height=height, margin=dict(l=4, r=4, t=10, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_STACK, size=12, color="#334155"),
        title=None, colorway=CHART_SEQUENCE)
    if legend == "bottom":
        fig.update_layout(legend=dict(orientation="h", y=-0.12, title=None,
                                      font=dict(size=11)))
    elif legend is None:
        # 无底部图例时图不会自动向下留白，需显式底边距，否则 x 轴 tick 被裁切
        fig.update_layout(showlegend=False, margin=dict(b=26))
    # automargin：轴标签撑开边距，避免 b=4 裁切 tick 文字
    fig.update_xaxes(gridcolor="#EEF2F7", zeroline=False, title=None,
                     tickfont=dict(size=11), linecolor="#E2E8F0", automargin=True)
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, title=None,
                     tickfont=dict(size=11), automargin=True)
    return fig
