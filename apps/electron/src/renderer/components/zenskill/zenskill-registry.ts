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
import { Brain, Inbox } from 'lucide-react'
import { GtdWorkspace } from './pages/GtdWorkspace'
import { MemoryBrowser } from './pages/MemoryBrowser'

/** The ZenSkill MCP source slug all ZenSkill pages talk to. */
export const ZENSKILL_SOURCE_SLUG = 'zenskill-4'

export interface ZenSkillPageProps {
  workspaceId?: string
  initialTab?: string
}

export interface ZenSkillPageRegistration {
  /** Route path segment under the zenskill navigator (e.g. 'gtd' -> zenskill/gtd) */
  slug: string
  component: ComponentType<ZenSkillPageProps>
  icon: LucideIcon
  i18nLabelKey: string
}

export const ZENSKILL_PAGES: ZenSkillPageRegistration[] = [
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
