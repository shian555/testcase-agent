"""SQLite 持久层：用例库 / 生成批次 / 测试单 / 执行结果。

纯标准库实现，不依赖 Streamlit；本地为真实持久化，云端容器内随部署存活（演示够用）。
连接纪律：每次操作开短连接（WAL + 外键 ON + 单事务），规避 Streamlit 重跑线程问题；
路径从模块位置解析，兼容 Windows 中文路径与云端不同的 CWD。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent / "data" / "platform.db"
_init_done = threading.Event()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS counters (
    name  TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS gen_batches (
    id          TEXT PRIMARY KEY,            -- B+时间戳
    mode        TEXT NOT NULL,               -- mock | real
    prd_excerpt TEXT DEFAULT '',
    score       INTEGER,
    point_count INTEGER DEFAULT 0,
    case_count  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id            TEXT PRIMARY KEY,          -- TC0001 起，全局唯一不复用
    module        TEXT NOT NULL,
    title         TEXT NOT NULL,
    precondition  TEXT DEFAULT '',
    steps         TEXT DEFAULT '',
    expected      TEXT DEFAULT '',
    priority      TEXT NOT NULL CHECK (priority IN ('P0','P1','P2')),
    method        TEXT NOT NULL,             -- 等价类/边界值/场景法/错误猜测/手工
    testpoint_id  TEXT DEFAULT '',           -- 需求追溯：关联测试点
    batch_id      TEXT DEFAULT '',           -- 来源批次（source=ai 时）
    source        TEXT NOT NULL DEFAULT 'manual',   -- ai | manual
    status        TEXT NOT NULL DEFAULT 'active',   -- active | deprecated
    tags          TEXT DEFAULT '',
    review_score  INTEGER,                   -- 采纳时的批次评审分快照
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_module ON cases(module);
CREATE INDEX IF NOT EXISTS idx_cases_batch  ON cases(batch_id);
CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- 显示为 RUN-0001
    name        TEXT NOT NULL,
    env         TEXT DEFAULT '测试环境',
    status      TEXT NOT NULL DEFAULT 'in_progress', -- in_progress | done
    note        TEXT DEFAULT '',
    owner       TEXT DEFAULT '',                     -- 执行人
    created_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS run_results (
    run_id     INTEGER NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    case_id    TEXT    NOT NULL REFERENCES cases(id)     ON DELETE CASCADE,
    result     TEXT    NOT NULL DEFAULT '未执行',        -- 未执行|通过|失败|阻塞|跳过
    note       TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, case_id)
);
CREATE TABLE IF NOT EXISTS defects (
    id             TEXT PRIMARY KEY,         -- BUG0001 起，全局唯一不复用
    title          TEXT NOT NULL,
    module         TEXT DEFAULT '',
    severity       TEXT NOT NULL DEFAULT '一般' CHECK (severity IN ('严重','一般','轻微')),
    status         TEXT NOT NULL DEFAULT '打开' CHECK (status IN ('打开','修复中','已解决','已关闭')),
    description    TEXT DEFAULT '',
    source_case_id TEXT DEFAULT '',          -- 来源失败用例（缺陷 ↔ 用例双向追溯）
    run_id         INTEGER,                  -- 发现于哪个测试单
    assignee       TEXT DEFAULT '',          -- 当前处理人（开发/测试）
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_defects_status ON defects(status);
INSERT OR IGNORE INTO counters(name, value) VALUES ('case_id', 0);
INSERT OR IGNORE INTO counters(name, value) VALUES ('defect_id', 0);
INSERT OR IGNORE INTO counters(name, value) VALUES ('data_version', 0);
"""


def set_db_path(path) -> None:
    """重设数据库路径（测试隔离 / 自定义存储位置），需在首次读写前调用。"""
    global _DB_PATH
    _DB_PATH = Path(path)
    _init_done.clear()


def db_path() -> Path:
    return _DB_PATH


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _init_db() -> None:
    if _init_done.is_set():
        return
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    _init_done.set()


