-- 触发器按 inserted/deleted 集合处理，一条语句修改多行时仍保持相同规则。
CREATE OR ALTER TRIGGER tr_assessment_frozen ON assessment AFTER UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d JOIN eligibility_snapshot s ON s.assessment_id=d.id)
        THROW 51101,N'已经用于服务的评估须保留原记录，复评请新增评估',1;
END;
GO
CREATE OR ALTER TRIGGER tr_plan_period ON care_plan AFTER INSERT,UPDATE AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @locked int;
    SELECT @locked=e.id FROM elderly e WITH (UPDLOCK,HOLDLOCK) JOIN inserted i ON i.elderly_id=e.id;
    IF EXISTS(SELECT 1 FROM inserted i JOIN care_plan p ON p.elderly_id=i.elderly_id AND p.id<>i.id
        AND p.status='active' AND i.status='active' AND p.starts_on<=i.ends_on AND p.ends_on>=i.starts_on)
        THROW 51102,N'同一老人不能拥有日期重叠的生效计划',1;
    IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON d.id=i.id JOIN eligibility_snapshot s ON s.plan_id=i.id
        JOIN service_order o ON o.id=s.order_id WHERE i.elderly_id<>d.elderly_id OR i.package_id<>d.package_id
          OR CAST(o.scheduled_at AS date) NOT BETWEEN i.starts_on AND i.ends_on)
        THROW 51103,N'计划变更不能改变已发生服务的依据',1;
END;
GO
CREATE OR ALTER TRIGGER tr_plan_item_frozen ON plan_item AFTER INSERT,UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM eligibility_snapshot s JOIN
        (SELECT plan_id FROM inserted UNION SELECT plan_id FROM deleted) p ON p.plan_id=s.plan_id)
        THROW 51104,N'已经用于服务的计划项目与频次不能变更',1;
END;
GO
CREATE OR ALTER TRIGGER tr_shift_rules ON shift AFTER INSERT,UPDATE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM inserted i JOIN shift s ON s.worker_id=i.worker_id AND s.id<>i.id
        AND s.starts_at<i.ends_at AND s.ends_at>i.starts_at)
        THROW 51105,N'同一护工的班次时间不能重叠',1;
    IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON d.id=i.id WHERE
        (i.worker_id<>d.worker_id OR i.starts_at<>d.starts_at OR i.ends_at<>d.ends_at)
        AND EXISTS(SELECT 1 FROM assignment a WHERE a.shift_id=i.id))
        THROW 51106,N'已派单班次的护工与时间须保留，调整请新建班次',1;
END;
GO
CREATE OR ALTER TRIGGER tr_assignment_slots ON assignment AFTER INSERT,UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    UPDATE s SET used_slots=(SELECT COUNT(*) FROM assignment a WHERE a.shift_id=s.id AND
        (a.status IN ('offered','accepted','completed') OR
         (a.status='terminated' AND EXISTS(SELECT 1 FROM work_log l WHERE l.assignment_id=a.id))))
    FROM shift s JOIN (SELECT shift_id FROM inserted UNION SELECT shift_id FROM deleted) x ON x.shift_id=s.id;
    IF EXISTS(SELECT 1 FROM deleted d JOIN service_order o ON o.id=d.order_id
        LEFT JOIN inserted i ON i.id=d.id WHERE o.status='completed' AND
        (i.id IS NULL OR i.order_id<>d.order_id OR i.shift_id<>d.shift_id OR i.is_current<>d.is_current
         OR ISNULL(i.service_record,N'')<>ISNULL(d.service_record,N'')
         OR ISNULL(i.confirmed_by,0)<>ISNULL(d.confirmed_by,0)
         OR ISNULL(i.confirmed_at,'19000101')<>ISNULL(d.confirmed_at,'19000101')))
        THROW 51107,N'已完成订单的派单、记录与确认不能变更',1;
