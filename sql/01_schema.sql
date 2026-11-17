-- 社区居家养老智慧服务平台。数据库由 scripts/manage.py init 创建。
-- 日期有效期包含两端；时间区间为 [开始, 结束)；金额单位为元。
CREATE TABLE area (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(60) NOT NULL,
    kind varchar(10) NOT NULL CHECK (kind IN ('district', 'street')),
    parent_id int NULL REFERENCES area(id),
    CHECK ((kind = 'district' AND parent_id IS NULL) OR (kind = 'street' AND parent_id IS NOT NULL))
);

CREATE TABLE community (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(60) NOT NULL UNIQUE,
    street_id int NOT NULL REFERENCES area(id),
    longitude decimal(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude decimal(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    radius_m int NOT NULL DEFAULT 3000 CHECK (radius_m > 0),
    checkin_radius_m int NOT NULL DEFAULT 200 CHECK (checkin_radius_m > 0)
);

CREATE TABLE agency (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(80) NOT NULL UNIQUE,
    district_id int NOT NULL REFERENCES area(id),
    active bit NOT NULL DEFAULT 1
);

CREATE TABLE app_user (
    id int IDENTITY PRIMARY KEY,
    username varchar(40) NOT NULL UNIQUE,
    display_name nvarchar(40) NOT NULL,
    password_hash varchar(256) NOT NULL,
    role varchar(12) NOT NULL CHECK (role IN ('admin', 'community', 'family', 'elderly', 'worker', 'agency', 'street', 'civil')),
    community_id int NULL REFERENCES community(id),
    agency_id int NULL REFERENCES agency(id),
    area_id int NULL REFERENCES area(id),
    active bit NOT NULL DEFAULT 1,
    failed_attempts int NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until datetime2(0) NULL,
    last_login datetime2(0) NULL
);

CREATE TABLE elderly (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(40) NOT NULL,
    identity_cipher varchar(256) NOT NULL,
    identity_hash char(64) NOT NULL UNIQUE,
    identity_mask nvarchar(24) NOT NULL,
    birth_date date NOT NULL,
    address nvarchar(200) NOT NULL,
    community_id int NOT NULL REFERENCES community(id),
    longitude decimal(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude decimal(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    living_alone bit NOT NULL DEFAULT 0,
    disabled bit NOT NULL DEFAULT 0,
    low_income bit NOT NULL DEFAULT 0,
    active bit NOT NULL DEFAULT 1,
    user_id int NULL REFERENCES app_user(id)
);

CREATE UNIQUE INDEX UX_elderly_user ON elderly(user_id)
    WHERE user_id IS NOT NULL;

CREATE TABLE contact (
    id int IDENTITY PRIMARY KEY,
    elderly_id int NOT NULL REFERENCES elderly(id),
    name nvarchar(40) NOT NULL,
    relationship nvarchar(20) NOT NULL,
    phone_cipher varchar(256) NOT NULL,
    phone_mask varchar(20) NOT NULL,
    is_primary bit NOT NULL DEFAULT 0,
    guardian bit NOT NULL DEFAULT 0,
    user_id int NULL REFERENCES app_user(id),
    authorized_from datetime2(0) NOT NULL,
    authorized_until datetime2(0) NULL,
    active bit NOT NULL DEFAULT 1,
    CHECK (authorized_until IS NULL OR authorized_until > authorized_from)
);

CREATE UNIQUE INDEX UX_contact_primary ON contact(elderly_id)
    WHERE is_primary = 1 AND active = 1;

CREATE TABLE assessment (
    id int IDENTITY PRIMARY KEY,
    elderly_id int NOT NULL REFERENCES elderly(id),
    scale varchar(8) NOT NULL CHECK (scale IN ('ADL', 'MMSE')),
    score decimal(5, 2) NOT NULL,
    ability_level tinyint NOT NULL CHECK (ability_level BETWEEN 0 AND 3),
    assessor_id int NOT NULL REFERENCES app_user(id),
    assessed_on date NOT NULL,
    valid_until date NOT NULL,
    UNIQUE (elderly_id, assessed_on),
    CHECK (valid_until >= assessed_on),
    CHECK ((scale = 'ADL' AND score BETWEEN 0 AND 100) OR (scale = 'MMSE' AND score BETWEEN 0 AND 30))
);

CREATE TABLE service_item (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(60) NOT NULL UNIQUE,
    category nvarchar(10) NOT NULL CHECK (category IN (N'助餐', N'助浴', N'陪诊', N'家政', N'康复护理')),
    unit varchar(8) NOT NULL CHECK (unit IN ('visit', 'hour')),
    price decimal(10, 2) NOT NULL CHECK (price >= 0),
    duration_minutes int NOT NULL CHECK (duration_minutes BETWEEN 1 AND 720),
    subsidized bit NOT NULL DEFAULT 1,
    certificate_type nvarchar(40) NULL,
    certificate_level tinyint NULL,
    CONSTRAINT CK_service_item_certificate_pair CHECK (
        (certificate_type IS NULL AND certificate_level IS NULL)
        OR (certificate_type IS NOT NULL AND certificate_level IS NOT NULL AND certificate_level BETWEEN 1 AND 3)
    )
);

CREATE TABLE service_package (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(80) NOT NULL UNIQUE,
    ability_level tinyint NOT NULL CHECK (ability_level BETWEEN 0 AND 3),
    active bit NOT NULL DEFAULT 1
);

CREATE TABLE package_item (
    package_id int NOT NULL REFERENCES service_package(id),
    item_id int NOT NULL REFERENCES service_item(id),
    frequency int NOT NULL CHECK (frequency > 0),
    period varchar(8) NOT NULL CHECK (period IN ('week', 'month')),
    PRIMARY KEY (package_id, item_id)
);

CREATE TABLE worker (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(40) NOT NULL,
    agency_id int NOT NULL REFERENCES agency(id),
    user_id int NOT NULL UNIQUE REFERENCES app_user(id),
    available_from time(0) NOT NULL DEFAULT '07:00',
    available_until time(0) NOT NULL DEFAULT '21:00',
    trained_on date NULL,
    status varchar(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'leave', 'left')),
    total_hours decimal(12, 2) NOT NULL DEFAULT 0 CHECK (total_hours >= 0),
    points int NOT NULL DEFAULT 0 CHECK (points >= 0),
    CHECK (available_until > available_from)
);

CREATE TABLE certificate (
    id int IDENTITY PRIMARY KEY,
    worker_id int NOT NULL REFERENCES worker(id),
    certificate_type nvarchar(40) NOT NULL,
    level tinyint NOT NULL CHECK (level BETWEEN 1 AND 3),
    number varchar(40) NOT NULL,
    issued_on date NOT NULL,
    valid_until date NOT NULL,
    UNIQUE (certificate_type,number),
    CHECK (valid_until >= issued_on)
);

CREATE TABLE worker_skill (
    worker_id int NOT NULL REFERENCES worker(id),
    item_id int NOT NULL REFERENCES service_item(id),
    PRIMARY KEY (worker_id, item_id)
);

CREATE TABLE worker_area (
    worker_id int NOT NULL REFERENCES worker(id),
    community_id int NOT NULL REFERENCES community(id),
    PRIMARY KEY (worker_id, community_id)
);

CREATE TABLE care_plan (
    id int IDENTITY PRIMARY KEY,
    elderly_id int NOT NULL REFERENCES elderly(id),
    package_id int NOT NULL REFERENCES service_package(id),
    worker_id int NOT NULL REFERENCES worker(id),
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    status varchar(10) NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'paused', 'ended')),
    CHECK (ends_on >= starts_on)
);

CREATE TABLE plan_item (
    plan_id int NOT NULL REFERENCES care_plan(id),
    item_id int NOT NULL REFERENCES service_item(id),
    frequency int NOT NULL CHECK (frequency > 0),
    period varchar(8) NOT NULL CHECK (period IN ('week', 'month')),
    PRIMARY KEY (plan_id, item_id)
);

CREATE TABLE shift (
    id int IDENTITY PRIMARY KEY,
    worker_id int NOT NULL REFERENCES worker(id),
    starts_at datetime2(0) NOT NULL,
    ends_at datetime2(0) NOT NULL,
    capacity int NOT NULL CHECK (capacity > 0),
    used_slots int NOT NULL DEFAULT 0,
    status varchar(10) NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published', 'closed')),
    CHECK (ends_at > starts_at AND CAST(starts_at AS date) = CAST(ends_at AS date)),
    CHECK (used_slots BETWEEN 0 AND capacity)
);

CREATE TABLE service_order (
    id int IDENTITY PRIMARY KEY,
    request_key varchar(64) NOT NULL UNIQUE,
    elderly_id int NOT NULL REFERENCES elderly(id),
    item_id int NOT NULL REFERENCES service_item(id),
    community_id int NOT NULL REFERENCES community(id),
    created_by int NOT NULL REFERENCES app_user(id),
    created_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    scheduled_at datetime2(0) NOT NULL,
    duration_minutes int NOT NULL CHECK (duration_minutes BETWEEN 1 AND 720),
    address nvarchar(200) NOT NULL,
    longitude decimal(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude decimal(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    unit_price decimal(10, 2) NOT NULL CHECK (unit_price >= 0),
    price_unit varchar(8) NOT NULL CHECK (price_unit IN ('visit', 'hour')),
    channel nvarchar(12) NOT NULL CHECK (channel IN (N'电话', N'家属端', N'社区代下单')),
    status varchar(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('ineligible', 'pending', 'offered', 'accepted', 'serving', 'confirming', 'completed', 'cancelled', 'exception', 'terminated')),
    settlement decimal(12, 2) NULL CHECK (settlement >= 0),
    completed_at datetime2(0) NULL,
    rating tinyint NULL CHECK (rating BETWEEN 1 AND 5),
    feedback nvarchar(500) NULL,
    complaint nvarchar(500) NULL,
    complaint_result nvarchar(500) NULL,
    CHECK (CAST(scheduled_at AS date) = CAST(DATEADD(MINUTE, duration_minutes, scheduled_at) AS date))
);

CREATE TABLE assignment (
    id int IDENTITY PRIMARY KEY,
    order_id int NOT NULL REFERENCES service_order(id),
    shift_id int NOT NULL REFERENCES shift(id),
    dispatcher_id int NOT NULL REFERENCES app_user(id),
    assigned_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    accepted_at datetime2(0) NULL,
    status varchar(12) NOT NULL DEFAULT 'offered' CHECK (status IN ('offered', 'accepted', 'completed', 'rejected', 'timeout', 'reassigned', 'invalid', 'terminated')),
    is_current bit NOT NULL DEFAULT 1,
    reason nvarchar(200) NULL,
    service_record nvarchar(1000) NULL,
    confirmed_by int NULL REFERENCES app_user(id),
    confirmed_at datetime2(0) NULL,
    proof_reference nvarchar(200) NULL
);

CREATE UNIQUE INDEX UX_assignment_current ON assignment(order_id)
    WHERE is_current = 1;

CREATE TABLE work_log (
    id int IDENTITY PRIMARY KEY,
    assignment_id int NOT NULL UNIQUE REFERENCES assignment(id),
    checkin_at datetime2(0) NOT NULL,
    checkout_at datetime2(0) NULL,
    longitude decimal(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    latitude decimal(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    geofence_ok bit NOT NULL,
    valid_hours decimal(8, 2) NULL CHECK (valid_hours > 0),
    review_status varchar(10) NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'auto', 'approved', 'rejected')),
    reviewer_id int NULL REFERENCES app_user(id),
    review_note nvarchar(500) NULL,
    CHECK (checkout_at IS NULL OR checkout_at > checkin_at)
);

CREATE TABLE eligibility_snapshot (
    order_id int PRIMARY KEY REFERENCES service_order(id),
    assessment_id int NOT NULL REFERENCES assessment(id),
    plan_id int NOT NULL REFERENCES care_plan(id),
    low_income bit NOT NULL,
    checked_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    checked_by int NOT NULL REFERENCES app_user(id)
);

CREATE TABLE device (
    id int IDENTITY PRIMARY KEY,
    serial_number varchar(40) NOT NULL UNIQUE,
    device_type nvarchar(20) NOT NULL,
    location nvarchar(100) NOT NULL,
    status varchar(10) NOT NULL DEFAULT 'online' CHECK (status IN ('online', 'offline', 'fault', 'inactive'))
);

CREATE TABLE device_binding (
    id int IDENTITY PRIMARY KEY,
    device_id int NOT NULL REFERENCES device(id),
    elderly_id int NOT NULL REFERENCES elderly(id),
    bound_at datetime2(0) NOT NULL,
    unbound_at datetime2(0) NULL,
    operator_id int NOT NULL REFERENCES app_user(id),
    CHECK (unbound_at IS NULL OR unbound_at > bound_at)
);

CREATE UNIQUE INDEX UX_binding_current ON device_binding(device_id)
    WHERE unbound_at IS NULL;

-- 每个社区每种指标一条示例阈值；被体征引用后禁止修改或删除，保证历史判定可复核。
-- 需要调整阈值时新增社区或指标版本属于后续扩展，当前版本不做多版本并存。
CREATE TABLE metric_rule (
    id int IDENTITY PRIMARY KEY,
    community_id int NOT NULL REFERENCES community(id),
    metric varchar(24) NOT NULL,
    unit nvarchar(12) NOT NULL,
    lower_bound decimal(8, 2) NOT NULL,
    upper_bound decimal(8, 2) NOT NULL,
    UNIQUE (community_id, metric),
    CHECK (upper_bound >= lower_bound)
);

CREATE TABLE vital (
    id int IDENTITY PRIMARY KEY,
    binding_id int NOT NULL REFERENCES device_binding(id),
    rule_id int NOT NULL REFERENCES metric_rule(id),
    collected_at datetime2(0) NOT NULL,
    received_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    value decimal(8, 2) NOT NULL,
    abnormal bit NOT NULL DEFAULT 0,
    confirmation varchar(10) NOT NULL DEFAULT 'normal' CHECK (confirmation IN ('normal', 'pending', 'confirmed', 'false')),
    source nvarchar(20) NOT NULL DEFAULT N'模拟设备',
    UNIQUE (binding_id, rule_id, collected_at)
);

CREATE TABLE emergency (
    id int IDENTITY PRIMARY KEY,
    request_key varchar(64) NOT NULL UNIQUE,
    elderly_id int NOT NULL REFERENCES elderly(id),
    community_id int NOT NULL REFERENCES community(id),
    vital_id int NULL REFERENCES vital(id),
    source nvarchar(20) NOT NULL,
    level tinyint NOT NULL CHECK (level BETWEEN 1 AND 3),
    occurred_at datetime2(0) NOT NULL,
    response_minutes int NOT NULL CHECK (response_minutes > 0),
    arrival_minutes int NOT NULL CHECK (arrival_minutes > 0),
    responder_id int NULL REFERENCES app_user(id),
    responded_at datetime2(0) NULL,
    arrived_at datetime2(0) NULL,
    escalated_at datetime2(0) NULL,
    status varchar(10) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'handling', 'closed')),
    result nvarchar(1000) NULL,
    closed_at datetime2(0) NULL,
    CHECK (arrival_minutes >= response_minutes),
    CHECK (responded_at IS NULL OR responded_at >= occurred_at),
    CHECK (arrived_at IS NULL OR (responded_at IS NOT NULL AND arrived_at >= responded_at)),
    CHECK (status <> 'closed' OR (result IS NOT NULL AND closed_at IS NOT NULL))
);

CREATE UNIQUE INDEX UX_emergency_vital ON emergency(vital_id)
    WHERE vital_id IS NOT NULL;

CREATE TABLE notification (
    id int IDENTITY PRIMARY KEY,
    event_id int NOT NULL REFERENCES emergency(id),
    recipient nvarchar(80) NOT NULL,
    stage varchar(12) NOT NULL CHECK (stage IN ('created', 'escalated', 'arrival')),
    status varchar(10) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed', 'manual')),
    attempts int NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    last_attempt_at datetime2(0) NULL,
    error nvarchar(200) NULL,
    UNIQUE (event_id, recipient, stage)
);

CREATE TABLE subsidy_policy (
    id int IDENTITY PRIMARY KEY,
    name nvarchar(100) NOT NULL,
    district_id int NOT NULL REFERENCES area(id),
    item_id int NOT NULL REFERENCES service_item(id),
    ability_level tinyint NOT NULL CHECK (ability_level BETWEEN 0 AND 3),
    low_income_only bit NOT NULL DEFAULT 0,
    rate decimal(10, 2) NOT NULL CHECK (rate >= 0),
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    CHECK (starts_on <= ends_on AND DAY(starts_on) = 1 AND ends_on = EOMONTH(ends_on))
);

CREATE TABLE subsidy_claim (
    id int IDENTITY PRIMARY KEY,
    elderly_id int NOT NULL REFERENCES elderly(id),
    item_id int NOT NULL REFERENCES service_item(id),
    month date NOT NULL CHECK (DAY(month) = 1),
    community_id int NOT NULL REFERENCES community(id),
    amount decimal(12, 2) NOT NULL CHECK (amount >= 0),
    status varchar(12) NOT NULL DEFAULT 'street' CHECK (status IN ('draft', 'street', 'civil', 'returned', 'rejected', 'approved', 'paid')),
    submitted_by int NOT NULL REFERENCES app_user(id),
    submitted_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    evidence nvarchar(500) NOT NULL,
    payment_reference varchar(60) NULL,
    paid_by int NULL REFERENCES app_user(id),
    paid_at datetime2(0) NULL,
    UNIQUE (elderly_id, item_id, month)
);

CREATE UNIQUE INDEX UX_claim_payment ON subsidy_claim(payment_reference)
    WHERE payment_reference IS NOT NULL;

CREATE TABLE claim_item (
    claim_id int NOT NULL REFERENCES subsidy_claim(id),
    order_id int NOT NULL UNIQUE REFERENCES service_order(id),
    policy_id int NOT NULL REFERENCES subsidy_policy(id),
    amount decimal(12, 2) NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (claim_id, order_id)
);

CREATE TABLE claim_review (
    id int IDENTITY PRIMARY KEY,
    claim_id int NOT NULL REFERENCES subsidy_claim(id),
    stage varchar(8) NOT NULL CHECK (stage IN ('street', 'civil')),
    reviewer_id int NOT NULL REFERENCES app_user(id),
    decision varchar(10) NOT NULL CHECK (decision IN ('approve', 'return', 'reject')),
    note nvarchar(500) NOT NULL,
    reviewed_at datetime2(0) NOT NULL DEFAULT SYSDATETIME()
);

CREATE TABLE quality_check (
    id int IDENTITY PRIMARY KEY,
    order_id int NULL REFERENCES service_order(id),
    worker_id int NULL REFERENCES worker(id),
    inspector_id int NOT NULL REFERENCES app_user(id),
    method nvarchar(20) NOT NULL CHECK (method IN (N'电话回访', N'上门核查')),
    score tinyint NOT NULL CHECK (score BETWEEN 1 AND 5),
    issue nvarchar(200) NULL,
    requirement nvarchar(500) NULL,
    restrict_agency bit NOT NULL DEFAULT 0,
    restricted_item_id int NULL REFERENCES service_item(id),
    due_on date NULL,
    result nvarchar(500) NULL,
    status varchar(10) NOT NULL DEFAULT 'clear' CHECK (status IN ('clear', 'open', 'review', 'resolved')),
    reviewer_id int NULL REFERENCES app_user(id),
    checked_at datetime2(0) NOT NULL DEFAULT SYSDATETIME(),
    CHECK ((order_id IS NULL AND worker_id IS NOT NULL) OR (order_id IS NOT NULL AND worker_id IS NULL)),
    CHECK (status = 'clear' OR (issue IS NOT NULL AND requirement IS NOT NULL AND due_on IS NOT NULL))
);

CREATE TABLE audit_log (
    id bigint IDENTITY PRIMARY KEY,
    entity varchar(30) NOT NULL,
    entity_id int NOT NULL,
    action varchar(40) NOT NULL,
    actor_id int NULL REFERENCES app_user(id),
    detail nvarchar(1000) NOT NULL,
    created_at datetime2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO

CREATE INDEX IX_order_community_date ON service_order(community_id, scheduled_at)
    INCLUDE(status, elderly_id, item_id, settlement);

CREATE INDEX IX_assignment_order ON assignment(order_id, assigned_at)
    INCLUDE(shift_id, status);

CREATE INDEX IX_shift_worker_time ON shift(worker_id, starts_at)
    INCLUDE(ends_at, capacity, used_slots, status);

CREATE INDEX IX_plan_elderly_period ON care_plan(elderly_id, starts_on)
    INCLUDE(ends_on, status, package_id);

CREATE INDEX IX_emergency_pending ON emergency(status, occurred_at)
    INCLUDE(response_minutes, arrival_minutes, responded_at, arrived_at, escalated_at, community_id);

CREATE INDEX IX_review_claim ON claim_review(claim_id, id)
    INCLUDE(stage, decision, reviewer_id);

CREATE INDEX IX_binding_history ON device_binding(device_id, bound_at)
    INCLUDE(unbound_at, elderly_id);

CREATE INDEX IX_vital_history ON vital(binding_id, collected_at)
    INCLUDE(rule_id, value, abnormal);

CREATE INDEX IX_audit_entity ON audit_log(entity, entity_id, created_at);

CREATE INDEX IX_assignment_shift ON assignment(shift_id, status)
    INCLUDE(is_current);

CREATE INDEX IX_order_elderly_item_date ON service_order(elderly_id, item_id, scheduled_at);
GO
