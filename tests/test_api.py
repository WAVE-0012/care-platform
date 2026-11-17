import time
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest

from tests.conftest import login


@pytest.mark.parametrize(
    "username",
    [
        "admin",
        "community01",
        "family01",
        "elderly01",
        "worker01",
        "agency01",
        "street01",
        "civil01",
    ],
)
def test_role_pages(client, username):
    login(client, username)
    for endpoint in [
        "me",
        "dashboard",
        "lookups",
        "list/elders",
        "list/orders",
        "list/vitals",
        "list/events",
        "list/claims",
    ]:
        result = client.get("/api/" + endpoint)
        assert result.status_code == 200, (endpoint, result.json)
    if username not in ["family01", "elderly01"]:
        for kind in ["workers", "shifts", "hours", "quality"]:
            result = client.get("/api/list/" + kind)
            assert result.status_code == 200, (kind, result.json)


def test_family_and_worker_scope(client):
    login(client, "family01")
    assert client.get("/api/orders/3").status_code == 403
    assert {
        row["elderly_id"] for row in client.get("/api/list/orders").json["rows"]
    } == {1}
    assert client.get("/api/list/workers").status_code == 403
    login(client, "worker01")
    assert client.get("/api/orders/3").status_code == 403


def test_csrf_and_role_rejection(client):
    headers = login(client, "family01")
    assert client.post("/api/maintenance", json={}).status_code == 403
    assert client.post("/api/maintenance", json={}, headers=headers).status_code == 403


