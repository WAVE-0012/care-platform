from datetime import datetime, timedelta

from care.security import BusinessError, check_elderly, check_order, require_role


def create(db, user, data):
    require_role(user, "admin", "community", "elderly", "family")
    elder = check_elderly(db, user, int(data["elderly_id"]))
    existing = db.one(
        "SELECT id,elderly_id,created_by FROM service_order WHERE request_key=?",
        data["request_key"],
    )
    if existing:
        if (
            existing["elderly_id"] != elder["id"]
            or existing["created_by"] != user["id"]
        ):
            raise BusinessError("请求编号已用于另一笔订单")
        return {"id": existing["id"]}
    scheduled = datetime.fromisoformat(data["scheduled_at"])
    if scheduled <= datetime.now():
        raise BusinessError("预约时间应晚于当前时间")
    item = db.one("SELECT * FROM service_item WHERE id=?", data["item_id"])
    if item is None:
        raise BusinessError("服务项目不存在")
    duration = (
        item["duration_minutes"]
        if item["unit"] == "visit"
        else int(data.get("duration_minutes", item["duration_minutes"]))
    )
    if not db.scalar(
        "SELECT COUNT(*) FROM community WHERE id=? AND dbo.fn_distance_m(?,?,longitude,latitude)<=radius_m",
        elder["community_id"],
        elder["longitude"],
        elder["latitude"],
    ):
        raise BusinessError("服务地址超出所属社区服务范围")
    status = (
        "pending"
        if db.scalar(
            "SELECT COUNT(*) FROM dbo.fn_eligibility(?,?,?)",
            elder["id"],
            item["id"],
            scheduled.date(),
        )
        else "ineligible"
    )
    order = db.insert(
        "INSERT service_order(request_key,elderly_id,item_id,community_id,created_by,scheduled_at,duration_minutes,address,longitude,latitude,unit_price,price_unit,channel,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        data["request_key"],
        elder["id"],
        item["id"],
        elder["community_id"],
        user["id"],
        scheduled,
        duration,
        elder["address"],
        elder["longitude"],
        elder["latitude"],
        item["price"],
        item["unit"],
        "家属端"
        if user["role"] in ["elderly", "family"]
        else data.get("channel", "社区代下单"),
        status,
    )
    db.audit("order", order, "create", user["id"], "保存预约地址与成交价格")
    return {"id": order, "status": status}


def dispatch(db, user, order_id, data):
    require_role(user, "admin", "community")
    check_order(db, user, order_id)
    return db.call(
        "sp_dispatch", order_id, data["shift_id"], user["id"], data.get("reason")
    )


def accept(db, user, order_id, data):
    require_role(user, "worker")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    assignment = db.one(
        "SELECT * FROM assignment WHERE order_id=? AND is_current=1", order_id
    )
    if order["status"] != "offered" or assignment["status"] != "offered":
        raise BusinessError("当前订单不在待接单状态")
    if assignment["assigned_at"] + timedelta(minutes=15) <= datetime.now():
        raise BusinessError("接单已超时，请由社区重新派单")
    if data.get("reject"):
        db.execute(
            "UPDATE assignment SET status='rejected',is_current=0,reason=? WHERE id=?",
            data.get("reason", "护工拒单"),
            assignment["id"],
        )
        db.execute("UPDATE service_order SET status='pending' WHERE id=?", order_id)
    else:
        db.execute(
            "UPDATE assignment SET status='accepted',accepted_at=GETDATE() WHERE id=?",
            assignment["id"],
        )
        db.execute("UPDATE service_order SET status='accepted' WHERE id=?", order_id)
    return {"id": order_id}


def cancel(db, user, order_id, data):
    require_role(user, "admin", "community", "elderly", "family")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    if order["status"] == "cancelled":
        return {"id": order_id}
    if order["status"] not in ["ineligible", "pending", "offered", "accepted"]:
        raise BusinessError("服务开始后须通过异常处理结束订单")
    reason = data.get("reason", "用户取消预约")
    db.execute(
        "UPDATE assignment SET status='invalid',is_current=0,reason=? WHERE order_id=? AND is_current=1",
        reason,
        order_id,
    )
    db.execute("UPDATE service_order SET status='cancelled' WHERE id=?", order_id)
    db.audit("order", order_id, "cancel", user["id"], reason)
    return {"id": order_id}


