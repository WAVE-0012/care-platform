"""五处逻辑修复的回归场景；由现有fixture在独立测试库执行。"""
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pyodbc
import pytest

from care import queries
from care.db import Repository, connect
from care.security import BusinessError
from care.services import elders, health, orders
from tests.test_database import actor, completed_order, new_order, new_shift


def assess(db, level, days, valid_until):
    return elders.assess(db, actor(db), 1, {
        "scale": "ADL", "score": 100 - 25 * level, "ability_level": level,
        "assessed_on": (date.today() + timedelta(days=days)).isoformat(),
        "valid_until": valid_until.isoformat(),
    })["id"]


def test_backdated_assessment_does_not_pause_current_plan(db):
    current = assess(db, 0, -2, date.today() + timedelta(days=100))
    assess(db, 1, -3, date.today() + timedelta(days=200))
    eligibility = db.one("SELECT * FROM dbo.fn_eligibility(1,1,?)", date.today())
    assert eligibility["assessment_id"] == current
    assert db.scalar("SELECT status FROM care_plan WHERE id=1") == "active"


def test_old_expiry_does_not_pause_new_valid_assessment(db):
    current = assess(db, 0, -1, date.today() + timedelta(days=100))
    assess(db, 0, -2, date.today() - timedelta(days=2))
    db.call("sp_expire_services")
    assert db.scalar("SELECT assessment_id FROM dbo.fn_eligibility(1,1,?)", date.today()) == current
    assert db.scalar("SELECT status FROM care_plan WHERE id=1") == "active"


@pytest.mark.parametrize("expired", [False, True])
def test_latest_invalid_assessment_releases_unstarted_assignment(db, expired):
    order = new_order(db)
    shift = new_shift(db)
    assignment = db.call("sp_dispatch", order, shift, actor(db)["id"])["id"]
    assess(db, 0 if expired else 1, -2,
           date.today() - timedelta(days=1) if expired else date.today() + timedelta(days=100))
    assert db.scalar("SELECT status FROM care_plan WHERE id=1") == "paused"
    assert db.scalar("SELECT is_current FROM assignment WHERE id=?", assignment) == 0
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 0
    assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == "ineligible"


@pytest.mark.parametrize("record", ["修改后的服务内容", "完成约定服务 "])
def test_record_change_cannot_reuse_confirmation(db, record):
    _, assignment, _ = completed_order(db)
    with pytest.raises(pyodbc.Error, match="51122"):
        db.execute("UPDATE assignment SET service_record=? WHERE id=?", record, assignment)


def test_record_change_requires_a_separate_reconfirmation(db):
    order, assignment, _ = completed_order(db)
    db.execute(
        "UPDATE assignment SET service_record=N'补充核实后的服务内容',confirmed_by=NULL,confirmed_at=NULL WHERE id=?",
        assignment,
    )
    assert db.scalar("SELECT confirmed_at FROM assignment WHERE id=?", assignment) is None
    assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == "confirming"
    orders.confirm(db, actor(db, "family01"), order, {})
    assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == "completed"


def test_modified_record_cannot_finish_before_reconfirmation(db):
    order, assignment, _ = completed_order(db)
    db.execute(
        "UPDATE assignment SET service_record=N'修改待重新确认',confirmed_by=NULL,confirmed_at=NULL WHERE id=?",
        assignment,
    )
    with pytest.raises(pyodbc.Error, match="51009"):
        db.call("sp_finish_order", order)


def test_completed_record_still_cannot_be_changed(db):
    order, assignment, _ = completed_order(db)
    db.call("sp_finish_order", order)
    with pytest.raises(pyodbc.Error, match="51107"):
        db.execute(
            "UPDATE assignment SET service_record=N'完成约定服务 ',confirmed_by=NULL,confirmed_at=NULL WHERE id=?",
            assignment,
        )


@pytest.mark.parametrize("certificate_type,level", [(None, None), ("护理", 1), ("护理", 2), ("护理", 3)])
def test_certificate_requirement_valid_pairs(db, certificate_type, level):
    db.execute("UPDATE service_item SET certificate_type=?,certificate_level=? WHERE id=1", certificate_type, level)
    item = db.one("SELECT certificate_type,certificate_level FROM service_item WHERE id=1")
    assert (item["certificate_type"], item["certificate_level"]) == (certificate_type, level)


@pytest.mark.parametrize("certificate_type,level", [(None, 1), ("护理", None), ("护理", 0), ("护理", 4)])
def test_certificate_requirement_invalid_pairs(db, certificate_type, level):
    with pytest.raises(pyodbc.Error, match="547"):
        db.execute("UPDATE service_item SET certificate_type=?,certificate_level=? WHERE id=1", certificate_type, level)


def pulse_record():
    return {"device_id": 1, "metric": "pulse", "value": 80.25,
            "collected_at": (datetime.now().replace(microsecond=0) - timedelta(minutes=3)).isoformat()}


