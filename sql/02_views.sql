-- A 档案与评估
CREATE OR ALTER VIEW v_elderly_masked AS
SELECT e.id,e.name,e.identity_mask,e.birth_date,e.address,e.community_id,c.name community_name,
       e.living_alone,e.disabled,e.low_income,e.active
FROM elderly e JOIN community c ON c.id=e.community_id;
GO
CREATE OR ALTER VIEW v_current_assessment AS
SELECT e.id elderly_id,e.name,e.community_id,a.id assessment_id,a.ability_level,a.assessed_on,a.valid_until,
       p.id plan_id,p.status plan_status,p.worker_id,p.starts_on,p.ends_on
FROM elderly e
OUTER APPLY (SELECT TOP 1 * FROM assessment a WHERE a.elderly_id=e.id AND a.assessed_on<=CAST(GETDATE() AS date) ORDER BY a.assessed_on DESC) a
OUTER APPLY (SELECT TOP 1 * FROM care_plan p WHERE p.elderly_id=e.id AND p.status='active'
             AND CAST(GETDATE() AS date) BETWEEN p.starts_on AND p.ends_on ORDER BY p.starts_on DESC) p;
GO
CREATE OR ALTER VIEW v_reassessment_due AS
SELECT * FROM v_current_assessment
WHERE valid_until IS NULL OR valid_until<=DATEADD(day,7,CAST(GETDATE() AS date));
GO
-- B 订单与派单
CREATE OR ALTER VIEW v_dispatch_pool AS
SELECT o.id,o.elderly_id,e.name elderly_name,o.community_id,o.item_id,i.name item_name,
       o.scheduled_at,o.duration_minutes,o.status,o.address,o.unit_price
FROM service_order o JOIN elderly e ON e.id=o.elderly_id JOIN service_item i ON i.id=o.item_id
WHERE o.status IN ('pending','ineligible');
GO
CREATE OR ALTER VIEW v_order_timeline AS
SELECT o.id order_id,o.elderly_id,e.name elderly_name,o.community_id,i.name item_name,o.scheduled_at,
       o.status order_status,o.settlement,a.id assignment_id,a.status assignment_status,a.is_current,
       w.id worker_id,w.name worker_name,a.assigned_at,a.accepted_at,l.checkin_at,l.checkout_at,
       a.service_record,a.confirmed_at,l.valid_hours,l.review_status
FROM service_order o JOIN elderly e ON e.id=o.elderly_id JOIN service_item i ON i.id=o.item_id
LEFT JOIN assignment a ON a.order_id=o.id LEFT JOIN shift s ON s.id=a.shift_id
LEFT JOIN worker w ON w.id=s.worker_id LEFT JOIN work_log l ON l.assignment_id=a.id;
GO
CREATE OR ALTER VIEW v_pending_confirmation AS
SELECT o.id order_id,o.elderly_id,o.community_id,a.id assignment_id,
       CASE WHEN NULLIF(LTRIM(RTRIM(a.service_record)),N'') IS NULL THEN 1 ELSE 0 END missing_record,
       CASE WHEN a.confirmed_at IS NULL THEN 1 ELSE 0 END missing_confirmation,
       CASE WHEN l.valid_hours IS NULL OR l.review_status NOT IN ('auto','approved') THEN 1 ELSE 0 END missing_hours
FROM service_order o JOIN assignment a ON a.order_id=o.id AND a.is_current=1
LEFT JOIN work_log l ON l.assignment_id=a.id WHERE o.status='confirming';
GO
-- C 护工与排班
CREATE OR ALTER VIEW v_shift_capacity AS
SELECT s.*,w.name worker_name,w.agency_id,s.capacity-s.used_slots remaining_slots,
       (SELECT COUNT(*) FROM assignment a WHERE a.shift_id=s.id AND
           (a.status IN ('offered','accepted','completed') OR
            (a.status='terminated' AND EXISTS(SELECT 1 FROM work_log l WHERE l.assignment_id=a.id)))) calculated_slots
FROM shift s JOIN worker w ON w.id=s.worker_id;
GO
CREATE OR ALTER VIEW v_worker_monthly AS
SELECT w.id worker_id,w.name,w.agency_id,DATEFROMPARTS(YEAR(o.scheduled_at),MONTH(o.scheduled_at),1) month,
       COUNT(*) orders_count,SUM(CASE WHEN o.status='completed' THEN 1 ELSE 0 END) completed_count,
       SUM(CASE WHEN o.status='completed' THEN l.valid_hours ELSE 0 END) valid_hours,
       SUM(CASE WHEN o.status='completed' AND o.complaint IS NOT NULL THEN 1 ELSE 0 END) complaint_count,
       CAST(1.0*SUM(CASE WHEN o.status='completed' THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) AS decimal(8,4)) completion_rate,
       CAST(1.0*SUM(CASE WHEN o.status='completed' AND o.complaint IS NOT NULL THEN 1 ELSE 0 END)/
            NULLIF(SUM(CASE WHEN o.status='completed' THEN 1 ELSE 0 END),0) AS decimal(8,4)) complaint_rate
