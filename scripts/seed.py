"""构造可重复的虚拟社区场景；只向空库写入一次。"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from care.db import transaction
from care.security import encrypt, identity_digest, password_hash

DEMO_PASSWORD = "Care2026!"


def seed():
    today = date.today()
    month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    start = month - timedelta(days=90)
    end = today + timedelta(days=365)
    digest = password_hash(DEMO_PASSWORD)
    with transaction() as db:
        if db.scalar("SELECT COUNT(*) FROM app_user"):
            raise ValueError("示例数据仅装载到空库")
        district = db.insert("INSERT area(name,kind) VALUES(N'示例城区','district')")
        streets, communities, agencies = [], [], []
        for i in range(20):
            street = db.insert(
                "INSERT area(name,kind,parent_id) VALUES(?,'street',?)",
                f"第{i+1:02}街道",
                district,
            )
            streets.append(street)
            communities.append(
                db.insert(
                    "INSERT community(name,street_id,longitude,latitude) VALUES(?,?,?,?)",
                    f"和悦{i+1:02}社区",
                    street,
                    116.30 + i * 0.01,
                    40.0,
                )
            )
            agencies.append(
                db.insert(
                    "INSERT agency(name,district_id) VALUES(?,?)",
                    f"安邻{i+1:02}服务中心",
                    district,
                )
            )
        users = {}
        for role in [
            "admin",
            "community",
            "agency",
            "street",
            "civil",
            "family",
            "elderly",
            "worker",
        ]:
            count = (
                1
                if role == "admin"
                else 40
                if role in ["family", "elderly", "worker"]
                else 20
            )
            for i in range(count):
                username = "admin" if role == "admin" else f"{role}{i+1:02}"
                users[(role, i)] = db.insert(
                    "INSERT app_user(username,display_name,password_hash,role,community_id,agency_id,area_id) VALUES(?,?,?,?,?,?,?)",
                    username,
                    f"{role} 演示账号 {i+1:02}",
                    digest,
                    role,
                    communities[i % 20] if role == "community" else None,
                    agencies[i % 20] if role == "agency" else None,
                    streets[i % 20]
                    if role == "street"
                    else district
                    if role == "civil"
                    else None,
                )
        categories = ["助餐", "助浴", "陪诊", "家政", "康复护理"]
        items = []
        for i in range(20):
            category = categories[i % 5]
            items.append(
                db.insert(
                    "INSERT service_item(name,category,unit,price,duration_minutes,certificate_type,certificate_level) VALUES(?,?,?,?,?,?,?)",
                    f'{category}{["基础","舒适","专护","周末"][i//5]}服务',
                    category,
                    "visit" if category in ["助餐", "助浴"] else "hour",
                    [18, 80, 60, 45, 90][i % 5],
                    60,
                    "养老护理员" if category in ["助浴", "康复护理"] else None,
                    2 if category in ["助浴", "康复护理"] else None,
                )
            )
        packages = []
        for i in range(20):
            package = db.insert(
                "INSERT service_package(name,ability_level) VALUES(?,?)",
                f'{["自理","轻度","中度","重度"][i%4]}照护方案{i//4+1}',
                i % 4,
            )
            packages.append(package)
            db.batch(
                "INSERT package_item VALUES(?,?,?,?)",
                [(package, item, 2, "week") for item in items],
            )
        workers, elders, assessments, plans = [], [], [], []
        for i in range(40):
            worker = db.insert(
                "INSERT worker(name,agency_id,user_id,trained_on) VALUES(?,?,?,?)",
                f'{["周","赵","孙","李","吴"][i%5]}护工{i+1:02}',
                agencies[i % 20],
                users[("worker", i)],
                start,
            )
            workers.append(worker)
            db.execute(
                "INSERT certificate(worker_id,certificate_type,level,number,issued_on,valid_until) VALUES(?,?,?,?,?,?)",
                worker,
                "养老护理员",
                3,
                f"DEMO-CERT-{i+1:03}",
                start,
                end,
            )
            db.batch(
                "INSERT worker_skill VALUES(?,?)", [(worker, item) for item in items]
            )
            db.execute("INSERT worker_area VALUES(?,?)", worker, communities[i % 20])
            identity = f"99000019400101{i+1:04}"
            elder = db.insert(
                "INSERT elderly(name,identity_cipher,identity_hash,identity_mask,birth_date,address,community_id,longitude,latitude,living_alone,disabled,low_income,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                f'{["陈","林","黄","王","郑"][i%5]}长者{i+1:02}',
                encrypt(identity),
                identity_digest(identity),
                identity[:3] + "***********" + identity[-4:],
                date(1940 + i % 20, 1 + i % 12, 1),
                f"和悦{i%20+1:02}社区关爱路{i+1}号",
                communities[i % 20],
                116.30 + (i % 20) * 0.01,
                40.0,
                i % 2 == 0,
                i % 4 > 0,
                i % 3 == 0,
                users[("elderly", i)],
            )
            elders.append(elder)
            db.execute(
                "INSERT contact(elderly_id,name,relationship,phone_cipher,phone_mask,is_primary,guardian,user_id,authorized_from) VALUES(?,?,?,?,?,?,?,?,?)",
                elder,
                f"家属{i+1:02}",
                "子女",
                encrypt(f"1990000{i+1:04}"),
                "199****" + f"{i+1:04}",
                1,
                1,
                users[("family", i)],
                datetime.combine(start, time()),
            )
            assessment = db.insert(
                "INSERT assessment(elderly_id,scale,score,ability_level,assessor_id,assessed_on,valid_until) VALUES(?,?,?,?,?,?,?)",
                elder,
                "ADL",
                100 - 25 * (i % 4),
                i % 4,
                users[("community", i % 20)],
                start,
                end,
            )
            assessments.append(assessment)
            plan = db.call(
                "sp_create_plan", elder, packages[i % 20], worker, start, end
            )["id"]
            plans.append(plan)
        # 上月完成订单：每位老人两单，完整保留工时、确认和准入依据。
        completed_orders = []
        for i, elder in enumerate(elders):
            for day in [5, 7]:
                scheduled = datetime.combine(month.replace(day=day), time(10))
                shift = db.call(
                    "sp_publish_shift",
                    workers[i],
                    scheduled.replace(hour=8),
                    scheduled.replace(hour=18),
                    4,
                )["id"]
                item = items[i % 20]
                price = db.one("SELECT * FROM service_item WHERE id=?", item)
                order = db.insert(
                    "INSERT service_order(request_key,elderly_id,item_id,community_id,created_by,scheduled_at,duration_minutes,address,longitude,latitude,unit_price,price_unit,channel,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    f"seed-completed-{i}-{day}",
                    elder,
                    item,
                    communities[i % 20],
                    users[("community", i % 20)],
                    scheduled,
                    60,
                    f"和悦{i%20+1:02}社区关爱路{i+1}号",
                    116.30 + (i % 20) * 0.01,
                    40.0,
                    price["price"],
                    price["unit"],
                    "社区代下单",
                    "confirming",
                )
                assignment = db.insert(
                    "INSERT assignment(order_id,shift_id,dispatcher_id,assigned_at,accepted_at,status,service_record,confirmed_by,confirmed_at) VALUES(?,?,?,?,?,'accepted',?,?,?)",
                    order,
                    shift,
                    users[("community", i % 20)],
                    scheduled - timedelta(days=1),
                    scheduled - timedelta(hours=1),
                    f'完成{price["name"]}，核对老人需求并整理服务现场。',
                    users[("family", i)],
                    scheduled + timedelta(hours=1, minutes=5),
                )
                db.execute(
                    "INSERT work_log(assignment_id,checkin_at,checkout_at,longitude,latitude,geofence_ok,valid_hours,review_status) VALUES(?,?,?,?,?,1,1,'auto')",
                    assignment,
                    scheduled,
                    scheduled + timedelta(hours=1),
                    116.30 + (i % 20) * 0.01,
                    40.0,
                )
                db.execute(
                    "INSERT eligibility_snapshot(order_id,assessment_id,plan_id,low_income,checked_by) VALUES(?,?,?,?,?)",
                    order,
                    assessments[i],
                    plans[i],
                    i % 3 == 0,
                    users[("worker", i)],
                )
                db.call("sp_finish_order", order)
                db.execute(
                    "UPDATE service_order SET rating=?,feedback=? WHERE id=?",
                    4 + i % 2,
                    "服务按时完成，沟通清楚。",
                    order,
                )
                completed_orders.append(order)
        for i, worker in enumerate(workers):
            for offset in range(1, 8):
                scheduled = datetime.combine(today + timedelta(days=offset), time(10))
                shift = db.call(
                    "sp_publish_shift",
                    worker,
                    scheduled.replace(hour=8),
                    scheduled.replace(hour=18),
                    4,
                )["id"]
                if offset == 1:
                    price = db.one(
                        "SELECT * FROM service_item WHERE id=?", items[i % 20]
                    )
                    order = db.insert(
                        "INSERT service_order(request_key,elderly_id,item_id,community_id,created_by,scheduled_at,duration_minutes,address,longitude,latitude,unit_price,price_unit,channel) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        f"seed-upcoming-{i}",
                        elders[i],
                        items[i % 20],
                        communities[i % 20],
                        users[("community", i % 20)],
                        scheduled,
                        60,
                        f"和悦{i%20+1:02}社区关爱路{i+1}号",
                        116.30 + (i % 20) * 0.01,
                        40.0,
                        price["price"],
                        price["unit"],
                        "社区代下单",
                    )
                    if i >= 20:
                        assignment = db.call(
                            "sp_dispatch", order, shift, users[("community", i % 20)]
                        )["id"]
                        if i >= 30:
                            db.execute(
                                "UPDATE assignment SET status='accepted',accepted_at=GETDATE() WHERE id=?",
                                assignment,
                            )
                            db.execute(
                                "UPDATE service_order SET status='accepted' WHERE id=?",
                                order,
                            )
        # 指标值与阈值均为课设测试数据；不用于医学判断。
        rules = {}
        for i, community in enumerate(communities):
            for metric, unit, lower, upper in [
                ("systolic", "mmHg", 90, 140),
                ("pulse", "次/分", 60, 100),
                ("temperature", "℃", 36, 37.3),
            ]:
                rules[(i, metric)] = db.insert(
                    "INSERT metric_rule(community_id,metric,unit,lower_bound,upper_bound) VALUES(?,?,?,?,?)",
                    community,
                    metric,
                    unit,
                    lower,
                    upper,
                )
        for i in range(40):
            device = db.insert(
                "INSERT device(serial_number,device_type,location) VALUES(?,?,?)",
                f"DEMO-DEVICE-{i+1:03}",
                "血压计",
                f"老人{elders[i]}居家客厅",
            )
            binding = db.call(
                "sp_bind_device",
                device,
                elders[i],
                users[("community", i % 20)],
                datetime.combine(start, time()),
            )["id"]
            vital = db.insert(
                "INSERT vital(binding_id,rule_id,collected_at,value) VALUES(?,?,?,?)",
                binding,
                rules[(i % 20, "systolic")],
                datetime.now().replace(microsecond=0) - timedelta(hours=2),
                155 if i % 2 == 0 else 125,
            )
            if i % 2 == 0:
                event = db.insert(
                    "INSERT emergency(request_key,elderly_id,community_id,vital_id,source,level,occurred_at,response_minutes,arrival_minutes) VALUES(?,?,?,?,?,2,?,10,30)",
                    f"seed-event-{i}",
                    elders[i],
                    communities[i % 20],
                    vital,
                    "设备告警",
                    datetime.now().replace(microsecond=0) - timedelta(minutes=20),
                )
                db.execute(
                    "UPDATE vital SET confirmation='confirmed' WHERE id=?", vital
                )
                db.batch(
                    "INSERT notification(event_id,recipient,stage,status,attempts) VALUES(?,?,'created','sent',1)",
                    [(event, "主联系人"), (event, "责任护工"), (event, "社区值班岗")],
                )
        for item in items:
            for level in range(4):
                db.execute(
                    "INSERT subsidy_policy(name,district_id,item_id,ability_level,rate,starts_on,ends_on) VALUES(?,?,?,?,?,?,?)",
                    f"示例城区{item}项目{level}级月补贴",
                    district,
                    item,
                    level,
                    Decimal("12") + level * 3,
                    start.replace(day=1),
                    date(end.year, 12, 31),
                )
        for i in range(20):
            claim = db.call(
                "sp_claim_month",
                elders[i],
                items[i % 20],
                month,
                users[("community", i)],
                "订单确认记录、签到签退、评估与计划可按明细追溯。",
            )["id"]
            db.call(
                "sp_review_claim",
                claim,
                users[("street", i)],
                "approve",
                "已核对工时、服务记录和政策范围。",
            )
            if i < 12:
                db.call(
                    "sp_review_claim",
                    claim,
                    users[("civil", i)],
                    "approve",
                    "核定金额与申报明细一致。",
                )
            if i < 6:
                db.call(
                    "sp_pay_claim", claim, users[("civil", i)], f"DEMO-PAY-{i+1:03}"
                )
            db.execute(
                "INSERT quality_check(order_id,inspector_id,method,score) VALUES(?,?,?,?)",
                completed_orders[2 * i],
                users[("street", i)],
                "电话回访",
                4 + i % 2,
            )
        for i in range(20):
            db.audit(
                "elderly",
                elders[i],
                "create",
                users[("community", i)],
                "初始化虚拟老人档案及授权联系人。",
            )
    print("已装载 20 个社区、40 位老人、40 名护工及五条业务线的虚拟测试数据。")
    print(
        "演示账号：admin / community01 / family01 / worker01 / agency01 / street01 / civil01；密码：Care2026!"
    )
