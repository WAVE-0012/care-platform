from care.security import (
    BusinessError,
    check_order,
    check_worker_area,
    require_role,
)


def claim(db, user, data):
    require_role(user, "admin", "community")
    elderly_id = int(data["elderly_id"])
    # 首次提交按老人当前社区，已有申报按首次申报社区，由过程统一判断。
    return db.call(
        "sp_claim_month",
        elderly_id,
        data["item_id"],
        data["month"],
        user["id"],
        data["evidence"],
    )


def review(db, user, claim_id, data):
    require_role(user, "street", "civil")
    return db.call(
        "sp_review_claim", claim_id, user["id"], data["decision"], data["note"]
    )


def pay(db, user, claim_id, data):
    require_role(user, "civil")
    return db.call("sp_pay_claim", claim_id, user["id"], data["reference"])


def quality(db, user, data):
    require_role(user, "street", "civil")
    order_id = data.get("order_id")
    worker_id = data.get("worker_id")
    if order_id:
        order = check_order(db, user, int(order_id))
        if order["status"] != "completed":
            raise BusinessError("订单抽查应选择已完成服务")
    elif worker_id:
        check_worker_area(db, user, int(worker_id))
    else:
        raise BusinessError("请选择订单或护工作为抽查对象")
    issue = data.get("issue", "").strip() or None
    check_id = db.insert(
        "INSERT quality_check(order_id,worker_id,inspector_id,method,score,issue,requirement,restrict_agency,restricted_item_id,due_on,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        order_id,
        worker_id,
        user["id"],
        data["method"],
        data["score"],
        issue,
        data.get("requirement") or None,
        bool(data.get("restrict_agency")),
        data.get("restricted_item_id"),
        data.get("due_on") or None,
        "open" if issue else "clear",
    )
    if issue:
        # 受限护工尚未开始的任务回到调度池，进行中的任务由社区处理。
        released = db.all(
            "SELECT a.id,a.order_id FROM assignment a JOIN shift s ON s.id=a.shift_id JOIN worker w ON w.id=s.worker_id JOIN service_order o ON o.id=a.order_id JOIN v_quality_restrictions q ON q.id=? AND ((q.restrict_agency=0 AND q.worker_id=w.id) OR (q.restrict_agency=1 AND q.agency_id=w.agency_id)) AND (q.restricted_item_id IS NULL OR q.restricted_item_id=o.item_id) WHERE a.is_current=1 AND o.status IN ('offered','accepted')",
            check_id,
        )
        for row in released:
            db.execute(
                "UPDATE assignment SET status='invalid',is_current=0,reason=N'质量整改限制' WHERE id=?",
                row["id"],
            )
            db.execute(
                "UPDATE service_order SET status='pending' WHERE id=?", row["order_id"]
            )
    db.audit("quality", check_id, "inspect", user["id"], issue or "服务符合要求")
    return {"id": check_id}


def rectify(db, user, check_id, data):
    check = db.one(
        "SELECT q.*,w.agency_id,COALESCE(q.worker_id,s.worker_id) target_worker FROM quality_check q WITH(UPDLOCK,HOLDLOCK) LEFT JOIN assignment a ON a.order_id=q.order_id AND a.is_current=1 LEFT JOIN shift s ON s.id=a.shift_id JOIN worker w ON w.id=COALESCE(q.worker_id,s.worker_id) WHERE q.id=?",
        check_id,
    )
    if check is None:
        raise BusinessError("抽查记录不存在")
    if data["action"] == "submit":
        require_role(user, "agency")
        if user["agency_id"] != check["agency_id"]:
            raise PermissionError("仅所属机构可提交整改结果")
        if check["status"] != "open" or not data.get("result", "").strip():
            raise BusinessError("请为待整改记录填写整改结果")
        db.execute(
            "UPDATE quality_check SET status='review',result=? WHERE id=?",
            data["result"].strip(),
            check_id,
        )
    elif data["action"] == "approve":
        require_role(user, "street", "civil")
        if check["order_id"]:
            check_order(db, user, check["order_id"])
        else:
            check_worker_area(db, user, check["target_worker"])
        if check["status"] != "review":
            raise BusinessError("机构提交整改后才能复核")
        db.execute(
            "UPDATE quality_check SET status='resolved',reviewer_id=? WHERE id=?",
            user["id"],
            check_id,
        )
    else:
        raise BusinessError("请选择提交整改或复核通过")
    db.audit(
        "quality", check_id, data["action"], user["id"], data.get("result", "监管复核通过")
    )
    return {"id": check_id}


def policy(db, user, data):
    require_role(user, "civil")
    policy_id = db.insert(
        "INSERT subsidy_policy(name,district_id,item_id,ability_level,low_income_only,rate,starts_on,ends_on) VALUES(?,?,?,?,?,?,?,?)",
        data["name"],
        user["area_id"],
        data["item_id"],
        data["ability_level"],
        bool(data.get("low_income_only")),
        data["rate"],
        data["starts_on"],
        data["ends_on"],
    )
    db.audit("policy", policy_id, "create", user["id"], "发布新的补贴政策版本")
    return {"id": policy_id}
