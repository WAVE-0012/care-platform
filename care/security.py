import hashlib
import hmac
from datetime import datetime

from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash, check_password_hash

from .config import KEYS

cipher = Fernet(KEYS["encryption_key"].encode())


def encrypt(value):
    return cipher.encrypt(value.encode()).decode()


def identity_digest(value):
    return hmac.new(
        KEYS["identity_key"].encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def password_hash(password):
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


class BusinessError(ValueError):
    pass


def require_role(user, *roles):
    if user["role"] not in roles:
        raise PermissionError("当前角色没有此操作权限")


def community_scope(user, alias="o"):
    """返回固定 SQL 片段与绑定参数，统一用于列表和单条读取。"""
    role = user["role"]
    if role == "admin":
        return "1=1", []
    if role == "community":
        return f"{alias}.community_id=?", [user["community_id"]]
    if role in ("street", "civil"):
        column = "c.street_id" if role == "street" else "a.parent_id"
        return (
            f"{alias}.community_id IN (SELECT c.id FROM community c JOIN area a ON a.id=c.street_id WHERE {column}=?)",
            [user["area_id"]],
        )
    if role == "elderly":
        return f"{alias}.elderly_id IN (SELECT id FROM elderly WHERE user_id=?)", [
            user["id"]
        ]
    if role == "family":
        return (
            f"{alias}.elderly_id IN (SELECT elderly_id FROM contact WHERE user_id=? AND active=1 "
            "AND authorized_from<=GETDATE() AND (authorized_until IS NULL OR authorized_until>GETDATE()))",
            [user["id"]],
        )
    if role in ("worker", "agency"):
        predicate = "w.user_id=?" if role == "worker" else "w.agency_id=?"
        value = user["id"] if role == "worker" else user["agency_id"]
        return (
            f"{alias}.elderly_id IN (SELECT p.elderly_id FROM care_plan p JOIN worker w ON w.id=p.worker_id WHERE {predicate} "
            f"UNION SELECT so.elderly_id FROM service_order so JOIN assignment d ON d.order_id=so.id AND d.is_current=1 "
            f"JOIN shift s ON s.id=d.shift_id JOIN worker w ON w.id=s.worker_id WHERE {predicate})",
            [value, value],
        )
    raise PermissionError("账号没有业务数据范围")


def check_community(db, user, community_id):
    predicate, params = community_scope(user)
    if not db.scalar(
        f"SELECT COUNT(*) FROM (SELECT ? community_id) o WHERE {predicate}",
        community_id,
        *params,
    ):
        raise PermissionError("该记录不在当前账号的管理范围内")


def check_elderly(db, user, elderly_id):
    predicate, params = community_scope(user)
    elderly = db.one(
        f"SELECT * FROM (SELECT e.*,e.id elderly_id FROM elderly e) o WHERE o.id=? AND {predicate}",
        elderly_id,
        *params,
    )
    if elderly is None:
        raise PermissionError("该老人不在当前账号的授权范围内")
    return elderly


def check_worker_area(db, user, worker_id):
    """与直接护工业务列表一致：至少一个服务社区在辖区内。"""
    require_role(user, "street", "civil")
    predicate, params = community_scope(user)
    if not db.scalar(
        f"SELECT COUNT(*) FROM worker_area o WHERE o.worker_id=? AND {predicate}",
        worker_id,
        *params,
    ):
        raise PermissionError("该护工不在当前账号的管辖范围内")


def check_order(db, user, order_id):
    predicate, params = order_scope(user)
    order = db.one(
        f"SELECT o.* FROM service_order o WHERE o.id=? AND {predicate}",
        order_id,
        *params,
    )
    if order is None:
        raise PermissionError("该订单不在当前账号的授权范围内")
    return order


def order_scope(user):
    predicate, params = community_scope(user)
    if user["role"] in ("worker", "agency"):
        column, value = (
            ("w.user_id", user["id"])
            if user["role"] == "worker"
            else ("w.agency_id", user["agency_id"])
        )
        predicate = f"EXISTS(SELECT 1 FROM assignment a JOIN shift s ON s.id=a.shift_id JOIN worker w ON w.id=s.worker_id WHERE a.order_id=o.id AND a.is_current=1 AND {column}=?)"
        params = [value]
    return predicate, params
