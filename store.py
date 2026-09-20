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
INSERT OR IGNORE INTO counters(name, value) VALUES ('case_id', 0);
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
        conn.commit()
    finally:
        conn.close()
    _init_done.set()


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


def set_case_status(case_ids: list[str], status: str) -> None:
    with _db() as conn:
        conn.executemany(
            "UPDATE cases SET status=?, updated_at=? WHERE id=?",
            [(status, _now(), cid) for cid in case_ids])


def delete_cases(case_ids: list[str]) -> None:
    """物理删除（run_results 由外键级联清理）。"""
    with _db() as conn:
        conn.executemany("DELETE FROM cases WHERE id=?", [(cid,) for cid in case_ids])


# ---------------- 测试单 / 执行结果 ----------------

def create_run(*, name: str, env: str = "测试环境", note: str = "",
               case_ids: list[str]) -> int:
    if not case_ids:
        raise ValueError("测试单至少需要圈选一条用例")
    now = _now()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO test_runs(name, env, note, created_at) VALUES (?,?,?,?)",
            (name, env, note, now))
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO run_results(run_id, case_id, result, updated_at) VALUES (?,?,?,?)",
            [(run_id, cid, "未执行", now) for cid in case_ids])
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


def finish_run(run_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE test_runs SET status='done', finished_at=? WHERE id=?",
            (_now(), run_id))


def delete_run(run_id: int) -> None:
    with _db() as conn:
        conn.execute("DELETE FROM test_runs WHERE id=?", (run_id,))


def run_stats(run_id: int) -> dict:
    return get_run(run_id) or {"total": 0, "passed": 0, "failed": 0, "blocked": 0,
                               "skipped": 0, "pending": 0, "executed": 0, "pass_rate": 0.0}


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
    return {
        "cases_total": total,
        "ai_share": round(ai / total, 4) if total else 0.0,
        "runs_total": len(runs),
        "runs_in_progress": sum(1 for r in runs if r["status"] == "in_progress"),
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


# ---------------- 演示数据 / 清空 ----------------

def seed_demo() -> None:
    """一键填充演示数据：mock 流水线跑样例 PRD → 采纳入库 → 建一个已完成的测试单。"""
    from agents import MockAnalyzerAgent, MockGeneratorAgent, MockReviewerAgent
    from pipeline import run as run_pipeline

    prd_path = Path(__file__).resolve().parent / "data" / "sample_prd.txt"
    prd_text = prd_path.read_text(encoding="utf-8")
    points, cases, review = run_pipeline(
        MockAnalyzerAgent(), MockGeneratorAgent(), MockReviewerAgent(), prd_text)

    items = [{"module": c.module, "title": c.title, "precondition": c.precondition,
              "steps": c.steps, "expected": c.expected, "priority": c.priority,
              "method": c.method, "testpoint_id": c.testpoint_id} for c in cases]
    _, ids = adopt_batch(prd_text, "mock", review.score, items)
    if not ids:
        return

    run_id = create_run(name="登录模块回归测试（演示数据）", env="测试环境",
                        note="由平台演示数据自动创建", case_ids=ids)
    # 确定性地铺一组真实感执行结果：绝大多数通过，少量失败/阻塞/跳过
    for i, cid in enumerate(ids):
        if i % 11 == 3:
            result, note = "失败", "实际未给出校验提示，已提缺陷"
        elif i % 17 == 5:
            result, note = "阻塞", "依赖环境暂不可用"
        elif i % 23 == 7:
            result, note = "跳过", "本迭代不涉及"
        else:
            result, note = "通过", ""
        set_result(run_id, cid, result, note)
    finish_run(run_id)


def clear_all() -> None:
    """清空业务数据（保留表结构与发号计数归零）。"""
    with _db() as conn:
        conn.execute("DELETE FROM run_results")
        conn.execute("DELETE FROM test_runs")
        conn.execute("DELETE FROM cases")
        conn.execute("DELETE FROM gen_batches")
        conn.execute("UPDATE counters SET value=0 WHERE name='case_id'")


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
