"""从实际数据库导出字段字典、主外键和关系模式。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from care.db import transaction

TABLES = {
    "area": "行政区划",
    "community": "社区",
    "agency": "服务机构",
    "app_user": "用户账号",
    "elderly": "老人档案",
    "contact": "老人联系人",
    "assessment": "能力评估",
    "service_item": "服务项目",
    "service_package": "服务包",
    "package_item": "服务包项目",
    "worker": "护工档案",
    "certificate": "护工资质",
    "worker_skill": "护工服务项目",
    "worker_area": "护工服务区域",
    "care_plan": "照护计划",
    "plan_item": "计划项目",
    "shift": "护工排班",
    "service_order": "服务订单",
    "assignment": "派单记录",
    "work_log": "工时记录",
    "eligibility_snapshot": "服务准入依据",
    "device": "监测设备",
    "device_binding": "设备绑定",
    "metric_rule": "指标阈值",
    "vital": "体征记录",
    "emergency": "应急事件",
    "notification": "通知记录",
    "subsidy_policy": "补贴政策",
    "subsidy_claim": "补贴申报",
    "claim_item": "申报明细",
    "claim_review": "审核记录",
    "quality_check": "质量抽查",
    "audit_log": "操作审计",
}
FIELDS = {
    "id": "记录编号",
    "name": "名称",
    "kind": "区划类型",
    "parent_id": "上级区划",
    "street_id": "所属街道",
    "district_id": "所属区县",
    "longitude": "经度",
    "latitude": "纬度",
    "radius_m": "社区服务半径 米",
    "checkin_radius_m": "签到围栏半径 米",
    "active": "是否启用",
    "username": "登录账号",
    "display_name": "显示姓名",
    "password_hash": "含盐的密码哈希",
    "role": "业务角色",
    "community_id": "所属社区或发生时社区",
    "agency_id": "所属服务机构",
    "area_id": "管理区划",
    "failed_attempts": "连续登录失败次数",
    "locked_until": "登录锁定截止",
    "last_login": "最近登录时间",
    "identity_cipher": "身份证加密值",
    "identity_hash": "身份证HMAC唯一检索值",
    "identity_mask": "脱敏身份证",
    "birth_date": "出生日期",
    "address": "居住地址或服务地址快照",
    "living_alone": "独居标记",
    "disabled": "失能标记",
    "low_income": "低保资格",
    "user_id": "关联登录账号",
    "elderly_id": "关联老人",
    "relationship": "联系人关系",
    "phone_cipher": "联系电话加密值",
    "phone_mask": "脱敏联系电话",
    "is_primary": "是否主联系人",
    "guardian": "监护人标记",
    "authorized_from": "代办授权生效时间",
    "authorized_until": "代办授权终止时间",
    "scale": "评估量表 ADL或MMSE",
    "score": "量表得分或抽查评分",
    "ability_level": "能力等级 0至3",
    "assessor_id": "评估人员账号",
    "assessed_on": "评估日期",
    "valid_until": "有效期截止 含当日",
    "category": "服务类别",
    "unit": "计价单位或指标单位",
    "price": "当前指导价 元",
    "duration_minutes": "标准或预约分钟数",
    "subsidized": "是否可申请补贴",
    "certificate_type": "证书类型",
    "certificate_level": "最低证书等级 1至3",
    "package_id": "服务包编号",
    "item_id": "服务项目编号",
    "frequency": "计划服务频次",
    "period": "频次周期 周或月",
    "available_from": "每日最早服务时刻",
    "available_until": "每日最晚服务时刻",
    "trained_on": "岗前培训完成日期",
    "status": "业务状态",
    "total_hours": "累计已完成有效工时 小时",
    "points": "已完成服务积分",
    "worker_id": "护工编号",
    "level": "证书或应急等级 1至3",
    "number": "证书编号",
    "issued_on": "证书发证日期",
    "starts_on": "生效日期 含当日",
    "ends_on": "失效日期 含当日",
    "plan_id": "照护计划编号",
    "starts_at": "班次开始 左闭",
    "ends_at": "班次结束 右开",
    "capacity": "班次可接单量",
    "used_slots": "已占用及使用名额",
    "request_key": "客户端请求唯一编号",
    "created_by": "下单账号",
    "created_at": "记录创建时间",
    "scheduled_at": "预约开始时间",
    "unit_price": "成交单价快照 元",
    "price_unit": "计价方式快照 次或小时",
    "channel": "下单渠道",
    "settlement": "已完成订单结算金额 元",
    "completed_at": "完成结算时间",
    "rating": "老人评价 1至5",
    "feedback": "评价内容",
    "complaint": "投诉内容",
    "complaint_result": "投诉处理结果",
    "order_id": "服务订单编号",
    "shift_id": "排班编号",
    "dispatcher_id": "派单人员账号",
    "assigned_at": "派单时间",
    "accepted_at": "接单时间",
    "is_current": "是否当前或最终派单",
    "reason": "改派或释放原因",
    "service_record": "实际服务内容",
    "confirmed_by": "老人或授权家属确认账号",
    "confirmed_at": "服务确认时间",
    "proof_reference": "证明材料引用",
    "assignment_id": "派单编号",
    "checkin_at": "签到时间",
    "checkout_at": "签退时间",
    "geofence_ok": "签到位置校验结果",
    "valid_hours": "认定有效工时 小时",
    "review_status": "工时复核状态",
    "reviewer_id": "审核或复核账号",
    "review_note": "工时复核依据",
    "assessment_id": "服务所用评估编号",
    "checked_at": "核验或抽查时间",
    "checked_by": "资格核验账号",
    "serial_number": "设备序列号",
    "device_type": "监测设备类型",
    "location": "设备安装位置",
    "device_id": "设备编号",
    "bound_at": "绑定开始 左闭",
    "unbound_at": "解绑时刻 右开",
    "operator_id": "绑定操作账号",
    "metric": "指标代码",
    "lower_bound": "阈值下限",
    "upper_bound": "阈值上限",
    "binding_id": "采集时设备绑定记录",
    "rule_id": "阈值配置编号",
    "collected_at": "设备采集时间",
    "received_at": "平台接收时间",
    "value": "指标采集值",
    "abnormal": "超出阈值标记",
    "confirmation": "体征核实状态",
    "source": "设备或求助来源",
    "vital_id": "关联异常体征",
    "occurred_at": "应急事件发生时间",
    "response_minutes": "响应时限 分钟",
    "arrival_minutes": "到场时限 分钟",
    "responder_id": "实际响应账号",
    "responded_at": "开始响应时间",
    "arrived_at": "实际到场时间",
    "escalated_at": "首次升级时间",
    "result": "处置或整改结果",
    "closed_at": "事件关闭时间",
    "event_id": "应急事件编号",
    "recipient": "模拟通知接收对象",
    "stage": "通知或审核阶段",
    "attempts": "发送尝试次数",
    "last_attempt_at": "最近发送时间",
    "error": "通知失败原因",
    "low_income_only": "是否限低保对象",
    "rate": "每次或每小时补贴额 元",
    "month": "自然月首日",
    "amount": "申报或补贴金额 元",
    "submitted_by": "申报人员账号",
    "submitted_at": "最近提交时间",
    "evidence": "申报材料说明",
    "payment_reference": "唯一拨付凭证号",
    "paid_by": "拨付经办账号",
    "paid_at": "拨付登记时间",
    "claim_id": "补贴申报编号",
    "policy_id": "使用的政策版本",
    "decision": "审核结论",
    "note": "审核意见",
    "reviewed_at": "审核时间",
    "inspector_id": "质量抽查账号",
    "method": "抽查方式",
    "issue": "问题说明",
    "requirement": "整改要求",
    "restrict_agency": "是否限制整个机构",
    "restricted_item_id": "受限项目 空值表示全部",
    "due_on": "整改截止日期",
    "entity": "审计对象类型",
    "entity_id": "审计对象编号",
    "action": "操作名称",
    "actor_id": "实际操作账号",
    "detail": "操作原因或摘要",
}


def export():
    with transaction() as db:
        columns = db.all(
            "SELECT t.name table_name,c.name,column_id,ty.name type,c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,dc.definition default_value FROM sys.tables t JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id LEFT JOIN sys.default_constraints dc ON dc.object_id=c.default_object_id ORDER BY t.name,c.column_id"
        )
        keys = db.all(
            "SELECT t.name table_name,i.name index_name,i.is_primary_key,i.is_unique,i.filter_definition,c.name column_name,ic.key_ordinal FROM sys.tables t JOIN sys.indexes i ON i.object_id=t.object_id JOIN sys.index_columns ic ON ic.object_id=t.object_id AND ic.index_id=i.index_id JOIN sys.columns c ON c.object_id=t.object_id AND c.column_id=ic.column_id WHERE i.is_unique=1 AND ic.key_ordinal>0 ORDER BY t.name,i.name,ic.key_ordinal"
        )
        fks = db.all(
            "SELECT fk.name,pt.name child,pc.name child_column,rt.name parent,rc.name parent_column,pc.is_nullable FROM sys.foreign_keys fk JOIN sys.foreign_key_columns f ON f.constraint_object_id=fk.object_id JOIN sys.tables pt ON pt.object_id=f.parent_object_id JOIN sys.columns pc ON pc.object_id=pt.object_id AND pc.column_id=f.parent_column_id JOIN sys.tables rt ON rt.object_id=f.referenced_object_id JOIN sys.columns rc ON rc.object_id=rt.object_id AND rc.column_id=f.referenced_column_id ORDER BY pt.name,pc.column_id"
        )
        checks = db.all(
            "SELECT OBJECT_NAME(parent_object_id) table_name,name,definition FROM sys.check_constraints ORDER BY table_name,name"
        )
        environment = db.one(
            "SELECT @@VERSION version,CAST(SERVERPROPERTY('Edition') AS nvarchar(100)) edition,CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(100)) product_version"
        )
    result = {
        "tables": {},
        "relationships": fks,
        "checks": checks,
        "environment": environment,
    }
    md = [
        "# 数据字典与关系模式",
        "",
        "本文件从实际数据库元数据生成。PK 为主键，FK 为外键，UK 为唯一约束或唯一索引。完整 CHECK 表达式位于每张表字段表后。",
        "",
    ]
    for name, label in TABLES.items():
        fields = [c for c in columns if c["table_name"] == name]
        pk = [
            k["column_name"]
            for k in keys
            if k["table_name"] == name and k["is_primary_key"]
        ]
        unique = {}
        filtered_unique = {}
        for key in keys:
            if key["table_name"] == name and not key["is_primary_key"]:
                if key["filter_definition"]:
                    entry = filtered_unique.setdefault(
                        key["index_name"],
                        {"columns": [], "filter": key["filter_definition"]},
                    )
                    entry["columns"].append(key["column_name"])
                else:
                    unique.setdefault(key["index_name"], []).append(key["column_name"])
        for c in fields:
            c["description"] = FIELDS[c["name"]]
            c["sql_type"] = c["type"]
            if c["type"] in ["varchar", "nvarchar", "char", "nchar"]:
                length = c["max_length"] // (2 if c["type"].startswith("n") else 1)
                c["sql_type"] += f"({length})"
            elif c["type"] == "decimal":
                c["sql_type"] += f'({c["precision"]},{c["scale"]})'
            elif c["type"] in ["datetime2", "time"]:
                c["sql_type"] += f'({c["scale"]})'
            c["constraints"] = []
            if c["name"] in pk:
                c["constraints"].append("PK")
            if c["is_identity"]:
                c["constraints"].append("IDENTITY")
            if not c["is_nullable"]:
                c["constraints"].append("NOT NULL")
            for fk in fks:
                if fk["child"] == name and fk["child_column"] == c["name"]:
                    c["constraints"].append(
                        f'FK → {fk["parent"]}.{fk["parent_column"]}'
                    )
            for cols in unique.values():
                if c["name"] in cols:
                    c["constraints"].append("UK(" + ",".join(cols) + ")")
            for entry in filtered_unique.values():
                if c["name"] in entry["columns"]:
                    c["constraints"].append(
                        "UNIQUE("
                        + ",".join(entry["columns"])
                        + ") WHERE "
                        + entry["filter"]
                    )
            if c["default_value"]:
                c["constraints"].append("DEFAULT " + c["default_value"])
        table_checks = [c["definition"] for c in checks if c["table_name"] == name]
        result["tables"][name] = {
            "label": label,
            "columns": fields,
            "primary_key": pk,
            "unique_keys": unique,
            "filtered_unique": filtered_unique,
            "checks": table_checks,
        }
        md += [
            f"## {label} {name}",
            "",
            f"关系模式：{name}(" + ", ".join(c["name"] for c in fields) + ")。",
            f'函数依赖：({", ".join(pk)}) → 其余属性。'
            + (
                "候选键还包括 "
                + "；".join("(" + ",".join(v) + ")" for v in unique.values())
                + "。"
                if unique
                else ""
            ),
            "",
            "| 字段 | 类型 | 约束 | 说明 |",
            "| --- | --- | --- | --- |",
        ]
        md += [
            f'| {c["name"]} | {c["sql_type"]} | {"；".join(c["constraints"])} | {c["description"]} |'
            for c in fields
        ]
        md += [
            "",
            "CHECK：" + ("；".join(table_checks) if table_checks else "无附加取值约束。"),
            "",
        ]
    (ROOT / "docs/design").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs/design/data_dictionary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (ROOT / "docs/design/数据字典与关系模式.md").write_text("\n".join(md), encoding="utf-8")
    print(f'导出 {len(result["tables"])} 张表、{len(columns)} 个字段、{len(fks)} 个外键。')


if __name__ == "__main__":
    export()
