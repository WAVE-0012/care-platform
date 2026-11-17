import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pyodbc
import pytest

from care.db import Repository, connect
from care.security import BusinessError
from care.services import health, orders, subsidy


def actor(db, name="admin"):
    return db.one("SELECT * FROM app_user WHERE username=?", name)


def new_order(db, elder=1, item=1, days=30, hour=10):
    return orders.create(
        db,
        actor(db),
        {
            "elderly_id": elder,
            "item_id": item,
            "scheduled_at": datetime.combine(
                date.today() + timedelta(days=days), time(hour)
            ).isoformat(),
            "duration_minutes": 60,
            "request_key": str(uuid4()),
        },
    )["id"]


def new_shift(db, worker=1, days=30, capacity=1):
    when = datetime.combine(date.today() + timedelta(days=days), time(8))
    return db.call("sp_publish_shift", worker, when, when.replace(hour=18), capacity)[
        "id"
    ]


def completed_order(db, elder=1, item=3, hours=Decimal("1.25"), days=-10):
    e = db.one("SELECT * FROM elderly WHERE id=?", elder)
    scheduled = datetime.combine(date.today() + timedelta(days=days), time(10))
    shift = db.call(
        "sp_publish_shift",
        elder,
        scheduled.replace(hour=8),
        scheduled.replace(hour=18),
        4,
    )["id"]
    o = db.insert(
        "INSERT service_order(request_key,elderly_id,item_id,community_id,created_by,scheduled_at,duration_minutes,address,longitude,latitude,unit_price,price_unit,channel,status) VALUES(?,?,?,?,?,?,90,?,?,?,60,'hour',N'社区代下单','confirming')",
        str(uuid4()),
        elder,
        item,
        e["community_id"],
        actor(db)["id"],
        scheduled,
        e["address"],
        e["longitude"],
        e["latitude"],
    )
    assignment = db.insert(
        "INSERT assignment(order_id,shift_id,dispatcher_id,status,service_record,confirmed_by,confirmed_at) VALUES(?,?,?,'accepted',N'完成约定服务',?,?)",
        o,
        shift,
        actor(db)["id"],
        e["user_id"],
        scheduled + timedelta(minutes=80),
    )
    db.execute(
        "INSERT work_log(assignment_id,checkin_at,checkout_at,longitude,latitude,geofence_ok,valid_hours,review_status) VALUES(?,?,?,?,?,1,?,'auto')",
        assignment,
        scheduled,
        scheduled + timedelta(minutes=75),
        e["longitude"],
        e["latitude"],
        hours,
    )
    eligibility = db.one(
        "SELECT * FROM dbo.fn_eligibility(?,?,?)", elder, item, scheduled.date()
    )
    db.execute(
        "INSERT eligibility_snapshot(order_id,assessment_id,plan_id,low_income,checked_by) VALUES(?,?,?,?,?)",
        o,
        eligibility["assessment_id"],
        eligibility["plan_id"],
        e["low_income"],
        actor(db)["id"],
    )
    return o, assignment, shift


def test_all_tables_have_twenty_rows(db):
    rows = db.all(
        "SELECT t.name,SUM(p.rows) n FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN(0,1) GROUP BY t.name"
    )
    assert len(rows) == 33
    assert all(row["n"] >= 20 for row in rows), rows
    assert db.scalar("SELECT COUNT(*) FROM sys.views") >= 15
    assert db.scalar("SELECT COUNT(*) FROM sys.procedures WHERE is_ms_shipped=0") >= 5
    assert db.scalar("SELECT COUNT(*) FROM sys.triggers WHERE parent_class=1") >= 5


def test_identity_duplicate(db):
    with pytest.raises(pyodbc.IntegrityError):
        db.execute(
            "UPDATE elderly SET identity_hash=(SELECT identity_hash FROM elderly WHERE id=1) WHERE id=2"
        )


def test_latest_expired_assessment_does_not_fall_back(db):
    db.execute(
        "INSERT assessment(elderly_id,scale,score,ability_level,assessor_id,assessed_on,valid_until) VALUES(1,'ADL',80,0,?,?,?)",
        actor(db)["id"],
        date.today() - timedelta(days=2),
        date.today() - timedelta(days=1),
    )
    assert (
        db.scalar("SELECT COUNT(*) FROM dbo.fn_eligibility(1,1,?)", date.today()) == 0
    )


