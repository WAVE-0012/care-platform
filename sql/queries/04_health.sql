-- D1：街道事件数、响应样本数及平均响应时长；直接聚合与先社区聚合。
-- query: D1.a

SELECT a.id street_id,a.name,COUNT(*) event_count,COUNT(e.responded_at) response_samples,
       CAST(AVG(CAST(DATEDIFF(SECOND, e.occurred_at, e.responded_at) AS decimal(14,
            4))) / 60 AS decimal(14,
            4)) average_minutes
FROM emergency e
JOIN community c ON c.id = e.community_id
JOIN area a ON a.id = c.street_id
GROUP BY a.id,a.name;

-- query: D1.b
WITH counts AS
    (SELECT community_id,COUNT(*) event_count,COUNT(responded_at) response_samples,
            SUM(CAST(DATEDIFF(SECOND, occurred_at, responded_at) AS decimal(14,
            4))) seconds_sum
     FROM emergency
     GROUP BY community_id)
SELECT a.id street_id,a.name,SUM(n.event_count) event_count,SUM(n.response_samples) response_samples,
       CAST(SUM(n.seconds_sum) / NULLIF(SUM(n.response_samples), 0) / 60 AS decimal(14,
            4)) average_minutes
FROM counts n
JOIN community c ON c.id = n.community_id
JOIN area a ON a.id = c.street_id
GROUP BY a.id,a.name;

-- D2：指定老人历史体征；直接关联与分层CTE。
-- query: D2.a

SELECT v.id,b.elderly_id,b.device_id,v.collected_at,r.metric,v.value
FROM vital v
JOIN device_binding b ON b.id = v.binding_id
JOIN metric_rule r ON r.id = v.rule_id
WHERE b.elderly_id = 1;

-- query: D2.b
WITH bindings AS
    (SELECT id,device_id,elderly_id
     FROM device_binding
     WHERE elderly_id = 1),
     samples AS
    (SELECT v.id,v.binding_id,v.collected_at,r.metric,v.value
     FROM vital v
     JOIN metric_rule r ON r.id = v.rule_id)
SELECT s.id,b.elderly_id,b.device_id,s.collected_at,s.metric,s.value
FROM bindings b
JOIN samples s ON s.binding_id = b.id;

-- D3：响应超时或通知失败的未关闭事件；EXISTS 与通知预聚合。
-- query: D3.a

SELECT e.id,e.elderly_id
FROM emergency e
WHERE e.status <> 'closed'
    AND ((e.responded_at IS NULL
          AND DATEADD(MINUTE, e.response_minutes, e.occurred_at) <= GETDATE())
         OR EXISTS
            (SELECT 1
            FROM notification n
            WHERE n.event_id = e.id
            AND n.status IN ('failed', 'manual')));

-- query: D3.b
WITH failed AS
    (SELECT event_id
     FROM notification
     WHERE status IN ('failed','manual')
     GROUP BY event_id)
SELECT e.id,e.elderly_id
FROM emergency e
LEFT JOIN failed f ON f.event_id = e.id
WHERE e.status <> 'closed'
    AND ((e.responded_at IS NULL
          AND DATEADD(MINUTE, e.response_minutes, e.occurred_at) <= GETDATE())
         OR f.event_id IS NOT NULL);
