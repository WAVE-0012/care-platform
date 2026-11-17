# 社区居家养老智慧服务平台

数据库系统课程设计。系统围绕老人档案、服务订单、护工排班、健康应急和补贴监管五条业务线实现业务闭环，使用 SQL Server、Python Flask 和原生 JavaScript。

## 本机运行

当前数据库为 `localhost\SQLEXPRESS` 上的 `CareHomeCourse2026`，已装载演示数据。在本目录执行：

```powershell
.\start.ps1
```

浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)。启动脚本同时启动每分钟运行一次的维护进程，处理评估到期、接单超时、应急升级和模拟通知。关闭服务后，脚本会结束自己启动的维护进程。

| 角色 | 演示账号 | 密码 |
| --- | --- | --- |
| 系统管理员 | admin | Care2026! |
| 社区管理员 | community01 | Care2026! |
| 老人 | elderly01 | Care2026! |
| 家属 | family01 | Care2026! |
| 护工 | worker01 | Care2026! |
| 机构负责人 | agency01 | Care2026! |
| 街道监管 | street01 | Care2026! |
| 民政监管 | civil01 | Care2026! |

这些账号和数据用于课程演示。姓名、身份证号、位置和健康读数均为合成数据。通知使用本地模拟发送，拨付记录使用演示流水号。

## 在另一台 Windows 电脑部署

### 环境要求

- **Python 3.11**（推荐 3.11.x）
- **SQL Server Express 2019+**（实例名：`.\SQLEXPRESS`，Windows 身份验证）
- **Microsoft ODBC Driver 18 for SQL Server**
- 当前 Windows 用户需要有 SQL Server 建库和备份权限

### 快速部署步骤

```powershell
# 1. 进入项目目录
cd 项目路径

# 2. 创建虚拟环境
python -m venv .venv

# 3. 安装依赖
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. （可选）配置数据库连接，默认为 .\SQLEXPRESS 和 CareHomeCourse2026
# $env:CARE_SERVER = '.\SQLEXPRESS'
# $env:CARE_DATABASE = 'CareHomeCourse2026'

# 5. 初始化数据库并装载演示数据
.\.venv\Scripts\python.exe scripts/manage.py init
.\.venv\Scripts\python.exe scripts/manage.py seed

# 6. 启动服务
.\start.ps1

# 7. 浏览器访问 http://127.0.0.1:5000
# 使用演示账号登录，所有账号密码统一为：Care2026!
```

### 命令说明

- `init` - 创建新数据库和表结构（数据库已存在会报错）
- `seed` - 向空库装载演示数据（约 50+ 条记录）
- `migrate` - 更新已有数据库的视图、函数、存储过程、触发器
- `.\start.ps1` - 启动 Flask 应用和后台维护进程，按 Ctrl+C 停止

### 重要说明

1. **密钥文件**：首次运行会在 `instance/keys.json` 生成会话签名、身份证加密和检索密钥。**迁移环境时必须将此文件与数据库一并迁移**，否则无法解密敏感数据。
2. **数据预检**：`migrate` 先执行 `sql/migrations` 的存量预检和增量约束，再更新视图、函数、过程、触发器，全部成功后统一提交。预检发现不合法项目或重复体征时列出记录并回滚，不自动删除历史数据。
3. **版本固定**：`requirements.txt` 固定本次验证的依赖版本，确保兼容性。
4. **密钥和备份**：`instance/keys.json` 和数据库备份不进入 Git。

### 常见问题

**端口 5000 被占用**：修改 `run.py` 中的端口号

**数据库连接失败**：
- 确认 SQL Server 服务正在运行：`Get-Service | Where-Object {$_.Name -like "*SQL*"}`
- 确认实例名称正确：`sqlcmd -L`
- 确认当前 Windows 用户有 sysadmin 权限

**ODBC Driver 找不到**：
- 确认已安装 ODBC Driver 18：`Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}`
- 如安装了其他版本，修改 `care/config.py` 第 28 行的驱动名称

**执行策略错误**：`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**重新初始化**：
```powershell
sqlcmd -S .\SQLEXPRESS -E -Q "DROP DATABASE CareHomeCourse2026"
.\.venv\Scripts\python.exe scripts/manage.py init
.\.venv\Scripts\python.exe scripts/manage.py seed
```

### 迁移到另一台电脑

**源电脑备份**：
```powershell
# 备份数据库
sqlcmd -S .\SQLEXPRESS -E -Q "BACKUP DATABASE CareHomeCourse2026 TO DISK='C:\backup\care.bak'"