def test_plan_overlap(db):
    with pytest.raises(pyodbc.Error, match="计划"):
        db.call(
            "sp_create_plan", 1, 1, 1, date.today(), date.today() + timedelta(days=5)
        )


def test_overlapping_shifts(db):
    new_shift(db)
    with pytest.raises(pyodbc.Error, match="重叠"):
        new_shift(db)


def test_boundary_shifts_can_touch(db):
    start = datetime.combine(date.today() + timedelta(days=31), time(8))
    db.call("sp_publish_shift", 1, start, start.replace(hour=10), 2)
    db.call("sp_publish_shift", 1, start.replace(hour=10), start.replace(hour=12), 2)


def test_dispatch_capacity_and_rollback(db):
    shift = new_shift(db)
    first, second = new_order(db), new_order(db, hour=12)
    db.call("sp_dispatch", first, shift, actor(db)["id"])
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 1
    # 存储过程异常回滚整个事务；独立并发测试进一步检查已提交数据。
    with pytest.raises(pyodbc.Error, match="名额"):
        db.call("sp_dispatch", second, shift, actor(db)["id"])


def test_certificate_restriction(db):
    shift = new_shift(db)
    order = new_order(db, item=2)
    db.execute(
        "UPDATE certificate SET valid_until=? WHERE worker_id=1",
        date.today() - timedelta(days=1),
    )
    assert not db.all(
        "SELECT * FROM dbo.fn_candidates(?) WHERE shift_id=?", order, shift
    )


def test_reassignment_preserves_history_and_capacity(db):
    first_shift = new_shift(db, worker=1)
    second_shift = new_shift(db, worker=21)
    order = new_order(db)
    db.call("sp_dispatch", order, first_shift, actor(db)["id"])
    db.call("sp_dispatch", order, second_shift, actor(db)["id"], "护工临时调整")
    assert db.scalar("SELECT COUNT(*) FROM assignment WHERE order_id=?", order) == 2
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM assignment WHERE order_id=? AND is_current=1", order
        )
        == 1
    )
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", first_shift) == 0
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", second_shift) == 1


def test_timeout_releases_once(db):
    shift = new_shift(db)
    order = new_order(db)
    assigned = db.call("sp_dispatch", order, shift, actor(db)["id"])["id"]
    db.execute(
        "UPDATE assignment SET assigned_at=DATEADD(minute,-16,GETDATE()) WHERE id=?",
        assigned,
    )
    db.call("sp_expire_services")
    db.call("sp_expire_services")
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 0
    assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == "pending"


def test_cancel_and_reschedule_release_slots(db):
    shift = new_shift(db)
    order = new_order(db)
    db.call("sp_dispatch", order, shift, actor(db)["id"])
    orders.reschedule(
        db,
        actor(db),
        order,
        {
            "scheduled_at": datetime.combine(
                date.today() + timedelta(days=32), time(10)
            ).isoformat()
        },
    )
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 0
    orders.cancel(db, actor(db), order, {"reason": "取消测试"})
    orders.cancel(db, actor(db), order, {"reason": "重复取消"})
    assert (
        db.scalar("SELECT status FROM service_order WHERE id=?", order) == "cancelled"
    )


def test_settlement_and_idempotence(db):
    order, assignment, shift = completed_order(db)
    before = db.scalar("SELECT total_hours FROM worker WHERE id=1")
    db.call("sp_finish_order", order)
    db.call("sp_finish_order", order)
    assert db.scalar(
        "SELECT settlement FROM service_order WHERE id=?", order
    ) == Decimal("75.00")
    assert db.scalar("SELECT total_hours FROM worker WHERE id=1") == before + Decimal(
        "1.25"
    )
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 1


