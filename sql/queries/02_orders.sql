-- B1：订单最终服务人、工时与历史派单次数；直接连接与分层CTE。
-- query: B1.a

SELECT o.id order_id,w.name worker_name,l.valid_hours,o.settlement,

    (SELECT COUNT(*)
     FROM assignment h
     WHERE h.order_id = o.id) assignment_count
FROM service_order o
LEFT JOIN assignment a ON a.order_id = o.id
AND a.is_current = 1
LEFT JOIN shift s ON s.id = a.shift_id
LEFT JOIN worker w ON w.id = s.worker_id
LEFT JOIN work_log l ON l.assignment_id = a.id;

-- query: B1.b
WITH current_service AS
    (SELECT a.order_id,w.name worker_name,l.valid_hours
     FROM assignment a
     JOIN shift s ON s.id = a.shift_id
     JOIN worker w ON w.id = s.worker_id
     LEFT JOIN work_log l ON l.assignment_id = a.id
     WHERE a.is_current = 1),
     history AS
    (SELECT order_id,COUNT(*) assignment_count
     FROM assignment
     GROUP BY order_id)
SELECT o.id order_id,c.worker_name,c.valid_hours,o.settlement,
       COALESCE(h.assignment_count, 0) assignment_count
FROM service_order o
LEFT JOIN current_service c ON c.order_id = o.id
LEFT JOIN history h ON h.order_id = o.id;

-- B2：接单超过15分钟的订单；EXISTS 与连接。
-- query: B2.a

SELECT o.id,o.elderly_id,o.scheduled_at
FROM service_order o
WHERE o.status = 'offered'
    AND EXISTS
        (SELECT 1
         FROM assignment a
         WHERE a.order_id = o.id
            AND a.is_current = 1
            AND a.status = 'offered'
            AND a.assigned_at <= DATEADD(MINUTE, -15, GETDATE()));

-- query: B2.b

SELECT o.id,o.elderly_id,o.scheduled_at
FROM service_order o
JOIN assignment a ON a.order_id = o.id
WHERE o.status = 'offered'
    AND a.is_current = 1
    AND a.status = 'offered'
    AND a.assigned_at <= DATEADD(MINUTE, -15, GETDATE());

-- B3：待确认订单缺项；CASE 与分项UNION ALL后聚合。
-- query: B3.a

SELECT order_id,missing_record,missing_confirmation,missing_hours
FROM v_pending_confirmation;

-- query: B3.b
WITH records AS
    (SELECT o.id,a.service_record,a.confirmed_at,l.valid_hours,l.review_status
     FROM service_order o
     JOIN assignment a ON a.order_id = o.id
     AND a.is_current = 1
     LEFT JOIN work_log l ON l.assignment_id = a.id
     WHERE o.status = 'confirming'),
     flags AS
    (SELECT id,1 kind
     FROM records
     WHERE NULLIF(LTRIM(RTRIM(service_record)), N'') IS NULL
     UNION ALL SELECT id,2
     FROM records
     WHERE confirmed_at IS NULL
     UNION ALL SELECT id,3
     FROM records
     WHERE valid_hours IS NULL
         OR review_status NOT IN ('auto','approved'))
SELECT r.id order_id,MAX(CASE WHEN f.kind = 1 THEN 1 ELSE 0
            END) missing_record,
       MAX(CASE WHEN f.kind = 2 THEN 1 ELSE 0
           END) missing_confirmation, MAX(CASE WHEN f.kind = 3 THEN 1 ELSE 0
            END) missing_hours
FROM records r
LEFT JOIN flags f ON f.id = r.id
GROUP BY r.id;