FROM worker w JOIN shift s ON s.worker_id=w.id JOIN assignment a ON a.shift_id=s.id AND a.is_current=1
JOIN service_order o ON o.id=a.order_id LEFT JOIN work_log l ON l.assignment_id=a.id
WHERE o.status<>'cancelled' GROUP BY w.id,w.name,w.agency_id,DATEFROMPARTS(YEAR(o.scheduled_at),MONTH(o.scheduled_at),1);
GO
CREATE OR ALTER VIEW v_work_review AS
SELECT l.*,w.id worker_id,w.name worker_name,w.agency_id,o.id order_id,o.elderly_id,o.community_id,
       o.scheduled_at,o.duration_minutes
FROM work_log l JOIN assignment a ON a.id=l.assignment_id JOIN shift s ON s.id=a.shift_id
JOIN worker w ON w.id=s.worker_id JOIN service_order o ON o.id=a.order_id
WHERE l.review_status='pending' AND l.checkout_at IS NOT NULL;
GO
-- D 健康与应急
CREATE OR ALTER VIEW v_vital_history AS
SELECT v.id,b.device_id,b.elderly_id,e.name elderly_name,r.community_id,r.metric,r.unit,
       v.collected_at,v.received_at,v.value,v.abnormal,v.confirmation,r.lower_bound,r.upper_bound
FROM vital v JOIN device_binding b ON b.id=v.binding_id JOIN elderly e ON e.id=b.elderly_id
JOIN metric_rule r ON r.id=v.rule_id;
GO
CREATE OR ALTER VIEW v_abnormal_vitals AS
SELECT * FROM v_vital_history WHERE abnormal=1 AND confirmation='pending';
GO
CREATE OR ALTER VIEW v_emergency_pending AS
SELECT e.*,p.name elderly_name,
       CASE WHEN responded_at IS NULL AND DATEADD(minute,response_minutes,occurred_at)<=GETDATE() THEN 1 ELSE 0 END response_overdue,
       CASE WHEN arrived_at IS NULL AND DATEADD(minute,arrival_minutes,occurred_at)<=GETDATE() THEN 1 ELSE 0 END arrival_overdue
FROM emergency e JOIN elderly p ON p.id=e.elderly_id WHERE e.status<>'closed';
GO
CREATE OR ALTER VIEW v_emergency_statistics AS
SELECT c.street_id,COUNT(*) event_count,COUNT(e.responded_at) response_samples,
       AVG(CAST(DATEDIFF(second,e.occurred_at,e.responded_at) AS decimal(12,2)))/60 average_response_minutes,
       SUM(CASE WHEN e.escalated_at IS NOT NULL THEN 1 ELSE 0 END) escalated_count
FROM emergency e JOIN community c ON c.id=e.community_id GROUP BY c.street_id;
GO
-- E 补贴与监管
CREATE OR ALTER VIEW v_claim_progress AS
SELECT c.*,e.name elderly_name,i.name item_name,
       (SELECT COUNT(*) FROM claim_item d WHERE d.claim_id=c.id) order_count,
       (SELECT COUNT(*) FROM claim_review r WHERE r.claim_id=c.id) review_count
FROM subsidy_claim c JOIN elderly e ON e.id=c.elderly_id JOIN service_item i ON i.id=c.item_id;
GO
CREATE OR ALTER VIEW v_subsidy_eligible AS
SELECT o.id order_id,o.elderly_id,o.item_id,o.community_id,o.scheduled_at,o.settlement,
       a.ability_level,s.low_income,l.valid_hours,o.price_unit,o.duration_minutes
FROM service_order o JOIN service_item i ON i.id=o.item_id AND i.subsidized=1
JOIN eligibility_snapshot s ON s.order_id=o.id JOIN assessment a ON a.id=s.assessment_id
JOIN assignment d ON d.order_id=o.id AND d.is_current=1 JOIN work_log l ON l.assignment_id=d.id
WHERE o.status='completed' AND d.confirmed_at IS NOT NULL AND d.service_record IS NOT NULL
AND l.review_status IN ('auto','approved') AND NOT EXISTS(SELECT 1 FROM claim_item ci WHERE ci.order_id=o.id);
GO
CREATE OR ALTER VIEW v_quality_restrictions AS
SELECT q.id,q.status,q.restricted_item_id,q.restrict_agency,COALESCE(q.worker_id,s.worker_id) worker_id,
       w.agency_id,q.issue,q.requirement,q.due_on