def test_missing_confirmation_blocks_completion(db):
    order, assignment, _ = completed_order(db)
    db.execute("UPDATE assignment SET confirmed_at=NULL WHERE id=?", assignment)
    with pytest.raises(pyodbc.Error, match="齐全"):
        db.call("sp_finish_order", order)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE service_order SET settlement=1 WHERE id=1",
        "UPDATE assessment SET score=0 WHERE id=1",
        "UPDATE work_log SET valid_hours=2 WHERE assignment_id=1",
        "UPDATE eligibility_snapshot SET low_income=0 WHERE order_id=1",
        "UPDATE assignment SET service_record=N'改写' WHERE id=1",
        "UPDATE plan_item SET frequency=4 WHERE plan_id=1",
        "UPDATE claim_item SET amount=1 WHERE claim_id=1",
        "UPDATE subsidy_claim SET amount=1 WHERE id=1",
    ],
)
def test_history_is_frozen(db, sql):
    with pytest.raises(pyodbc.Error):
        db.execute(sql)


def test_device_rebinding_and_late_arrival(db):
    admin = actor(db)
    now = datetime.now().replace(microsecond=0)
    split = now - timedelta(hours=1)
    db.call("sp_bind_device", 1, 21, admin["id"], split)
    records = [
        {
            "device_id": 1,
            "metric": "pulse",
            "collected_at": (split - timedelta(seconds=1)).isoformat(),
            "value": 80,
        },
        {
            "device_id": 1,
            "metric": "pulse",
            "collected_at": split.isoformat(),
            "value": 82,
        },
    ]
    ids = health.upload(db, admin, records)["ids"]
    owners = [
        db.scalar(
            "SELECT b.elderly_id FROM vital v JOIN device_binding b ON b.id=v.binding_id WHERE v.id=?",
            i,
        )
        for i in ids
    ]
    assert owners == [1, 21]
    assert health.upload(db, admin, records)["ids"] == ids
    records[0]["value"] = 85
    with pytest.raises(BusinessError, match="不同数值"):
        health.upload(db, admin, records)


def test_multirow_threshold_trigger(db):
    now = datetime.now().replace(microsecond=0)
    db.execute(
        "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(1,1,?,140),(2,4,?,141)",
        now,
        now,
    )
    rows = db.all(
        "SELECT value,abnormal FROM vital WHERE collected_at=? ORDER BY value", now
    )
    assert [(r["value"], r["abnormal"]) for r in rows] == [
        (Decimal("140.00"), False),
        (Decimal("141.00"), True),
    ]


def test_vital_rule_must_match_elderly_community(db):
    now = datetime.now().replace(microsecond=0)
    with pytest.raises(pyodbc.Error, match="社区"):
        db.execute(
            "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(1,4,?,120)",
            now,
        )


def test_emergency_survives_expired_plan_and_escalates_once(db):
    db.execute("UPDATE care_plan SET status='paused' WHERE elderly_id=1")
    event = health.create_event(
        db, actor(db), {"elderly_id": 1, "level": 3, "request_key": str(uuid4())}
    )["id"]
    db.execute(
        "UPDATE emergency SET occurred_at=DATEADD(minute,-20,GETDATE()) WHERE id=?",
        event,
    )
    db.call("sp_escalate_emergencies")
    db.call("sp_escalate_emergencies")
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM notification WHERE event_id=? AND stage='escalated'",
            event,
        )
        == 1
    )
    health.send_notifications(db, fail=True)
    health.send_notifications(db, fail=True)
    health.send_notifications(db, fail=True)
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM notification WHERE event_id=? AND status='manual'",
            event,
        )
        >= 3
    )


def test_claim_repeated_and_review_round(db):
    month = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    first = db.call(
        "sp_claim_month", 21, 1, month, actor(db, "community01")["id"], "完整材料"
    )["id"]
    assert (
        first
        == db.call(
            "sp_claim_month", 21, 1, month, actor(db, "community01")["id"], "重复提交"
        )["id"]
    )
    street = actor(db, "street01")["id"]
    civil = actor(db, "civil01")["id"]
    db.call("sp_review_claim", first, street, "approve", "核对通过")
    db.call("sp_review_claim", first, civil, "return", "补充证明")
    db.call("sp_claim_month", 21, 1, month, actor(db, "community01")["id"], "补齐材料")
    assert db.scalar("SELECT status FROM subsidy_claim WHERE id=?", first) == "street"
    db.call("sp_review_claim", first, street, "approve", "重新初审")
    db.call("sp_review_claim", first, civil, "approve", "终审通过")
    db.call("sp_pay_claim", first, civil, "TEST-PAY-" + str(first))
    db.call("sp_pay_claim", first, civil, "TEST-PAY-" + str(first))
    assert db.scalar("SELECT COUNT(*) FROM claim_review WHERE claim_id=?", first) == 4


