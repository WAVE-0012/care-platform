"""页面查询。表名、列名、排序方式均由这里的固定 SQL 决定。"""
from care.security import community_scope, order_scope, require_role


def listing(db, user, kind, page=1, keyword=""):
    predicate, params = community_scope(user)
    search = ""
    if kind == "elders":
        source = "SELECT e.id,e.id elderly_id,e.name,e.identity_mask,e.birth_date,e.address,e.community_id,c.name community_name,e.living_alone,e.disabled,e.low_income,e.active,a.ability_level,a.valid_until,a.plan_id,a.plan_status FROM elderly e JOIN community c ON c.id=e.community_id LEFT JOIN v_current_assessment a ON a.elderly_id=e.id"
        search = "name"
    elif kind == "orders":
        predicate, params = order_scope(user)
        source = "SELECT s.*,e.name elderly_name,i.name item_name,c.name community_name,a.id assignment_id,w.name worker_name,l.review_status,l.valid_hours FROM service_order s JOIN elderly e ON e.id=s.elderly_id JOIN service_item i ON i.id=s.item_id JOIN community c ON c.id=s.community_id LEFT JOIN assignment a ON a.order_id=s.id AND a.is_current=1 LEFT JOIN shift t ON t.id=a.shift_id LEFT JOIN worker w ON w.id=t.worker_id LEFT JOIN work_log l ON l.assignment_id=a.id"
        search = "elderly_name"
    elif kind in ["workers", "shifts", "hours"]:
        require_role(user, "admin", "community", "agency", "worker", "street", "civil")
        if user["role"] == "agency":
            predicate, params = "o.agency_id=?", [user["agency_id"]]
        elif user["role"] == "worker":
            (
                predicate,
                params,
            ) = "o.worker_id IN (SELECT id FROM worker WHERE user_id=?)", [user["id"]]
        elif user["role"] == "admin":
            predicate, params = "1=1", []
        else:
            scope, values = community_scope(user, "area_scope")
            predicate, params = (
                f'o.worker_id IN (SELECT wa.worker_id FROM worker_area wa JOIN community area_scope ON area_scope.id=wa.community_id WHERE {scope.replace("area_scope.community_id","area_scope.id")})',
                values,
            )
        if kind == "workers":
            source = "SELECT w.*,w.id worker_id,a.name agency_name,(SELECT AVG(CAST(o.rating AS decimal(5,2))) FROM service_order o JOIN assignment d ON d.order_id=o.id AND d.is_current=1 JOIN shift s ON s.id=d.shift_id WHERE s.worker_id=w.id AND o.status='completed') rating FROM worker w JOIN agency a ON a.id=w.agency_id"
            search = "name"
        elif kind == "shifts":
            source = "SELECT * FROM v_shift_capacity"
            search = "worker_name"
        else:
            source = "SELECT * FROM v_work_review"
            search = "worker_name"
    elif kind == "vitals":
        source = "SELECT * FROM v_vital_history"
        search = "elderly_name"
    elif kind == "events":
        source = "SELECT e.*,p.name elderly_name FROM emergency e JOIN elderly p ON p.id=e.elderly_id"
        search = "elderly_name"
    elif kind == "claims":
        source = "SELECT * FROM v_claim_progress"
        search = "elderly_name"
    elif kind == "quality":
        require_role(user, "admin", "community", "agency", "worker", "street", "civil")
        source = "SELECT q.*,COALESCE(q.worker_id,s.worker_id) target_worker,w.agency_id,w.name worker_name,o.elderly_id,o.community_id FROM quality_check q LEFT JOIN service_order o ON o.id=q.order_id LEFT JOIN assignment a ON a.order_id=o.id AND a.is_current=1 LEFT JOIN shift s ON s.id=a.shift_id JOIN worker w ON w.id=COALESCE(q.worker_id,s.worker_id)"
        if user["role"] == "agency":
            predicate, params = "o.agency_id=?", [user["agency_id"]]
        elif user["role"] == "worker":
            (
                predicate,
                params,
            ) = "o.target_worker IN(SELECT id FROM worker WHERE user_id=?)", [
                user["id"]
            ]
        elif user["role"] != "admin":
            scope, values = community_scope(user, "x")
            predicate = (
                f"((o.order_id IS NOT NULL AND {predicate}) OR "
                f"(o.order_id IS NULL AND o.target_worker IN(SELECT wa.worker_id FROM worker_area wa "
                f"JOIN (SELECT id community_id FROM community) x ON x.community_id=wa.community_id WHERE {scope})))"
            )
            params += values
        search = "worker_name"
    elif kind == "notifications":
        require_role(user, "admin", "community", "street", "civil")
        source = "SELECT n.*,e.elderly_id,e.community_id FROM notification n JOIN emergency e ON e.id=n.event_id"
        search = "recipient"
    elif kind == "audit":
        require_role(user, "admin", "community", "agency", "street", "civil")
        source = "SELECT a.*,u.display_name actor_name FROM audit_log a LEFT JOIN app_user u ON u.id=a.actor_id"
        predicate, params = (
            ("1=1", []) if user["role"] == "admin" else ("o.actor_id=?", [user["id"]])
        )
        search = "detail"
    else:
        raise ValueError("未知数据列表")
    if keyword:
        predicate += f" AND o.{search} LIKE ?"
        params.append("%" + keyword + "%")
    total = db.scalar(f"SELECT COUNT(*) FROM ({source}) o WHERE {predicate}", *params)
    rows = db.all(
        f"SELECT * FROM ({source}) o WHERE {predicate} ORDER BY o.id DESC OFFSET ? ROWS FETCH NEXT 20 ROWS ONLY",
        *params,
        (page - 1) * 20,
    )
    return {"rows": rows, "total": total, "page": page, "page_size": 20}