@pytest.mark.parametrize("new_community_has_rule", [True, False])
def test_duplicate_upload_after_migration_keeps_original_record(db, new_community_has_rule):
    record = pulse_record()
    original_id = health.upload(db, actor(db), [record])["ids"][0]
    original = db.one("SELECT binding_id,rule_id,received_at,value FROM vital WHERE id=?", original_id)
    community = 2
    if not new_community_has_rule:
        community = db.insert(
            "INSERT community(name,street_id,longitude,latitude) VALUES(?,2,116.31,40)",
            "未配置指标的迁入社区-" + uuid4().hex,
        )
    elders.update(db, actor(db), 1, {"community_id": community, "reason": "跨社区迁移回归场景"})
    assert health.upload(db, actor(db), [record])["ids"] == [original_id]
    assert db.one("SELECT binding_id,rule_id,received_at,value FROM vital WHERE id=?", original_id) == original
    assert db.scalar(
        "SELECT COUNT(*) FROM vital v JOIN device_binding b ON b.id=v.binding_id JOIN metric_rule r ON r.id=v.rule_id "
        "WHERE b.device_id=1 AND v.collected_at=? AND r.metric='pulse'",
        datetime.fromisoformat(record["collected_at"]),
    ) == 1


def test_conflicting_upload_after_migration_does_not_overwrite(db):
    record = pulse_record()
    original_id = health.upload(db, actor(db), [record])["ids"][0]
    before = db.scalar("SELECT value FROM vital WHERE id=?", original_id)
    elders.update(db, actor(db), 1, {"community_id": 2})
    with pytest.raises(BusinessError, match="不同数值"):
        health.upload(db, actor(db), [{**record, "value": 81}])
    assert db.scalar("SELECT value FROM vital WHERE id=?", original_id) == before


def test_database_rejects_duplicate_collection_with_another_rule(db):
    record = pulse_record()
    original = health.upload(db, actor(db), [record])["ids"][0]
    binding = db.scalar("SELECT binding_id FROM vital WHERE id=?", original)
    another_rule = db.scalar("SELECT id FROM metric_rule WHERE community_id=2 AND metric='pulse'")
    with pytest.raises(pyodbc.Error, match="51123"):
        db.insert(
            "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(?,?,?,?)",
            binding, another_rule, datetime.fromisoformat(record["collected_at"]), record["value"],
        )


def test_database_rejects_duplicates_within_one_insert(db):
    record = pulse_record()
    collected = datetime.fromisoformat(record["collected_at"])
    rules = [db.scalar("SELECT id FROM metric_rule WHERE community_id=? AND metric='pulse'", c) for c in (1, 2)]
    with pytest.raises(pyodbc.Error, match="51123"):
        db.execute(
            "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(1,?,?,80),(1,?,?,80)",
            rules[0], collected, rules[1], collected,
        )


def test_distinct_metrics_and_devices_can_share_collection_time(db):
    record = pulse_record()
    ids = health.upload(db, actor(db), [record, {**record, "metric": "systolic", "value": 120},
                                       {**record, "device_id": 2}])["ids"]
    assert len(set(ids)) == 3


def test_concurrent_reuploads_return_one_record(database):
    connection = connect()
    setup = Repository(connection)
    try:
        user = actor(setup)
        device = setup.insert(
            "INSERT device(serial_number,device_type,location) VALUES(?,N'血压计',N'并发测试')",
            "TEST-" + uuid4().hex,
        )
        setup.call("sp_bind_device", device, 1, user["id"], datetime.now() - timedelta(days=1))
        connection.commit()
    finally:
        connection.close()
    record = {**pulse_record(), "device_id": device}
    barrier = Barrier(2)

    def upload_once(_):
        conn = connect()
        try:
            barrier.wait(timeout=10)
            result = health.upload(Repository(conn), user, [record])["ids"][0]
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(upload_once, range(2)))
    assert ids[0] == ids[1]
    conn = connect()
    try:
        assert Repository(conn).scalar(
            "SELECT COUNT(*) FROM vital v JOIN device_binding b ON b.id=v.binding_id WHERE b.device_id=?",
            device,
        ) == 1
    finally:
        conn.close()


