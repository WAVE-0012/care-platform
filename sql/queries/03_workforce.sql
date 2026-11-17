-- C1：月有效工时、完成数与投诉数；条件聚合与分指标预聚合。
-- query: C1.a

SELECT w.id worker_id,CONVERT(char(7), o.scheduled_at, 120) month,COUNT(*) orders_count,
            SUM(CASE
            WHEN o.status = 'completed' THEN 1 ELSE 0
            END) completed_count,
            SUM(CASE
            WHEN o.status = 'completed' THEN l.valid_hours ELSE 0
            END) valid_hours,
            SUM(CASE
            WHEN o.status = 'completed'
            AND o.complaint IS NOT NULL THEN 1 ELSE 0
            END) complaint_count
FROM worker w
JOIN shift s ON s.worker_id = w.id
JOIN assignment a ON a.shift_id = s.id
AND a.is_current = 1
JOIN service_order o ON o.id = a.order_id
LEFT JOIN work_log l ON l.assignment_id = a.id
WHERE o.status <> 'cancelled'
GROUP BY w.id,CONVERT(char(7), o.scheduled_at, 120);

-- query: C1.b
WITH service AS
    (SELECT s.worker_id,CONVERT(char(7), o.scheduled_at, 120) month,o.status,o.complaint,
            l.valid_hours
     FROM shift s
     JOIN assignment a ON a.shift_id = s.id
     AND a.is_current = 1
     JOIN service_order o ON o.id = a.order_id
     LEFT JOIN work_log l ON l.assignment_id = a.id
     WHERE o.status <> 'cancelled'),
     totals AS
    (SELECT worker_id,month,COUNT(*) orders_count
     FROM service
     GROUP BY worker_id,month),
     done AS
    (SELECT worker_id,month,COUNT(*) completed_count,SUM(valid_hours) valid_hours,
            COUNT(complaint) complaint_count
     FROM service
     WHERE status = 'completed'
     GROUP BY worker_id,month)
SELECT t.worker_id,t.month,t.orders_count,COALESCE(d.completed_count,
            0) completed_count,
       COALESCE(d.valid_hours, 0) valid_hours,COALESCE(d.complaint_count,
            0) complaint_count
FROM totals t
LEFT JOIN done d ON d.worker_id = t.worker_id
AND d.month = t.month;

-- C2：持有效中级及以上养老护理员证书的在岗护工；EXISTS 与连接去重。
-- query: C2.a

SELECT w.id,w.name
FROM worker w
WHERE w.status = 'active'
    AND EXISTS
        (SELECT 1
         FROM certificate c
         WHERE c.worker_id = w.id
            AND c.certificate_type = N'养老护理员'
            AND c.level >= 2
            AND CAST(GETDATE() AS date) BETWEEN c.issued_on AND c.valid_until);

-- query: C2.b

SELECT DISTINCT w.id,w.name
FROM worker w
JOIN certificate c ON c.worker_id = w.id
WHERE w.status = 'active'
    AND c.certificate_type = N'养老护理员'
    AND c.level >= 2
    AND CAST(GETDATE() AS date) BETWEEN c.issued_on AND c.valid_until;

-- C3：班次保存名额与派单重算名额；相关聚合与分组连接。
-- query: C3.a

SELECT id,used_slots,calculated_slots
FROM v_shift_capacity;

-- query: C3.b
WITH counts AS
    (SELECT a.shift_id,COUNT(*) slots
     FROM assignment a
     LEFT JOIN work_log l ON l.assignment_id = a.id
     WHERE a.status IN ('offered','accepted','completed')
         OR (a.status = 'terminated'
            AND l.id IS NOT NULL)
     GROUP BY a.shift_id)
SELECT s.id,s.used_slots,COALESCE(c.slots, 0) calculated_slots
FROM shift s
LEFT JOIN counts c ON c.shift_id = s.id;
