/**
 * 读数条纯函数单测（第十九批 D 段）
 *
 * ★ 守的是**量纲纪律**：能量 = 点 / 注意力 = 分钟，两者**不相加、不换算**
 *   ⇒ 每个读数格必须带自己的单位；「点」和「分钟」挂错格就是缺陷。
 * ★ 同时守「读不到 ≠ 0」：会话侧读不到近期深度占用时，注意力是**上限**（标「至多」），
 *   不是 0 分钟。
 */
import { describe, test, expect } from 'bun:test'
import {
  buildReadoutCells,
  type ZenloopStatusData,
  type EnergyLevelData,
  type AttentionStatusData,
  type DelegationStatusData,
  type ReadoutTranslate,
} from '../panels/DomainReadout'

// 测试用的翻译桩：直接回显 fallback，opts 里的 {n} 会被替换
const t: ReadoutTranslate = (key, fallback, opts) => {
  let out = fallback
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      out = out.replaceAll(`{${k}}`, String(v))
    }
  }
  return out
}

const loop: ZenloopStatusData = {
  active: 3,
  top: [{ id: 'r1', channel: 'reflect', maturity: 'insight', concept: '洞见' }],
}

const energy: EnergyLevelData = {
  status: {
    level: 'normal',
    pct: 0.62,
    current_energy: 124,
    max_energy: 200,
    pending_recovery: 0,
    stored_energy: 124,
    recovery_rate: 30,
  },
}

const delegation: DelegationStatusData = {
  status: { total: 20, agent_created: 5, ratio: 0.25, available: true },
}

const attention: AttentionStatusData = {
  status: {
    remaining_minutes: 180,
    available_minutes: 240,
    session_available: true,
    session_window: 10,
  },
}

describe('buildReadoutCells —— 量纲纪律', () => {
  test('能量格的单位是「点」', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const energyCell = cells.find((c) => c.label === '能量')
    expect(energyCell).toBeDefined()
    expect(energyCell!.unit).toBe('点')
    expect(energyCell!.value).toBe('124 / 200')
  })

  test('注意力格的单位是「分钟」', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const att = cells.find((c) => c.label === '注意力')
    expect(att).toBeDefined()
    expect(att!.unit).toBe('分钟')
    expect(att!.value).toBe('180')
  })

  test('★ 两种量纲**各带各的单位**（不得合并成一个值）', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const units = cells.map((c) => c.unit).filter(Boolean)
    expect(units).toContain('点')
    expect(units).toContain('分钟')
    // 没有任何一格把点与分钟**混在同一个单位里**（那等于让读者把两种量纲相加）
    for (const c of cells) {
      if (!c.unit) continue
      expect(c.unit.includes('点') && c.unit.includes('分钟')).toBe(false)
    }
  })

  test('轮次格无量纲（不挂单位）', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const loopCell = cells.find((c) => c.label === '轮次')
    expect(loopCell).toBeDefined()
    expect(loopCell!.unit).toBeUndefined()
  })
})

describe('buildReadoutCells —— 读不到 ≠ 0', () => {
  test('会话侧读不到近期深度占用 ⇒ 标「至多」并给上限说明', () => {
    const cells = buildReadoutCells(
      loop,
      energy,
      { status: { remaining_minutes: 240, session_available: false } },
      delegation,
      t,
    )
    const att = cells.find((c) => c.label === '注意力')
    expect(att!.prefix).toBe('至多')
    expect(att!.hint).toContain('上限')
  })

  test('读得到 ⇒ 不加「至多」', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const att = cells.find((c) => c.label === '注意力')
    expect(att!.prefix).toBeUndefined()
  })

  test('注意力读不到 ⇒ 该格**不出现**（不是 0 分钟）', () => {
    const cells = buildReadoutCells(loop, energy, { status: {} }, delegation, t)
    expect(cells.find((c) => c.label === '注意力')).toBeUndefined()
  })

  test('能量读不到 ⇒ 该格不出现', () => {
    const cells = buildReadoutCells(loop, { status: {} }, attention, delegation, t)
    expect(cells.find((c) => c.label === '能量')).toBeUndefined()
  })

  test('没有任何数据 ⇒ 空数组（上层据此不渲染）', () => {
    expect(buildReadoutCells(null, null, null, null, t)).toEqual([])
  })
})

describe('buildReadoutCells —— 智能体承担（比例量纲）', () => {
  test('委派格显示为百分比，且**不带点/分钟**', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const d = cells.find((c) => c.label === '智能体承担')
    expect(d).toBeDefined()
    expect(d!.value).toBe('25%')
    expect(d!.unit).toBeUndefined()
    expect(d!.hint).toContain('5 / 20')
  })

  test('★ 四种量纲各占一格，**互不混算**', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const labels = cells.map((c) => c.label)
    expect(labels).toContain('能量')
    expect(labels).toContain('注意力')
    expect(labels).toContain('智能体承担')
    // 每个带单位的格只带一种单位
    for (const c of cells) {
      if (!c.unit) continue
      expect(c.unit.includes('点') && c.unit.includes('分钟')).toBe(false)
    }
  })

  test('没有行动可统计 ⇒ 委派格**不出现**（不是 0%）', () => {
    const cells = buildReadoutCells(
      loop,
      energy,
      attention,
      { status: { total: 0, agent_created: 0, ratio: 0, available: false } },
      t,
    )
    expect(cells.find((c) => c.label === '智能体承担')).toBeUndefined()
  })
})

describe('buildReadoutCells —— 能量恢复提示', () => {
  test('有待恢复量 ⇒ 提示「恢复中 +N 点」', () => {
    const cells = buildReadoutCells(
      loop,
      { status: { ...energy.status, pending_recovery: 48 } },
      attention,
      delegation,
      t,
    )
    const e = cells.find((c) => c.label === '能量')
    expect(e!.hint).toContain('恢复中')
    expect(e!.hint).toContain('48')
  })

  test('没有待恢复量 ⇒ 不给提示', () => {
    const cells = buildReadoutCells(loop, energy, attention, delegation, t)
    const e = cells.find((c) => c.label === '能量')
    expect(e!.hint).toBeUndefined()
  })
})