def test_claim_current_month_rejected(db):
    with pytest.raises(pyodbc.Error, match="次月"):
        db.call(
            "sp_claim_month", 1, 1, date.today().replace(day=1), actor(db)["id"], "材料"
        )


def test_quality_restrictions_require_regulator(db):
    check = subsidy.quality(
        db,
        actor(db, "street01"),
        {
            "worker_id": 1,
            "method": "上门核查",
            "score": 2,
            "issue": "证书记录缺项",
            "requirement": "补齐证书核验记录",
            "due_on": date.today() + timedelta(days=7),
        },
    )["id"]
    assert (
        db.scalar("SELECT COUNT(*) FROM v_quality_restrictions WHERE id=?", check) == 1
    )
    subsidy.rectify(
        db, actor(db, "agency01"), check, {"action": "submit", "result": "完成补录并提交证书扫描件"}
    )
    assert (
        db.scalar("SELECT COUNT(*) FROM v_quality_restrictions WHERE id=?", check) == 1
    )
    with pytest.raises(PermissionError):
        subsidy.rectify(db, actor(db, "agency01"), check, {"action": "approve"})
    subsidy.rectify(db, actor(db, "street01"), check, {"action": "approve"})
    assert (
        db.scalar("SELECT COUNT(*) FROM v_quality_restrictions WHERE id=?", check) == 0
    )


def test_batch_rollback(db):
    with pytest.raises(pyodbc.Error):
        db.batch(
            "INSERT worker_area(worker_id,community_id) VALUES(?,?)",
            [(1, 2), (999999, 2)],
        )
    db.connection.rollback()
    assert (
        db.scalar(
            "SELECT COUNT(*) FROM worker_area WHERE worker_id=1 AND community_id=2"
        )
        == 0
    )


def test_concurrent_last_slot(database):
    connection = connect()
    db = Repository(connection)
    shift = new_shift(db, days=45)
    ids = [new_order(db, days=45, hour=10), new_order(db, days=45, hour=12)]
    user_id = actor(db)["id"]
    connection.commit()
    connection.close()
    barrier = Barrier(2)

    def reserve(order_id):
        conn = connect()
        try:
            barrier.wait(timeout=10)
            Repository(conn).call("sp_dispatch", order_id, shift, user_id)
            conn.commit()
            return "success"
        except pyodbc.Error:
            conn.rollback()
            return "rejected"
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, ids))
    assert sorted(results) == ["rejected", "success"]
    conn = connect()
    check = Repository(conn)
    assert check.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 1
    assert check.scalar("SELECT COUNT(*) FROM assignment WHERE shift_id=?", shift) == 1
    conn.close()


def query_cases():
    cases = {}
    for path in sorted(
        (Path(__file__).resolve().parents[1] / "sql/queries").glob("*.sql")
    ):
        parts = re.split(
            r"^-- query: (\w+\.[ab])\s*$", path.read_text(encoding="utf-8"), flags=re.M
        )
        for key, sql in zip(parts[1::2], parts[2::2]):
            cases[key] = sql
    return cases


@pytest.mark.parametrize(
    "query_id", [f"{letter}{number}" for letter in "ABCDE" for number in range(1, 4)]
)
def test_query_variants_equivalent(db, query_id):
    cases = query_cases()
    a = db.all(cases[query_id + ".a"])
    b = db.all(cases[query_id + ".b"])
    normalize = lambda rows: sorted(
        [tuple((key, str(value)) for key, value in row.items()) for row in rows]
    )
    assert normalize(a) == normalize(b)


def test_runtime_identity_cannot_change_schema_or_audit(database):
    from care.db import transaction

    with transaction(restricted=True) as db:
        assert db.scalar("SELECT COUNT(*) FROM elderly") >= 40
        with pytest.raises(pyodbc.Error):
            db.execute("CREATE TABLE forbidden_schema_change(id int)")
        with pytest.raises(pyodbc.Error):
            db.execute("DELETE FROM audit_log WHERE id=1")
