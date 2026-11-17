-- A1：有有效照护计划的重度失能老人及责任护工；APPLY 与窗口函数。
-- query: A1.a

SELECT e.id elderly_id,e.name,w.name worker_name,p.id plan_id
FROM elderly e CROSS APPLY
    (SELECT TOP 1 *
     FROM assessment a
     WHERE a.elderly_id = e.id
         AND a.assessed_on <= CAST(GETDATE() AS date)
     ORDER BY a.assessed_on DESC) a
JOIN care_plan p ON p.elderly_id = e.id
JOIN worker w ON w.id = p.worker_id
WHERE e.active = 1
    AND a.ability_level = 3
    AND a.valid_until >= CAST(GETDATE() AS date)
    AND p.status = 'active'
    AND CAST(GETDATE() AS date) BETWEEN p.starts_on AND p.ends_on;

-- query: A1.b
WITH ranked AS
    (SELECT *,ROW_NUMBER() OVER(PARTITION BY elderly_id
            ORDER BY assessed_on DESC) rn
     FROM assessment
     WHERE assessed_on <= CAST(GETDATE() AS date))
SELECT e.id elderly_id,e.name,w.name worker_name,p.id plan_id
FROM ranked a
JOIN elderly e ON e.id = a.elderly_id
JOIN care_plan p ON p.elderly_id = e.id
JOIN worker w ON w.id = p.worker_id
WHERE a.rn = 1
    AND e.active = 1
    AND a.ability_level = 3
    AND a.valid_until >= CAST(GETDATE() AS date)
    AND p.status = 'active'
    AND CAST(GETDATE() AS date) BETWEEN p.starts_on AND p.ends_on;

-- A2：未来7天到期的最新评估；NOT EXISTS 与反连接。
-- query: A2.a

SELECT a.elderly_id,a.assessed_on,a.valid_until
FROM assessment a
WHERE a.assessed_on <= CAST(GETDATE() AS date)
    AND a.valid_until BETWEEN CAST(GETDATE() AS date) AND DATEADD(DAY,
            7, CAST(GETDATE() AS date))
    AND NOT EXISTS
        (SELECT 1
         FROM assessment n
         WHERE n.elderly_id = a.elderly_id
            AND n.assessed_on > a.assessed_on
            AND n.assessed_on <= CAST(GETDATE() AS date));

-- query: A2.b

SELECT a.elderly_id,a.assessed_on,a.valid_until
FROM assessment a
LEFT JOIN assessment n ON n.elderly_id = a.elderly_id
AND n.assessed_on > a.assessed_on
AND n.assessed_on <= CAST(GETDATE() AS date)
WHERE a.assessed_on <= CAST(GETDATE() AS date)
    AND a.valid_until BETWEEN CAST(GETDATE() AS date) AND DATEADD(DAY,
            7, CAST(GETDATE() AS date))
    AND n.id IS NULL;

-- A3：社区在册老人按等级统计，保留零人数等级；相关子查询与预聚合。
-- query: A3.a

SELECT c.id community_id,l.level,

    (SELECT COUNT(*)
     FROM v_current_assessment a
     JOIN elderly e ON e.id = a.elderly_id
     WHERE a.community_id = c.id
         AND a.ability_level = l.level
         AND e.active = 1) people
FROM community c
CROSS JOIN(
           VALUES(0),(1),(2),(3)) l(level);

-- query: A3.b
WITH counts AS
    (SELECT a.community_id,a.ability_level,COUNT(*) people
     FROM v_current_assessment a
     JOIN elderly e ON e.id = a.elderly_id
     WHERE e.active = 1
     GROUP BY a.community_id,a.ability_level)
SELECT c.id community_id,l.level,COALESCE(n.people, 0) people
FROM community c
CROSS JOIN(
           VALUES(0),(1),(2),(3)) l(level)
LEFT JOIN counts n ON n.community_id = c.id
AND n.ability_level = l.level;
