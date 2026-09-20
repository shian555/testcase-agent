"""自动截图脚本：用 Playwright 驱动系统 Edge 给平台页面截图（README 用）。

用法：先启动网页（python -m streamlit run app.py），再运行本脚本。
注意：截图前请先在工作台「填充演示数据」（或调用 store.seed_demo()），看板才有内容。
"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
OUT = "docs"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)

    # 图1：工作台看板（KPI 卡 + 分布图表 + 最近测试单）——默认页在根路径
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(9000)
    page.screenshot(path=f"{OUT}/demo_home.png")

    # 图2：用例生成页执行完成（流水线状态 + 指标 + 评审进度条）
    page.goto(f"{BASE}/generate?auto=1", wait_until="networkidle")
    page.wait_for_timeout(6000)
    page.screenshot(path=f"{OUT}/demo_result.png")

    # 图3：用例库（筛选器 + 用例表格）——加高视口让表格完整入镜
    page.goto(f"{BASE}/library", wait_until="networkidle")
    page.set_viewport_size({"width": 1500, "height": 1400})
    page.wait_for_timeout(6000)
    page.screenshot(path=f"{OUT}/demo_cases.png")

    # 图4：测试执行（执行面板：进度条 + 结果 pill + 明细编辑表）
    page.goto(f"{BASE}/execution", wait_until="networkidle")
    page.wait_for_timeout(6000)
    page.screenshot(path=f"{OUT}/demo_execution.png")

    # 图5：测试报告（KPI 带 + 结论横幅 + 结果分布图表）
    page.goto(f"{BASE}/reports", wait_until="networkidle")
    page.wait_for_timeout(7000)
    page.screenshot(path=f"{OUT}/demo_report.png")

    browser.close()

print("已输出 demo_home / demo_result / demo_cases / demo_execution / demo_report")
