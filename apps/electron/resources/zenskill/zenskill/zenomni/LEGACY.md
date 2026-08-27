# ZenOmni — 遗留模块

> Phase Z2C | marked deprecated in v2.6.0

## 历史

ZenOmni 是 Coze/OmniAgent 平台时代的技能基类系统，设计于 ZenSkill 早期阶段。

## 迁移

| 旧 (ZenOmni) | 新 (Phase D) |
|:-------------|:-------------|
| `ZenOmniSkill` 基类 | `SkillDefinition` (skill_dsl.py) + `SkillProfile` (core/) |
| `ZenOmniSkill.memory` | `SkillDAO.record_event()` / `SkillDAO.get_events()` |
| `ZenOmniSkill.cultivating` | `SkillProfile.load()` — level/stats/progress |
| `global_skill_registry` | `SkillSearchEngine` (search_engine.py) |
| `omni_skill` 装饰器 | `SkillCodeGenerator` (skill_dsl.py, Phase 9J) |
| `SkillType` 枚举 | `zenskill.core.skill_types.SkillType` |
| `TaskPlanner` / `StepExecutor` | 不再需要 — 技能通过 CLI + DAO 执行 |

## 时间线

- v2.6.0: 标记 Deprecated，导入触发 DeprecationWarning
- v2.x: 保留导入兼容
- v3.0: 移除 zenomni/ 目录

## 相关文档

- [Phase Z 路线图](../docs/PHASE_Z_ROADMAP.md)
- [Phase D 数据层统一](../docs/PHASE_D_ROADMAP.md)