END;
GO
CREATE OR ALTER TRIGGER tr_order_completion ON service_order AFTER INSERT,UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d LEFT JOIN inserted i ON i.id=d.id WHERE d.status='completed' AND
       (i.id IS NULL OR i.status<>d.status OR i.elderly_id<>d.elderly_id OR i.item_id<>d.item_id OR i.community_id<>d.community_id
        OR i.scheduled_at<>d.scheduled_at OR i.duration_minutes<>d.duration_minutes OR i.unit_price<>d.unit_price
        OR i.price_unit<>d.price_unit OR i.address<>d.address OR i.longitude<>d.longitude OR i.latitude<>d.latitude
        OR i.created_by<>d.created_by OR i.channel<>d.channel OR i.created_at<>d.created_at
        OR ISNULL(i.completed_at,'19000101')<>ISNULL(d.completed_at,'19000101')
        OR ISNULL(i.settlement,-1)<>ISNULL(d.settlement,-1)))
        THROW 51108,N'已完成订单的服务与结算依据不能修改',1;
    IF EXISTS(SELECT 1 FROM inserted i LEFT JOIN deleted d ON d.id=i.id
        WHERE i.status='completed' AND ISNULL(d.status,'')<>'completed'
          AND (i.settlement IS NULL OR i.completed_at IS NULL))
        THROW 51122,N'完成订单必须同时写入结算金额与完成时间',1;
    IF EXISTS(SELECT 1 FROM inserted i LEFT JOIN deleted d ON d.id=i.id WHERE i.status='completed' AND ISNULL(d.status,'')<>'completed'
        AND NOT EXISTS(SELECT 1 FROM assignment a JOIN work_log l ON l.assignment_id=a.id JOIN eligibility_snapshot e ON e.order_id=a.order_id
            WHERE a.order_id=i.id AND a.is_current=1 AND NULLIF(LTRIM(RTRIM(a.service_record)),N'') IS NOT NULL
            AND a.confirmed_at>=l.checkout_at AND l.review_status IN ('auto','approved') AND l.valid_hours>0))
        THROW 51109,N'完成订单必须具备服务记录、确认、有效工时和资格快照',1;
    UPDATE w SET total_hours=w.total_hours+t.hours,points=w.points+t.orders
    FROM worker w JOIN (
        SELECT s.worker_id,SUM(l.valid_hours) hours,COUNT(*) orders
        FROM inserted i LEFT JOIN deleted d ON d.id=i.id JOIN assignment a ON a.order_id=i.id AND a.is_current=1
        JOIN shift s ON s.id=a.shift_id JOIN work_log l ON l.assignment_id=a.id
        WHERE i.status='completed' AND ISNULL(d.status,'')<>'completed' GROUP BY s.worker_id
    ) t ON t.worker_id=w.id;
END;
GO
CREATE OR ALTER TRIGGER tr_work_log_frozen ON work_log AFTER UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d JOIN assignment a ON a.id=d.assignment_id JOIN service_order o ON o.id=a.order_id WHERE o.status='completed')
        THROW 51110,N'已完成订单的工时不能修改',1;
END;
GO
CREATE OR ALTER TRIGGER tr_snapshot_frozen ON eligibility_snapshot AFTER UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted) THROW 51111,N'服务资格快照写入后不能变更',1;
END;
GO
CREATE OR ALTER TRIGGER tr_binding_period ON device_binding AFTER INSERT,UPDATE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM inserted i JOIN device_binding b ON b.device_id=i.device_id AND b.id<>i.id
        AND i.bound_at<COALESCE(b.unbound_at,'99991231') AND b.bound_at<COALESCE(i.unbound_at,'99991231'))
        THROW 51112,N'同一设备的绑定时间不能重叠',1;
    IF EXISTS(SELECT 1 FROM inserted i JOIN deleted d ON d.id=i.id JOIN vital v ON v.binding_id=i.id
        WHERE i.device_id<>d.device_id OR i.elderly_id<>d.elderly_id OR v.collected_at<i.bound_at
            OR v.collected_at>=COALESCE(i.unbound_at,'99991231'))
        THROW 51113,N'设备换绑不能改变已采集数据的归属',1;
