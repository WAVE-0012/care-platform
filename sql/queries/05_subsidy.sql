-- E1：申报、明细政策、订单工时及审核次数；相关子查询与审核预聚合。
-- query: E1.a

SELECT c.id claim_id,d.order_id,p.name policy_name,d.amount,l.valid_hours,

    (SELECT COUNT(*)
     FROM claim_review r
     WHERE r.claim_id = c.id) reviews
FROM subsidy_claim c
JOIN claim_item d ON d.claim_id = c.id
JOIN subsidy_policy p ON p.id = d.policy_id
JOIN assignment a ON a.order_id = d.order_id
AND a.is_current = 1
JOIN work_log l ON l.assignment_id = a.id;

-- query: E1.b
WITH reviews AS
    (SELECT claim_id,COUNT(*) reviews
     FROM claim_review
     GROUP BY claim_id),
     details AS
    (SELECT d.claim_id,d.order_id,p.name policy_name,d.amount,l.valid_hours
     FROM claim_item d
     JOIN subsidy_policy p ON p.id = d.policy_id
     JOIN assignment a ON a.order_id = d.order_id
     AND a.is_current = 1
     JOIN work_log l ON l.assignment_id = a.id)
SELECT c.id claim_id,d.order_id,d.policy_name,d.amount,d.valid_hours,COALESCE(r.reviews,
            0) reviews
FROM subsidy_claim c
JOIN details d ON d.claim_id = c.id
LEFT JOIN reviews r ON r.claim_id = c.id;

-- E2：当前受整改限制的护工；两路EXISTS与限制集合UNION。
-- query: E2.a

SELECT w.id,w.name
FROM worker w
WHERE EXISTS
        (SELECT 1
         FROM v_quality_restrictions q
         WHERE q.restrict_agency = 0
            AND q.worker_id = w.id)
    OR EXISTS
        (SELECT 1
         FROM v_quality_restrictions q
         WHERE q.restrict_agency = 1
            AND q.agency_id = w.agency_id);

-- query: E2.b
WITH RESTRICTED AS
    (SELECT worker_id
     FROM v_quality_restrictions
     WHERE restrict_agency = 0
     UNION SELECT w.id
     FROM worker w
     JOIN v_quality_restrictions q ON q.agency_id = w.agency_id
     WHERE q.restrict_agency = 1)
SELECT w.id,w.name
FROM worker w
JOIN RESTRICTED r ON r.worker_id = w.id;

-- E3：老人完成服务费用、核定补贴与自付；LEFT JOIN 与按申报情况UNION ALL。
-- query: E3.a

SELECT o.id,o.elderly_id,o.settlement,
       COALESCE(CASE WHEN c.status IN ('approved', 'paid') THEN d.amount
            END, 0) subsidy,
       o.settlement - COALESCE(CASE WHEN c.status IN ('approved',
            'paid') THEN d.amount
            END, 0) payable
FROM service_order o
LEFT JOIN claim_item d ON d.order_id = o.id
LEFT JOIN subsidy_claim c ON c.id = d.claim_id
WHERE o.status = 'completed';

-- query: E3.b

SELECT o.id,o.elderly_id,o.settlement,
       CASE WHEN c.status IN ('approved','paid') THEN d.amount ELSE 0
       END subsidy, o.settlement - CASE WHEN c.status IN ('approved','paid') THEN d.amount ELSE 0
            END payable
FROM service_order o
JOIN claim_item d ON d.order_id = o.id
JOIN subsidy_claim c ON c.id = d.claim_id
WHERE o.status = 'completed'
UNION ALL
SELECT o.id,o.elderly_id,o.settlement,CAST(0 AS decimal(12,
            2)),o.settlement
FROM service_order o
WHERE o.status = 'completed'
    AND NOT EXISTS
        (SELECT 1
         FROM claim_item d
         WHERE d.order_id = o.id);
