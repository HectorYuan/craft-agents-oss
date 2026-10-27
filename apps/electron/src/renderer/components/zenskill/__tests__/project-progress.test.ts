/**
 * 项目域读数（进度）纯函数单测（第二十一批 C 段）
 *
 * ★ 守的是**读数纪律**：
 *   1. `progress` 是 **0–1 的比例**（后端已统一口径）⇒ 百分比 = round(p×100)
 *      ⇒ 曾经后端给 0–100、前端按 0–1 用 ⇒ **进度条恒满、title 显示 4600%**；
 *   2. ★ **读不到 ≠ 读到 0**：`available === false`（还没有行动可统计）
 *      ⇒ **不画进度条**（不用 0% 冒充「一件都没做」）；
 *   3. 有分子分母 ⇒ 显示「7 / 15 行动完成」（GTD 的原话），否则退回纯百分比。
 */
import { describe, test, expect } from 'bun:test'
import { projectProgressTitle } from '../panels/ProjectsPanel'
import type { GtdProject } from '../panels/types'

const t = (key: string, fallback: string, opts?: Record<string, unknown>) => {
  let out = fallback
  if (opts) {
    for (const [k, v] of Object.entries(opts)) {
      out = out.replaceAll(`{${k}}`, String(v))
    }
  }
  return out
}

const withCounts: GtdProject = {
  id: 'proj1',
  name: '示例项目',
  progress: 0.4667,
  done: 7,
  total: 15,
  available: true,
}

describe('projectProgressTitle —— 比例口径', () => {
  test('0–1 比例 ⇒ 百分比 = round(p×100)', () => {
    const title = projectProgressTitle({ id: 'p', name: 'n', progress: 0.5 }, t)
    expect(title).toBe('50%')
  })

  test('46.67% ⇒ 47%（不是 4667%）', () => {
    const title = projectProgressTitle({ id: 'p', name: 'n', progress: 0.4667 }, t)
    expect(title).toBe('47%')
  })

  test('有分子分母 ⇒ 显示「7 / 15 行动完成」', () => {
    expect(projectProgressTitle(withCounts, t)).toBe('7 / 15 行动完成')
  })
})

describe('projectProgressTitle —— 读不到 ≠ 读到 0', () => {
  test('available=false ⇒ 不出标题（不冒充 0%）', () => {
    const p: GtdProject = { id: 'p', name: 'n', progress: 0, done: 0, total: 0, available: false }
    expect(projectProgressTitle(p, t)).toBeNull()
  })

  test('没有 progress ⇒ 不出标题', () => {
    expect(projectProgressTitle({ id: 'p', name: 'n' }, t)).toBeNull()
  })
})