def _migrate(conn) -> None:
    """老库平滑升级：缺失列按默认值补齐（幂等，老数据不受影响）。"""
    for table, col, ddl in (("test_runs", "owner", "TEXT DEFAULT ''"),
                            ("defects", "assignee", "TEXT DEFAULT ''")):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


@contextmanager
def _db():
    """短连接 + 单事务：成功提交、异常回滚、用毕即关。"""
    _init_db()
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _bump(conn) -> None:
    """任一写操作自增数据版本号：视图层用 version() 作为导出缓存的失效盐。"""
    conn.execute("UPDATE counters SET value=value+1 WHERE name='data_version'")


def version() -> int:
    """当前数据版本号：任何写操作都会使其 +1（导出缓存的 key 盐）。"""
    with _db() as conn:
        row = conn.execute("SELECT value FROM counters WHERE name='data_version'").fetchone()
        return int(row["value"])


# ---------------- 用例 ----------------

def _norm_priority(p) -> str:
    return p if p in ("P0", "P1", "P2") else "P2"


def _next_id(conn) -> str:
    """事务内自增发号；删除用例不回收号码，历史报告引用不悬空。"""
    row = conn.execute("SELECT value FROM counters WHERE name='case_id'").fetchone()
    value = int(row["value"]) + 1
    conn.execute("UPDATE counters SET value=? WHERE name='case_id'", (value,))
    return f"TC{value:04d}"


def next_case_id() -> str:
    with _db() as conn:
        return _next_id(conn)


def add_case(*, module: str, title: str, priority: str, method: str,
             precondition: str = "", steps: str = "", expected: str = "",
             testpoint_id: str = "", source: str = "manual", tags: str = "",
             batch_id: str = "", review_score: int | None = None,
             status: str = "active") -> str:
    now = _now()
    with _db() as conn:
        cid = _next_id(conn)
        conn.execute(
            "INSERT INTO cases(id, module, title, precondition, steps, expected, priority, method,"
            " testpoint_id, batch_id, source, status, tags, review_score, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, module, title, precondition, steps, expected, _norm_priority(priority),
             method, testpoint_id, batch_id, source, status, tags, review_score, now, now))
        _bump(conn)
    return cid


def add_cases(items: list[dict], *, source: str, batch_id: str = "") -> list[str]:
    """批量入库（单事务）；items 为含用例字段的 dict 列表。"""
    now = _now()
    ids = []
    with _db() as conn:
        for it in items:
            cid = _next_id(conn)
            conn.execute(
                "INSERT INTO cases(id, module, title, precondition, steps, expected, priority, method,"
                " testpoint_id, batch_id, source, status, tags, review_score, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, it.get("module", ""), it["title"], it.get("precondition", ""),
                 it.get("steps", ""), it.get("expected", ""), _norm_priority(it.get("priority")),
                 it.get("method", ""), it.get("testpoint_id", ""), batch_id, source,
                 "active", it.get("tags", ""), it.get("review_score"), now, now))
            ids.append(cid)
        _bump(conn)
    return ids


def adopt_batch(prd_text: str, mode: str, score: int | None, items: list[dict], *,
                dedup: bool = False) -> tuple[str, list[str]]:
    """生成结果采纳入库：批次行 + 用例行一个事务；(batch_id, 实际入库的用例 id) 。"""
    batch_id = f"B{datetime.now():%Y%m%d%H%M%S%f}"[:-3]
    now = _now()
    with _db() as conn:
        conn.execute(
            "INSERT INTO gen_batches(id, mode, prd_excerpt, score, point_count, case_count, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (batch_id, mode, prd_text[:2000], score, len(items), 0, now))
        if dedup:
            existing = {r["module"] + "|" + r["title"] for r in
                        conn.execute("SELECT module, title FROM cases WHERE status='active'")}
        else:
            existing = set()
        ids = []
        for it in items:
            if it["module"] + "|" + it["title"] in existing:
                continue
            cid = _next_id(conn)
            conn.execute(
                "INSERT INTO cases(id, module, title, precondition, steps, expected, priority, method,"
                " testpoint_id, batch_id, source, status, tags, review_score, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, it.get("module", ""), it["title"], it.get("precondition", ""),
                 it.get("steps", ""), it.get("expected", ""), _norm_priority(it.get("priority")),
                 it.get("method", ""), it.get("testpoint_id", ""), batch_id, "ai",
                 "active", it.get("tags", ""), score, now, now))
            ids.append(cid)
        conn.execute("UPDATE gen_batches SET case_count=? WHERE id=?", (len(ids), batch_id))
        _bump(conn)
    return batch_id, ids


