from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from care.security import BusinessError, check_community, check_elderly, require_role


def bind(db, user, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, int(data["elderly_id"]))
    current = db.one(
        "SELECT elderly_id FROM device_binding WHERE device_id=? AND unbound_at IS NULL",
        data["device_id"],
    )
    if current:
        check_elderly(db, user, current["elderly_id"])
    return db.call(
        "sp_bind_device",
        data["device_id"],
        data["elderly_id"],
        user["id"],
        datetime.fromisoformat(data["bound_at"]),
    )


def upload(db, user, records):
    require_role(user, "admin", "community")
    if not 1 <= len(records) <= 500:
        raise BusinessError("每次上传1至500条体征记录")
    ids = []
    for data in records:
        try:
            value = Decimal(str(data["value"]))
            if not value.is_finite():
                raise InvalidOperation
            value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if abs(value) > Decimal("999999.99"):
                raise InvalidOperation
        except InvalidOperation:
            raise BusinessError("指标值须为有效数字，按两位小数保存且不能超出数据库范围") from None
        collected = datetime.fromisoformat(data["collected_at"])
        if collected > datetime.now():
            raise BusinessError("采集时间不能晚于当前时间")
        db.one(
            "SELECT id FROM device WITH(UPDLOCK,HOLDLOCK) WHERE id=?", data["device_id"]
        )
        binding = db.one(
            "SELECT b.*,e.community_id FROM device_binding b JOIN elderly e ON e.id=b.elderly_id WHERE b.device_id=? AND b.bound_at<=? AND (b.unbound_at IS NULL OR b.unbound_at>?)",
            data["device_id"],
            collected,
            collected,
        )
        if not binding:
            raise BusinessError("设备在该采集时间没有绑定老人")
        check_elderly(db, user, binding["elderly_id"])
        # 先按采集业务身份查历史记录，迁移后的新规则不能改变重传身份。
        existing = db.one(
            "SELECT v.id,v.value FROM vital v JOIN device_binding b ON b.id=v.binding_id "
            "JOIN metric_rule r ON r.id=v.rule_id WHERE b.device_id=? AND v.collected_at=? AND r.metric=?",
            data["device_id"],
            collected,
            data["metric"],
        )
        if existing:
            if existing["value"] != value:
                raise BusinessError("同一采集记录已存在不同数值，请核对设备数据")
            ids.append(existing["id"])
        else:
            rule = db.one(
                "SELECT * FROM metric_rule WHERE community_id=? AND metric=?",
                binding["community_id"],
                data["metric"],
            )
            if rule is None:
                raise BusinessError("该社区未配置此指标")
            ids.append(
                db.insert(
                    "INSERT vital(binding_id,rule_id,collected_at,value,source) VALUES(?,?,?,?,?)",
                    binding["id"],
                    rule["id"],
                    collected,
                    value,
                    "模拟设备",
                )
            )
    return {"ids": ids}


def create_event(db, user, data):
    require_role(user, "admin", "community", "family", "elderly", "worker")
    elder = check_elderly(db, user, int(data["elderly_id"]))
    db.one("SELECT id FROM elderly WITH(UPDLOCK,HOLDLOCK) WHERE id=?", elder["id"])
    existing = db.one(
        "SELECT id,elderly_id FROM emergency WHERE request_key=?", data["request_key"]
    )
    if existing:
        if existing["elderly_id"] != elder["id"]:
            raise BusinessError("请求编号已用于其他事件")
        return {"id": existing["id"]}
    vital_id = data.get("vital_id")
    if vital_id:
        vital = db.one(
            "SELECT v.*,b.elderly_id FROM vital v JOIN device_binding b ON b.id=v.binding_id WHERE v.id=?",
            vital_id,
        )
        if vital is None or vital["elderly_id"] != elder["id"] or not vital["abnormal"]:
            raise BusinessError("应关联该老人的异常体征")
        existing = db.one("SELECT id FROM emergency WHERE vital_id=?", vital_id)
        if existing:
            return existing
    level = int(data["level"])
    limits = {1: (15, 45), 2: (10, 30), 3: (5, 15)}
    if level not in limits:
        raise BusinessError("事件等级为1至3级")
    response, arrival = limits[level]
    event = db.insert(
        "INSERT emergency(request_key,elderly_id,community_id,vital_id,source,level,occurred_at,response_minutes,arrival_minutes) VALUES(?,?,?,?,?,?,GETDATE(),?,?)",
        data["request_key"],
        elder["id"],
        elder["community_id"],
        vital_id,
        "设备告警" if vital_id else "主动上报",
        level,
        response,
        arrival,
    )
    if vital_id:
        db.execute("UPDATE vital SET confirmation='confirmed' WHERE id=?", vital_id)
    contacts = db.all(
        "SELECT id,name FROM contact WHERE elderly_id=? AND is_primary=1 AND active=1",
        elder["id"],
    )
    recipients = [f'联系人 {c["id"]} {c["name"]}' for c in contacts] + ["责任护工", "社区值班岗"]
    db.batch(
        "INSERT notification(event_id,recipient,stage) VALUES(?,?,'created')",
        [(event, r) for r in recipients],
    )
    db.audit(
        "emergency", event, "create", user["id"], data.get("description", "收到紧急求助")
    )
    return {"id": event}


def process_event(db, user, event_id, data):
    require_role(user, "admin", "community", "street", "civil")
    event = db.one(
        "SELECT * FROM emergency WITH(UPDLOCK,HOLDLOCK) WHERE id=?", event_id
    )
    if not event:
        raise BusinessError("应急事件不存在")
    check_community(db, user, event["community_id"])
    if event["status"] == "closed":
        raise BusinessError("事件已关闭")
    action = data["action"]
    if action == "respond" and event["responded_at"] is None:
        db.execute(
            "UPDATE emergency SET status='handling',responder_id=?,responded_at=GETDATE() WHERE id=?",
            user["id"],
            event_id,
        )
    elif action == "arrive" and event["responded_at"] and not event["arrived_at"]:
        db.execute("UPDATE emergency SET arrived_at=GETDATE() WHERE id=?", event_id)
    elif action == "close" and data.get("result", "").strip():
        db.execute(
            "UPDATE emergency SET status='closed',result=?,closed_at=GETDATE() WHERE id=?",
            data["result"].strip(),
            event_id,
        )
    else:
        raise BusinessError("请依次记录响应和到场，关闭时填写处置结果")
    db.audit("emergency", event_id, action, user["id"], data.get("result", "记录处置进展"))
    return {"id": event_id}


def send_notifications(db, fail=False):
    # 课设消息接口：记录模拟发送结果，保留独立通知表以便接入短信服务。
    return db.execute(
        "UPDATE notification SET attempts=attempts+1,last_attempt_at=GETDATE(),status=CASE WHEN ?=0 THEN 'sent' WHEN attempts+1>=3 THEN 'manual' ELSE 'failed' END,error=CASE WHEN ?=1 THEN N'模拟通道暂不可用' ELSE NULL END WHERE status IN ('pending','failed') AND attempts<3",
        fail,
        fail,
    ).rowcount


def create_device(db, user, data):
    require_role(user, "admin", "community")
    check_elderly(db, user, int(data["elderly_id"]))
    device = db.insert(
        "INSERT device(serial_number,device_type,location) VALUES(?,?,?)",
        data["serial_number"],
        data["device_type"],
        data["location"],
    )
    db.call(
        "sp_bind_device",
        device,
        data["elderly_id"],
        user["id"],
        datetime.now().replace(microsecond=0),
    )
    return {"id": device}
