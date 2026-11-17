from datetime import datetime

from care.security import BusinessError, check_order, require_role, password_hash


def check_worker(db, user, worker_id):
    worker = db.one("SELECT * FROM worker WHERE id=?", worker_id)
    if worker is None or (
        user["role"] != "admin" and worker["agency_id"] != user["agency_id"]
    ):
        raise PermissionError("该护工不属于当前机构")
    return worker


def publish_shift(db, user, data):
    require_role(user, "admin", "agency")
    check_worker(db, user, int(data["worker_id"]))
    return db.call(
        "sp_publish_shift",
        data["worker_id"],
        datetime.fromisoformat(data["starts_at"]),
        datetime.fromisoformat(data["ends_at"]),
        data["capacity"],
    )


def certificate(db, user, data):
    require_role(user, "admin", "agency")
    check_worker(db, user, int(data["worker_id"]))
    return {
        "id": db.insert(
            "INSERT certificate(worker_id,certificate_type,level,number,issued_on,valid_until) VALUES(?,?,?,?,?,?)",
            data["worker_id"],
            data["certificate_type"],
            data["level"],
            data["number"],
            data["issued_on"],
            data["valid_until"],
        )
    }


def checkin(db, user, order_id, data):
    require_role(user, "worker")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    if order["status"] != "accepted":
        raise BusinessError("护工接单后才能签到")
    assignment = db.one(
        "SELECT a.*,s.worker_id,s.starts_at,s.ends_at FROM assignment a JOIN shift s ON s.id=a.shift_id WHERE a.order_id=? AND a.is_current=1",
        order_id,
    )
    db.one(
        "SELECT id FROM worker WITH(UPDLOCK,HOLDLOCK) WHERE id=?",
        assignment["worker_id"],
    )
    if db.scalar(
        "SELECT COUNT(*) FROM work_log l JOIN assignment a ON a.id=l.assignment_id JOIN shift s ON s.id=a.shift_id WHERE s.worker_id=? AND l.checkout_at IS NULL",
        assignment["worker_id"],
    ):
        raise BusinessError("上一项服务尚未签退")
    now = datetime.now().replace(microsecond=0)
    if now.date() != order["scheduled_at"].date():
        raise BusinessError("请在预约当天签到")
    eligibility = db.one(
        "SELECT * FROM dbo.fn_eligibility(?,?,?)",
        order["elderly_id"],
        order["item_id"],
        order["scheduled_at"].date(),
    )
    if not eligibility:
        raise BusinessError("评估或照护计划需要更新")
    # 当日签入也复核资质、整改和服务区域；当前任务不计为自己的时间冲突。
    if not db.scalar(
        "SELECT COUNT(*) FROM dbo.fn_candidates(?) WHERE shift_id=?",
        order_id,
        assignment["shift_id"],
    ):
        raise BusinessError("护工资质、排班或整改状态已变化，请联系社区改派")
    geofence = db.scalar(
        "SELECT CASE WHEN dbo.fn_distance_m(?,?,?,?)<=checkin_radius_m THEN 1 ELSE 0 END FROM community WHERE id=?",
        data["longitude"],
        data["latitude"],
        order["longitude"],
        order["latitude"],
        order["community_id"],
    )
    log = db.insert(
        "INSERT work_log(assignment_id,checkin_at,longitude,latitude,geofence_ok) VALUES(?,?,?,?,?)",
        assignment["id"],
        now,
        data["longitude"],
        data["latitude"],
        geofence,
    )
    db.execute(
        "INSERT eligibility_snapshot(order_id,assessment_id,plan_id,low_income,checked_by) VALUES(?,?,?,?,?)",
        order_id,
        eligibility["assessment_id"],
        eligibility["plan_id"],
        eligibility["low_income"],
        user["id"],
    )
    db.execute("UPDATE service_order SET status='serving' WHERE id=?", order_id)
    return {"id": log, "geofence_ok": bool(geofence)}


