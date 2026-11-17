"""在新数据库演练全量、差异和日志恢复，不覆盖源数据库。"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pyodbc
from care.config import DATABASE, SERVER
from care.db import Repository


def run():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = DATABASE + "_restore_" + stamp
    if not re.fullmatch(r"CareHomeCourse2026(?:_test_\d{8}_\d{6})?", DATABASE):
        raise ValueError("本演练仅用于本项目数据库")
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;",
        autocommit=True,
    )
    db = Repository(conn)

    def execute_complete(sql, *params):
        cursor = db.execute(sql, *params)
        while cursor.nextset():
            pass

    backup_dir = Path(
        db.scalar(
            "SELECT CAST(SERVERPROPERTY('InstanceDefaultBackupPath') AS nvarchar(260))"
        )
    )
    data_dir = Path(
        db.scalar(
            "SELECT CAST(SERVERPROPERTY('InstanceDefaultDataPath') AS nvarchar(260))"
        )
    )
    log_dir = Path(
        db.scalar(
            "SELECT CAST(SERVERPROPERTY('InstanceDefaultLogPath') AS nvarchar(260))"
        )
    )
    paths = {
        kind: backup_dir / f"{DATABASE}_{stamp}_{kind}.{extension}"
        for kind, extension in [("full", "bak"), ("diff", "bak"), ("log", "trn")]
    }
    start = time.perf_counter()
    try:
        execute_complete(
            f"BACKUP DATABASE [{DATABASE}] TO DISK=? WITH INIT,CHECKSUM",
            str(paths["full"]),
        )
        execute_complete(
            f"BACKUP DATABASE [{DATABASE}] TO DISK=? WITH DIFFERENTIAL,INIT,CHECKSUM",
            str(paths["diff"]),
        )
        execute_complete(
            f"BACKUP LOG [{DATABASE}] TO DISK=? WITH INIT,CHECKSUM", str(paths["log"])
        )
        for path in paths.values():
            execute_complete("RESTORE VERIFYONLY FROM DISK=? WITH CHECKSUM", str(path))
        files = db.all("RESTORE FILELISTONLY FROM DISK=?", str(paths["full"]))
        moves = []
        for item in files:
            destination = (data_dir if item["Type"] == "D" else log_dir) / (
                target + (".mdf" if item["Type"] == "D" else ".ldf")
            )
            logical = item["LogicalName"].replace("'", "''")
            moves.append(
                f"MOVE N'{logical}' TO N'{str(destination).replace(chr(39),chr(39)*2)}'"
            )
        restore_started = time.perf_counter()
        execute_complete(
            f"RESTORE DATABASE [{target}] FROM DISK=? WITH NORECOVERY,CHECKSUM,"
            + ",".join(moves),
            str(paths["full"]),
        )
        execute_complete(
            f"RESTORE DATABASE [{target}] FROM DISK=? WITH NORECOVERY,CHECKSUM",
            str(paths["diff"]),
        )
        execute_complete(
            f"RESTORE LOG [{target}] FROM DISK=? WITH RECOVERY,CHECKSUM",
            str(paths["log"]),
        )
        restore_seconds = time.perf_counter() - restore_started
        execute_complete(f"DBCC CHECKDB([{target}]) WITH NO_INFOMSGS")

        def counts(name):
            return db.one(
                f"SELECT (SELECT COUNT(*) FROM [{name}].dbo.elderly) elders,(SELECT COUNT(*) FROM [{name}].dbo.service_order) orders,(SELECT SUM(settlement) FROM [{name}].dbo.service_order) settlement,(SELECT SUM(valid_hours) FROM [{name}].dbo.work_log) hours,(SELECT SUM(amount) FROM [{name}].dbo.subsidy_claim) claims"
            )

        source_values, restored_values = counts(DATABASE), counts(target)
        assert source_values == restored_values, (source_values, restored_values)
        result = {
            "source": DATABASE,
            "restored_database": target,
            "started_at": stamp,
            "restore_seconds": round(restore_seconds, 3),
            "total_seconds": round(time.perf_counter() - start, 3),
            "source_values": source_values,
            "restored_values": restored_values,
            "checksum": "passed",
            "checkdb": "passed",
            "matching": "passed",
            "backup_files": {k: str(v) for k, v in paths.items()},
        }
        (ROOT / "docs/evidence/backup-restore.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        # 只删除本次创建的恢复演练库。
        if db.scalar("SELECT DB_ID(?)", target) is not None:
            db.execute(f"DROP DATABASE [{target}]")
        conn.close()


if __name__ == "__main__":
    run()
