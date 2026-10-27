/**
 * 项目域读数条纯函数单测（第二十一批 B 段）
 *
 * ★ 守的是**「读不到 ≠ 读到 0」**：
 *   · `available !== true`（没关联 / 关联到多个）⇒ **一格都不出**（不是「0%」）
 *   · `available === true` 但 `total === 0`（关联到了、但还没行动）⇒ 出格，提示「还没有行动」
 *   ⇒ 两种空**可区分** ⇒ 不会把「没建关联」说成「进度 0%」。
 */
import { describe, test, expect } from 'bun:test'
import { buildProjectCells, type ProjectStatusData } from '../panels/ProjectDomainReadout'

const t = (key: string, fallback: string, opts?: Record<string, unknown>) => {
  let out = fallback
  if (opts) {
    for (const [k, v] of Object.entries(opts)) out = out.replaceAll(`{${k}}`, String(v))
  }
  return out
}

const linked: ProjectStatusData = {
  ok: true,
  available: true,
  progress: { done: 7, total: 15, progress: 0.4667, available: true },
}

describe('buildProjectCells —— 读不到 ≠ 读到 0', () => {
  test('未关联（available=false）⇒ 一格都不出', () => {
    expect(buildProjectCells({ ok: true, available: false }, t).length).toBe(0)
  })

  test('歧义（ambiguous）⇒ 一格都不出', () => {
    expect(buildProjectCells({ ok: true, available: false, ambiguous: true }, t).length).toBe(0)
  })

  test('null 载荷 ⇒ 一格都不出', () => {
    expect(buildProjectCells(null, t).length).toBe(0)
  })
})

describe('buildProjectCells —— 关联到了就出格', () => {
  test('进度格：百分比 + 分子分母提示', () => {
    const cells = buildProjectCells(linked, t)
    expect(cells.length).toBe(1)
    expect(cells[0].label).toBe('进度')
    expect(cells[0].value).toBe('47%')
    expect(cells[0].hint).toContain('7 / 15')
  })

  test('关联到了但还没有行动 ⇒ 出格，提示「还没有行动」（不是「读不到」）', () => {
    const cells = buildProjectCells(
      { ok: true, available: true, progress: { done: 0, total: 0, progress: 0, available: false } },
      t,
    )
    expect(cells.length).toBe(1)
    expect(cells[0].value).toBe('0%')
    expect(cells[0].hint).toBe('还没有行动')
  })
})
