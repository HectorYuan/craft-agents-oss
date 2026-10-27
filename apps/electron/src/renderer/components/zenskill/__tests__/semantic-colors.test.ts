/**
 * 语义色集中表纪律单测（第二十一批 D 段）
 *
 * ★ 守的是**颜色纪律**（不是「好看」）：
 *   1. ★ **同族不撞色**：一族里的每一档必须用**不同**的语义类
 *      —— 原实现里 `reflect` 与 `consolidate` 其实**都是紫** ⇒ 标签根本分不开；
 *   2. ★ **不用 Tailwind 默认色**（`purple-500` 这类）：默认色是**裸值**，
 *      没有双模（暗色下不变）、没有语义归属 ⇒ 散落即失控；
 *   3. ★ **不用字面量 hex**（`#7c5cff` 这类）：同理，且没有暗色变体；
 *   4. ★ **色相不承载档位**：技术分层（记忆 L1/L2/L3）三层**同色**，
 *      档位由**标签文字**承载（区分「技术分层」与「等级色阶」）。
 */
import { describe, test, expect } from 'bun:test'
import {
  LEVEL_COLORS,
  LOOP_CHANNEL_COLORS,
  SUGGEST_TYPE_COLORS,
  RELATION_COLORS,
  MEMORY_LAYER_COLORS,
} from '../panels/semanticColors'

/** 取一格里的「语义类名」（如 `bg-accent/15 text-accent` → accent / info / …） */
function semanticTokens(value: string): string[] {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((c) => c.replace(/^(bg|text|border|ring)-/, '').replace(/\/.*$/, '').replace(/-text$/, ''))
}

describe('集中表 —— 同族不撞色', () => {
  test('境界 5 档各用不同语义类', () => {
    const tokens = Object.values(LEVEL_COLORS).map((s) => s.text.replace(/^text-/, '').replace(/-text$/, ''))
    expect(new Set(tokens).size).toBe(tokens.length)
  })

  test('ZenLoop 四通道各用不同语义类', () => {
    const tokens = Object.values(LOOP_CHANNEL_COLORS).flatMap(semanticTokens)
    // 每格两个类（底 + 字）⇒ 取「字」那一半来比
    const textTokens = Object.values(LOOP_CHANNEL_COLORS).map((c) =>
      c.split(/\s+/).find((x) => x.startsWith('text-'))!.replace(/^text-/, ''),
    )
    expect(new Set(textTokens).size).toBe(textTokens.length)
    expect(tokens.length).toBeGreaterThan(0)
  })

  test('建议类型 4 类各用不同语义类', () => {
    const textTokens = Object.values(SUGGEST_TYPE_COLORS).map((c) =>
      c.split(/\s+/).find((x) => x.startsWith('text-'))!.replace(/^text-/, ''),
    )
    expect(new Set(textTokens).size).toBe(textTokens.length)
  })

  test('技能关系 5 种各用不同语义类', () => {
    const tokens = Object.values(RELATION_COLORS).map((v) => v.replace('var(--', '').replace(')', ''))
    expect(new Set(tokens).size).toBe(tokens.length)
  })
})

describe('集中表 —— 不用默认色 / 不用字面量 hex', () => {
  const all = [
    ...Object.values(LEVEL_COLORS).flatMap((s) => [s.bg, s.text, s.border]),
    ...Object.values(LOOP_CHANNEL_COLORS),
    ...Object.values(SUGGEST_TYPE_COLORS),
    ...Object.values(RELATION_COLORS),
    ...Object.values(MEMORY_LAYER_COLORS),
  ]

  test('没有 Tailwind 默认色尾号（-100..-950）', () => {
    const offenders = all.filter((v) => /-(100|200|300|400|500|600|700|800|900|950)\b/.test(v))
    expect(offenders).toEqual([])
  })

  test('没有字面量 hex（必须走 CSS 变量 / 语义类）', () => {
    const offenders = all.filter((v) => v.includes('#'))
    expect(offenders).toEqual([])
  })

  test('关系色都走 var(--*) 形式（inline style 用不了 Tailwind 类）', () => {
    for (const v of Object.values(RELATION_COLORS)) {
      expect(v.startsWith('var(--')).toBe(true)
    }
  })
})

describe('色相不承载档位 —— 技术分层同色', () => {
  test('记忆层级 L1/L2/L3 三层同色（档位由标签文字承载）', () => {
    const values = Object.values(MEMORY_LAYER_COLORS)
    expect(new Set(values).size).toBe(1)
  })

  test('★ 但境界色阶保留色阶（等级的身份色是产品价值的一部分）', () => {
    const values = Object.values(LEVEL_COLORS).map((s) => s.text)
    expect(new Set(values).size).toBeGreaterThan(1)
  })
})
