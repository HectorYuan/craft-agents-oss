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
  type CompanionData,
  type AttentionStatusData,
  type ReadoutTranslate,
} from '../panels/DomainReadout'

// 测试用的翻译桩：直接回显 fallback，opts 里的 {n} 会被替换
const t: ReadoutTranslate = (key, fallback, opts) => {
  let out = fallback
  if (opts && typeof opts.n === 'number') out = out.replace('{n}', String(opts.n))
  return out
}

const loop: ZenloopStatusData = {
  active: 3,
  top: [{ id: 'r1', channel: 'reflect', maturity: 'insight', concept: '洞见' }],
}

const companion: CompanionData = { energy: { level: 'normal', pct: 62, current: 124, max: 200 } }

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
    const cells = buildReadoutCells(loop, companion, attention, t)
    const energy = cells.find((c) => c.label === '能量')
    expect(energy).toBeDefined()
    expect(energy!.unit).toBe('点')
    expect(energy!.value).toBe('124 / 200')
  })

  test('注意力格的单位是「分钟」', () => {
    const cells = buildReadoutCells(loop, companion, attention, t)
    const att = cells.find((c) => c.label === '注意力')
    expect(att).toBeDefined()
    expect(att!.unit).toBe('分钟')
    expect(att!.value).toBe('180')
  })

  test('★ 两种量纲**各带各的单位**（不得合并成一个值）', () => {
    const cells = buildReadoutCells(loop, companion, attention, t)
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
    const cells = buildReadoutCells(loop, companion, attention, t)
    const loopCell = cells.find((c) => c.label === '轮次')
    expect(loopCell).toBeDefined()
    expect(loopCell!.unit).toBeUndefined()
  })
})

describe('buildReadoutCells —— 读不到 ≠ 0', () => {
  test('会话侧读不到近期深度占用 ⇒ 标「至多」并给上限说明', () => {
    const cells = buildReadoutCells(
      loop,
      companion,
      { status: { remaining_minutes: 240, session_available: false } },
      t,
    )
    const att = cells.find((c) => c.label === '注意力')
    expect(att!.prefix).toBe('至多')
    expect(att!.hint).toContain('上限')
  })

  test('读得到 ⇒ 不加「至多」', () => {
    const cells = buildReadoutCells(loop, companion, attention, t)
    const att = cells.find((c) => c.label === '注意力')
    expect(att!.prefix).toBeUndefined()
  })

  test('注意力读不到 ⇒ 该格**不出现**（不是 0 分钟）', () => {
    const cells = buildReadoutCells(loop, companion, { status: {} }, t)
    expect(cells.find((c) => c.label === '注意力')).toBeUndefined()
  })

  test('能量读不到 ⇒ 该格不出现', () => {
    const cells = buildReadoutCells(loop, { mood: 'x' }, attention, t)
    expect(cells.find((c) => c.label === '能量')).toBeUndefined()
  })

  test('没有任何数据 ⇒ 空数组（上层据此不渲染）', () => {
    expect(buildReadoutCells(null, null, null, t)).toEqual([])
  })
})
