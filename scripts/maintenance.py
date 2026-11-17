"""每分钟检查一次到期、超时与模拟通知；支持单次执行。"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from care.config import INSTANCE
from care.db import transaction
from care.services.health import send_notifications


def tick():
    with transaction() as db:
        result = {
            "expiry": db.call("sp_expire_services"),
            "emergency": db.call("sp_escalate_emergencies"),
            "notifications": send_notifications(db),
        }
        db.audit("scheduler", 0, "tick", None, json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        filename=INSTANCE / "scheduler.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    while True:
        try:
            result = tick()
            logging.info(json.dumps(result, ensure_ascii=False))
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception:
            logging.exception("本轮维护任务失败")
            if not args.loop:
                raise
        if not args.loop:
            break
        time.sleep(60)
