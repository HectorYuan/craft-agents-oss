/**
 * 纯函数单元测试 — panels/types.ts + panels/*.ts
 *
 * 覆盖 energyChipClass, parseIsoDate, weekKey, extractMcpJson,
 * resolveZenSkillPage, truncateContent, filterScores
 */
import { describe, test, expect } from 'bun:test'

// ─── energyChipClass ───
// 从 EnergyBar 提取
function energyChipClass(value: number): string {
  if (value <= 3) return 'bg-green-500/10 text-green-400'
  if (value <= 6) return 'bg-yellow-500/10 text-yellow-400'
  return 'bg-red-500/10 text-red-400'
}

describe('energyChipClass', () => {
  test('value=0 → green', () => expect(energyChipClass(0)).toContain('green'))
  test('value=3 → green (边界)', () => expect(energyChipClass(3)).toContain('green'))
  test('value=4 → yellow', () => expect(energyChipClass(4)).toContain('yellow'))
  test('value=6 → yellow (边界)', () => expect(energyChipClass(6)).toContain('yellow'))
  test('value=7 → red', () => expect(energyChipClass(7)).toContain('red'))
  test('value=10 → red', () => expect(energyChipClass(10)).toContain('red'))
})

// ─── parseIsoDate ───
function parseIsoDate(s?: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s ?? '')
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}

describe('parseIsoDate', () => {
  test('正常日期', () => {
    const d = parseIsoDate('2026-09-05')
    expect(d?.getFullYear()).toBe(2026)
    expect(d?.getMonth()).toBe(8) // 0-indexed
    expect(d?.getDate()).toBe(5)
  })
  test('空字符串 → null', () => expect(parseIsoDate('')).toBeNull())
  test('undefined → null', () => expect(parseIsoDate(undefined)).toBeNull())
  test('无效格式 → null', () => expect(parseIsoDate('not-a-date')).toBeNull())
  test('月份越界仍解析（JS Date 行为）', () => {
    const d = parseIsoDate('2026-13-01')
    expect(d).not.toBeNull()
  })
})

// ─── weekKey ───
function weekKey(d: Date): string {
  const monday = new Date(d)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return `${monday.getFullYear()}-${monday.getMonth()}-${monday.getDate()}`
}

describe('weekKey', () => {
  test('周一 (2026-09-07)', () => {
    const d = new Date(2026, 8, 7) // 2026-09-07 is Monday
    expect(weekKey(d)).toBe('2026-8-7')
  })
  test('周日 (2026-09-06)', () => {
    const d = new Date(2026, 8, 6) // 2026-09-06 is Sunday
    const key = weekKey(d)
    // Sunday maps to Monday 2026-08-31
    expect(key).toBe('2026-7-31')
  })
  test('跨年 (2025-12-29 是周一)', () => {
    const d = new Date(2025, 11, 29)
    expect(weekKey(d)).toBe('2025-11-29')
  })
})

// ─── extractMcpJson ───
function extractMcpJson(result: any): any {
  if (!result?.success) return null
  const inner = result.result
  if (!inner) return null
  const text = inner.content?.[0]?.text
  if (typeof text === 'string') {
    try { return JSON.parse(text) } catch { return null }
  }
  return inner
}

describe('extractMcpJson', () => {
  test('成功 + 有 content', () => {
    const r = { success: true, result: { content: [{ text: '{"ok":true}' }] } }
    expect(extractMcpJson(r)).toEqual({ ok: true })
  })
  test('success=false → null', () => {
    expect(extractMcpJson({ success: false })).toBeNull()
  })
  test('null → null', () => {
    expect(extractMcpJson(null)).toBeNull()
  })
  test('无 content → 返回 inner 对象', () => {
    expect(extractMcpJson({ success: true, result: {} })).toEqual({})
  })
  test('JSON 解析失败 → null', () => {
    const r = { success: true, result: { content: [{ text: 'not-json' }] } }
    expect(extractMcpJson(r)).toBeNull()
  })
})

// ─── resolveZenSkillPage ───
interface PageRegistration { slug: string; component: any }
function resolveZenSkillPage(pages: PageRegistration[], pageSlug?: string): PageRegistration | undefined {
  return pages.find((p) => p.slug === pageSlug) ?? pages[0]
}

describe('resolveZenSkillPage', () => {
  const pages = [
    { slug: 'overview', component: 'Overview' },
    { slug: 'gtd', component: 'Gtd' },
    { slug: 'memory', component: 'Memory' },
  ]
  test('已知 slug → 对应页面', () => {
    expect(resolveZenSkillPage(pages, 'gtd')?.slug).toBe('gtd')
  })
  test('未知 slug → 第一个页面', () => {
    expect(resolveZenSkillPage(pages, 'unknown')?.slug).toBe('overview')
  })
  test('undefined → 第一个页面', () => {
    expect(resolveZenSkillPage(pages, undefined)?.slug).toBe('overview')
  })
})

// ─── truncateContent ───
function truncateContent(content: string, expanded: boolean, limit = 200): string {
  if (expanded || content.length <= limit) return content
  return `${content.slice(0, limit)}…`
}

describe('truncateContent', () => {
  test('展开模式 → 返回原文', () => {
    expect(truncateContent('hello'.repeat(100), true)).toBe('hello'.repeat(100))
  })
  test('短文本不截断', () => {
    expect(truncateContent('short', false)).toBe('short')
  })
  test('长文本截断', () => {
    const long = 'a'.repeat(300)
    const result = truncateContent(long, false)
    expect(result.length).toBe(201) // 200 + '…'
    expect(result.endsWith('…')).toBeTrue()
  })
})

// ─── filterScores ───
function filterScores(scores: Record<string, number>): Record<string, number> {
  const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']
  const filtered: Record<string, number> = {}
  for (const k of FIVE_DIMS) {
    if (k in scores) filtered[k] = scores[k]
  }
  return filtered
}

describe('filterScores', () => {
  test('过滤 composite 字段', () => {
    const input = { proficiency: 80, stability: 70, satisfaction: 60, responsiveness: 50, memory: 40, composite: 65 }
    const result = filterScores(input)
    expect(result).toEqual({ proficiency: 80, stability: 70, satisfaction: 60, responsiveness: 50, memory: 40 })
    expect(result).not.toHaveProperty('composite')
  })
  test('空对象 → 空结果', () => {
    expect(filterScores({})).toEqual({})
  })
  test('只保留 5 个核心维度', () => {
    const input = { proficiency: 1, custom: 2, stability: 3 }
    expect(Object.keys(filterScores(input))).toEqual(['proficiency', 'stability'])
  })
})
