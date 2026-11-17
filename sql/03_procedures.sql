CREATE OR ALTER PROCEDURE sp_create_plan
    @elderly_id int,@package_id int,@worker_id int,@starts_on date,@ends_on date
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @locked int,@level tinyint,@valid_until date;
        SELECT @locked=id FROM elderly WITH (UPDLOCK,HOLDLOCK) WHERE id=@elderly_id;
        SELECT TOP 1 @level=ability_level,@valid_until=valid_until FROM assessment WHERE elderly_id=@elderly_id
            AND assessed_on<=@starts_on ORDER BY assessed_on DESC;
        IF @level IS NULL OR @valid_until<@starts_on OR NOT EXISTS(SELECT 1 FROM service_package WHERE id=@package_id AND ability_level=@level AND active=1)
            THROW 51001,N'评估等级与服务包不匹配，或评估已过期',1;
        IF EXISTS(SELECT 1 FROM care_plan WHERE elderly_id=@elderly_id AND status='active' AND starts_on<=@ends_on AND ends_on>=@starts_on)
            THROW 51002,N'生效照护计划的日期不能重叠',1;
        INSERT care_plan(elderly_id,package_id,worker_id,starts_on,ends_on) VALUES(@elderly_id,@package_id,@worker_id,@starts_on,@ends_on);
        DECLARE @id int=SCOPE_IDENTITY();
        INSERT plan_item SELECT @id,item_id,frequency,period FROM package_item WHERE package_id=@package_id;
        COMMIT; SELECT @id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_publish_shift
    @worker_id int,@starts_at datetime2(0),@ends_at datetime2(0),@capacity int
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @ends_at<=@starts_at THROW 51024,N'班次结束时间须晚于开始时间',1;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @id int;
        SELECT @id=id FROM worker WITH (UPDLOCK,HOLDLOCK) WHERE id=@worker_id;
        IF NOT EXISTS(SELECT 1 FROM worker WHERE id=@worker_id AND status='active'
            AND CAST(@starts_at AS time)>=available_from AND CAST(@ends_at AS time)<=available_until)
            THROW 51003,N'班次须位于在岗护工的可服务时段内',1;
        IF EXISTS(SELECT 1 FROM shift WHERE worker_id=@worker_id AND starts_at<@ends_at AND ends_at>@starts_at)
            THROW 51004,N'同一护工的班次不能重叠',1;
        INSERT shift(worker_id,starts_at,ends_at,capacity) VALUES(@worker_id,@starts_at,@ends_at,@capacity);
        SET @id=SCOPE_IDENTITY();
        COMMIT; SELECT @id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_dispatch
    @order_id int,@shift_id int,@actor_id int,@reason nvarchar(200)=NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @status varchar(16),@worker int,@locked int;
        SELECT @status=status FROM service_order WITH (UPDLOCK,HOLDLOCK) WHERE id=@order_id;
        IF @status IS NULL OR @status NOT IN ('pending','ineligible','offered','accepted')
            THROW 51005,N'当前订单状态不能派单',1;
        SELECT @worker=worker_id FROM shift WHERE id=@shift_id;
        SELECT @locked=id FROM worker WITH (UPDLOCK,HOLDLOCK) WHERE id=@worker;
        IF EXISTS(SELECT 1 FROM assignment WHERE order_id=@order_id AND is_current=1)
        BEGIN
            IF NULLIF(LTRIM(RTRIM(@reason)),N'') IS NULL THROW 51006,N'改派需要填写原因',1;
            UPDATE assignment SET status='reassigned',is_current=0,reason=@reason WHERE order_id=@order_id AND is_current=1;
        END;
        IF NOT EXISTS(SELECT 1 FROM dbo.fn_candidates(@order_id) WHERE shift_id=@shift_id)
            THROW 51007,N'护工的资质、区域、排班、名额或整改条件不满足派单要求',1;
        INSERT assignment(order_id,shift_id,dispatcher_id) VALUES(@order_id,@shift_id,@actor_id);
        DECLARE @assignment_id int=SCOPE_IDENTITY();
        UPDATE service_order SET status='offered' WHERE id=@order_id;
        INSERT audit_log(entity,entity_id,action,actor_id,detail)
            VALUES('order',@order_id,'dispatch',@actor_id,COALESCE(@reason,N'首次派单'));
        COMMIT; SELECT @assignment_id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_expire_services @now datetime2(0)=NULL AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @now=COALESCE(@now,SYSDATETIME());
    BEGIN TRY
        BEGIN TRANSACTION;
        UPDATE p SET status='paused' FROM care_plan p
        OUTER APPLY(SELECT TOP 1 a.valid_until FROM assessment a WHERE a.elderly_id=p.elderly_id
                    AND a.assessed_on<=CAST(@now AS date) ORDER BY a.assessed_on DESC) a
        WHERE p.status='active' AND (a.valid_until IS NULL OR a.valid_until<CAST(@now AS date));
        DECLARE @plans int=@@ROWCOUNT;
        UPDATE a SET status=CASE WHEN DATEADD(minute,15,a.assigned_at)<=@now AND a.status='offered' THEN 'timeout' ELSE 'invalid' END,
                     is_current=0,reason=N'定时任务释放派单'
        FROM assignment a JOIN service_order o ON o.id=a.order_id
        WHERE a.is_current=1 AND o.status IN ('offered','accepted') AND
              ((a.status='offered' AND DATEADD(minute,15,a.assigned_at)<=@now)
               OR NOT EXISTS(SELECT 1 FROM dbo.fn_eligibility(o.elderly_id,o.item_id,CAST(o.scheduled_at AS date))));
        DECLARE @released int=@@ROWCOUNT;
        UPDATE o SET status=CASE WHEN EXISTS(SELECT 1 FROM dbo.fn_eligibility(o.elderly_id,o.item_id,CAST(o.scheduled_at AS date)))
                                THEN 'pending' ELSE 'ineligible' END
        FROM service_order o WHERE o.status IN ('offered','accepted','pending','ineligible')
        AND NOT EXISTS(SELECT 1 FROM assignment a WHERE a.order_id=o.id AND a.is_current=1);
        COMMIT; SELECT @plans paused_plans,@released released_assignments;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_finish_order @order_id int,@actor_id int=NULL AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @status varchar(16),@hours decimal(8,2),@assignment int,@price decimal(10,2),@unit varchar(8),@minutes int;
        SELECT @status=status,@price=unit_price,@unit=price_unit,@minutes=duration_minutes
            FROM service_order WITH (UPDLOCK,HOLDLOCK) WHERE id=@order_id;
        IF @status='completed' BEGIN COMMIT; SELECT @order_id id; RETURN; END;
        IF @status IS NULL OR @status<>'confirming' THROW 51008,N'订单尚未进入待确认状态',1;
        SELECT @assignment=a.id,@hours=l.valid_hours FROM assignment a JOIN work_log l ON l.assignment_id=a.id
        WHERE a.order_id=@order_id AND a.is_current=1 AND NULLIF(LTRIM(RTRIM(a.service_record)),N'') IS NOT NULL
          AND a.confirmed_at>=l.checkout_at AND l.valid_hours>0 AND l.review_status IN ('auto','approved')
          AND EXISTS(SELECT 1 FROM eligibility_snapshot e WHERE e.order_id=@order_id);
        IF @hours IS NULL THROW 51009,N'服务记录、服务确认或有效工时尚未齐全',1;
        UPDATE service_order SET status='completed',completed_at=SYSDATETIME(),
            settlement=ROUND(@price*CASE WHEN @unit='visit' THEN 1 WHEN @hours<@minutes/60.0 THEN @hours ELSE @minutes/60.0 END,2)
        WHERE id=@order_id;
        UPDATE assignment SET status='completed' WHERE id=@assignment;
        INSERT audit_log(entity,entity_id,action,actor_id,detail)
            VALUES('order',@order_id,'complete',@actor_id,N'确认服务并结算');
        COMMIT; SELECT @order_id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_review_hours
    @log_id int,@reviewer_id int,@hours decimal(8,2),@note nvarchar(500)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF @hours<=0 OR NULLIF(LTRIM(RTRIM(@note)),N'') IS NULL THROW 51010,N'复核需要正工时和核验说明',1;
    BEGIN TRY
        BEGIN TRANSACTION;
        IF NOT EXISTS(SELECT 1 FROM work_log l WITH (UPDLOCK,HOLDLOCK)
            JOIN assignment a ON a.id=l.assignment_id JOIN shift s ON s.id=a.shift_id
            JOIN worker w ON w.id=s.worker_id JOIN app_user u ON u.id=@reviewer_id
            WHERE l.id=@log_id AND l.review_status='pending' AND l.checkout_at IS NOT NULL AND u.id<>w.user_id
              AND (u.role='admin' OR (u.role='agency' AND u.agency_id=w.agency_id))
              AND @hours<=DATEDIFF(second,l.checkin_at,l.checkout_at)/3600.0+0.01)
            THROW 51011,N'复核人、工时或记录状态不符合要求',1;
        UPDATE work_log SET valid_hours=@hours,review_status='approved',reviewer_id=@reviewer_id,review_note=@note WHERE id=@log_id;
        COMMIT;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_bind_device
    @device_id int,@elderly_id int,@actor_id int,@bound_at datetime2(0)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @locked int;
        SELECT @locked=id FROM device WITH (UPDLOCK,HOLDLOCK) WHERE id=@device_id;
        IF EXISTS(SELECT 1 FROM device_binding WHERE device_id=@device_id AND bound_at>=@bound_at)
            THROW 51012,N'新绑定时间须晚于已有绑定开始时间',1;
        UPDATE device_binding SET unbound_at=@bound_at WHERE device_id=@device_id AND unbound_at IS NULL;
        INSERT device_binding(device_id,elderly_id,bound_at,operator_id) VALUES(@device_id,@elderly_id,@bound_at,@actor_id);
        DECLARE @id int=SCOPE_IDENTITY();
        COMMIT; SELECT @id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_escalate_emergencies @now datetime2(0)=NULL AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    SET @now=COALESCE(@now,SYSDATETIME());
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @events TABLE(id int);
        UPDATE emergency SET escalated_at=@now OUTPUT inserted.id INTO @events
        WHERE status='open' AND responded_at IS NULL AND escalated_at IS NULL AND DATEADD(minute,response_minutes,occurred_at)<=@now;
        INSERT notification(event_id,recipient,stage)
            SELECT id,N'街道监管值班岗','escalated' FROM @events;
        INSERT notification(event_id,recipient,stage)
            SELECT e.id,N'社区值班岗','arrival' FROM emergency e
            WHERE e.status<>'closed' AND e.arrived_at IS NULL AND DATEADD(minute,e.arrival_minutes,e.occurred_at)<=@now
            AND NOT EXISTS(SELECT 1 FROM notification n WITH (UPDLOCK,HOLDLOCK) WHERE n.event_id=e.id AND n.stage='arrival');
        COMMIT; SELECT COUNT(*) escalated_count FROM @events;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_claim_month
    @elderly_id int,@item_id int,@month date,@actor_id int,@evidence nvarchar(500)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    IF DAY(@month)<>1 OR DATEADD(month,1,@month)>CAST(GETDATE() AS date)
        THROW 51013,N'次月起才能提交完整自然月的补贴申报',1;
    IF NULLIF(LTRIM(RTRIM(@evidence)),N'') IS NULL THROW 51014,N'请填写证明材料说明',1;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @community int,@claim int,@status varchar(12);
        SELECT @community=community_id FROM elderly WITH (UPDLOCK,HOLDLOCK) WHERE id=@elderly_id;
        SELECT @claim=id,@status=status FROM subsidy_claim WITH (UPDLOCK,HOLDLOCK)
            WHERE elderly_id=@elderly_id AND item_id=@item_id AND month=@month;
        -- 非退回状态按幂等处理：重复提交返回原申报；已驳回须明确提示，不能假装成功。
        IF @claim IS NOT NULL AND @status<>'returned'
        BEGIN
            IF @status='rejected' THROW 51017,N'该月申报已被驳回，请核对材料后重新办理',1;
            COMMIT; SELECT @claim id; RETURN;
        END;
        IF EXISTS(SELECT 1 FROM service_order WHERE elderly_id=@elderly_id AND item_id=@item_id
            AND scheduled_at>=@month AND scheduled_at<DATEADD(month,1,@month) AND status NOT IN ('completed','cancelled','terminated'))
            THROW 51015,N'该月仍有未结束订单，请先完成服务处理',1;
        -- 退回重提：先释放旧明细，再按当前可申报订单重算，避免沿用旧金额。
        IF @claim IS NOT NULL DELETE claim_item WHERE claim_id=@claim;
        DECLARE @items TABLE(order_id int,policy_id int,amount decimal(12,2));
        INSERT @items
        SELECT v.order_id,p.id,ROUND(CASE WHEN p.rate*q.quantity<v.settlement THEN p.rate*q.quantity ELSE v.settlement END,2)
        FROM v_subsidy_eligible v JOIN community c ON c.id=v.community_id JOIN area street ON street.id=c.street_id
        CROSS APPLY(SELECT TOP 1 * FROM subsidy_policy p WHERE p.district_id=street.parent_id AND p.item_id=v.item_id
            AND p.ability_level=v.ability_level AND (p.low_income_only=0 OR v.low_income=1)
            AND CAST(v.scheduled_at AS date) BETWEEN p.starts_on AND p.ends_on ORDER BY p.low_income_only DESC,p.id) p
        CROSS APPLY(SELECT CASE WHEN v.price_unit='visit' THEN 1 WHEN v.valid_hours<v.duration_minutes/60.0
                                THEN v.valid_hours ELSE v.duration_minutes/60.0 END quantity) q
        WHERE v.elderly_id=@elderly_id AND v.item_id=@item_id AND v.scheduled_at>=@month AND v.scheduled_at<DATEADD(month,1,@month);
        IF NOT EXISTS(SELECT 1 FROM @items) THROW 51016,N'该月没有符合政策的服务订单',1;
        IF @claim IS NULL
        BEGIN
            INSERT subsidy_claim(elderly_id,item_id,month,community_id,amount,submitted_by,evidence)
                SELECT @elderly_id,@item_id,@month,@community,SUM(amount),@actor_id,@evidence FROM @items;
            SET @claim=SCOPE_IDENTITY();
        END
        ELSE
        BEGIN
            UPDATE subsidy_claim SET status='street',amount=(SELECT SUM(amount) FROM @items),
                evidence=@evidence,submitted_by=@actor_id,submitted_at=SYSDATETIME()
            WHERE id=@claim;
        END
        INSERT claim_item SELECT @claim,order_id,policy_id,amount FROM @items;
        INSERT audit_log(entity,entity_id,action,actor_id,detail) VALUES('claim',@claim,'submit',@actor_id,@evidence);
        COMMIT; SELECT @claim id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_review_claim
    @claim_id int,@actor_id int,@decision varchar(10),@note nvarchar(500)
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @status varchar(12),@submitter int,@community int,@role varchar(12),@area int;
        SELECT @status=status,@submitter=submitted_by,@community=community_id FROM subsidy_claim WITH (UPDLOCK,HOLDLOCK) WHERE id=@claim_id;
        SELECT @role=role,@area=area_id FROM app_user WHERE id=@actor_id AND active=1;
        IF @status IS NULL OR @status NOT IN ('street','civil') OR @actor_id=@submitter
            THROW 51017,N'审核顺序或审核人员不符合要求',1;
        IF NOT EXISTS(SELECT 1 FROM community c JOIN area a ON a.id=c.street_id WHERE c.id=@community AND
           ((@status='street' AND @role='street' AND c.street_id=@area) OR (@status='civil' AND @role='civil' AND a.parent_id=@area)))
            THROW 51018,N'审核角色或辖区不匹配',1;
        IF EXISTS(SELECT 1 FROM claim_review WHERE claim_id=@claim_id AND reviewer_id=@actor_id AND stage<>@status)
            THROW 51019,N'初审与终审人员须分离',1;
        IF @decision NOT IN ('approve','return','reject') OR NULLIF(LTRIM(RTRIM(@note)),N'') IS NULL
            THROW 51020,N'请填写有效审核结论与意见',1;
        INSERT claim_review(claim_id,stage,reviewer_id,decision,note) VALUES(@claim_id,@status,@actor_id,@decision,@note);
        UPDATE subsidy_claim SET status=CASE WHEN @decision='return' THEN 'returned' WHEN @decision='reject' THEN 'rejected'
             WHEN @status='street' THEN 'civil' ELSE 'approved' END WHERE id=@claim_id;
        COMMIT; SELECT @claim_id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
