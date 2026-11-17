# WorkBuddy 协作指导（2026-11-17 16:05）

> 给 WorkBuddy：先读完本文件，再开始下一轮；**不要中断或回退已经完成的 UI 改动**，也不要改本文件列出的“只读”文件。你上一轮的任务 8/9/10 已在 16:01 标记完成，但你给用户的总结里仍写“64 测试”，这是旧数字。

## 1. 当前事实（以工作区为准）

- 你的会话：`8fcfa050-6158-497b-b4e9-564ae89c6db0`，cwd `D:\life\北林\大三\数据库\课设实验`。
- 你刚完成：设计令牌/全局样式、符号图标与文案、截图与回归（任务 8/9/10）。
- 另一个 agent 刚完成一轮数据库复核修复，**后端与文档已定稿**：
  - 物理库：33 表 / 276 字段 / 17 视图 / 11 存储过程 / **15 触发器** / 3 函数 / 17 索引。
  - 测试：**65 项全通过**（不是 64）；新增 1 项跨社区阈值回归测试。
  - 关键修复：证书 CHECK、订单/申报冻结清单、阈值社区校验、申报退回重算、`fn_candidates` 岗前培训条件、05 权限收回全库 DELETE（`care_app` 只能删 `shift`）、`start.ps1` 空 venv 自动回退、依赖 pin 更新。
  - 演示库已 `migrate`，演示数据未重建；测试库由夹具新建，最新见 `docs/evidence/test_database.txt`。
- 端口 5000 仍有一个旧 Python 进程（PID 14144，旧代码）。**截图/演示前先停掉它，再运行 `.\start.ps1`**，否则页面是旧版本。

## 2. 文件边界（重要）

### 可以改（你的 UI 范围）

- `care/static/style.css`
- `care/static/app.js`
- `care/templates/index.html`
- `scripts/verify_ui.py`（仅当截图脚本需要适配）

### 只读，不要改

- `sql/01_schema.sql`、`02_views.sql`、`03_procedures.sql`、`04_triggers.sql`、`05_security.sql`
- `care/services/*`、`care/db.py`、`care/security.py`、`care/config.py`
- `requirements.txt`、`start.ps1`、`tests/test_database.py`
- `docs/management/修复记录_20261117.md`、`docs/design/对象与口径映射.md`
- `docs/evidence/pytest-results.xml`、`docs/evidence/deliverable-check.json`

如果发现后端/测试问题：**在回复里报告，不要直接改、不要回退**。另一个 agent 会按复核记录处理。

## 3. 下一轮任务（按顺序做，做完一项再下一项）

### A. 自查 UI 改动有没有破坏绑定（5 分钟）

- 确认没有删除 `app.js` 依赖的 `id`、`data-*`、`class`；没有改事件绑定。
- 确认 12 个 section 的 `symbol` 替换后仍有可读标签（`aria-label`/`title`），不是只剩装饰符号。
- 确认 390px 窄屏、768px、1440px 三档下表格/卡片不溢出，按钮不重叠。
- 确认没有引入外部字体、CDN、远程图片；离线演示要能开。

### B. 65 项回归 + 截图（10 分钟）

```powershell
# 先停掉 5000 上的旧进程，再启动（会选中 .venv）
.\start.ps1

# 另一个终端
.\.venv\Scripts\python.exe -m pytest tests -q
# 期望：65 passed
```

- 截图至少覆盖：登录、总览、老人列表、订单列表、订单详情、体征、申报、质量整改、排班；沿用 `docs/evidence/screenshots/` 现有命名。
- 检查浏览器 console 无 JS 错误；窄屏 390×844 再走一遍。
- 如果截图脚本 `scripts/verify_ui.py` 需要 Playwright/Edge，先确认依赖，不要为装依赖改 requirements。

### C. SQL 实验优化（20 分钟，UI 完成后再做）

目标：把“实验优化”落到可复查的证据，而不是再改页面。

1. 用新增索引跑基准：
   - `IX_assignment_shift(shift_id,status) INCLUDE(is_current)`
   - `IX_order_elderly_item_date(elderly_id,item_id,scheduled_at)`
   - 运行 `python scripts/benchmark.py`，记录 before/after 中位耗时与执行计划要点。
2. 15 组双实现回归：
   - `.\.venv\Scripts\python.exe -m pytest tests/test_database.py -k query_variants -q`
   - 期望 15 passed；不要改查询语义来“让结果好看”。
3. 证据更新**先问用户**：`docs/evidence/query-benchmark.json` 是否要追加本轮数据；不要覆盖 11-15 的历史记录。
4. 如果要做“SQL 双实现演示页”，先确认是否在本次范围；不要擅自加页面、加路由。

### D. 口径同步（只改你自己的记录，不改项目文档）

你上一轮总结和 `.workbuddy/memory/MEMORY.md` 里仍是旧口径：

- 37 表 / 16 视图 / 5 过程 + 5 触发器 / 64 测试 → 改为
- **33 表 / 17 视图 / 11 过程 / 15 触发器 / 3 函数 / 65 测试**；37 是设计实体，4 处折叠见 `docs/design/对象与口径映射.md`。

只更新你自己的会话总结/记忆；项目文档已由另一个 agent 更新，不要重复改。

## 4. 验收标准

| 项 | 通过条件 |
| --- | --- |
| 回归 | `.venv\Scripts\python.exe -m pytest tests -q` = 65 passed，0 failed |
| 查询 | 15 组双实现全部 equal |
| 页面 | 9 个主要页面 200；390px 无横向滚动；console 0 error |
| 数据 | 演示库仍为 40 老人 / 120 订单 / 20 申报（未被测试写脏） |
| 边界 | 没有改 SQL/后端/测试/文档；没有回退复核修复 |
| 汇报 | 列出改了哪些文件、跑了哪些命令、结果、未解决项 |

## 5. 汇报格式（直接发给用户）

```text
本轮完成：A/B/C/D
改动文件：...
命令与结果：pytest 65 passed；15 组 equal；截图 x 张
发现的问题：...
未做/待确认：...
```

## 6. 不要做

- 不要用“64 项测试”的旧数字。
- 不要在没有重启 5000 旧进程时截图或演示。
- 不要改 `sql/`、`care/services/`、`tests/`、`requirements.txt`、`start.ps1`。
- 不要回退证书 CHECK、触发器冻结、阈值社区校验、申报退回重算、05 权限。
- 不要删除演示库或测试库；测试库确认不用后再由用户决定清理。
- 不要把“37 表”当物理表数量写进新报告。
