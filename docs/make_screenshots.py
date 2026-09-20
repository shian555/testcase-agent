"""自动截图脚本：用 Playwright 驱动系统 Edge 给 Streamlit Demo 截图（README 用）。

用法：先启动网页（python -m streamlit run app.py），再运行本脚本。
"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
OUT = "docs"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)

    # 图1：首页（输入 PRD + 生成按钮）
    page = browser.new_page(viewport={"width": 1500, "height": 950})
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT}/demo_home.png")

    # 图2：点击生成后的完整结果页（状态 + 指标卡 + 进度条）
    page.click("text=生成测试用例")
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{OUT}/demo_result.png")

    # 图3：测试用例页签（筛选器 + 用例表格）——加高视口让表格完整入镜
    page.set_viewport_size({"width": 1500, "height": 2200})
    page.click("text=🧾 测试用例")
    page.wait_for_timeout(2000)
    page.screenshot(path=f"{OUT}/demo_cases.png")

    browser.close()

print("已输出 demo_home.png / demo_result.png / demo_review.png")