CREATE OR ALTER PROCEDURE sp_pay_claim @claim_id int,@actor_id int,@reference varchar(60) AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        DECLARE @status varchar(12),@existing varchar(60);
        SELECT @status=status,@existing=payment_reference FROM subsidy_claim WITH (UPDLOCK,HOLDLOCK) WHERE id=@claim_id;
        IF @status='paid' AND @existing=@reference BEGIN COMMIT; SELECT @claim_id id; RETURN; END;
        IF @status IS NULL OR @status<>'approved' THROW 51021,N'只有终审通过的申报可以登记拨付',1;
        IF NULLIF(LTRIM(RTRIM(@reference)),'') IS NULL THROW 51022,N'拨付凭证号不能为空',1;
        IF NOT EXISTS(SELECT 1 FROM app_user u JOIN subsidy_claim s ON s.id=@claim_id JOIN community c ON c.id=s.community_id
            JOIN area a ON a.id=c.street_id WHERE u.id=@actor_id AND u.active=1 AND u.role='civil' AND u.area_id=a.parent_id)
            THROW 51023,N'拨付人员须为辖区民政监管人员',1;
        UPDATE subsidy_claim SET status='paid',payment_reference=@reference,paid_by=@actor_id,paid_at=SYSDATETIME() WHERE id=@claim_id;
        INSERT audit_log(entity,entity_id,action,actor_id,detail) VALUES('claim',@claim_id,'pay',@actor_id,@reference);
        COMMIT; SELECT @claim_id id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT>0 ROLLBACK; THROW;
    END CATCH
END;
GO
