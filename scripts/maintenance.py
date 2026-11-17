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
        expiry = db.call("sp_expire_services")
        emergency = db.call("sp_escalate_emergencies")
        notifications = send_notifications(db)
        result = {
            "expiry": expiry,
            "emergency": emergency,
            "notifications": notifications,
        }
        # 只有确实处理了数据才写操作留痕；空转只进 scheduler.log。
        if (
            expiry["paused_plans"]
            or expiry["released_assignments"]
            or emergency["escalated_count"]
            or notifications
        ):
            db.audit(
                "scheduler",
                0,
                "maintenance",
                None,
                f"到期暂停 {expiry['paused_plans']} 个计划，释放 {expiry['released_assignments']} 个派单；"
                f"应急升级 {emergency['escalated_count']} 件；发送通知 {notifications} 条",
            )
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
