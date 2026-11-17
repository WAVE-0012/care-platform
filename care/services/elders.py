from datetime import date, datetime

from care.security import (
    BusinessError,
    check_community,
    check_elderly,
    encrypt,
    identity_digest,
    require_role,
)


def create(db, user, data):
    require_role(user, "admin", "community")
    community_id = int(data["community_id"])
    check_community(db, user, community_id)
    identity = data["identity"].strip().upper()
    if (
        len(identity) != 18
        or not identity[:17].isdigit()
        or identity[-1] not in "0123456789X"
    ):
        raise BusinessError("身份证号应为18位，末位可以是X")
    birth = date.fromisoformat(data["birth_date"])
    if birth > date.today():
        raise BusinessError("出生日期不能晚于今天")
    community = db.one("SELECT * FROM community WHERE id=?", community_id)
    phone = data["contact_phone"].strip()
    if not 7 <= len(phone) <= 20:
        raise BusinessError("请填写有效的联系人电话")
    elder_id = db.insert(
        "INSERT elderly(name,identity_cipher,identity_hash,identity_mask,birth_date,address,community_id,longitude,latitude,living_alone,disabled,low_income) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        data["name"].strip(),
        encrypt(identity),
        identity_digest(identity),
        identity[:3] + "***********" + identity[-4:],
        birth,
        data["address"].strip(),
        community_id,
        data.get("longitude", community["longitude"]),
        data.get("latitude", community["latitude"]),
        bool(data.get("living_alone")),
        bool(data.get("disabled")),
        bool(data.get("low_income")),
    )
    db.execute(
        "INSERT contact(elderly_id,name,relationship,phone_cipher,phone_mask,is_primary,guardian,authorized_from) VALUES(?,?,?,?,?,1,1,GETDATE())",
        elder_id,
        data["contact_name"].strip(),
        data.get("relationship", "子女"),
        encrypt(phone),
        phone[:3] + "****" + phone[-4:],
    )
    db.audit("elderly", elder_id, "create", user["id"], "建立档案及主联系人")
    return {"id": elder_id}


def update(db, user, elder_id, data):
    require_role(user, "admin", "community")
    elder = check_elderly(db, user, elder_id)
    community_id = int(data.get("community_id", elder["community_id"]))
    # 迁入社区必须存在；当前社区管理员负责移交，历史订单保留原归属。
    community = db.one("SELECT * FROM community WHERE id=?", community_id)
    if community is None:
        raise BusinessError("请选择有效社区")
    db.execute(
        "UPDATE elderly SET address=?,community_id=?,longitude=?,latitude=?,living_alone=?,disabled=?,low_income=? WHERE id=?",
        data.get("address", elder["address"]),
        community_id,
        data.get("longitude", community["longitude"]),
        data.get("latitude", community["latitude"]),
        data.get("living_alone", elder["living_alone"]),
        data.get("disabled", elder["disabled"]),
        data.get("low_income", elder["low_income"]),
        elder_id,
    )
    db.audit(
        "elderly",
        elder_id,
        "update",
        user["id"],
        f'社区 {elder["community_id"]} → {community_id}；{data.get("reason","更新档案")}',
    )
    return {"id": elder_id}


def assess(db, user, elder_id, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, elder_id)
    assessed_on = date.fromisoformat(data["assessed_on"])
    if assessed_on > date.today():
        raise BusinessError("评估日期不能晚于今天")
    assessment_id = db.insert(
        "INSERT assessment(elderly_id,scale,score,ability_level,assessor_id,assessed_on,valid_until) VALUES(?,?,?,?,?,?,?)",
        elder_id,
        data["scale"],
        data["score"],
        data["ability_level"],
        user["id"],
        assessed_on,
        data["valid_until"],
    )
    db.execute(
        "UPDATE p SET status='paused' FROM care_plan p JOIN service_package k ON k.id=p.package_id WHERE p.elderly_id=? AND p.status='active' AND k.ability_level<>?",
        elder_id,
        data["ability_level"],
    )
    db.call("sp_expire_services")
    db.audit("assessment", assessment_id, "create", user["id"], "完成能力评估")
    return {"id": assessment_id}


def plan(db, user, elder_id, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, elder_id)
    return db.call(
        "sp_create_plan",
        elder_id,
        data["package_id"],
        data["worker_id"],
        data["starts_on"],
        data["ends_on"],
    )


def authorize(db, user, elder_id, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, elder_id)
    if data.get("revoke"):
        db.execute(
            "UPDATE contact SET authorized_until=GETDATE() WHERE id=? AND elderly_id=?",
            data["contact_id"],
            elder_id,
        )
    else:
        account = db.one(
            "SELECT id FROM app_user WHERE id=? AND role='family' AND active=1",
            data["user_id"],
        )
        if not account:
            raise BusinessError("请选择有效家属账号")
        db.execute(
            "UPDATE contact SET user_id=?,authorized_from=GETDATE(),authorized_until=NULL WHERE id=? AND elderly_id=?",
            data["user_id"],
            data["contact_id"],
            elder_id,
        )
    db.audit("elderly", elder_id, "authorize", user["id"], "更新家属授权")
    return {"id": elder_id}


def plan_state(db, user, elder_id, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, elder_id)
    db.one("SELECT id FROM elderly WITH(UPDLOCK,HOLDLOCK) WHERE id=?", elder_id)
    state = data["status"]
    if state not in ["active", "paused", "ended"]:
        raise BusinessError("请选择生效、暂停或结束")
    plan = db.one(
        "SELECT p.*,k.ability_level FROM care_plan p JOIN service_package k ON k.id=p.package_id WHERE p.id=? AND p.elderly_id=?",
        data["plan_id"],
        elder_id,
    )
    if plan is None:
        raise BusinessError("照护计划不属于该老人")
    if state == "active":
        assessment = db.one(
            "SELECT TOP 1 * FROM assessment WHERE elderly_id=? AND assessed_on<=CAST(GETDATE() AS date) ORDER BY assessed_on DESC",
            elder_id,
        )
        if (
            not assessment
            or assessment["valid_until"] < date.today()
            or assessment["ability_level"] != plan["ability_level"]
        ):
            raise BusinessError("恢复计划需要有效且等级匹配的评估")
    db.execute("UPDATE care_plan SET status=? WHERE id=?", state, plan["id"])
    db.call("sp_expire_services")
    db.audit("plan", plan["id"], "status", user["id"], f"计划调整为 {state}")
    return {"id": plan["id"]}
