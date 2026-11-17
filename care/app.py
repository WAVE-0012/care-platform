import logging
import re
import secrets
import time
from datetime import date, datetime, timedelta, time as clock_time
from decimal import Decimal

import pyodbc
from flask import Flask, g, jsonify, render_template, request, session
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import check_password_hash

from .config import KEYS, ROOT
from .db import transaction as database_transaction
from .security import BusinessError, check_elderly, check_order, require_role
from .services import elders, orders, workforce, health, subsidy
from . import queries


def transaction():
    return database_transaction(restricted=True)


class JSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(value):
        if isinstance(value, (datetime, date, clock_time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return DefaultJSONProvider.default(value)


def create_app():
    app = Flask(__name__)
    app.json = JSONProvider(app)
    app.json.ensure_ascii = False
    app.config.update(
        SECRET_KEY=KEYS["secret"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )

    @app.before_request
    def authenticate():
        if request.path in ["/", "/api/login"] or request.path.startswith("/static/"):
            return
        if "user_id" not in session or time.time() - session.get("last_seen", 0) > 1800:
            session.clear()
            return jsonify(error="请登录，或重新登录已超时的会话"), 401
        with transaction() as db:
            g.user = db.one(
                "SELECT id,username,display_name,role,community_id,agency_id,area_id FROM app_user WHERE id=? AND active=1",
                session["user_id"],
            )
        if g.user is None:
            session.clear()
            return jsonify(error="账号已停用"), 401
        if request.method not in [
            "GET",
            "HEAD",
            "OPTIONS",
        ] and not secrets.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session["csrf"]
        ):
            return jsonify(error="会话校验失败，请刷新页面"), 403
        session["last_seen"] = time.time()

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers[
            "Content-Security-Policy"
        ] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.errorhandler(PermissionError)
    def permission(error):
        return jsonify(error=str(error)), 403

    @app.errorhandler(ValueError)
    def bad_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing_field(error):
        return jsonify(error=f"缺少必填字段：{error.args[0]}"), 400

    @app.errorhandler(pyodbc.Error)
    def database_error(error):
        message = str(error)
        business = re.search(r"\[SQL Server\](.*?)(?:\s*\(51\d{3}\))", message)
        if business:
            return jsonify(error=business.group(1)), 409
        if "2601" in message or "2627" in message:
            return jsonify(error="这条记录已经存在，请检查唯一编号或重复提交"), 409
        if "547" in message:
            return jsonify(error="记录仍有关联业务，或字段超出允许范围"), 409
        app.logger.exception("数据库操作失败")
        return jsonify(error="数据库操作失败，请查看运行日志"), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/login")
    def login():
        data = request.get_json()
        with transaction() as db:
            user = db.one(
                "SELECT * FROM app_user WITH(UPDLOCK,HOLDLOCK) WHERE username=?",
                data["username"],
            )
            if user is None:
                # 与已存在账号使用相同的哈希开销。
                check_password_hash(
                    app.config.get("DUMMY_HASH", "pbkdf2:sha256:600000$dummy$00"),
                    data["password"],
                )
                return jsonify(error="账号或密码不正确"), 401
            if not user["active"]:
                return jsonify(error="账号已停用"), 403
            if user["locked_until"] and user["locked_until"] > datetime.now():
                return jsonify(error="连续登录失败，账号锁定30分钟"), 423
            if not check_password_hash(user["password_hash"], data["password"]):
                attempts = 1 if user["locked_until"] else user["failed_attempts"] + 1
                db.execute(
                    "UPDATE app_user SET failed_attempts=?,locked_until=? WHERE id=?",
                    attempts,
                    datetime.now() + timedelta(minutes=30) if attempts >= 5 else None,
                    user["id"],
                )
                return jsonify(error="账号或密码不正确"), 401
            db.execute(
                "UPDATE app_user SET failed_attempts=0,locked_until=NULL,last_login=GETDATE() WHERE id=?",
                user["id"],
            )
        session.clear()
        session.update(
            user_id=user["id"], csrf=secrets.token_hex(24), last_seen=time.time()
        )
        return jsonify(ok=True)

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me():
        return jsonify(user=g.user, csrf=session["csrf"])

    @app.get("/api/dashboard")
    def dashboard():
        with transaction() as db:
            return jsonify(queries.dashboard(db, g.user))

    @app.get("/api/lookups")
    def lookups():
        with transaction() as db:
            return jsonify(queries.lookups(db, g.user))

    @app.get("/api/list/<kind>")
    def listing(kind):
        page = max(1, int(request.args.get("page", 1)))
        with transaction() as db:
            return jsonify(
                queries.listing(
                    db, g.user, kind, page, request.args.get("q", "").strip()
                )
            )

    @app.get("/api/elders/<int:elder_id>")
    def elder_detail(elder_id):
        with transaction() as db:
            check_elderly(db, g.user, elder_id)
            return jsonify(
                assessments=db.all(
                    "SELECT * FROM assessment WHERE elderly_id=? ORDER BY assessed_on DESC",
                    elder_id,
                ),
                plans=db.all(
                    "SELECT p.*,s.name package_name FROM care_plan p JOIN service_package s ON s.id=p.package_id WHERE p.elderly_id=?",
                    elder_id,
                ),
                contacts=db.all(
                    "SELECT id,name,relationship,phone_mask,is_primary,authorized_until FROM contact WHERE elderly_id=?",
                    elder_id,
                ),
            )

    @app.get("/api/orders/<int:order_id>")
    def order_detail(order_id):
        with transaction() as db:
            order = check_order(db, g.user, order_id)
            return jsonify(
                order=order,
                timeline=db.all(
                    "SELECT * FROM v_order_timeline WHERE order_id=? ORDER BY assignment_id",
                    order_id,
                ),
                costs=db.one("SELECT * FROM v_elderly_cost WHERE order_id=?", order_id),
            )

    @app.get("/api/orders/<int:order_id>/candidates")
    def candidates(order_id):
        require_role(g.user, "admin", "community")
        with transaction() as db:
            check_order(db, g.user, order_id)
            return jsonify(
                rows=db.all(
                    "SELECT * FROM dbo.fn_candidates(?) ORDER BY priority,remaining_slots DESC,worker_id",
                    order_id,
                )
            )

    @app.get("/api/claims/<int:claim_id>")
    def claim_detail(claim_id):
        from .security import community_scope

        with transaction() as db:
            predicate, params = community_scope(g.user)
            claim = db.one(
                f"SELECT * FROM subsidy_claim o WHERE id=? AND {predicate}",
                claim_id,
                *params,
            )
            if not claim:
                raise PermissionError("申报不在当前账号范围内")
            return jsonify(
                claim=claim,
                items=db.all(
                    "SELECT i.*,p.name policy_name,o.settlement FROM claim_item i JOIN subsidy_policy p ON p.id=i.policy_id JOIN service_order o ON o.id=i.order_id WHERE i.claim_id=?",
                    claim_id,
                ),
                reviews=db.all(
                    "SELECT r.*,u.display_name reviewer_name FROM claim_review r JOIN app_user u ON u.id=r.reviewer_id WHERE claim_id=? ORDER BY r.id",
                    claim_id,
                ),
            )

    # 路由只负责取参和事务；业务规则放在各业务线服务中。
    actions = {
        "elders": elders.create,
        "orders": orders.create,
        "shifts": workforce.publish_shift,
        "certificates": workforce.certificate,
        "device-bindings": health.bind,
        "events": health.create_event,
        "claims": subsidy.claim,
        "quality": subsidy.quality,
        "workers": workforce.create,
        "devices": health.create_device,
        "policies": subsidy.policy,
    }

    @app.post("/api/<kind>")
    def create(kind):
        if kind not in actions:
            return jsonify(error="操作不存在"), 404
        with transaction() as db:
            return jsonify(actions[kind](db, g.user, request.get_json())), 201

    entity_actions = {
        ("elders", "update"): elders.update,
        ("elders", "assess"): elders.assess,
        ("elders", "plan"): elders.plan,
        ("elders", "authorize"): elders.authorize,
        ("elders", "plan-state"): elders.plan_state,
        ("workers", "update"): workforce.update,
        ("orders", "dispatch"): orders.dispatch,
        ("orders", "accept"): orders.accept,
        ("orders", "cancel"): orders.cancel,
        ("orders", "reschedule"): orders.reschedule,
        ("orders", "confirm"): orders.confirm,
        ("orders", "feedback"): orders.feedback,
        ("orders", "resolve"): orders.resolve,
        ("orders", "checkin"): workforce.checkin,
        ("orders", "checkout"): workforce.checkout,
        ("hours", "review"): workforce.review,
        ("events", "process"): health.process_event,
        ("claims", "review"): subsidy.review,
        ("claims", "pay"): subsidy.pay,
        ("quality", "rectify"): subsidy.rectify,
    }

    @app.post("/api/<kind>/<int:entity_id>/<action>")
    def mutate(kind, entity_id, action):
        service = entity_actions.get((kind, action))
        if service is None:
            return jsonify(error="操作不存在"), 404
        with transaction() as db:
            return jsonify(service(db, g.user, entity_id, request.get_json()))

    @app.post("/api/vitals/batch")
    def upload_vitals():
        with transaction() as db:
            return jsonify(health.upload(db, g.user, request.get_json()["records"]))

    @app.post("/api/orders/<int:order_id>/finish")
    def finish(order_id):
        require_role(g.user, "admin", "community", "agency")
        with transaction() as db:
            check_order(db, g.user, order_id)
            return jsonify(db.call("sp_finish_order", order_id, g.user["id"]))

    @app.delete("/api/shifts/<int:shift_id>")
    def delete_shift(shift_id):
        require_role(g.user, "admin", "agency")
        with transaction() as db:
            row = db.one("SELECT * FROM shift WHERE id=?", shift_id)
            if row is None:
                raise BusinessError("班次不存在")
            workforce.check_worker(db, g.user, row["worker_id"])
            if db.scalar("SELECT COUNT(*) FROM assignment WHERE shift_id=?", shift_id):
                raise BusinessError("已有派单记录的班次须保留")
            db.execute("DELETE FROM shift WHERE id=?", shift_id)
            db.audit("shift", shift_id, "delete", g.user["id"], "删除未使用班次")
        return jsonify(ok=True)

    @app.post("/api/maintenance")
    def maintenance():
        require_role(g.user, "admin")
        with transaction() as db:
            expired = db.call("sp_expire_services")
            events = db.call("sp_escalate_emergencies")
            sent = health.send_notifications(db)
        return jsonify(expired=expired, events=events, notifications=sent)

    return app
