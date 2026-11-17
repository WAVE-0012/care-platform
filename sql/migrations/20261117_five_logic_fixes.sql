-- 由 scripts/manage.py init/migrate 在同一事务内执行，重复执行不增加表或重复约束。
-- 有历史问题时列出记录并中止，不自动改值、删行或合并体征。
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @locked_rows bigint;
SELECT @locked_rows=COUNT_BIG(*) FROM dbo.service_item WITH(TABLOCKX,HOLDLOCK);
SELECT @locked_rows=COUNT_BIG(*) FROM dbo.vital WITH(TABLOCKX,HOLDLOCK);

IF EXISTS(SELECT 1 FROM dbo.service_item WHERE NOT (
    (certificate_type IS NULL AND certificate_level IS NULL) OR
    (certificate_type IS NOT NULL AND certificate_level IS NOT NULL AND certificate_level BETWEEN 1 AND 3)))
BEGIN
    SELECT id,name,certificate_type,certificate_level FROM dbo.service_item WHERE NOT (
        (certificate_type IS NULL AND certificate_level IS NULL) OR
        (certificate_type IS NOT NULL AND certificate_level IS NOT NULL AND certificate_level BETWEEN 1 AND 3))
    ORDER BY id;
    THROW 51201,N'存在证书类型与等级不匹配的服务项目，请确认上述记录后重新更新',1;
END;

DECLARE @duplicate_keys TABLE(device_id int,collected_at datetime2(0),metric varchar(24));
INSERT @duplicate_keys(device_id,collected_at,metric)
SELECT b.device_id,v.collected_at,r.metric FROM dbo.vital v
JOIN dbo.device_binding b ON b.id=v.binding_id
JOIN dbo.metric_rule r ON r.id=v.rule_id
GROUP BY b.device_id,v.collected_at,r.metric HAVING COUNT_BIG(*)>1;
IF EXISTS(SELECT 1 FROM @duplicate_keys)
BEGIN
    SELECT v.id,b.device_id,v.collected_at,r.metric,v.binding_id,v.rule_id
    FROM dbo.vital v JOIN dbo.device_binding b ON b.id=v.binding_id
    JOIN dbo.metric_rule r ON r.id=v.rule_id
    JOIN @duplicate_keys d ON d.device_id=b.device_id AND d.collected_at=v.collected_at AND d.metric=r.metric
    ORDER BY b.device_id,v.collected_at,r.metric,v.id;
    THROW 51202,N'存在同设备、采集时间及指标的重复体征，请确认上述记录后重新更新',1;
END;

IF NOT EXISTS(SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id=OBJECT_ID(N'dbo.service_item') AND name=N'CK_service_item_certificate_pair')
    ALTER TABLE dbo.service_item WITH CHECK ADD CONSTRAINT CK_service_item_certificate_pair CHECK (
        (certificate_type IS NULL AND certificate_level IS NULL) OR
        (certificate_type IS NOT NULL AND certificate_level IS NOT NULL AND certificate_level BETWEEN 1 AND 3));
ALTER TABLE dbo.service_item WITH CHECK CHECK CONSTRAINT CK_service_item_certificate_pair;
GO