# 复制到目标电脑：
# - 整个项目文件夹
# - instance/keys.json（重要！）
# - C:\backup\care.bak
```

**目标电脑恢复**：
```powershell
# 1. 完成环境准备和步骤 1-3
# 2. 复制 keys.json 到 instance 目录
# 3. 恢复数据库
sqlcmd -S .\SQLEXPRESS -E -Q "RESTORE DATABASE CareHomeCourse2026 FROM DISK='C:\backup\care.bak' WITH REPLACE"
# 4. 启动服务
.\start.ps1
```

详细部署指南请参阅：**`部署指南.md`**

## 操作顺序

1. 社区管理员在“老人档案”建档，登记联系人授权、能力评估和照护计划。老人跨社区迁移时修改原档案的归属，历史订单保留服务发生时的社区。
2. 机构负责人在“护工排班”登记护工、证书和班次；班次使用半开时间区间，相邻班次可以衔接。
3. 家属或社区创建服务订单。社区查看候选护工后派单；改派需要原因，旧派单留在详情中。
4. 护工接单、签到、签退并填写服务记录；家属确认后结算。签到时间或位置异常时，由机构负责人复核工时。
5. 在“健康监测”登记设备、绑定和上传体征。在“应急响应”发起事件，依次响应、到场、关闭。设备换绑按采集时间判断历史归属。
6. 社区在次月归集补贴；街道初审、民政终审后登记拨付。质量抽查产生整改时暂停有关护工接单，监管复核完成后解除限制。

演示已有历史订单、审批记录和应急事件。新订单应使用当前日期之后的预约时间；签到签退使用实际时间和所填经纬度。

## 代码目录

```text
care/                   Flask 应用、权限、事务和业务服务
  app.py                路由、登录、输入与业务错误处理
  db.py                 参数化 Repository 和事务上下文
  security.py           密码、身份证加密、角色与数据范围
  queries.py            列表、分页和统计查询
  services/             按五条业务线组织的操作
  templates/            页面模板
  static/               JavaScript 和样式
sql/                    按依赖顺序执行的数据库脚本
  01_schema.sql         33 张表、约束、索引
  02_views.sql          17 个视图、3 个函数
  03_procedures.sql     11 个存储过程
  04_triggers.sql       15 个触发器
  05_security.sql       应用数据库身份及权限
  queries/              15 组业务查询，每组两种实现
  migrations/           已有数据预检及幂等结构更新
scripts/                建库、数据、维护、备份、实验脚本
tests/                  API、事务、并发及查询等价性测试
docs/design/            数据字典、关系模式、图的源文件和图片
docs/evidence/          自动化测试、执行计划、截图和恢复证据
docs/management/        项目记录和待实际活动填写的表格
业务分析.md             保留的前期分析材料
```

## 复现实验

```powershell
python -m pytest -q --junitxml=docs/evidence/pytest-results.xml
python scripts/manage.py inventory
python scripts/benchmark.py
python scripts/backup_restore.py
python scripts/maintenance.py
```

测试自动创建带时间戳的独立数据库，不向演示库写测试记录。测试数据库名保存在 `docs/evidence/test_database.txt`，检查完成后可在 SQL Server 中删除该独立库。浏览器检查另外需要 `pip install playwright` 和 Microsoft Edge，在服务运行时执行 `python scripts/verify_ui.py`。

修订前验证记录：64 项测试通过；8 个主要页面正常加载，390 像素窄屏和快速切换页面时的延迟响应检查通过。10 万行临时表实验中，指定查询预热后六次执行的中位时间由 16.838 ms 降为 0.263 ms；该数值对应本机单会话实验。备份演练使用完整、差异、日志三段恢复，恢复后人数、订单数、结算额、工时及补贴金额一致。这些历史结果不覆盖2026-11-17五项逻辑修复、后端七项功能修复及新增回归测试，修复说明见 `docs/五项逻辑修复说明.md` 和 `docs/后端功能修复说明.md`。

## 材料与版本管理

课程报告和答辩 PPT 位于上一级的 `课程设计报告`。详细技术说明见 `docs/设计与验证说明.md`，交付对照见 `docs/任务与评分对照.md`。前期业务分析中的独立角色、角色关联、当前绑定、绑定历史、告警关联和响应等级配置等对象，分别通过角色枚举、有效期绑定记录、事件外键和事件时限快照表达，实际数据库对象以数据字典和 SQL 为准。

本项目使用本地 Git 保存实际文件版本。成员信息和任务分工按要求留空；个人报告需在分工确定后选用本人实际参与的内容。报告目录已提供约五分钟的无声系统录屏和发言脚本，可作为录制底片。会议记录、全员发言的答辩录像、教师提问与反馈，按实际活动补入对应目录。
