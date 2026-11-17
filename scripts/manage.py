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
        base = sorted((ROOT / "sql").glob("0[1-5]_*.sql"))
        paths = [path for path in base if path.name.startswith("01_") and include_schema]
        # 先跑存量预检/迁移，再更新视图、过程、触发器和权限；任一步失败整体回滚。
        paths += sorted((ROOT / "sql/migrations").glob("*.sql"))
        paths += [path for path in base if not path.name.startswith("01_")]
        for path in paths:
            for batch in re.split(
                r"^GO\s*$", path.read_text(encoding="utf-8"), flags=re.M | re.I
            ):
                if batch.strip():
                    cursor = connection.execute(batch)
                    try:
                        # 预检会先返回问题记录再 THROW，必须先把结果集读完。
                        while True:
                            if cursor.description:
                                columns = [column[0] for column in cursor.description]
                                for row in cursor:
                                    print(json.dumps(dict(zip(columns, row)), ensure_ascii=False, default=str))
                            if not cursor.nextset():
                                break
                    finally:
                        cursor.close()
        connection.commit()
        for path in paths:
            print(path.relative_to(ROOT))
    except Exception:
        connection.rollback()
        raise
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