END;
GO
CREATE OR ALTER TRIGGER tr_vital_threshold ON vital AFTER INSERT AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM inserted i JOIN device_binding b ON b.id=i.binding_id
        JOIN elderly e ON e.id=b.elderly_id JOIN metric_rule r ON r.id=i.rule_id
        WHERE r.community_id<>e.community_id)
        THROW 51120,N'体征阈值须属于老人当前社区',1;
    IF EXISTS(SELECT 1 FROM inserted i JOIN device_binding b ON b.id=i.binding_id
        WHERE i.collected_at<b.bound_at OR i.collected_at>=COALESCE(b.unbound_at,'99991231'))
        THROW 51114,N'采集时间不在设备绑定区间内',1;
    UPDATE v SET abnormal=CASE WHEN i.value<r.lower_bound OR i.value>r.upper_bound THEN 1 ELSE 0 END,
                 confirmation=CASE WHEN i.value<r.lower_bound OR i.value>r.upper_bound THEN 'pending' ELSE 'normal' END
    FROM vital v JOIN inserted i ON i.id=v.id JOIN metric_rule r ON r.id=i.rule_id;
END;
GO
CREATE OR ALTER TRIGGER tr_metric_frozen ON metric_rule AFTER UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d JOIN vital v ON v.rule_id=d.id)
        THROW 51115,N'已使用的体征阈值须保留原记录',1;
END;
GO
CREATE OR ALTER TRIGGER tr_policy_period ON subsidy_policy AFTER INSERT,UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d JOIN claim_item c ON c.policy_id=d.id)
        THROW 51116,N'已用于申报的政策版本不能变更',1;
    IF EXISTS(SELECT 1 FROM inserted i JOIN subsidy_policy p ON p.id<>i.id AND p.district_id=i.district_id
        AND p.item_id=i.item_id AND p.ability_level=i.ability_level AND p.low_income_only=i.low_income_only
        AND i.starts_on<=p.ends_on AND p.starts_on<=i.ends_on)
        THROW 51117,N'同一适用条件的补贴政策月份不能重叠',1;
END;
GO
CREATE OR ALTER TRIGGER tr_claim_frozen ON subsidy_claim AFTER UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM deleted d LEFT JOIN inserted i ON i.id=d.id WHERE d.status IN ('approved','paid') AND
       (i.id IS NULL OR i.amount<>d.amount OR i.elderly_id<>d.elderly_id OR i.item_id<>d.item_id OR i.month<>d.month
        OR i.community_id<>d.community_id OR i.evidence<>d.evidence OR i.status NOT IN ('approved','paid')
        OR ISNULL(i.submitted_by,0)<>ISNULL(d.submitted_by,0)
        OR ISNULL(i.submitted_at,'19000101')<>ISNULL(d.submitted_at,'19000101')
        OR (d.status='paid' AND (i.status<>'paid' OR ISNULL(i.payment_reference,'')<>d.payment_reference
            OR ISNULL(i.paid_by,0)<>ISNULL(d.paid_by,0)
            OR ISNULL(i.paid_at,'19000101')<>ISNULL(d.paid_at,'19000101')))))
        THROW 51118,N'终审后的申报材料和核定金额不能修改',1;
END;
GO
CREATE OR ALTER TRIGGER tr_claim_item_frozen ON claim_item AFTER INSERT,UPDATE,DELETE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM subsidy_claim c JOIN
        (SELECT claim_id FROM inserted UNION SELECT claim_id FROM deleted) x ON x.claim_id=c.id
        WHERE c.status IN ('approved','paid'))
        THROW 51119,N'终审后的申报明细不能修改',1;
END;
GO
CREATE OR ALTER TRIGGER tr_quality_order_completed ON quality_check AFTER INSERT,UPDATE AS
BEGIN
    SET NOCOUNT ON;
    IF EXISTS(SELECT 1 FROM inserted i JOIN service_order o ON o.id=i.order_id WHERE o.status<>'completed')
        THROW 51121,N'订单抽查只能针对已完成服务',1;
END;
GO
