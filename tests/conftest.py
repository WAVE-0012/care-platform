"""在本次运行创建的独立数据库中验证，不改动演示库。"""
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CARE_DATABASE"] = "CareHomeCourse2026_test_" + datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

from care.app import create_app
from care.db import Repository, connect
from scripts.manage import initialize
from scripts.seed import seed


@pytest.fixture(scope="session", autouse=True)
def database():
    initialize()
    seed()
    yield
    # 测试库保留到验证脚本记录结果后统一清理，可用失败现场复查。
    (ROOT / "docs/evidence/test_database.txt").write_text(
        os.environ["CARE_DATABASE"], encoding="utf-8"
    )


@pytest.fixture
def db(database):
    connection = connect()
    yield Repository(connection)
    connection.rollback()
    connection.close()


@pytest.fixture
def client(database):
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def login(client, username="admin"):
    response = client.post(
        "/api/login", json={"username": username, "password": "Care2026!"}
    )
    assert response.status_code == 200, response.json
    token = client.get("/api/me").json["csrf"]
    return {"X-CSRF-Token": token}
