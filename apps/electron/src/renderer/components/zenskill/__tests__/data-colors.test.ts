/**
 * 动态分类色的**双模与对比度**单测（第二十一批 D-2）
 *
 * ★ 守两件事（都来自实测，不是审美偏好）：
 *   1. ★ **双模到位**：每个分类色在 `:root`（亮色）与 `.dark`（暗色）**各有一套值**
 *      —— 分类名来自数据，不能穷举成语义类；但「不能穷举」**不等于**「放弃双模」。
 *   2. ★ **对比度达标**：实测这 17 个色在**暗底**上都够用（≥ 4.24），
 *      但在**亮底**上有一半 < 3:1 ⇒ ★ **亮色模式才是问题** ⇒
 *      ⇒ 亮色版必须**加深**到对亮底 ≥ 3:1（图形/描边/图标的 WCAG 非文本标准）。
 *
 * ★ 本测试**直接读 CSS 文件**（不是复制一份到测试里）⇒ 测的就是真实定义
 *   ⇒ 避免「测试里那份副本与产品那份分叉」的老问题（本次 D-1/D-2 都踩过）。
 */
import { describe, test, expect } from 'bun:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(join(here, '../panels/dataColors.css'), 'utf-8')

/** 解析某个块里的 `--name: #hex;` */
function blockVars(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`)
  expect(start).toBeGreaterThan(-1)
  const body = css.slice(start, css.indexOf('}', start))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out[m[1]] = m[2]
  }
  return out
}

const light = blockVars(':root')
const dark = blockVars('.dark')

/** WCAG 相对亮度与对比度 */
function srgb(c: number): number {
  const v = c / 255
  return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
}
function luminance(hex: string): number {
  const h = hex.replace('#', '')
  const r = srgb(parseInt(h.slice(0, 2), 16))
  const g = srgb(parseInt(h.slice(2, 4), 16))
  const b = srgb(parseInt(h.slice(4, 6), 16))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function contrast(a: string, b: string): number {
  const la = luminance(a)
  const lb = luminance(b)
  const hi = Math.max(la, lb)
  const lo = Math.min(la, lb)
  return (hi + 0.05) / (lo + 0.05)
}

const LIGHT_BG = '#F7F8FA' // --Semantic-bg-canvas
const DARK_BG = '#080A10' // 上游 .dark 页面底
const MIN_GRAPHICS = 3.0 // WCAG 非文本对比（图形/描边/图标）

const names = Object.keys(light)

describe('动态分类色 —— 双模到位', () => {
  test('两模的变量集合完全一致', () => {
    expect(Object.keys(dark).sort()).toEqual(names.slice().sort())
  })

  test('每个变量在两模都有值（无「只有亮色」的孤儿）', () => {
    for (const n of names) {
      expect(light[n]).toMatch(/^#[0-9a-fA-F]{6}$/)
      expect(dark[n]).toMatch(/^#[0-9a-fA-F]{6}$/)
    }
  })

  test('域名色 10 个 + 洞察类型色 7 个', () => {
    expect(names.filter((n) => n.startsWith('zenskill-domain-')).length).toBe(10)
    expect(names.filter((n) => n.startsWith('zenskill-insight-')).length).toBe(7)
  })
})

describe('动态分类色 —— 对比度达标（★ 亮色模式才是问题）', () => {
  test('亮色版对亮底 ≥ 3:1（图形/描边/图标）', () => {
    for (const n of names) {
      expect({ name: n, ratio: contrast(light[n], LIGHT_BG) }).toEqual({
        name: n,
        ratio: expect.any(Number),
      })
      expect(contrast(light[n], LIGHT_BG)).toBeGreaterThanOrEqual(MIN_GRAPHICS)
    }
  })

  test('暗色版对暗底 ≥ 3:1', () => {
    for (const n of names) {
      expect(contrast(dark[n], DARK_BG)).toBeGreaterThanOrEqual(MIN_GRAPHICS)
    }
  })

  test('亮色版是「同色相的加深版」⇒ 不该比暗色版更亮', () => {
    for (const n of names) {
      expect(luminance(light[n])).toBeLessThanOrEqual(luminance(dark[n]) + 0.001)
    }
  })
})

describe('动态分类色 —— 同模内互相可区分', () => {
  test('亮色版两两不同（分类色要能互相区分）', () => {
    const vals = names.map((n) => light[n].toLowerCase())
    expect(new Set(vals).size).toBe(vals.length)
  })

  test('暗色版两两不同', () => {
    const vals = names.map((n) => dark[n].toLowerCase())
    expect(new Set(vals).size).toBe(vals.length)
  })
})