def test_login_lockout(client):
    for _ in range(5):
        assert (
            client.post(
                "/api/login", json={"username": "family40", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login", json={"username": "family40", "password": "Care2026!"}
        ).status_code
        == 423
    )


def test_session_idle_expiry(client):
    login(client)
    with client.session_transaction() as session:
        session["last_seen"] = time.time() - 1801
    assert client.get("/api/me").status_code == 401


def test_pagination_and_parameterized_search(client):
    login(client)
    first = client.get("/api/list/elders?page=1").json
    second = client.get("/api/list/elders?page=2").json
    assert len(first["rows"]) == len(second["rows"]) == 20
    assert not {r["id"] for r in first["rows"]} & {r["id"] for r in second["rows"]}
    result = client.get("/api/list/elders", query_string={"q": "' OR 1=1 --"})
    assert result.status_code == 200 and result.json["total"] == 0


def test_create_read_update_delete(client):
    headers = login(client, "agency01")
    day = (date.today() + timedelta(days=60)).isoformat()
    result = client.post(
        "/api/shifts",
        json={
            "worker_id": 1,
            "starts_at": day + "T08:00",
            "ends_at": day + "T18:00",
            "capacity": 2,
        },
        headers=headers,
    )
    assert result.status_code == 201, result.json
    shift_id = result.json["id"]
    assert any(r["id"] == shift_id for r in client.get("/api/list/shifts").json["rows"])
    assert client.delete(f"/api/shifts/{shift_id}", headers=headers).status_code == 200


def test_create_order_idempotent_and_cancel(client):
    headers = login(client, "family01")
    data = {
        "elderly_id": 1,
        "item_id": 1,
        "scheduled_at": (datetime.now() + timedelta(days=70))
        .replace(hour=10, minute=0, second=0)
        .isoformat(),
        "request_key": str(uuid4()),
    }
    first = client.post("/api/orders", json=data, headers=headers)
    assert first.status_code == 201, first.json
    second = client.post("/api/orders", json=data, headers=headers)
    assert first.json["id"] == second.json["id"]
    assert (
        client.post(
            f'/api/orders/{first.json["id"]}/cancel',
            json={"reason": "测试取消"},
            headers=headers,
        ).status_code
        == 200
    )


def test_elder_creation_and_update(client):
    headers = login(client, "community01")
    data = {
        "name": "测试建档老人",
        "identity": "990000195001019999",
        "birth_date": "1950-01-01",
        "address": "和悦社区测试路1号",
        "community_id": 1,
        "contact_name": "测试联系人",
        "contact_phone": "19900009999",
    }
    created = client.post("/api/elders", json=data, headers=headers)
    assert created.status_code == 201, created.json
    elder_id = created.json["id"]
    assert client.get(f"/api/elders/{elder_id}").status_code == 200
    assert (
        client.post(
            f"/api/elders/{elder_id}/update",
            json={"address": "和悦社区测试路2号", "low_income": True},
            headers=headers,
        ).status_code
        == 200
    )
    assert client.post("/api/elders", json=data, headers=headers).status_code == 409


def test_service_lifecycle_through_api(client, db):
    db.execute(
        "UPDATE worker SET available_from='00:00',available_until='23:59' WHERE id=4"
    )
    db.connection.commit()
    day = date.today().isoformat()
    headers = login(client, "agency04")
    shift = client.post(
        "/api/shifts",
        json={
            "worker_id": 4,
            "starts_at": day + "T00:00:00",
            "ends_at": day + "T23:59:00",
            "capacity": 4,
        },
        headers=headers,
    )
    assert shift.status_code == 201, shift.json
    headers = login(client, "family04")
    created = client.post(
        "/api/orders",
        json={
            "elderly_id": 4,
            "item_id": 4,
            "scheduled_at": (datetime.now() + timedelta(minutes=5)).isoformat(),
            "duration_minutes": 60,
            "request_key": str(uuid4()),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.json
    order_id = created.json["id"]
    # 在测试库调整预约与签到时间，省去等待；接口仍使用服务器时钟。
    db.execute(
        "UPDATE service_order SET scheduled_at=DATEADD(minute,-3,GETDATE()) WHERE id=?",
        order_id,
    )
    db.connection.commit()
    headers = login(client, "community04")
    assert (
        client.post(
            f"/api/orders/{order_id}/dispatch",
            json={"shift_id": shift.json["id"]},
            headers=headers,
        ).status_code
        == 200
    )
    headers = login(client, "worker04")
    assert (
        client.post(
            f"/api/orders/{order_id}/accept", json={}, headers=headers
        ).status_code
        == 200
    )
    checkin = client.post(
        f"/api/orders/{order_id}/checkin",
        json={"longitude": 116.33, "latitude": 40},
        headers=headers,
    )
    assert checkin.status_code == 200, checkin.json
    db.execute(
        "UPDATE work_log SET checkin_at=DATEADD(second,-90,GETDATE()) WHERE id=?",
        checkin.json["id"],
    )
    db.connection.commit()
    checkout = client.post(
        f"/api/orders/{order_id}/checkout",
        json={"longitude": 116.33, "latitude": 40, "service_record": "完成居家整理，核对服务项目。"},
        headers=headers,
    )
    assert checkout.status_code == 200, checkout.json
    headers = login(client, "family04")
    confirmed = client.post(f"/api/orders/{order_id}/confirm", json={}, headers=headers)
    assert confirmed.status_code == 200, confirmed.json
    final = client.get(f"/api/orders/{order_id}").json
    assert final["order"]["status"] == "completed"
    assert final["order"]["settlement"] > 0


def test_worker_registration_and_device_upload(client):
    headers = login(client, "agency01")
    worker = client.post(
        "/api/workers",
        json={
            "username": "worker_test",
            "name": "新登记护工",
            "password": "NewCare2026!",
            "trained_on": date.today().isoformat(),
            "item_ids": [1, 4],
            "community_ids": [1],
        },
        headers=headers,
    )
    assert worker.status_code == 201, worker.json
    changed = client.post(
        f'/api/workers/{worker.json["id"]}/update',
        json={"status": "leave"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.json
    headers = login(client, "community01")
    device = client.post(
        "/api/devices",
        json={
            "elderly_id": 1,
            "serial_number": "API-TEST-DEVICE",
            "device_type": "心率计",
            "location": "客厅",
        },
        headers=headers,
    )
    assert device.status_code == 201, device.json
    uploaded = client.post(
        "/api/vitals/batch",
        json={
            "records": [
                {
                    "device_id": device.json["id"],
                    "metric": "pulse",
                    "collected_at": datetime.now().replace(microsecond=0).isoformat(),
                    "value": 80,
                }
            ]
        },
        headers=headers,
    )
    assert uploaded.status_code == 200, uploaded.json


def test_family_authorization_revocation(client):
    headers = login(client, "community01")
    response = client.post(
        "/api/elders/21/authorize",
        json={"contact_id": 21, "revoke": True},
        headers=headers,
    )
    assert response.status_code == 200, response.json
    login(client, "family21")
    assert client.get("/api/elders/21").status_code == 403
