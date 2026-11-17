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
EXECUTE ON SCHEMA::dbo TO care_runtime;

-- 只保留“删除未使用班次”这一个删除入口；其它业务表的删除一律收回。
REVOKE DELETE ON SCHEMA::dbo
FROM care_runtime;

GRANT DELETE ON OBJECT::shift TO care_runtime;

REVOKE CONTROL ON SCHEMA::dbo
FROM care_runtime;

DENY
ALTER,TAKE OWNERSHIP ON SCHEMA::dbo TO care_runtime;

DENY
DELETE,
UPDATE ON OBJECT::audit_log TO care_runtime;

DENY
DELETE,
UPDATE ON OBJECT::claim_review TO care_runtime;

-- 部署到独立 Windows 服务账号时，由管理员额外执行（本机课程环境用 Windows 管理员连接，不需要）：
--   GRANT IMPERSONATE ON USER::care_app TO [服务账号];
GO
