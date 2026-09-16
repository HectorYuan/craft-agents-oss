/**
 * Slug consistency guard (R6, updated after the R-series slug unification).
 *
 * Every ZenSkill page must talk to the seeded MCP source through the single
 * ZENSKILL_SOURCE_SLUG export ('zenskill', see ../zenskill-registry.ts;
 * zenskill-seed.ts seeds the MCP source under the same slug).
 * A locally hardcoded `'zenskill-4'` literal is a stale pre-unification
 * remnant that points at a non-existent source. This test scans the page
 * sources so a regression fails CI instead of surfacing at runtime.
 */
import { describe, test, expect } from 'bun:test'
import { readFileSync, readdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const pagesDir = join(here, '..', 'pages')
const marketSearchPath = join(here, '..', 'ZenSkillMarketSearch.tsx')

/** Source files that must not carry a local 'zenskill' (slug) literal. */
function guardedFiles(): { name: string; content: string }[] {
  const pages = readdirSync(pagesDir)
    .filter((f) => f.endsWith('.tsx'))
    .map((f) => ({
      name: `pages/${f}`,
      content: readFileSync(join(pagesDir, f), 'utf8'),
    }))
  const marketSearch = {
    name: 'ZenSkillMarketSearch.tsx',
    content: readFileSync(marketSearchPath, 'utf8'),
  }
  return [...pages, marketSearch]
}

// Matches a stale pre-unification 'zenskill-4' slug literal.
// The unified slug is the bare 'zenskill' (see zenskill-seed.ts).
const STALE_SLUG_LITERAL = /'zenskill-4'/

describe('ZenSkill source slug consistency', () => {
  const files = guardedFiles()

  test('guard finds the ZenSkill pages and market search files', () => {
    expect(files.length).toBeGreaterThan(5)
    expect(files.some((f) => f.name === 'ZenSkillMarketSearch.tsx')).toBe(true)
  })

  test("no page carries the stale 'zenskill-4' slug literal", () => {
    const offenders = files.filter((f) => STALE_SLUG_LITERAL.test(f.content))
    expect(
      offenders.map((f) => f.name),
    ).toEqual([])
  })

  test('pages import ZENSKILL_SOURCE_SLUG from the registry (or use no slug at all)', () => {
    const registry = readFileSync(join(here, '..', 'zenskill-registry.ts'), 'utf8')
    expect(registry).toContain("export const ZENSKILL_SOURCE_SLUG = 'zenskill'")
  })
})
