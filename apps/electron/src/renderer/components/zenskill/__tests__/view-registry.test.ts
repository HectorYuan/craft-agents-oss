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
