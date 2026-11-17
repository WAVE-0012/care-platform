"""后端七项功能修复；沿用独立测试库fixture，不操作演示库。"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pyodbc
import pytest

from care import queries
from care.security import BusinessError
from care.services import elders, health, orders, subsidy, workforce
from tests.conftest import login
from tests.test_database import actor, completed_order, new_shift


def service_order(db, serving=False):
    order, assignment, shift = completed_order(db)
    if serving:
        db.execute("UPDATE assignment SET confirmed_by=NULL,confirmed_at=NULL WHERE id=?", assignment)
        db.execute(
            "UPDATE work_log SET checkout_at=NULL,valid_hours=NULL,review_status='pending' WHERE assignment_id=?",
            assignment,
        )
        db.execute("UPDATE service_order SET status='serving' WHERE id=?", order)
    return order, assignment, shift


@pytest.mark.parametrize("signed_out,expected", [(False, "serving"), (True, "confirming")])
def test_exception_resume_restores_matching_service_state(db, signed_out, expected):
    order, assignment, _ = service_order(db, serving=not signed_out)
    original_checkout = db.scalar("SELECT checkout_at FROM work_log WHERE assignment_id=?", assignment)
    orders.resolve(db, actor(db), order, {"action": "exception", "reason": "服务中断核实"})
    orders.resolve(db, actor(db), order, {"action": "resume", "reason": "已核实继续办理"})
    assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == expected
    assert db.scalar("SELECT checkout_at FROM work_log WHERE assignment_id=?", assignment) == original_checkout
    if not signed_out:
        target = db.one("SELECT longitude,latitude FROM service_order WHERE id=?", order)
        workforce.checkout(db, actor(db, "worker01"), order, {**target, "service_record": "恢复服务后完成签退"})
        assert db.scalar("SELECT status FROM service_order WHERE id=?", order) == "confirming"
        assert db.scalar("SELECT checkout_at FROM work_log WHERE assignment_id=?", assignment) is not None


def accepted_order_today(db):
    elder = db.one("SELECT * FROM elderly WHERE id=1")
    order = db.insert(
        "INSERT service_order(request_key,elderly_id,item_id,community_id,created_by,scheduled_at,duration_minutes,"
        "address,longitude,latitude,unit_price,price_unit,channel) VALUES(?,1,3,?,?,?,60,?,?,?,60,'hour',N'社区代下单')",
        uuid4().hex, elder["community_id"], actor(db)["id"], datetime.combine(date.today(), time(10)),
        elder["address"], elder["longitude"], elder["latitude"],
    )
    shift = new_shift(db, days=0)
    db.call("sp_dispatch", order, shift, actor(db)["id"])
    orders.accept(db, actor(db, "worker01"), order, {})
    return order, {"longitude": elder["longitude"], "latitude": elder["latitude"]}


def test_terminated_unsigned_log_does_not_block_next_checkin(db):
    old, assignment, shift = service_order(db, serving=True)
    orders.resolve(db, actor(db), old, {"action": "exception", "reason": "实际服务中断"})
    orders.resolve(db, actor(db), old, {"action": "terminate", "reason": "核实后终止，不予结算"})
    assert db.scalar("SELECT checkout_at FROM work_log WHERE assignment_id=?", assignment) is None
    assert db.scalar("SELECT valid_hours FROM work_log WHERE assignment_id=?", assignment) is None
    assert db.scalar("SELECT settlement FROM service_order WHERE id=?", old) is None
    assert db.scalar("SELECT used_slots FROM shift WHERE id=?", shift) == 1
    new, position = accepted_order_today(db)
    workforce.checkin(db, actor(db, "worker01"), new, position)
    assert db.scalar("SELECT status FROM service_order WHERE id=?", new) == "serving"


def test_unfinished_exception_still_blocks_next_checkin(db):
    old, _, _ = service_order(db, serving=True)
    orders.resolve(db, actor(db), old, {"action": "exception", "reason": "仍未结束的服务"})
    new, position = accepted_order_today(db)
    with pytest.raises(BusinessError, match="尚未签退"):
        workforce.checkin(db, actor(db, "worker01"), new, position)


def test_tag_only_update_preserves_coordinates(db):
    db.execute("UPDATE elderly SET longitude=116.333,latitude=40.012 WHERE id=1")
    elders.update(db, actor(db), 1, {"low_income": True})
    row = db.one("SELECT longitude,latitude,low_income FROM elderly WHERE id=1")
    assert (row["longitude"], row["latitude"]) == (Decimal("116.333"), Decimal("40.012"))
    assert row["low_income"]


def test_explicit_coordinates_can_be_updated(db):
    elders.update(db, actor(db), 1, {"address": "核实后新住址", "longitude": "116.334", "latitude": "40.013"})
    row = db.one("SELECT longitude,latitude FROM elderly WHERE id=1")
    assert (row["longitude"], row["latitude"]) == (Decimal("116.334"), Decimal("40.013"))


@pytest.mark.parametrize("raw,stored", [("80.251", "80.25"), ("80.255", "80.26"), ("-1.235", "-1.24")])
def test_vital_save_and_reupload_use_identical_precision(db, raw, stored):
    record = {"device_id": 1, "metric": "pulse", "value": raw,
              "collected_at": (datetime.now().replace(microsecond=0) - timedelta(minutes=3)).isoformat()}
    first = health.upload(db, actor(db), [record])["ids"]
    assert db.scalar("SELECT value FROM vital WHERE id=?", first[0]) == Decimal(stored)
    assert health.upload(db, actor(db), [record])["ids"] == first
    record["value"] = str(Decimal(stored) + Decimal("0.01"))
    with pytest.raises(BusinessError, match="不同数值"):
        health.upload(db, actor(db), [record])


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "not-a-number", "1000000"])
def test_invalid_vital_values_rejected_before_writing(db, raw):
    before = db.scalar("SELECT COUNT(*) FROM vital")
    with pytest.raises(BusinessError, match="指标值"):
        health.upload(db, actor(db), [{"device_id": 1, "metric": "pulse", "value": raw,
                                     "collected_at": datetime.now().isoformat()}])
    assert db.scalar("SELECT COUNT(*) FROM vital") == before


def reviewed_order(db):
    order, _, _ = completed_order(db)
    db.call("sp_finish_order", order)
    db.execute(
        "UPDATE service_order SET rating=4,feedback=N'原服务评价',complaint=N'原投诉',complaint_result=N'原处理结果' WHERE id=?",
        order,
    )
    return order


@pytest.mark.parametrize("data", [{"rating": 3}, {"rating": 3, "feedback": "", "complaint": "  "}])
def test_feedback_update_preserves_other_content(db, data):
    order = reviewed_order(db)
    orders.feedback(db, actor(db, "family01"), order, data)
    row = db.one("SELECT rating,feedback,complaint,complaint_result FROM service_order WHERE id=?", order)
    assert row == {"rating": 3, "feedback": "原服务评价", "complaint": "原投诉", "complaint_result": "原处理结果"}


def test_explicit_null_clears_feedback_and_complaint(db):
    order = reviewed_order(db)
    orders.feedback(db, actor(db, "family01"), order, {"feedback": None, "complaint": None})
    row = db.one("SELECT rating,feedback,complaint,complaint_result FROM service_order WHERE id=?", order)
    assert row == {"rating": 4, "feedback": None, "complaint": None, "complaint_result": None}


def test_new_complaint_does_not_reuse_old_resolution(db):
    order = reviewed_order(db)
    orders.feedback(db, actor(db, "family01"), order, {"complaint": "重新反馈的问题"})
    row = db.one("SELECT rating,feedback,complaint,complaint_result FROM service_order WHERE id=?", order)
    assert row == {"rating": 4, "feedback": "原服务评价", "complaint": "重新反馈的问题", "complaint_result": None}


def worker_check_data():
    return {"worker_id": 1, "method": "上门核查", "score": 2, "issue": "记录缺项",
            "requirement": "补齐并说明", "due_on": date.today() + timedelta(days=7)}


def test_cross_area_worker_check_can_be_created_and_reviewed_in_scope(db):
    db.execute("INSERT worker_area(worker_id,community_id) VALUES(1,2)")
    check = subsidy.quality(db, actor(db, "street01"), worker_check_data())["id"]
    for username in ("street01", "street02"):
        assert check in {row["id"] for row in queries.listing(db, actor(db, username), "quality")["rows"]}
    subsidy.rectify(db, actor(db, "agency01"), check, {"action": "submit", "result": "完成补录"})
    subsidy.rectify(db, actor(db, "street02"), check, {"action": "approve"})
    assert db.scalar("SELECT status FROM quality_check WHERE id=?", check) == "resolved"


def test_worker_check_outside_all_service_areas_is_rejected(db):
    db.execute("INSERT worker_area(worker_id,community_id) VALUES(1,2)")
    with pytest.raises(PermissionError):
        subsidy.quality(db, actor(db, "street03"), worker_check_data())
    check = subsidy.quality(db, actor(db, "street01"), worker_check_data())["id"]
    subsidy.rectify(db, actor(db, "agency01"), check, {"action": "submit", "result": "完成补录"})
    with pytest.raises(PermissionError):
        subsidy.rectify(db, actor(db, "street03"), check, {"action": "approve"})
    assert db.scalar("SELECT status FROM quality_check WHERE id=?", check) == "review"


def test_order_check_still_uses_order_community(db):
    db.execute("INSERT worker_area(worker_id,community_id) VALUES(1,2)")
    order, _, _ = completed_order(db)
    db.call("sp_finish_order", order)
    with pytest.raises(PermissionError):
        subsidy.quality(db, actor(db, "street02"), {"order_id": order, "method": "上门核查", "score": 4})


def claim_data():
    month = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    return {"elderly_id": 21, "item_id": 1, "month": month, "evidence": "订单记录和资格材料"}


def migrated_returned_claim(db):
    data = claim_data()
    claim = subsidy.claim(db, actor(db, "community01"), data)["id"]
    db.call("sp_review_claim", claim, actor(db, "street01")["id"], "approve", "初审通过")
    db.call("sp_review_claim", claim, actor(db, "civil01")["id"], "return", "补充材料")
    elders.update(db, actor(db), 21, {"community_id": 2, "reason": "申报后迁移"})
    return claim, data


def test_original_community_can_resubmit_after_migration(db):
    claim, data = migrated_returned_claim(db)
    result = subsidy.claim(db, actor(db, "community01"), {**data, "evidence": "已补齐材料"})
    assert result["id"] == claim
    row = db.one("SELECT community_id,status,submitted_by,evidence FROM subsidy_claim WHERE id=?", claim)
    assert row == {"community_id": 1, "status": "street", "submitted_by": actor(db, "community01")["id"],
                   "evidence": "已补齐材料"}


@pytest.mark.parametrize("entry", ["service", "procedure"])
def test_new_community_cannot_resubmit_original_claim(db, entry):
    _, data = migrated_returned_claim(db)
    with pytest.raises(pyodbc.Error, match="51025"):
        if entry == "service":
            subsidy.claim(db, actor(db, "community02"), data)
        else:
            db.call("sp_claim_month", data["elderly_id"], data["item_id"], data["month"],
                    actor(db, "community02")["id"], data["evidence"])


def test_first_submission_uses_current_community(db):
    elders.update(db, actor(db), 21, {"community_id": 2})
    claim = subsidy.claim(db, actor(db, "community02"), claim_data())["id"]
    assert db.scalar("SELECT community_id FROM subsidy_claim WHERE id=?", claim) == 2


def test_previous_community_cannot_create_new_claim_after_migration(db):
    elders.update(db, actor(db), 21, {"community_id": 2})
    with pytest.raises(pyodbc.Error, match="51025"):
        subsidy.claim(db, actor(db, "community01"), claim_data())


def test_claim_scope_failure_is_http_forbidden(client):
    headers = login(client, "community02")
    data = claim_data()
    data.update(elderly_id=1, month=data["month"].isoformat())
    response = client.post("/api/claims", json=data, headers=headers)
    assert response.status_code == 403, response.json
