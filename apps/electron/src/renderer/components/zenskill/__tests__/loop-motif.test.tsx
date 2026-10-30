/**
 * 母题「五层回路」签名图形 + 回合状态徽章 —— 守卫（第二十三批 · 页面侧）
 *
 * ★ 守的是**稿面契约**，不是「好看」：
 *   1. ★ 五段齐全、顺序固定（回路走向：左上斜 → 左竖 → 底横 → 右竖 → 右上斜）；
 *   2. ★ 当前层高亮落在正确的段上（稿 `3:396`「96 · 当前 L3」⇒ 第 3 段 = 底横）；
 *   3. ★ 越界层号夹到有效区间（数据异常时不能「一段都不亮」）；
 *   4. ★ 颜色全走 `--Semantic-*` token（组件与色表**都不含字面 hex**）。
 *
 * 真相源：ardot `3:304`（五层回路）+ `3:310`（回合状态）；页面落点 `6:379` / `6:418`。
 */
import { describe, test, expect } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  LOOP_MOTIF_SEGMENTS,
  activeSegmentIndex,
  LoopMotif,
  LoopStatusMotif,
} from '../panels/LoopMotif'
import { LOOP_MOTIF_COLORS } from '../panels/semanticColors'

const HEX = /#[0-9a-fA-F]{3,8}\b/

describe('五层回路 —— 几何与层号', () => {
  test('五段齐全，顺序即回路走向（底横 = 第 3 段）', () => {
    expect(LOOP_MOTIF_SEGMENTS.length).toBe(5)
    const ys = LOOP_MOTIF_SEGMENTS.map((s) => s.ty)
    const bottom = ys.indexOf(Math.max(...ys))
    expect(bottom).toBe(2)
  })

  test('当前层 → 高亮段索引（稿「当前 L3」= 第 3 段）', () => {
    expect(activeSegmentIndex(3)).toBe(2)
    expect(activeSegmentIndex(1)).toBe(0)
    expect(activeSegmentIndex(5)).toBe(4)
  })

  test('越界层号夹到 [1,5]，永不返回越界索引', () => {
    expect(activeSegmentIndex(0)).toBe(0)
    expect(activeSegmentIndex(-7)).toBe(0)
    expect(activeSegmentIndex(99)).toBe(4)
    expect(activeSegmentIndex(Number.NaN)).toBe(2)
  })
})

describe('渲染 —— 稿面兑现', () => {
  test('96 档：五段都在，且只有当前层那一段用 accent 色', () => {
    const html = renderToStaticMarkup(<LoopMotif currentLayer={3} size={96} />)
    const paths = html.match(/<path/g) ?? []
    expect(paths.length).toBe(5)
    const accent = html.split(LOOP_MOTIF_COLORS.current).length - 1
    expect(accent).toBe(1)
    const track = html.split(LOOP_MOTIF_COLORS.track).length - 1
    expect(track).toBe(4)
  })

  test('换层 ⇒ 高亮段跟着换（不是写死第 3 段）', () => {
    const a = renderToStaticMarkup(<LoopMotif currentLayer={1} size={96} />)
    const b = renderToStaticMarkup(<LoopMotif currentLayer={3} size={96} />)
    expect(a).not.toBe(b)
  })

  test('48/32/24 档是同一几何的缩放（viewBox 不变，只改尺寸）', () => {
    const h96 = renderToStaticMarkup(<LoopMotif currentLayer={3} size={96} />)
    const h48 = renderToStaticMarkup(<LoopMotif currentLayer={3} size={48} />)
    expect(h48).toContain('viewBox="0 0 96 96"')
    expect(h48).toContain('width="48"')
    expect(h96).toContain('width="96"')
  })

  test('16 档是单环（另一种画法，不是缩放）', () => {
    const html = renderToStaticMarkup(<LoopMotif currentLayer={3} size={16} />)
    expect(html).toContain('<circle')
    expect((html.match(/<path/g) ?? []).length).toBe(0)
  })

  test('三种回合状态：形态不同（点 / 空环 / 对勾）', () => {
    const active = renderToStaticMarkup(<LoopStatusMotif status="active" />)
    const pending = renderToStaticMarkup(<LoopStatusMotif status="pending" />)
    const done = renderToStaticMarkup(<LoopStatusMotif status="done" />)
    expect(active).toContain(LOOP_MOTIF_COLORS.statusActive)
    expect(pending).toContain(LOOP_MOTIF_COLORS.statusPending)
    expect(done).toContain(LOOP_MOTIF_COLORS.statusDone)
    // ★ 三态互不相同 —— 否则「进行中 / 待触发 / 已完成」在图上分不开
    expect(new Set([active, pending, done]).size).toBe(3)
  })
})

describe('颜色纪律 —— token 化、零字面 hex', () => {
  test('LOOP_MOTIF_COLORS 全部是 var(--Semantic-*) 且不含 hex', () => {
    for (const [k, v] of Object.entries(LOOP_MOTIF_COLORS)) {
      expect(v.startsWith('var(--Semantic-')).toBe(true)
      expect(HEX.test(v)).toBe(false)
    }
  })

  test('渲染产物里也不出现字面 hex', () => {
    const html = renderToStaticMarkup(<LoopMotif currentLayer={3} size={96} />)
    expect(HEX.test(html)).toBe(false)
  })

  test('三种回合状态色互不相同（可区分）', () => {
    const { statusActive, statusPending, statusDone } = LOOP_MOTIF_COLORS
    expect(new Set([statusActive, statusPending, statusDone]).size).toBe(3)
  })
})