def list_cases(*, keyword: str = "", module: str = "", method: list[str] | None = None,
               priority: list[str] | None = None, source: str | None = None,
               status: str = "active") -> list[dict]:
    """按条件查询用例；status='all' 查全部。返回按 id 倒序的 dict 列表。"""
    sql = "SELECT * FROM cases WHERE 1=1"
    params: list = []
    if status != "all":
        sql += " AND status=?"
        params.append(status)
    if keyword:
        sql += " AND (title LIKE ? OR module LIKE ? OR tags LIKE ?)"
        params += [f"%{keyword}%"] * 3
    if module:
        sql += " AND module=?"
        params.append(module)
    if method:
        sql += f" AND method IN ({','.join('?' * len(method))})"
        params += method
    if priority:
        sql += f" AND priority IN ({','.join('?' * len(priority))})"
        params += priority
    if source:
        sql += " AND source=?"
        params.append(source)
    sql += " ORDER BY id DESC"
    with _db() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_case(case_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return dict(row) if row else None


_CASE_FIELDS = {"title", "module", "precondition", "steps", "expected", "priority",
                "method", "tags", "status", "testpoint_id"}


def update_case(case_id: str, **fields) -> None:
    """白名单字段更新，自动刷新 updated_at。"""
    cols = {k: v for k, v in fields.items() if k in _CASE_FIELDS}
    if not cols:
        return
    if "priority" in cols:
        cols["priority"] = _norm_priority(cols["priority"])
    sets = ", ".join(f"{k}=?" for k in cols)
    params = list(cols.values()) + [_now(), case_id]
    with _db() as conn:
        conn.execute(f"UPDATE cases SET {sets}, updated_at=? WHERE id=?", params)
        _bump(conn)


def set_case_status(case_ids: list[str], status: str) -> None:
    with _db() as conn:
        conn.executemany(
            "UPDATE cases SET status=?, updated_at=? WHERE id=?",
            [(status, _now(), cid) for cid in case_ids])
        _bump(conn)


def delete_cases(case_ids: list[str]) -> None:
    """物理删除（run_results 由外键级联清理）。"""
    with _db() as conn:
        conn.executemany("DELETE FROM cases WHERE id=?", [(cid,) for cid in case_ids])
        _bump(conn)


# ---------------- 测试单 / 执行结果 ----------------

def create_run(*, name: str, env: str = "测试环境", note: str = "",
               owner: str = "", case_ids: list[str]) -> int:
    if not case_ids:
        raise ValueError("测试单至少需要圈选一条用例")
    now = _now()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO test_runs(name, env, note, owner, created_at) VALUES (?,?,?,?,?)",
            (name, env, note, owner.strip(), now))
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO run_results(run_id, case_id, result, updated_at) VALUES (?,?,?,?)",
            [(run_id, cid, "未执行", now) for cid in case_ids])
        _bump(conn)
    return run_id


_RUN_STATS_SQL = """
SELECT r.*,
       COUNT(rr.case_id)                    AS total,
       SUM(rr.result = '通过')               AS passed,
       SUM(rr.result = '失败')               AS failed,
       SUM(rr.result = '阻塞')               AS blocked,
       SUM(rr.result = '跳过')               AS skipped,
       SUM(rr.result = '未执行')             AS pending
FROM test_runs r
LEFT JOIN run_results rr ON rr.run_id = r.id
"""


def _run_row_to_dict(r) -> dict:
    d = dict(r)
    executed = (d["total"] or 0) - (d["pending"] or 0)
    d["executed"] = executed
    d["pass_rate"] = round((d["passed"] or 0) / executed, 4) if executed else 0.0
    return d


