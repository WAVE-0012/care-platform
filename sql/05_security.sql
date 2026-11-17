-- 应用专用数据库身份不具备 DDL、备份或服务器管理权限。
IF NOT EXISTS
    (SELECT 1
     FROM sys.database_principals
     WHERE name = 'care_app')
CREATE USER care_app WITHOUT LOGIN;

IF NOT EXISTS
    (SELECT 1
     FROM sys.database_principals
     WHERE name = 'care_runtime')
CREATE ROLE care_runtime;


ALTER ROLE care_runtime ADD MEMBER care_app;

GRANT
SELECT,
INSERT,
UPDATE,
DELETE,EXECUTE ON SCHEMA::dbo TO care_runtime;

REVOKE CONTROL ON SCHEMA::dbo
FROM care_runtime;

DENY
ALTER,TAKE OWNERSHIP ON SCHEMA::dbo TO care_runtime;

DENY
DELETE,
UPDATE ON OBJECT::audit_log TO care_runtime;

-- 补贴写入仅经同属 dbo 的存储过程完成；所有权链允许过程内部的静态 SQL，
-- 应用账号不能直接新增、修改、删除申报、明细或伪造审核记录。
DENY INSERT,UPDATE,DELETE ON OBJECT::dbo.subsidy_claim TO care_runtime;
DENY INSERT,UPDATE,DELETE ON OBJECT::dbo.claim_item TO care_runtime;
DENY INSERT,UPDATE,DELETE ON OBJECT::dbo.claim_review TO care_runtime;
GO
