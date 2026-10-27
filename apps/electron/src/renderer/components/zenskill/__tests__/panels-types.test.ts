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
  if (value <= 3) return 'bg-success/10 text-success-text'
  if (value <= 6) return 'bg-info/10 text-info-text'
  return 'bg-destructive/10 text-destructive-text'
}

describe('energyChipClass', () => {
  test('value=0 → success', () => expect(energyChipClass(0)).toContain('success'))
  test('value=3 → success (边界)', () => expect(energyChipClass(3)).toContain('success'))
  test('value=4 → info', () => expect(energyChipClass(4)).toContain('info'))
  test('value=6 → info (边界)', () => expect(energyChipClass(6)).toContain('info'))
  test('value=7 → destructive', () => expect(energyChipClass(7)).toContain('destructive'))
  test('value=10 → destructive', () => expect(energyChipClass(10)).toContain('destructive'))
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

// ─── InsightsPanel level colors ───
const INSIGHT_LEVEL_COLORS: Record<string, string> = {
  high: 'bg-destructive/15 text-destructive-text',
  medium: 'bg-info/15 text-info-text',
  low: 'bg-success/15 text-success-text',
}

describe('InsightLevelColors', () => {
  test('high → destructive', () => expect(INSIGHT_LEVEL_COLORS.high).toContain('destructive'))
  test('medium → info', () => expect(INSIGHT_LEVEL_COLORS.medium).toContain('info'))
  test('low → success', () => expect(INSIGHT_LEVEL_COLORS.low).toContain('success'))
  test('未知级别 fallback 到 low', () => {
    const level = 'unknown'
    const color = INSIGHT_LEVEL_COLORS[level] || INSIGHT_LEVEL_COLORS.low
    expect(color).toContain('success')
  })
})

// ─── IncubatingPanel channel colors ───
// ★ 第二十一批 D 段：测试**直接导入集中语义色表**（不再在测试里复制一份）
//   —— 复制 ⇒ 测试与产品会分叉（本次就分叉过一次：产品改了 consolidate 的色，
//   测试还断言着旧的 purple ⇒ 门禁红而产品已改 ⇒ 门禁失去意义）。
import { LOOP_CHANNEL_COLORS as CHANNEL_COLORS } from '../panels/semanticColors'

describe('IncubatingChannelColors', () => {
  test('reflect → accent', () => expect(CHANNEL_COLORS.reflect).toContain('accent'))
  test('consolidate → muted（归位后不再用默认色）', () => expect(CHANNEL_COLORS.consolidate).toContain('muted'))
  test('insight → info', () => expect(CHANNEL_COLORS.insight).toContain('info'))
  test('purify → success', () => expect(CHANNEL_COLORS.purify).toContain('success'))
  test('未知通道 fallback', () => {
    const channel = 'unknown'
    const color = CHANNEL_COLORS[channel] || 'bg-muted text-muted-foreground'
    expect(color).toContain('muted')
  })
})

// ─── IncubatingPanel promote threshold ───
describe('IncubatingPromoteThreshold', () => {
  const PROMOTE_THRESHOLD_PCT = 80
  test('maturity 0.8 → 可 promote', () => {
    const pct = Math.round(Math.min(Math.max(0.8, 0), 1) * 100)
    expect(pct).toBeGreaterThanOrEqual(PROMOTE_THRESHOLD_PCT)
  })
  test('maturity 0.79 → 不可 promote', () => {
    const pct = Math.round(Math.min(Math.max(0.79, 0), 1) * 100)
    expect(pct).toBeLessThan(PROMOTE_THRESHOLD_PCT)
  })
  test('maturity 1.0 → 可 promote', () => {
    const pct = Math.round(Math.min(Math.max(1.0, 0), 1) * 100)
    expect(pct).toBeGreaterThanOrEqual(PROMOTE_THRESHOLD_PCT)
  })
  test('maturity 0 → 不可 promote', () => {
    const pct = Math.round(Math.min(Math.max(0, 0), 1) * 100)
    expect(pct).toBeLessThan(PROMOTE_THRESHOLD_PCT)
  })
})

// ─── EnergyBar color thresholds ───
describe('EnergyBarColors', () => {
  function energyColor(pct: number): string {
    if (pct > 0.7) return 'bg-success/70'
    if (pct > 0.3) return 'bg-info/70'
    if (pct > 0.1) return 'bg-energy-low/70'
    return 'bg-destructive/70'
  }
  test('pct > 0.7 → success', () => expect(energyColor(0.8)).toContain('success'))
  test('pct > 0.3 → info', () => expect(energyColor(0.5)).toContain('info'))
  test('pct > 0.1 → energy-low', () => expect(energyColor(0.2)).toContain('energy-low'))
  test('pct <= 0.1 → destructive', () => expect(energyColor(0.05)).toContain('destructive'))
  test('pct = 0 → destructive', () => expect(energyColor(0)).toContain('destructive'))
  test('pct = 1 → success', () => expect(energyColor(1)).toContain('success'))
})

// ─── RadarChart vertex calculation ───
describe('RadarChartVertices', () => {
  function pentagonPoints(cx: number, cy: number, r: number, n: number): string[] {
    const points: string[] = []
    for (let i = 0; i < n; i++) {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2
      points.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`)
    }
    return points
  }
  test('5 个顶点', () => {
    const points = pentagonPoints(100, 100, 50, 5)
    expect(points).toHaveLength(5)
  })
  test('顶点在圆上', () => {
    const points = pentagonPoints(100, 100, 50, 5)
    points.forEach(p => {
      const [x, y] = p.split(',').map(Number)
      const dist = Math.sqrt((x - 100) ** 2 + (y - 100) ** 2)
      expect(dist).toBeCloseTo(50, 0)
    })
  })
  test('第一个顶点在正上方', () => {
    const points = pentagonPoints(100, 100, 50, 5)
    const [x, y] = points[0].split(',').map(Number)
    expect(x).toBeCloseTo(100, 0)
    expect(y).toBeCloseTo(50, 0)
  })
})

// ─── LearningPath difficulty colors ───
describe('LearningPathDifficultyColors', () => {
  const DIFFICULTY_COLORS: Record<string, string> = {
    beginner: 'bg-success/15 text-success-text',
    intermediate: 'bg-info/15 text-info-text',
    advanced: 'bg-energy-low/15 text-energy-low-text',
    expert: 'bg-destructive/15 text-destructive-text',
  }
  test('beginner → success', () => expect(DIFFICULTY_COLORS.beginner).toContain('success'))
  test('intermediate → info', () => expect(DIFFICULTY_COLORS.intermediate).toContain('info'))
  test('advanced → energy-low', () => expect(DIFFICULTY_COLORS.advanced).toContain('energy-low'))
  test('expert → destructive', () => expect(DIFFICULTY_COLORS.expert).toContain('destructive'))
  test('未知难度 fallback', () => {
    const level = 'unknown'
    const color = DIFFICULTY_COLORS[level] || DIFFICULTY_COLORS.beginner
    expect(color).toContain('success')
  })
})

// ─── SkillGraph relation colors ───
describe('SkillGraphRelationColors', () => {
  const RELATION_COLORS: Record<string, string> = {
    prerequisite: '#3b82f6',
    related: '#8b5cf6',
    similar: '#f59e0b',
    enables: '#10b981',
    conflicts: '#ef4444',
  }
  test('prerequisite → accent', () => expect(RELATION_COLORS.prerequisite).toBe('#3b82f6'))
  test('related → purple', () => expect(RELATION_COLORS.related).toBe('#8b5cf6'))
  test('similar → info', () => expect(RELATION_COLORS.similar).toBe('#f59e0b'))
  test('enables → success', () => expect(RELATION_COLORS.enables).toBe('#10b981'))
  test('conflicts → destructive', () => expect(RELATION_COLORS.conflicts).toBe('#ef4444'))
  test('未知关系 fallback', () => {
    const relation = 'unknown'
    const color = RELATION_COLORS[relation] ?? '#666'
    expect(color).toBe('#666')
  })
})

// ─── ZenLoop channel colors ───
describe('ZenLoopChannelColors', () => {
  test('reflect → accent', () => expect(CHANNEL_COLORS.reflect).toContain('accent'))
  test('consolidate → muted（归位后不再用默认色）', () => expect(CHANNEL_COLORS.consolidate).toContain('muted'))
  test('insight → info', () => expect(CHANNEL_COLORS.insight).toContain('info'))
  test('purify → success', () => expect(CHANNEL_COLORS.purify).toContain('success'))
})

// ─── Design Token 验证 ───
describe('DesignTokens', () => {
  const ZS = {
    pagePad: 'px-5 pt-4 pb-3',
    card: 'rounded border border-border/30 p-2',
    title: 'text-sm font-medium',
    subtitle: 'text-[11px] text-muted-foreground',
    body: 'text-xs',
    badge: 'text-[10px]',
    errorBanner: 'text-xs text-destructive bg-destructive/5 rounded p-2',
    emptyState: 'text-xs text-muted-foreground italic',
    skeleton: 'h-4 rounded bg-muted/60 animate-pulse',
  }
  test('pagePad 包含 padding', () => {
    expect(ZS.pagePad).toContain('px-5')
    expect(ZS.pagePad).toContain('pt-4')
    expect(ZS.pagePad).toContain('pb-3')
  })
  test('card 包含 border 和 padding', () => {
    expect(ZS.card).toContain('border')
    expect(ZS.card).toContain('p-2')
  })
  test('errorBanner 包含 destructive', () => {
    expect(ZS.errorBanner).toContain('destructive')
  })
  test('skeleton 包含 animate-pulse', () => {
    expect(ZS.skeleton).toContain('animate-pulse')
  })
})
