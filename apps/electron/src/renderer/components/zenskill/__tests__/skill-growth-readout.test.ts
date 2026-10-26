/**
 * 技能域成长契约读数条纯函数单测（第二十一批 B 段）
 *
 * ★ 守三件事：
 *   1. **域特有读数独立成条**：成长契约（等级 / 里程碑 / 使用记录）**不进**通用四格读数条
 *      —— 通用条读的是四种量纲，成长契约是**等级 + 计数**，两者量纲不同 ⇒ 混在一起会被加总。
 *   2. ★ **读不到 ≠ 读到 0**：技能不可用 ⇒ 一格都不出；技能可用但**没有里程碑/使用记录**
 *      ⇒ 那两格**不出现**（不是 0 个 / 0 次）。
 *   3. ★ **量纲纪律**：本条读数里**不得**出现「点」「分钟」—— 那是能量与注意力。
 */
import { describe, test, expect } from 'bun:test'
import {
  buildGrowthCells,
  type SkillGrowthData,
  type GrowthTranslate,
} from '../panels/SkillGrowthReadout'

const t: GrowthTranslate = (key, fallback, opts) => {
  let out = fallback
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      out = out.replaceAll(`{${k}}`, String(v))
    }
  }
  return out
}

const full: SkillGrowthData = {
  ok: true,
  available: true,
  skill_id: 'zenloop-orchestration',
  level: 'EXPERT',
  level_progress: 0.62,
  total_interactions: 23,
  success_rate: 0.78,
  milestones: [
    { level: 'APPRENTICE', achieved_at: '2026-09-01', description: '入门' },
    { level: 'EXPERT', achieved_at: '2026-10-01', description: '首次编排' },
  ],
  events: [{ action: 'execute', created_at: '2026-10-20', success: true }],
}

describe('buildGrowthCells —— 成长契约三要素', () => {
  test('等级 / 里程碑 / 使用记录各占一格', () => {
    const cells = buildGrowthCells(full, t)
    expect(cells.map((c) => c.label)).toEqual(['等级', '里程碑', '使用记录'])
  })

  test('等级格给等级名，进度放在提示里', () => {
    const cells = buildGrowthCells(full, t)
    expect(cells[0].value).toBe('EXPERT')
    expect(cells[0].hint).toContain('62%')
  })

  test('里程碑格给个数，使用记录格给次数', () => {
    const cells = buildGrowthCells(full, t)
    expect(cells[1].value).toBe('2 个')
    expect(cells[2].value).toBe('23 次')
  })

  test('使用记录格带成功率提示', () => {
    const cells = buildGrowthCells(full, t)
    expect(cells[2].hint).toContain('78%')
  })
})

describe('buildGrowthCells —— 读不到 ≠ 读到 0', () => {
  test('技能不可用 ⇒ 一格都不出（不是 0）', () => {
    const cells = buildGrowthCells({ ok: false, available: false }, t)
    expect(cells.length).toBe(0)
  })

  test('null 载荷 ⇒ 一格都不出', () => {
    expect(buildGrowthCells(null, t).length).toBe(0)
  })

  test('有等级但没有里程碑与使用记录 ⇒ 那两格不出现', () => {
    const cells = buildGrowthCells(
      { ok: true, available: true, level: 'NOVICE', milestones: [], events: [], total_interactions: 0 },
      t,
    )
    expect(cells.length).toBe(1)
    expect(cells[0].label).toBe('等级')
    expect(cells.some((c) => c.label === '里程碑')).toBe(false)
    expect(cells.some((c) => c.label === '使用记录')).toBe(false)
  })
})

describe('buildGrowthCells —— 量纲纪律', () => {
  test('成长契约的读数里不出现「点」「分钟」', () => {
    const cells = buildGrowthCells(full, t)
    const blob = JSON.stringify(cells)
    expect(blob).not.toContain('点')
    expect(blob).not.toContain('分钟')
  })

  test('等级格不带单位（等级名不是计量单位）', () => {
    const cells = buildGrowthCells(full, t)
    expect(cells[0].unit).toBeUndefined()
  })
})
