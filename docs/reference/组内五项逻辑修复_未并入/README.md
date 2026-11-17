# 组内五项逻辑与后端修复（未并入最终版）

本目录保留初版 `3663cc8` 中的另一条修复线，供对照和后续合并参考，**不属于本版 65 项测试的通过范围**。

包含：

- `五项逻辑修复说明.md`
- `后端功能修复说明.md`
- `数据库规则修订.md`
- `20261117_five_logic_fixes.sql`
- `tests/test_five_logic_fixes.py`
- `tests/test_backend_fixes.py`

## 为什么没有直接并入

本版以本地 2026-11-17 工作区为准，已经完成并验证了 17 组数据库/后端复核修复（F01—F17，见 `docs/management/修复记录_20261117.md`），测试为 **65 项全通过**。

组内这条修复线与本地修复在 `sql/03_procedures.sql`、`sql/04_triggers.sql`、`care/queries.py`、`care/services/*` 等位置有重叠。把两边直接叠加会出现两套未联合验证的规则，且这条线在原说明中明确写着“未连接数据库、未运行集成测试、未执行迁移”。为了保证最终版可复现，本版没有把它放进 `tests/` 和 `sql/migrations/`，而是移到本目录，避免 `pytest` 误收集、`manage.py migrate` 误执行。

## 如果后续要合并

建议单独开分支，按以下顺序处理：

1. 先对齐 `sql/01_schema.sql` 到 `05_security.sql` 的约束、过程、触发器和权限；
2. 再对齐 `care/services/*` 与 `care/queries.py` 的同名规则；
3. 把两套回归测试都放进 `tests/`，在独立测试库跑全量；
4. 通过后再更新 `docs/management/版本记录.txt` 和本目录说明。

在完成上述步骤前，不要把本目录的 SQL 直接放进 `sql/migrations/`。