def list_runs() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(_RUN_STATS_SQL + " GROUP BY r.id ORDER BY r.id DESC").fetchall()
        return [_run_row_to_dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    with _db() as conn:
        r = conn.execute(_RUN_STATS_SQL + " WHERE r.id=? GROUP BY r.id", (run_id,)).fetchone()
        return _run_row_to_dict(r) if r else None


def run_cases(run_id: int) -> list[dict]:
    """执行明细：run_results ⋈ cases（执行页编辑 / 报告页统计共用）。"""
    with _db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT rr.case_id, c.module, c.title, c.priority, c.method, c.precondition,"
            " c.steps, c.expected, rr.result, rr.note"
            " FROM run_results rr JOIN cases c ON c.id = rr.case_id"
            " WHERE rr.run_id=? ORDER BY rr.case_id", (run_id,))]


def set_result(run_id: int, case_id: str, result: str, note: str = "") -> None:
    with _db() as conn:
        conn.execute(
            "INSERT INTO run_results(run_id, case_id, result, note, updated_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(run_id, case_id) DO UPDATE SET result=excluded.result,"
            " note=excluded.note, updated_at=excluded.updated_at",
            (run_id, case_id, result, note, _now()))
        _bump(conn)


def finish_run(run_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE test_runs SET status='done', finished_at=? WHERE id=?",
            (_now(), run_id))
        _bump(conn)


def delete_run(run_id: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM test_runs WHERE id=?", (run_id,))
        _bump(conn)


def run_stats(run_id: int) -> dict:
    return get_run(run_id) or {"total": 0, "passed": 0, "failed": 0, "blocked": 0,
                               "skipped": 0, "pending": 0, "executed": 0, "pass_rate": 0.0}


# ---------------- 缺陷 ----------------

_SEVERITIES = ("严重", "一般", "轻微")
_DEFECT_STATUSES = ("打开", "修复中", "已解决", "已关闭")


def _next_defect_id(conn) -> str:
    row = conn.execute("SELECT value FROM counters WHERE name='defect_id'").fetchone()
    value = int(row["value"]) + 1
    conn.execute("UPDATE counters SET value=? WHERE name='defect_id'", (value,))
    return f"BUG{value:04d}"


def create_defect(*, title: str, module: str = "", severity: str = "一般",
                  description: str = "", source_case_id: str = "",
                  run_id: int | None = None, assignee: str = "") -> str:
    """登记缺陷；来源用例/测试单可选，形成 缺陷 ↔ 用例 追溯。"""
    now = _now()
    if severity not in _SEVERITIES:
        severity = "一般"
    with _db() as conn:
        did = _next_defect_id(conn)
        conn.execute(
            "INSERT INTO defects(id, title, module, severity, status, description,"
            " source_case_id, run_id, assignee, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (did, title, module, severity, "打开", description, source_case_id,
             run_id, assignee.strip(), now, now))
        _bump(conn)
    return did