def test_quality_scope_separates_order_and_worker_targets_with_pagination(db):
    order, _, _ = completed_order(db)
    db.call("sp_finish_order", order)
    db.execute("INSERT worker_area(worker_id,community_id) VALUES(1,2)")
    keyword = "范围核查-" + uuid4().hex
    db.execute("UPDATE worker SET name=? WHERE id=1", keyword)
    original = db.all(
        "SELECT q.id,q.order_id FROM quality_check q LEFT JOIN assignment a ON a.order_id=q.order_id AND a.is_current=1 "
        "LEFT JOIN shift s ON s.id=a.shift_id WHERE COALESCE(q.worker_id,s.worker_id)=1"
    )
    order_ids = {row["id"] for row in original if row["order_id"] is not None}
    direct_ids = {row["id"] for row in original if row["order_id"] is None}
    for _ in range(23):
        order_ids.add(db.insert(
            "INSERT quality_check(order_id,inspector_id,method,score) VALUES(?,?,N'上门核查',4)",
            order, actor(db, "civil01")["id"],
        ))
        direct_ids.add(db.insert(
            "INSERT quality_check(worker_id,inspector_id,method,score) VALUES(1,?,N'上门核查',4)",
            actor(db, "civil01")["id"],
        ))
    users = {name: actor(db, name) for name in (
        "street01", "street02", "community01", "community02", "civil01", "agency01", "worker01", "admin"
    )}
    db.execute("EXECUTE AS USER='care_app'")
    try:
        for name, user in users.items():
            expected = direct_ids if name in ("street02", "community02") else direct_ids | order_ids
            first = queries.listing(db, user, "quality", page=1, keyword=keyword)
            assert first["total"] == len(expected), name
            rows = first["rows"]
            for page in range(2, (first["total"] + 19) // 20 + 1):
                result = queries.listing(db, user, "quality", page=page, keyword=keyword)
                assert result["total"] == len(expected), name
                rows += result["rows"]
            assert {row["id"] for row in rows} == expected, name
            assert len(rows) == len(expected), name
    finally:
        db.execute("REVERT")


def execute_upgrade(db):
    path = Path(__file__).resolve().parents[1] / "sql/migrations/20261117_five_logic_fixes.sql"
    # 此脚本只有一个有效批次；使用相同的GO拆分规则并消费后续错误。
    import re
    for batch in re.split(r"^GO\s*$", path.read_text(encoding="utf-8"), flags=re.M | re.I):
        if batch.strip():
            cursor = db.execute(batch)
            try:
                while cursor.nextset():
                    pass
            finally:
                cursor.close()


def test_existing_database_upgrade_is_idempotent(db):
    before = db.scalar("SELECT COUNT(*) FROM vital")
    execute_upgrade(db)
    execute_upgrade(db)
    assert db.scalar("SELECT COUNT(*) FROM vital") == before
    assert db.scalar(
        "SELECT COUNT(*) FROM sys.check_constraints WHERE name='CK_service_item_certificate_pair' "
        "AND is_disabled=0 AND is_not_trusted=0"
    ) == 1
    assert db.scalar("SELECT COUNT(*) FROM sys.tables") == 33


def test_upgrade_rejects_invalid_existing_certificate_pair(db):
    db.execute("ALTER TABLE service_item DROP CONSTRAINT CK_service_item_certificate_pair")
    db.execute("UPDATE service_item SET certificate_type=N'护理',certificate_level=NULL WHERE id=1")
    with pytest.raises(pyodbc.Error, match="51201"):
        execute_upgrade(db)


def test_upgrade_rejects_existing_cross_rule_duplicates(db):
    db.execute("DISABLE TRIGGER dbo.tr_vital_identity ON dbo.vital")
    rule1 = db.scalar("SELECT id FROM metric_rule WHERE community_id=1 AND metric='pulse'")
    rule2 = db.scalar("SELECT id FROM metric_rule WHERE community_id=2 AND metric='pulse'")
    collected = datetime.now().replace(microsecond=0) - timedelta(minutes=3)
    db.execute(
        "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(1,?,?,80),(1,?,?,80)",
        rule1, collected, rule2, collected,
    )
    with pytest.raises(pyodbc.Error, match="51202"):
        execute_upgrade(db)


@pytest.mark.parametrize("fail_after_result", [False, True])
def test_migration_runner_drains_errors_and_commits_atomically(monkeypatch, tmp_path, capsys, fail_after_result):
    from scripts import manage

    sql = tmp_path / "sql"
    (sql / "migrations").mkdir(parents=True)
    (sql / "01_schema.sql").write_text("SCHEMA", encoding="utf-8")
    (sql / "migrations/20261117.sql").write_text("PREFLIGHT", encoding="utf-8")
    (sql / "02_views.sql").write_text("VIEWS\nGO\nFUNCTIONS", encoding="utf-8")

    class Cursor:
        def __init__(self, statement):
            self.statement = statement
            self.description = [("id",)] if fail_after_result and statement == "PREFLIGHT" else None

        def __iter__(self):
            return iter([(99,)])

        def nextset(self):
            if self.description:
                raise pyodbc.Error("51201: invalid existing record")
            return False

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.statements = []
            self.commits = self.rollbacks = 0
            self.closed = False

        def execute(self, statement):
            self.statements.append(statement.strip())
            return Cursor(statement.strip())

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(manage, "ROOT", tmp_path)
    monkeypatch.setattr(manage, "connect", lambda: connection)
    if fail_after_result:
        with pytest.raises(pyodbc.Error, match="51201"):
            manage.migrate()
        assert '"id": 99' in capsys.readouterr().out
        assert connection.statements == ["PREFLIGHT"]
        assert (connection.commits, connection.rollbacks) == (0, 1)
    else:
        manage.migrate()
        assert connection.statements == ["PREFLIGHT", "VIEWS", "FUNCTIONS"]
        assert (connection.commits, connection.rollbacks) == (1, 0)
    assert connection.closed