def dashboard(db, user):
    ep, ev = community_scope(user)
    op, ov = order_scope(user)
    elders = db.scalar(
        f"SELECT COUNT(*) FROM (SELECT id elderly_id,community_id FROM elderly WHERE active=1) o WHERE {ep}",
        *ev,
    )
    orders = db.one(
        f"SELECT COUNT(*) total,SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,SUM(CASE WHEN status IN ('pending','ineligible','offered') THEN 1 ELSE 0 END) waiting,COALESCE(SUM(settlement),0) amount FROM service_order o WHERE {op}",
        *ov,
    )
    events = db.scalar(
        f"SELECT COUNT(*) FROM emergency o WHERE status<>'closed' AND {ep}", *ev
    )
    claims = db.scalar(
        f"SELECT COALESCE(SUM(amount),0) FROM subsidy_claim o WHERE status IN ('approved','paid') AND {ep}",
        *ev,
    )
    trend = db.all(
        f"SELECT CONVERT(char(7),scheduled_at,120) month,COUNT(*) orders,SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed FROM service_order o WHERE {op} GROUP BY CONVERT(char(7),scheduled_at,120) ORDER BY month",
        *ov,
    )
    tasks = db.all(
        f"SELECT TOP 6 e.id,e.name,a.valid_until FROM (SELECT e.*,e.id elderly_id FROM elderly e) o JOIN elderly e ON e.id=o.id JOIN v_current_assessment a ON a.elderly_id=e.id WHERE {ep} AND (a.valid_until IS NULL OR a.valid_until<=DATEADD(day,7,GETDATE())) ORDER BY a.valid_until",
        *ev,
    )
    return {
        "elders": elders,
        "orders": orders,
        "events": events,
        "subsidy": claims,
        "trend": trend,
        "reassessment": tasks,
    }


def lookups(db, user):
    ep, ev = community_scope(user)
    elders = db.all(
        f"SELECT o.id,o.name,o.community_id,o.longitude,o.latitude FROM (SELECT e.*,e.id elderly_id FROM elderly e) o WHERE {ep} ORDER BY o.id",
        *ev,
    )
    communities = db.all("SELECT id,name FROM community ORDER BY id")
    if user["role"] == "community":
        communities = [c for c in communities if c["id"] == user["community_id"]]
    workers = []
    if user["role"] not in ["family", "elderly"]:
        # 复用护工列表的范围查询，避免表单绕过列表权限。
        first = listing(db, user, "workers", 1)
        workers = first["rows"]
        for page in range(2, (first["total"] + 19) // 20 + 1):
            workers += listing(db, user, "workers", page)["rows"]
    return {
        "elders": elders,
        "communities": communities,
        "workers": workers,
        "items": db.all("SELECT * FROM service_item ORDER BY id"),
        "packages": db.all(
            "SELECT id,name,ability_level FROM service_package WHERE active=1 ORDER BY id"
        ),
    }
