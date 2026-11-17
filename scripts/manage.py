"""建库、装载示例数据和查看数据库对象。"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc
from care.config import DATABASE, SERVER
from care.db import connect, Repository


def initialize():
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", DATABASE):
        raise ValueError("数据库名称只能包含英文字母、数字和下划线")
    with pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;",
        autocommit=True,
    ) as connection:
        if connection.execute("SELECT DB_ID(?)", DATABASE).fetchval() is not None:
            raise SystemExit(f"{DATABASE} 已存在。init 仅创建新库；更新过程和视图使用 migrate。")
        connection.execute(f"CREATE DATABASE [{DATABASE}]")
        connection.execute(f"ALTER DATABASE [{DATABASE}] SET RECOVERY FULL")
    migrate(include_schema=True)


def migrate(include_schema=False):
    connection = connect()
    try:
        for path in sorted((ROOT / "sql").glob("0[1-5]_*.sql")):
            if path.name.startswith("01_") and not include_schema:
                continue
            for batch in re.split(
                r"^GO\s*$", path.read_text(encoding="utf-8"), flags=re.M | re.I
            ):
                if batch.strip():
                    connection.execute(batch)
            connection.commit()
            print(path.name)
    finally:
        connection.close()


def inventory():
    connection = connect()
    try:
        db = Repository(connection)
        tables = db.all(
            "SELECT t.name,SUM(p.rows) rows FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) GROUP BY t.name ORDER BY t.name"
        )
        objects = db.all(
            "SELECT type_desc,COUNT(*) count FROM sys.objects WHERE is_ms_shipped=0 GROUP BY type_desc"
        )
        result = {"database": DATABASE, "tables": tables, "objects": objects}
        (ROOT / "docs/evidence").mkdir(parents=True, exist_ok=True)
        (ROOT / "docs/evidence/database_inventory.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "migrate", "seed", "inventory"])
    command = parser.parse_args().command
    if command == "init":
        initialize()
    elif command == "migrate":
        migrate()
    elif command == "seed":
        from scripts.seed import seed

        seed()
    else:
        inventory()
