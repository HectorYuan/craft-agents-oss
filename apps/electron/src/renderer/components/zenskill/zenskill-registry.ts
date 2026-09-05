/**
 * ZenSkill page registry (L1).
 *
 * Single source of truth for ZenSkill top-level full-page views surfaced
 * through the app shell sidebar and MainContentPanel. Adding a page is a
 * one-entry change here plus a route builder — upstream files never grow
 * per-page branches (they delegate to this registry via ZenSkillPageMount).
 *
 * Route logic (parse/build) lives in the sibling zero-dependency module
 * zenskill-routes.ts so shared/route-parser.ts can delegate without
 * importing the component tree.
 */
import type { ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Brain, Inbox, Zap } from 'lucide-react'
import { GtdWorkspace } from './pages/GtdWorkspace'
import { MemoryBrowser } from './pages/MemoryBrowser'
import { ZenSkillOverview } from './pages/ZenSkillOverview'

/** The ZenSkill MCP source slug all ZenSkill pages talk to. */
export const ZENSKILL_SOURCE_SLUG = 'zenskill-4'

export interface ZenSkillPageProps {
  workspaceId?: string
  initialTab?: string
  onNavigateToChat?: (message: string) => void
}

export interface ZenSkillPageRegistration {
  /** Route path segment under the zenskill navigator (e.g. 'gtd' -> zenskill/gtd) */
  slug: string
  component: ComponentType<ZenSkillPageProps>
  icon: LucideIcon
  i18nLabelKey: string
  /** 自定义路由构建器；缺省使用 zenskill/{slug} */
  routeBuilder?: () => string
}

export const ZENSKILL_PAGES: ZenSkillPageRegistration[] = [
  {
    slug: 'overview',
    component: ZenSkillOverview,
    icon: Zap,
    i18nLabelKey: 'zenskill.overview.title',
  },
  {
    slug: 'gtd',
    component: GtdWorkspace,
    icon: Inbox,
    i18nLabelKey: 'zenskill.gtd.title',
  },
  {
    slug: 'memory',
    component: MemoryBrowser,
    icon: Brain,
    i18nLabelKey: 'zenskill.memory.title',
  },
]

/** Resolve a page registration by route slug; falls back to the first page. */
export function resolveZenSkillPage(pageSlug?: string): ZenSkillPageRegistration | undefined {
  return ZENSKILL_PAGES.find((p) => p.slug === pageSlug) ?? ZENSKILL_PAGES[0]
}

/**
 * Product ordering for ZenSkill-created Pages in the sidebar (overview first,
 * matching the IA review's recommended order). Slugs come from the ZenSkill
 * MCP bundled Pages resources. Pages whose slug is not listed keep their
 * original relative order after the listed ones.
 */
export const ZENSKILL_PAGE_ORDER: readonly string[] = [
  'zenskill-dashboard',
  'zenskill-daily-review',
  'zenskill-zenloop',
  'zenskill-growth',
  'zenskill-skill-graph',
]

/**
 * Sort loaded pages for the app-shell sidebar: listed slugs in product order,
 * then unlisted pages in their original order (Array#sort is stable).
 */
export function sortPagesForSidebar<T extends { config: { slug: string } }>(pages: T[]): T[] {
  const idx = new Map(ZENSKILL_PAGE_ORDER.map((s, i) => [s, i]))
  const fallback = idx.size
  return [...pages].sort(
    (a, b) => (idx.get(a.config.slug) ?? fallback) - (idx.get(b.config.slug) ?? fallback),
  )
}