def list_defects(*, keyword: str = "", status: str | None = None,
                 severity: str | None = None, module: str = "") -> list[dict]:
    """按条件查询缺陷，id 倒序。status/severity 为 None 时不过滤。"""
    sql = "SELECT * FROM defects WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if severity:
        sql += " AND severity=?"
        params.append(severity)
    if module:
        sql += " AND module=?"
        params.append(module)
    if keyword:
        sql += " AND (title LIKE ? OR module LIKE ? OR description LIKE ? OR source_case_id LIKE ?)"
        params += [f"%{keyword}%"] * 4
    sql += " ORDER BY id DESC"
    with _db() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_defect(defect_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("SELECT * FROM defects WHERE id=?", (defect_id,)).fetchone()
        return dict(row) if row else None


def update_defect(defect_id: str, *, status: str | None = None, severity: str | None = None,
                  title: str | None = None, description: str | None = None,
                  assignee: str | None = None) -> None:
    """白名单字段更新（状态流转 / 信息修正 / 指派处理人）。"""
    cols: dict = {}
    if status and status in _DEFECT_STATUSES:
        cols["status"] = status
    if severity and severity in _SEVERITIES:
        cols["severity"] = severity
    if title:
        cols["title"] = title
    if description is not None:
        cols["description"] = description
    if assignee is not None:
        cols["assignee"] = assignee.strip()
    if not cols:
        return
    sets = ", ".join(f"{k}=?" for k in cols)
    with _db() as conn:
        conn.execute(f"UPDATE defects SET {sets}, updated_at=? WHERE id=?",
                     list(cols.values()) + [_now(), defect_id])
        _bump(conn)


def delete_defects(defect_ids: list[str]) -> None:
    with _db() as conn:
        conn.executemany("DELETE FROM defects WHERE id=?", [(d,) for d in defect_ids])
        _bump(conn)


def defect_stats() -> dict:
    """各状态缺陷数（看板 KPI 与缺陷页共用）。"""
    with _db() as conn:
        rows = conn.execute("SELECT status, COUNT(*) c FROM defects GROUP BY status").fetchall()
    by = {r["status"]: r["c"] for r in rows}
    return {"total": sum(by.values()),
            "打开": by.get("打开", 0), "修复中": by.get("修复中", 0),
            "已解决": by.get("已解决", 0), "已关闭": by.get("已关闭", 0)}


# ---------------- 看板统计 ----------------

def kpi_snapshot() -> dict:
    """工作台 KPI 卡数据源。"""
    with _db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) c FROM cases WHERE status='active'").fetchone()["c"]
        ai = conn.execute(
            "SELECT COUNT(*) c FROM cases WHERE status='active' AND source='ai'").fetchone()["c"]
    runs = list_runs()
    done = [r for r in runs if r["status"] == "done"]
    last = done[0] if done else None
    with _db() as conn:
        defects_open = conn.execute(
            "SELECT COUNT(*) c FROM defects WHERE status IN ('打开','修复中')").fetchone()["c"]
    return {
        "cases_total": total,
        "ai_share": round(ai / total, 4) if total else 0.0,
        "runs_total": len(runs),
        "runs_in_progress": sum(1 for r in runs if r["status"] == "in_progress"),
        "defects_open": defects_open,
        "last_pass_rate": last["pass_rate"] if last else None,
        "last_run_name": last["name"] if last else "",
    }


def method_stats() -> list[dict]:
    with _db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT method, COUNT(*) count FROM cases WHERE status='active'"
            " GROUP BY method ORDER BY count DESC")]


def priority_stats() -> list[dict]:
    """每个优先级的 total / ai / manual（active 用例）。"""
    with _db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT priority, source, COUNT(*) count FROM cases WHERE status='active'"
            " GROUP BY priority, source")]
    agg: dict[str, dict] = {}
    for r in rows:
        d = agg.setdefault(r["priority"], {"priority": r["priority"], "total": 0, "ai": 0, "manual": 0})
        d["total"] += r["count"]
        d[r["source"]] = d.get(r["source"], 0) + r["count"]
    return [agg[p] for p in ("P0", "P1", "P2") if p in agg]


def trend_last_runs(n: int = 10) -> list[dict]:
    """最近 n 个已完成的测试单通过率，按时间正序。"""
    done = [r for r in list_runs() if r["status"] == "done"][:n]
    return [{"run": f"RUN-{r['id']:04d}", "name": r["name"], "pass_rate": r["pass_rate"]}
            for r in reversed(done)]


def module_quality() -> list[dict]:
    """各模块在已完成测试单中的通过情况（工作台模块质量图数据源）。"""
    with _db() as conn:
        rows = conn.execute(
            "SELECT c.module AS module,"
            " SUM(rr.result = '通过') AS passed,"
            " SUM(rr.result != '未执行') AS executed"
            " FROM run_results rr"
            " JOIN cases c ON c.id = rr.case_id"
            " JOIN test_runs r ON r.id = rr.run_id"
            " WHERE r.status = 'done'"
            " GROUP BY c.module ORDER BY executed DESC").fetchall()
    return [{"module": r["module"], "passed": r["passed"] or 0,
             "executed": r["executed"] or 0,
             "rate": round((r["passed"] or 0) / r["executed"], 4) if r["executed"] else 0.0}
            for r in rows]


# ---------------- 演示数据 / 清空 ----------------

