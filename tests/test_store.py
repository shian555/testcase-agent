"""store.py 离线单测：临时数据库上验证 CRUD、发号、测试单生命周期与级联删除。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store


@pytest.fixture()
def tmp_db(tmp_path):
    """每个用例独享一个临时库，结束恢复默认路径。"""
    original = store.db_path()
    store.set_db_path(tmp_path / "test.db")
    yield
    store.set_db_path(original)


def _case(title="登录成功", module="登录", **kw):
    kw.setdefault("priority", "P0")
    kw.setdefault("method", "场景法")
    return store.add_case(module=module, title=title, **kw)


def test_case_crud(tmp_db):
    cid = _case()
    got = store.get_case(cid)
    assert got["title"] == "登录成功" and got["source"] == "manual"

    store.update_case(cid, title="登录成功（改）", priority="P1", tags="冒烟")
    got = store.get_case(cid)
    assert got["title"] == "登录成功（改）" and got["priority"] == "P1" and got["tags"] == "冒烟"

    assert len(store.list_cases()) == 1
    assert store.list_cases(keyword="改") and not store.list_cases(keyword="不存在")
    assert store.list_cases(priority=["P1"]) and not store.list_cases(priority=["P2"])

    store.set_case_status([cid], "deprecated")
    assert not store.list_cases() and store.list_cases(status="all")

    store.delete_cases([cid])
    assert store.get_case(cid) is None


def test_ids_monotonic_never_reused(tmp_db):
    a = _case("用例A")
    b = _case("用例B")
    assert (a, b) == ("TC0001", "TC0002")
    store.delete_cases([b])
    assert _case("用例C") == "TC0003"  # 删除后号码不复用


def test_adopt_batch_and_dedup(tmp_db):
    items = [{"module": "登录", "title": "空密码登录", "priority": "P1",
              "method": "等价类", "testpoint_id": "TP001"},
             {"module": "登录", "title": "超长密码", "priority": "P2",
              "method": "边界值", "testpoint_id": "TP002"}]
    batch_id, ids = store.adopt_batch("PRD...", "mock", 100, items)
    assert len(ids) == 2 and all(i.startswith("TC") for i in ids)
    case = store.get_case(ids[0])
    assert case["source"] == "ai" and case["batch_id"] == batch_id
    assert case["review_score"] == 100 and case["testpoint_id"] == "TP001"

    _, ids2 = store.adopt_batch("PRD...", "mock", 100, items, dedup=True)
    assert ids2 == []  # 同模块同名被去重
    _, ids3 = store.adopt_batch("PRD...", "mock", 100, items, dedup=False)
    assert len(ids3) == 2  # 不去重则允许重复入库


def test_run_lifecycle_and_stats(tmp_db):
    ids = [_case(f"用例{i}") for i in range(4)]
    run_id = store.create_run(name="回归", case_ids=ids)
    stats = store.run_stats(run_id)
    assert stats["total"] == 4 and stats["pending"] == 4 and stats["pass_rate"] == 0.0

    store.set_result(run_id, ids[0], "通过")
    store.set_result(run_id, ids[1], "通过")
    store.set_result(run_id, ids[2], "失败", "提了缺陷")
    stats = store.run_stats(run_id)
    assert (stats["passed"], stats["failed"], stats["pending"]) == (2, 1, 1)
    assert stats["pass_rate"] == round(2 / 3, 4)  # 通过率 = 通过 / 已执行

    run = store.get_run(run_id)
    assert run["status"] == "in_progress"
    store.finish_run(run_id)
    runs = store.list_runs()
    assert runs[0]["status"] == "done" and runs[0]["name"] == "回归"
    assert store.trend_last_runs(5)[0]["pass_rate"] == round(2 / 3, 4)

    store.delete_run(run_id)
    assert store.get_run(run_id) is None


def test_delete_case_cascades_run_results(tmp_db):
    cid = _case("被删用例")
    run_id = store.create_run(name="R", case_ids=[cid])
    store.delete_cases([cid])
    assert store.run_cases(run_id) == []
    assert store.run_stats(run_id)["total"] == 0


def test_seed_demo_and_clear(tmp_db):
    store.seed_demo()
    store.seed_demo()  # 幂等：重复填充不产生重复数据
    cases = store.list_cases()
    assert len(cases) > 0 and {c["source"] for c in cases} == {"ai", "manual"}

    runs = store.list_runs()
    assert len(runs) == 3 and sum(r["status"] == "done" for r in runs) == 2
    assert runs[0]["status"] == "in_progress"  # 功能测试保持执行中间态
    assert all(r["passed"] > 0 for r in runs if r["status"] == "done")

    # 缺陷覆盖 打开 / 修复中 / 已解决 / 已关闭 全状态
    stats = store.defect_stats()
    assert (stats["total"], stats["打开"], stats["修复中"],
            stats["已解决"], stats["已关闭"]) == (5, 2, 1, 1, 1)

    kpi = store.kpi_snapshot()
    assert kpi["cases_total"] == len(cases) and kpi["last_pass_rate"] is not None
    assert kpi["defects_open"] == 3  # 打开 2 + 修复中 1
    assert len(store.trend_last_runs(5)) == 2  # 两张已完成单形成趋势线
    assert store.method_stats() and store.priority_stats()

    store.clear_all()
    assert store.list_cases() == [] and store.list_runs() == []
    assert store.defect_stats()["total"] == 0
    assert store.next_case_id() == "TC0001"  # 发号归零


def test_defect_crud_and_flow(tmp_db):
    cid = _case("验证码为空仍可提交", module="登录")
    v0 = store.version()
    did = store.create_defect(title="[登录] 验证码为空仍可提交", module="登录",
                              severity="严重", description="实际可提交",
                              source_case_id=cid, run_id=None)
    assert did == "BUG0001"
    assert store.version() == v0 + 1  # 写操作推进数据版本（导出缓存盐）

    got = store.get_defect(did)
    assert got["status"] == "打开" and got["severity"] == "严重"
    assert got["source_case_id"] == cid

    # 状态流转：打开 → 修复中 → 已解决 → 已关闭；非法值被拒
    for status in ("修复中", "已解决", "已关闭"):
        store.update_defect(did, status=status)
        assert store.get_defect(did)["status"] == status
    store.update_defect(did, status="不存在的状态")
    assert store.get_defect(did)["status"] == "已关闭"
    store.update_defect(did, severity="轻微")
    assert store.get_defect(did)["severity"] == "轻微"

    # 过滤与列表
    store.create_defect(title="另一缺陷", module="注册", severity="轻微")
    assert len(store.list_defects()) == 2
    assert [d["id"] for d in store.list_defects(status="已关闭")] == [did]
    assert len(store.list_defects(severity="轻微")) == 2  # BUG0001 已改为轻微
    assert len(store.list_defects(keyword="验证码")) == 1
    stats = store.defect_stats()
    assert stats["total"] == 2 and stats["已关闭"] == 1

    store.delete_defects([did])
    assert store.get_defect(did) is None
    assert store.defect_stats()["total"] == 1
