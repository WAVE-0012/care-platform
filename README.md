# 社区居家养老智慧服务平台

数据库系统课程设计。系统围绕老人档案、服务订单、护工排班、健康应急和补贴监管五条业务线实现业务闭环，使用 SQL Server、Python Flask 和原生 JavaScript。当前物理库为 33 表、17 视图、11 存储过程、16 触发器、3 函数；设计实体 37 个到 33 张表的映射见 [对象与口径映射](docs/design/对象与口径映射.md)。

## 本机运行

当前数据库为 `localhost\SQLEXPRESS` 上的 `CareHomeCourse2026`，已装载演示数据。在本目录执行：

```powershell
.\start.ps1
```

浏览器打开 [http://127.0.0.1:5000](http://127.0.0.1:5000)。启动脚本同时启动每分钟运行一次的维护进程，处理评估到期、接单超时、应急升级和模拟通知。关闭服务后，脚本会结束自己启动的维护进程。 登录页和业务顶栏右上角可切换「暖茶 / 浅绿」两套配色，选择会保存在浏览器本地。

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

使用 Python 3.11 及以上（本次在 3.11.9 虚拟环境与 3.14.0 全局环境验证）、SQL Server Express 及 Microsoft ODBC Driver 18 for SQL Server。requirements.txt 固定本次验证的依赖版本。SQL Server 使用 Windows 身份验证；初始化和备份脚本需要建库、备份权限。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:CARE_SERVER = '.\SQLEXPRESS'
$env:CARE_DATABASE = 'CareHomeCourse2026'
.\.venv\Scripts\python.exe scripts/manage.py init
.\.venv\Scripts\python.exe scripts/manage.py seed
.\start.ps1
```

`init` 创建新库；已有数据库更新视图、函数、过程和触发器时使用 `migrate`。`seed` 只向空库写入合成数据。第一次运行会在 `instance/keys.json` 生成会话签名、身份证加密和检索密钥；更换环境时应与数据库一并迁移该文件。密钥和数据库备份不进入 Git。

启动脚本会先确认 `.venv` 能导入 Flask 和 pyodbc，导入失败时自动回退到 PATH 中的 Python；如果两者都不可用，按上面的命令补装依赖。2026-11-17 的 17 组复核修复、界面改版和审计噪声修复见 [最终版变更总览](docs/management/最终版变更总览_20261117.md)，数据库细节见 [修复记录](docs/management/修复记录_20261117.md)。

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
  04_triggers.sql       16 个触发器
  05_security.sql       应用数据库身份及权限
  queries/              15 组业务查询，每组两种实现
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

当前验证结果：121 项测试通过（本地 65 + 组内 56）；12 个业务页面正常加载，390 像素窄屏和快速切换页面时的延迟响应检查通过。10 万行临时表实验中，指定查询预热后六次执行的中位时间由 16.838 ms 降为 0.263 ms；该数值对应本机单会话实验。备份演练使用完整、差异、日志三段恢复，恢复后人数、订单数、结算额、工时及补贴金额一致。

## 材料与版本管理

课程报告和答辩 PPT 位于上一级的 `课程设计报告`。详细技术说明见 `docs/设计与验证说明.md`，交付对照见 `docs/任务与评分对照.md`。前期业务分析中的独立角色、角色关联、当前绑定、绑定历史、告警关联和响应等级配置等对象，分别通过角色枚举、有效期绑定记录、事件外键和事件时限快照表达，实际数据库对象以数据字典和 SQL 为准。

本仓库包含 Git 历史，版本与修复记录见 `docs/management/版本记录.txt`、`docs/management/最终版变更总览_20261117.md` 和 `docs/management/修复记录_20261117.md`。成员信息和任务分工按要求留空；个人报告需在分工确定后选用本人实际参与的内容。报告目录已提供约五分钟的无声系统录屏和发言脚本，可作为录制底片。会议记录、全员发言的答辩录像、教师提问与反馈，按实际活动补入对应目录。