def seed_demo() -> None:
    """一键填充演示数据：电商场景三模块 + 回归/冒烟/功能三张测试单 + 全状态缺陷。

    幂等：同模块同名的用例不会重复入库；库中已有全部演示数据时为空操作。
    """
    from agents import MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent
    from pipeline import run as run_pipeline

    prd_path = Path(__file__).resolve().parent / "data" / "sample_prd.txt"
    prd_text = prd_path.read_text(encoding="utf-8")
    points, cases, review = run_pipeline(
        MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent(), prd_text)

    items = [{"module": c.module, "title": c.title, "precondition": c.precondition,
              "steps": c.steps, "expected": c.expected, "priority": c.priority,
              "method": c.method, "testpoint_id": c.testpoint_id} for c in cases]
    _, login_ids = adopt_batch(prd_text, "mock", review.score, items, dedup=True)

    # 手工补充 注册 / 购物车 两模块（模拟从 Excel 导入的存量用例）
    manual = [
        {"module": "用户注册", "title": "手机号注册成功并收到验证码", "priority": "P0",
         "method": "场景法", "tags": "冒烟", "precondition": "手机号未注册",
         "steps": "1. 输入未注册手机号\n2. 点击获取验证码\n3. 填写验证码与密码并提交",
         "expected": "注册成功，跳转至首页"},
        {"module": "用户注册", "title": "已注册手机号重复注册给出引导", "priority": "P1",
         "method": "等价类", "precondition": "手机号已注册",
         "steps": "1. 输入已注册手机号\n2. 点击获取验证码",
         "expected": "提示「该手机号已注册」，引导去登录"},
        {"module": "用户注册", "title": "弱密码强度校验", "priority": "P2",
         "method": "边界值",
         "steps": "1. 输入 7 位纯数字密码\n2. 提交注册",
         "expected": "提示密码强度不足，要求字母+数字组合"},
        {"module": "用户注册", "title": "验证码有效期 5 分钟", "priority": "P2",
         "method": "场景法",
         "steps": "1. 获取验证码\n2. 等待 6 分钟后填写提交",
         "expected": "提示验证码已过期，可重新获取"},
        {"module": "购物车", "title": "加入购物车后角标数量同步", "priority": "P0",
         "method": "场景法", "tags": "冒烟", "precondition": "已登录，角标为 0",
         "steps": "1. 商品详情页点击「加入购物车」\n2. 观察底部导航角标",
         "expected": "角标数量 +1，与购物车内件数一致"},
        {"module": "购物车", "title": "删除商品后合计金额重算", "priority": "P1",
         "method": "场景法", "precondition": "购物车内含 2 件商品",
         "steps": "1. 左滑删除其中 1 件\n2. 查看合计金额",
         "expected": "合计金额同步减少，角标 -1"},
        {"module": "购物车", "title": "单商品购买数量上限 99 件", "priority": "P2",
         "method": "边界值",
         "steps": "1. 数量步进调至 99 与 100\n2. 观察提交结果",
         "expected": "99 正常保存；100 提示超出单商品上限"},
        {"module": "购物车", "title": "下架商品不参与结算", "priority": "P1",
         "method": "错误猜测", "precondition": "购物车内含 1 件已下架商品",
         "steps": "1. 全选商品点击结算\n2. 查看订单明细",
         "expected": "下架商品被自动剔除并提示，仅结算有效商品"},
    ]
    existing = {(c["module"], c["title"]) for c in list_cases()}
    fresh_manual = [m for m in manual if (m["module"], m["title"]) not in existing]
    manual_ids = add_cases(fresh_manual, source="manual") if fresh_manual else []
    if not login_ids and not manual_ids:
        return

    # ① 登录模块回归（已完成 · 通过率 78.8%）：确定性铺真实感结果分布
    defect_sources: list[tuple[dict, str, str]] = []  # (执行行, 严重程度, 状态)
    if login_ids:
        run1 = create_run(name="登录模块回归测试", env="测试环境",
                          note="v2.4.0 发布前回归", owner="陈曦", case_ids=login_ids)
        for i, cid in enumerate(login_ids):
            if i % 11 == 3:
                set_result(run1, cid, "失败", "实际未给出校验提示，已提缺陷")
            elif i % 17 == 5:
                set_result(run1, cid, "阻塞", "验证码服务环境暂不可用")
            elif i % 23 == 7:
                set_result(run1, cid, "跳过", "本迭代不涉及")
            else:
                set_result(run1, cid, "通过", "")
        finish_run(run1)
        rows1 = run_cases(run1)
        fails = [r for r in rows1 if r["result"] == "失败"]
        blocks = [r for r in rows1 if r["result"] == "阻塞"]
        if fails:
            defect_sources.append((fails[0], "一般", "打开"))
        if blocks:
            defect_sources.append((blocks[0], "轻微", "打开"))
        if len(fails) > 1:
            defect_sources.append((fails[1], "一般", "已解决"))   # 已修复，待回归验证
        if len(blocks) > 1:
            defect_sources.append((blocks[1], "轻微", "已关闭"))  # 已关闭

    # ② 每日冒烟（已完成 · P0 用例 · 高通过率，其中 1 条严重缺陷在修）
    p0_cases = list_cases(priority=["P0"], status="active")[:10]
    if p0_cases:
        run2 = create_run(name="每日冒烟测试", env="测试环境",
                          note="每日构建后圈选 P0 用例", owner="李梅",
                          case_ids=[c["id"] for c in p0_cases])
        smoke_fail = None
        for c in p0_cases:
            if "角标" in c["title"]:
                smoke_fail = c
                set_result(run2, c["id"], "失败", "角标数量未同步刷新，已提严重缺陷")
            else:
                set_result(run2, c["id"], "通过", "")
        if smoke_fail is not None:
            defect_sources.insert(1, ({"case_id": smoke_fail["id"], "module": smoke_fail["module"],
                                       "title": smoke_fail["title"],
                                       "note": "角标数量与购物车实际件数不一致",
                                       "result": "冒烟失败"},
                                      "严重", "修复中"))
        finish_run(run2)

    # ③ 功能测试（进行中 · 部分执行）：演示执行中间态
    func_ids = manual_ids + (login_ids[-4:] if login_ids else [])
    if func_ids:
        run3 = create_run(name="注册与购物车功能测试", env="预发环境",
                          note="迭代 2410 功能验证", owner="张涛", case_ids=func_ids)
        for i, cid in enumerate(func_ids[:5]):
            set_result(run3, cid, "失败" if i == 3 else "通过",
                       "提示文案含糊，待产品确认口径" if i == 3 else "")
    # run3 故意不 finish：保持「进行中」状态用于演示

    # 演示缺陷：覆盖 打开 / 修复中 / 已解决 / 已关闭 全状态，与用例、测试单双向关联
    result_word = {"失败": "回归失败", "阻塞": "执行受阻"}
    for row, severity, status in defect_sources:
        word = result_word.get(row.get("result"), row.get("result") or "测试失败")
        did = create_defect(
            title=f"[{row['module']}] {row['title']} {word}",
            module=row["module"], severity=severity,
            description=f"来源：{'每日冒烟测试' if '角标' in row['title'] else '登录模块回归测试'}；"
                        f"{row.get('note') or '详见执行明细'}",
            source_case_id=row["case_id"],
            assignee="王皓" if status == "已关闭" else "刘畅")
        if status != "打开":
            update_defect(did, status=status)


def clear_all() -> None:
    """清空业务数据（保留表结构与发号计数归零）。"""
    with _db() as conn:
        conn.execute("DELETE FROM run_results")
        conn.execute("DELETE FROM test_runs")
        conn.execute("DELETE FROM cases")
        conn.execute("DELETE FROM gen_batches")
        conn.execute("DELETE FROM defects")
        conn.execute("UPDATE counters SET value=0 WHERE name='case_id'")
        conn.execute("UPDATE counters SET value=0 WHERE name='defect_id'")
        _bump(conn)


def backup_bytes() -> bytes:
    """在线备份数据库为 bytes（SQLite backup API，避开 WAL 未合并问题）。"""
    import io

    buf = io.BytesIO()
    src = sqlite3.connect(_DB_PATH)
    dst = sqlite3.connect(buf)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()
    return buf.getvalue()
