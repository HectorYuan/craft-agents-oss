/**
 * View registry guard (P0 · 视图注册表).
 *
 * The ZenSkill navigator is migrating from "11 flat pages" to "views grouped by
 * their host domain". Two files carry that knowledge and are joined by `slug`:
 *
 *   - zenskill-registry.ts  → components + icons + i18n label keys
 *   - zenskill-views.ts     → hostDomain / mode / slot  (pure data, no React)
 *
 * A slug present in one file but not the other would silently fall back to the
 * wrong domain (or get dropped from the sidebar). These tests make that a CI
 * failure instead of a runtime surprise.
 *
 * Design source: docs/spec_zenskill_domain_architecture_v1_20261031.md (§5).
 */
import { describe, test, expect } from 'bun:test'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { ZENSKILL_PAGES } from '../zenskill-registry'
import {
  ZENSKILL_VIEW_SPECS,
  HOST_DOMAIN_ORDER,
  HOST_DOMAIN_LABEL_KEYS,
  groupViewsByHostDomain,
  isSidebarVisibleMode,
  resolveViewSpec,
} from '../zenskill-views'

const here = dirname(fileURLToPath(import.meta.url))

/**
 * Locate the shared locale bundle by walking up from this test file.
 * (A hard-coded relative depth breaks as soon as the file moves.)
 */
function findLocaleFile(): string {
  let dir = here
  for (let i = 0; i < 10; i++) {
    const candidate = join(dir, 'packages/shared/src/i18n/locales/en.json')
    if (existsSync(candidate)) return candidate
    dir = dirname(dir)
  }
  throw new Error('cannot locate packages/shared/src/i18n/locales/en.json')
}

const localePath = findLocaleFile()

describe('ZenSkill view registry', () => {
  test('registry and view specs cover exactly the same slugs', () => {
    const pageSlugs = ZENSKILL_PAGES.map((p) => p.slug).sort()
    const specSlugs = ZENSKILL_VIEW_SPECS.map((v) => v.slug).sort()
    expect(specSlugs).toEqual(pageSlugs)
  })

  test('no duplicate slugs on either side', () => {
    const pageSlugs = ZENSKILL_PAGES.map((p) => p.slug)
    const specSlugs = ZENSKILL_VIEW_SPECS.map((v) => v.slug)
    expect(new Set(pageSlugs).size).toBe(pageSlugs.length)
    expect(new Set(specSlugs).size).toBe(specSlugs.length)
  })

  test('every registry page carries hostDomain and mode', () => {
    for (const page of ZENSKILL_PAGES) {
      expect(page.hostDomain).toBeTruthy()
      expect(page.mode).toBeTruthy()
      // The fallback in the registry must never actually be needed.
      expect(resolveViewSpec(page.slug)).toBeDefined()
    }
  })

  test('every used hostDomain is in HOST_DOMAIN_ORDER (so no group is dropped)', () => {
    const used = new Set(ZENSKILL_VIEW_SPECS.map((v) => v.hostDomain))
    for (const domain of used) {
      expect(HOST_DOMAIN_ORDER).toContain(domain)
    }
  })

  test('every hostDomain has a label key', () => {
    for (const domain of HOST_DOMAIN_ORDER) {
      expect(HOST_DOMAIN_LABEL_KEYS[domain]).toBeTruthy()
    }
  })

  test('every label key resolves in the en locale', () => {
    const locale = JSON.parse(readFileSync(localePath, 'utf8'))
    for (const domain of HOST_DOMAIN_ORDER) {
      const key = HOST_DOMAIN_LABEL_KEYS[domain]
      expect(locale[key]).toBeTruthy()
    }
  })

  test('grouping keeps HOST_DOMAIN_ORDER and drops empty groups', () => {
    const groups = groupViewsByHostDomain()
    const order = groups.map((g) => g.hostDomain)
    // Must be a subsequence of HOST_DOMAIN_ORDER, not a re-ordering.
    const positions = order.map((d) => HOST_DOMAIN_ORDER.indexOf(d))
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
    for (const group of groups) {
      expect(group.views.length).toBeGreaterThan(0)
    }
  })

  test('grouping is lossless (every visible view appears exactly once)', () => {
    const groups = groupViewsByHostDomain()
    const grouped = groups.flatMap((g) => g.views.map((v) => v.slug))
    expect(grouped.sort()).toEqual(ZENSKILL_VIEW_SPECS.map((v) => v.slug).sort())
  })

  test('panel and quick modes stay out of the sidebar; page and tab do not', () => {
    expect(isSidebarVisibleMode('panel')).toBe(false)
    expect(isSidebarVisibleMode('quick')).toBe(false)
    expect(isSidebarVisibleMode('page')).toBe(true)
    expect(isSidebarVisibleMode('tab')).toBe(true)
  })

  test('mode="quick" views are excluded from the sidebar grouping', () => {
    const groups = groupViewsByHostDomain(ZENSKILL_VIEW_SPECS, true)
    const slugs = groups.flatMap((g) => g.views.map((v) => v.slug))
    for (const view of ZENSKILL_VIEW_SPECS) {
      if (view.mode === 'panel' || view.mode === 'quick') {
        expect(slugs).not.toContain(view.slug)
      }
    }
  })

  test('resolveViewSpec returns undefined for unknown slugs', () => {
    expect(resolveViewSpec('nope')).toBeUndefined()
    expect(resolveViewSpec(undefined)).toBeUndefined()
    expect(resolveViewSpec('gtd')?.hostDomain).toBe('project')
  })
})

