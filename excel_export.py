"""Excel 导出：与网页同色系的工作簿构建器。

全部返回 bytes（BytesIO），不落盘——兼容 Streamlit Cloud 只读约束；
表头/优先级/结果色与 styles.py 设计令牌一致，导出物像平台自己的报表。
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_HEADER_FILL = PatternFill("solid", fgColor="2563EB")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_THIN = Side(style="thin", color="E2E8F0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_WRAP = Alignment(wrap_text=True, vertical="top")
_CENTER = Alignment(vertical="center")

# 值 → (填充色, 字色)：与 styles.py 的令牌一致
_PILL = {"P0": ("FEE2E2", "B91C1C"), "P1": ("FEF3C7", "B45309"), "P2": ("E2E8F0", "475569"),
         "通过": ("DCFCE7", "15803D"), "失败": ("FEE2E2", "B91C1C"),
         "阻塞": ("FEF3C7", "B45309"), "跳过": ("E2E8F0", "475569"),
         "未执行": ("F8FAFC", "94A3B8"), "AI": ("DBEAFE", "1E40AF"), "手工": ("E2E8F0", "475569"),
         "启用": ("DCFCE7", "15803D"), "停用": ("FEE2E2", "B91C1C")}


def _add_sheet(wb: Workbook, title: str, headers: list[str], rows: list[list],
               widths: list[int], pill_cols: tuple[int, ...] = (), wrap_cols: tuple[int, ...] = ()):
    """加一个格式化工作表：蓝底白字表头、冻结首行、列宽、长文本换行、指定列色块。"""
    ws = wb.create_sheet(title)
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font, cell.alignment = _HEADER_FILL, _HEADER_FONT, _CENTER
    for row in rows:
        ws.append(row)
    for r in ws.iter_rows(min_row=2):
        for cell in r:
            cell.border = _BORDER
            if cell.column in wrap_cols:
                cell.alignment = _WRAP
            val = str(cell.value) if cell.value is not None else ""
            if cell.column in pill_cols and val in _PILL:
                bg, fg = _PILL[val]
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.font = Font(color=fg, bold=True)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


def _wb_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generation_workbook(points, cases, review) -> bytes:
    """生成报告：生成汇总 / 测试点 / 用例清单。"""
    wb = Workbook()
    wb.remove(wb.active)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [["评审得分", f"{review.score}/100"], ["测试点数", len(points)],
            ["用例数", len(cases)], ["生成时间", now]]
    rows.append(["—— 评审检查项 ——", ""])
    rows += [[c["criterion"], "通过" if c["passed"] else "未通过"] for c in review.checks]
    rows.append(["—— 改进建议 ——", ""])
    rows += [[f"建议 {i}", s] for i, s in enumerate(review.suggestions, 1)]
    _add_sheet(wb, "生成汇总", ["项目", "内容"], rows, widths=[22, 80], wrap_cols=(2,))

    _add_sheet(wb, "测试点",
               ["ID", "模块", "测试点", "方法", "优先级"],
               [[p.id, p.module, p.description, p.method, p.priority] for p in points],
               widths=[10, 14, 50, 10, 8], pill_cols=(5,), wrap_cols=(3,))

    _add_sheet(wb, "用例清单",
               ["ID", "模块", "标题", "方法", "优先级", "前置条件", "步骤", "预期结果"],
               [[c.id, c.module, c.title, c.method, c.priority, c.precondition,
                 c.steps, c.expected] for c in cases],
               widths=[10, 12, 32, 10, 8, 26, 45, 32],
               pill_cols=(5,), wrap_cols=(6, 7, 8))
    return _wb_bytes(wb)


def library_workbook(cases: list[dict]) -> bytes:
    """用例库导出：含来源 / 状态 / 标签 / 追溯全列。"""
    wb = Workbook()
    wb.remove(wb.active)
    _add_sheet(wb, "用例库",
               ["ID", "模块", "标题", "方法", "优先级", "来源", "状态", "标签",
                "前置条件", "步骤", "预期结果", "测试点", "创建时间"],
               [[c["id"], c["module"], c["title"], c["method"], c["priority"],
                 "AI" if c["source"] == "ai" else "手工",
                 "启用" if c["status"] == "active" else "停用",
                 c["tags"], c["precondition"], c["steps"], c["expected"],
                 c["testpoint_id"], c["created_at"]] for c in cases],
               widths=[10, 12, 32, 10, 8, 8, 8, 12, 26, 45, 32, 12, 20],
               pill_cols=(5, 6, 7), wrap_cols=(9, 10, 11))
    return _wb_bytes(wb)


def run_report_workbook(run: dict, rows: list[dict],
                        defect_links: dict[str, list[str]] | None = None) -> bytes:
    """执行报表：执行汇总 / 执行明细 / 问题清单 / 追溯矩阵（失败 + 阻塞）。"""
    wb = Workbook()
    wb.remove(wb.active)

    executed = run["executed"]
    summary = [
        ["测试单", f"RUN-{run['id']:04d}"], ["名称", run["name"]],
        ["环境", run["env"]], ["执行人", run.get("owner") or "—"],
        ["状态", "已完成" if run["status"] == "done" else "进行中"],
        ["用例总数", run["total"]], ["已执行", executed],
        ["通过", run["passed"]], ["失败", run["failed"]],
        ["阻塞", run["blocked"]], ["跳过", run["skipped"]],
        ["未执行", run["pending"]],
        ["通过率", f"{run['pass_rate']:.1%}" if executed else "—"],
    ]
    # 按模块 × 结果
    modules: dict[str, dict[str, int]] = {}
    for r in rows:
        m = modules.setdefault(r["module"], {k: 0 for k in ("通过", "失败", "阻塞", "跳过", "未执行")})
        m[r["result"]] += 1
    summary.append(["", ""])
    summary.append(["—— 模块 × 结果 ——", ""])
    summary += [[m, " / ".join(f"{k}{v}" for k, v in d.items() if v)] for m, d in modules.items()]
    # 按优先级通过率
    summary.append(["—— 优先级通过率 ——", ""])
    for p in ("P0", "P1", "P2"):
        prows = [r for r in rows if r["priority"] == p]
        if not prows:
            continue
        pexe = sum(1 for r in prows if r["result"] != "未执行")
        pok = sum(1 for r in prows if r["result"] == "通过")
        rate = f"{pok / pexe:.1%}" if pexe else "—"
        summary.append([f"{p} 通过率", f"{pok}/{pexe}（{rate}）"])
    _add_sheet(wb, "执行汇总", ["项目", "内容"], summary, widths=[22, 70], wrap_cols=(2,))

    _add_sheet(wb, "执行明细",
               ["用例ID", "模块", "标题", "优先级", "方法", "结果", "备注"],
               [[r["case_id"], r["module"], r["title"], r["priority"], r["method"],
                 r["result"], r["note"]] for r in rows],
               widths=[10, 12, 32, 8, 10, 8, 30], pill_cols=(4, 6), wrap_cols=(7,))

    issues = [r for r in rows if r["result"] in ("失败", "阻塞")]
    _add_sheet(wb, "问题清单",
               ["用例ID", "模块", "标题", "优先级", "问题类型", "执行备注"],
               [[r["case_id"], r["module"], r["title"], r["priority"],
                 r["result"], r["note"]] for r in issues],
               widths=[10, 12, 32, 8, 10, 40], pill_cols=(4, 5), wrap_cols=(6,))

    links = defect_links or {}
    _add_sheet(wb, "追溯矩阵",
               ["用例ID", "模块", "标题", "优先级", "结果", "关联缺陷"],
               [[r["case_id"], r["module"], r["title"], r["priority"], r["result"],
                 "、".join(links.get(r["case_id"], [])) or "—"] for r in rows],
               widths=[10, 12, 32, 8, 8, 34], pill_cols=(4, 5), wrap_cols=(3, 6))
    return _wb_bytes(wb)