FROM quality_check q LEFT JOIN assignment a ON a.order_id=q.order_id AND a.is_current=1
LEFT JOIN shift s ON s.id=a.shift_id JOIN worker w ON w.id=COALESCE(q.worker_id,s.worker_id)
WHERE q.status IN ('open','review');
GO
CREATE OR ALTER VIEW v_elderly_cost AS
SELECT o.id order_id,o.elderly_id,o.community_id,o.scheduled_at,o.settlement,c.status claim_status,
       COALESCE(CASE WHEN c.status NOT IN ('rejected','returned') THEN d.amount END,0) expected_subsidy,
       COALESCE(CASE WHEN c.status IN ('approved','paid') THEN d.amount END,0) approved_subsidy,
       o.settlement-COALESCE(CASE WHEN c.status IN ('approved','paid') THEN d.amount END,0) payable
FROM service_order o LEFT JOIN claim_item d ON d.order_id=o.id LEFT JOIN subsidy_claim c ON c.id=d.claim_id
WHERE o.status='completed';
GO
CREATE OR ALTER FUNCTION fn_distance_m(@lon1 float,@lat1 float,@lon2 float,@lat2 float)
RETURNS float AS
BEGIN
    RETURN geography::Point(@lat1,@lon1,4326).STDistance(geography::Point(@lat2,@lon2,4326));
END;
GO
CREATE OR ALTER FUNCTION fn_eligibility(@elderly_id int,@item_id int,@service_date date)
RETURNS TABLE AS RETURN (
    SELECT a.id assessment_id,p.id plan_id,e.low_income,p.worker_id preferred_worker
    FROM elderly e CROSS APPLY (
        SELECT TOP 1 * FROM assessment a WHERE a.elderly_id=e.id AND a.assessed_on<=@service_date
        ORDER BY a.assessed_on DESC
    ) a JOIN care_plan p ON p.elderly_id=e.id AND p.status='active'
    JOIN service_package k ON k.id=p.package_id AND k.ability_level=a.ability_level
    JOIN plan_item i ON i.plan_id=p.id AND i.item_id=@item_id
    WHERE e.id=@elderly_id AND e.active=1 AND a.valid_until>=@service_date
      AND @service_date BETWEEN p.starts_on AND p.ends_on
);
GO
CREATE OR ALTER FUNCTION fn_candidates(@order_id int)
RETURNS TABLE AS RETURN (
    SELECT s.id shift_id,w.id worker_id,w.name,w.agency_id,s.starts_at,s.ends_at,s.capacity-s.used_slots remaining_slots,
           CASE WHEN w.id=g.preferred_worker THEN 0 ELSE 1 END priority
    FROM service_order o CROSS APPLY dbo.fn_eligibility(o.elderly_id,o.item_id,CAST(o.scheduled_at AS date)) g
    JOIN service_item i ON i.id=o.item_id JOIN worker_skill k ON k.item_id=o.item_id
    JOIN worker w ON w.id=k.worker_id AND w.status='active'
    JOIN agency ag ON ag.id=w.agency_id AND ag.active=1
    JOIN worker_area r ON r.worker_id=w.id AND r.community_id=o.community_id
    JOIN shift s ON s.worker_id=w.id AND s.status='published' AND
        (s.used_slots<s.capacity OR EXISTS(SELECT 1 FROM assignment own WHERE own.order_id=o.id AND own.shift_id=s.id AND own.is_current=1))
    JOIN community c ON c.id=o.community_id
    WHERE o.id=@order_id AND o.scheduled_at>=s.starts_at AND DATEADD(minute,o.duration_minutes,o.scheduled_at)<=s.ends_at
      AND dbo.fn_distance_m(o.longitude,o.latitude,c.longitude,c.latitude)<=c.radius_m
      AND (i.certificate_type IS NULL OR EXISTS(SELECT 1 FROM certificate z WHERE z.worker_id=w.id
          AND z.certificate_type=i.certificate_type AND z.level>=i.certificate_level
          AND CAST(o.scheduled_at AS date) BETWEEN z.issued_on AND z.valid_until))
      AND NOT EXISTS(SELECT 1 FROM assignment a JOIN shift t ON t.id=a.shift_id JOIN service_order x ON x.id=a.order_id
          WHERE t.worker_id=w.id AND a.is_current=1 AND a.status IN ('offered','accepted','completed') AND x.id<>o.id
          AND x.scheduled_at<DATEADD(minute,o.duration_minutes,o.scheduled_at)
          AND DATEADD(minute,x.duration_minutes,x.scheduled_at)>o.scheduled_at)
      AND NOT EXISTS(SELECT 1 FROM v_quality_restrictions q WHERE
          ((q.restrict_agency=0 AND q.worker_id=w.id) OR (q.restrict_agency=1 AND q.agency_id=w.agency_id))
          AND (q.restricted_item_id IS NULL OR q.restricted_item_id=o.item_id))
);
GO