def checkout(db, user, order_id, data):
    require_role(user, "worker")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    if order["status"] != "serving":
        raise BusinessError("签到开始服务后才能签退")
    if not data["service_record"].strip():
        raise BusinessError("请填写实际服务内容")
    log = db.one(
        "SELECT l.*,s.starts_at,s.ends_at FROM work_log l JOIN assignment a ON a.id=l.assignment_id JOIN shift s ON s.id=a.shift_id WHERE a.order_id=? AND a.is_current=1",
        order_id,
    )
    now = datetime.now().replace(microsecond=0)
    minutes = (now - log["checkin_at"]).total_seconds() / 60
    if minutes < 1:
        raise BusinessError("服务至少持续1分钟后签退")
    distance = db.scalar(
        "SELECT dbo.fn_distance_m(?,?,?,?)",
        data["longitude"],
        data["latitude"],
        order["longitude"],
        order["latitude"],
    )
    radius = db.scalar(
        "SELECT checkin_radius_m FROM community WHERE id=?", order["community_id"]
    )
    scheduled_end = db.scalar(
        "SELECT DATEADD(minute,duration_minutes,scheduled_at) FROM service_order WHERE id=?",
        order_id,
    )
    normal = (
        log["geofence_ok"]
        and distance <= radius
        and log["checkin_at"] >= max(log["starts_at"], order["scheduled_at"])
        and now <= min(log["ends_at"], scheduled_end)
    )
    db.execute(
        "UPDATE work_log SET checkout_at=?,valid_hours=?,review_status=? WHERE id=?",
        now,
        round(minutes / 60, 2) if normal else None,
        "auto" if normal else "pending",
        log["id"],
    )
    db.execute(
        "UPDATE assignment SET service_record=?,confirmed_by=NULL,confirmed_at=NULL WHERE id=?",
        data["service_record"].strip(),
        log["assignment_id"],
    )
    db.execute("UPDATE service_order SET status='confirming' WHERE id=?", order_id)
    return {"id": order_id, "review_status": "auto" if normal else "pending"}


def review(db, user, log_id, data):
    require_role(user, "admin", "agency")
    db.call("sp_review_hours", log_id, user["id"], data["hours"], data["note"])
    db.audit("work_log", log_id, "review", user["id"], data["note"])
    return {"id": log_id}


def create(db, user, data):
    require_role(user, "admin", "agency")
    agency_id = (
        user["agency_id"] if user["role"] == "agency" else int(data["agency_id"])
    )
    if len(data["password"]) < 8:
        raise BusinessError("账号密码至少8位")
    account = db.insert(
        "INSERT app_user(username,display_name,password_hash,role) VALUES(?,?,?,'worker')",
        data["username"],
        data["name"],
        password_hash(data["password"]),
    )
    worker = db.insert(
        "INSERT worker(name,agency_id,user_id,trained_on) VALUES(?,?,?,?)",
        data["name"],
        agency_id,
        account,
        data.get("trained_on") or None,
    )
    db.batch(
        "INSERT worker_skill VALUES(?,?)",
        [(worker, int(item)) for item in data["item_ids"]],
    )
    db.batch(
        "INSERT worker_area VALUES(?,?)",
        [(worker, int(area)) for area in data["community_ids"]],
    )
    db.audit("worker", worker, "create", user["id"], "登记护工账号、服务项目和服务区域")
    return {"id": worker}


def update(db, user, worker_id, data):
    require_role(user, "admin", "agency")
    check_worker(db, user, worker_id)
    worker = db.one("SELECT * FROM worker WITH(UPDLOCK,HOLDLOCK) WHERE id=?", worker_id)
    status = data.get("status", worker["status"])
    db.execute(
        "UPDATE worker SET status=?,trained_on=? WHERE id=?",
        status,
        data.get("trained_on", worker["trained_on"]),
        worker_id,
    )
    if status != "active":
        pending = db.all(
            "SELECT a.id,a.order_id FROM assignment a JOIN shift s ON s.id=a.shift_id JOIN service_order o ON o.id=a.order_id WHERE s.worker_id=? AND a.is_current=1 AND o.status IN ('offered','accepted')",
            worker_id,
        )
        for row in pending:
            db.execute(
                "UPDATE assignment SET status='invalid',is_current=0,reason=N'护工在岗状态变更' WHERE id=?",
                row["id"],
            )
            db.execute(
                "UPDATE service_order SET status='pending' WHERE id=?", row["order_id"]
            )
    db.audit("worker", worker_id, "update", user["id"], f"在岗状态 {status}")
    return {"id": worker_id}