/**
 * 侧边栏条目构造器 —— 分组、标题落位、活跃判定。
 *
 * ★ 为什么要单独守：
 *   这层是「信息架构」在界面上的唯一落点 —— 分组错了就等于设计没实现。
 *   且它有三条容易被改坏的隐含契约：
 *   ① 分组顺序固定（不是字母序）
 *   ② 分组标题只挂在**组首项**上（否则一个组会出现两个标题）
 *   ③ 活跃判定必须与路由 slug 一致（点错高亮会误导用户）
 */
import { buildDomainGroupedNavItems } from '../zenskill-nav-items'

const t = (key: string) => key
const navigate = () => {}

describe('ZenSkill domain-grouped nav items', () => {
  test('按 HOST_DOMAIN_ORDER 分组，且每组第一个条目带分组标题', () => {
    const items = buildDomainGroupedNavItems(t, navigate, { navigator: 'sessions' })
    const labels = items
      .map((i) => ('sectionLabel' in i ? (i as { sectionLabel?: string }).sectionLabel : undefined))
      .filter(Boolean)
    // 每个分组只出现一次标题
    expect(new Set(labels).size).toBe(labels.length)
    expect(labels.length).toBeGreaterThan(1)
    // 顺序 = 会话 → 项目 → 技能 → 今日 → 设置
    expect(labels).toEqual([
      'zenskill.domain.conversation',
      'zenskill.domain.project',
      'zenskill.domain.skill',
      'zenskill.domain.today',
      'zenskill.domain.settings',
    ])
  })

  test('条目 id 与 slug 一一对应（点击目标不漂移）', () => {
    const items = buildDomainGroupedNavItems(t, navigate, { navigator: 'sessions' })
    const ids = items.map((i) => i.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.every((id) => id.startsWith('nav:zenskill:'))).toBe(true)
  })

  test('当前页高亮，且只有当前页高亮', () => {
    const items = buildDomainGroupedNavItems(t, navigate, {
      navigator: 'zenskill',
      details: { type: 'zenskill-page', pageSlug: 'gtd' },
    })
    const active = items.filter((i) => ('variant' in i ? i.variant : '') === 'default')
    expect(active).toHaveLength(1)
    expect(active[0].id).toBe('nav:zenskill:gtd')
  })

  test('不在该导航上时不高亮任何条目', () => {
    const items = buildDomainGroupedNavItems(t, navigate, { navigator: 'sessions' })
    const active = items.filter((i) => ('variant' in i ? i.variant : '') === 'default')
    expect(active).toHaveLength(0)
  })
})