def reschedule(db, user, order_id, data):
    require_role(user, "admin", "community", "elderly", "family")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    if order["status"] not in ["ineligible", "pending", "offered", "accepted"]:
        raise BusinessError("当前状态不能改期")
    scheduled = datetime.fromisoformat(data["scheduled_at"])
    if scheduled <= datetime.now():
        raise BusinessError("预约时间应晚于当前时间")
    minutes = (
        order["duration_minutes"]
        if order["price_unit"] == "visit"
        else int(data.get("duration_minutes", order["duration_minutes"]))
    )
    db.execute(
        "UPDATE assignment SET status='invalid',is_current=0,reason=N'订单改期' WHERE order_id=? AND is_current=1",
        order_id,
    )
    status = (
        "pending"
        if db.scalar(
            "SELECT COUNT(*) FROM dbo.fn_eligibility(?,?,?)",
            order["elderly_id"],
            order["item_id"],
            scheduled.date(),
        )
        else "ineligible"
    )
    db.execute(
        "UPDATE service_order SET scheduled_at=?,duration_minutes=?,status=? WHERE id=?",
        scheduled,
        minutes,
        status,
        order_id,
    )
    db.audit("order", order_id, "reschedule", user["id"], f"预约时间调整为 {scheduled}")
    return {"id": order_id}


def confirm(db, user, order_id, data):
    require_role(user, "elderly", "family")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    if order["status"] not in ["confirming", "completed"]:
        raise BusinessError("服务签退后才能确认")
    if order["status"] == "completed":
        return {"id": order_id}
    assignment = db.one(
        "SELECT a.*,l.checkout_at FROM assignment a JOIN work_log l ON l.assignment_id=a.id WHERE a.order_id=? AND a.is_current=1",
        order_id,
    )
    if (
        not assignment["service_record"]
        or not assignment["checkout_at"]
        or assignment["checkout_at"] > datetime.now()
    ):
        raise BusinessError("请先核对已完成的服务记录")
    db.execute(
        "UPDATE assignment SET confirmed_by=?,confirmed_at=GETDATE() WHERE id=?",
        user["id"],
        assignment["id"],
    )
    # 异常工时尚待机构复核时保留确认，复核后由完成操作进行结算。
    if db.scalar(
        "SELECT COUNT(*) FROM work_log WHERE assignment_id=? AND review_status IN ('auto','approved') AND valid_hours>0",
        assignment["id"],
    ):
        db.call("sp_finish_order", order_id, user["id"])
    return {"id": order_id}


def feedback(db, user, order_id, data):
    require_role(user, "elderly", "family")
    db.one("SELECT id FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id)
    order = check_order(db, user, order_id)
    if order["status"] != "completed":
        raise BusinessError("完成服务后才能评价或投诉")

    def text_value(key):
        # 现有表单未回填旧文本：空白表示本次不修改，显式null才清空。
        if key not in data:
            return order[key]
        if data[key] is None:
            return None
        value = data[key].strip()
        return value if value else order[key]

    rating = data.get("rating", order["rating"])
    if rating == "":
        rating = order["rating"]
    content = text_value("feedback")
    complaint = text_value("complaint")
    result = order["complaint_result"] if complaint == order["complaint"] else None
    db.execute(
        "UPDATE service_order SET rating=?,feedback=?,complaint=?,complaint_result=? WHERE id=?",
        rating,
        content,
        complaint,
        result,
        order_id,
    )
    return {"id": order_id}


def resolve(db, user, order_id, data):
    require_role(user, "admin", "community")
    check_order(db, user, order_id)
    order = db.one(
        "SELECT * FROM service_order WITH(UPDLOCK,HOLDLOCK) WHERE id=?", order_id
    )
    reason = data["reason"].strip()
    action = data["action"]
    if not reason:
        raise BusinessError("请填写处理原因")
    if action == "complaint":
        db.execute(
            "UPDATE service_order SET complaint_result=? WHERE id=?", reason, order_id
        )
    elif action == "exception" and order["status"] in ["serving", "confirming"]:
        db.execute("UPDATE service_order SET status='exception' WHERE id=?", order_id)
    elif action == "resume" and order["status"] == "exception":
        log = db.one(
            "SELECT l.checkout_at FROM work_log l JOIN assignment a ON a.id=l.assignment_id "
            "WHERE a.order_id=? AND a.is_current=1",
            order_id,
        )
        if log is None:
            raise BusinessError("缺少服务工时记录，请先核实后再恢复")
        state = "serving" if log["checkout_at"] is None else "confirming"
        db.execute("UPDATE service_order SET status=? WHERE id=?", state, order_id)
    elif action == "terminate" and order["status"] == "exception":
        db.execute(
            "UPDATE assignment SET status='terminated',reason=? WHERE order_id=? AND is_current=1",
            reason,
            order_id,
        )
        db.execute("UPDATE service_order SET status='terminated' WHERE id=?", order_id)
    else:
        raise BusinessError("处理动作与订单状态不匹配")
    db.audit("order", order_id, action, user["id"], reason)
    return {"id": order_id}
