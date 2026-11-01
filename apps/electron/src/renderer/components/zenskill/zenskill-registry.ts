/**
 * ZenSkill page registry (L1) — 组件与图标侧；**视图归属侧见 zenskill-views.ts**。
 *
 * Single source of truth for ZenSkill top-level full-page views surfaced
 * through the app shell sidebar and MainContentPanel. Adding a page is a
 * one-entry change here plus a route builder — upstream files never grow
 * per-page branches (they delegate to this registry via ZenSkillPageMount).
 *
 * Route logic (parse/build) lives in the sibling zero-dependency module
 * zenskill-routes.ts so shared/route-parser.ts can delegate without
 * importing the component tree.
 *
 * ★ 视图元数据（归哪个域 / 以什么形态出现）在 zenskill-views.ts ——
 *   那里是纯数据模块，不 import 任何组件 ⇒ 无循环依赖。
 *   本文件只负责把元数据**挂到**每个注册项上，
 *   两边按 slug 关联，1:1 完整性由 __tests__/view-registry.test.ts 守住。
 */
import type { ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Brain, Inbox, Zap, Lightbulb, User, Network, GitBranch, BookOpen, RefreshCw, Store, Sprout } from 'lucide-react'
import { GtdWorkspace } from './pages/GtdWorkspace'
import { MemoryBrowser } from './pages/MemoryBrowser'
import { ZenSkillOverview } from './pages/ZenSkillOverview'
import { ZenSkillInsights } from './pages/ZenSkillInsights'
import { ZenSkillProfile } from './pages/ZenSkillProfile'
import { ZenSkillCollaboration } from './pages/ZenSkillCollaboration'
import { ZenSkillSkillGraph } from './pages/ZenSkillSkillGraph'
import { SkillMarketPage } from './pages/SkillMarketPage'
import { LearningPathPage } from './pages/LearningPathPage'
import { ZenloopStandalonePage } from './pages/ZenloopStandalonePage'
import { CultivationPage } from './pages/CultivationPage'
import { resolveViewSpec, type HostDomain, type ViewMode } from './zenskill-views'

/**
 * The ZenSkill MCP source slug all ZenSkill pages talk to.
 *
 * MUST stay "zenskill": the seeded source uses this slug (see
 * packages/shared/src/sources/zenskill-seed.ts), the "ZenSkill Data" panel in
 * SourceInfoPage keys off it, and backend system prompts hardcode the tool
 * prefix `mcp__zenskill__*`. Changing it makes every ZenSkill page fall back
 * to "Source not found".
 */
export const ZENSKILL_SOURCE_SLUG = 'zenskill'

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
  /** 归哪个对象域（会话/项目/技能/今日/设置）—— 侧边栏据此分组 */
  hostDomain: HostDomain
  /** 以什么形态出现（page/tab/panel/quick）—— 侧边栏据此决定是否列出 */
  mode: ViewMode
  /** 宿主页内锚点（P1+ 随内容归位生效） */
  slot?: string
}

/** 组件侧登记表（slug + 组件 + 图标 + 文案键）。 */
const PAGE_COMPONENTS: Array<Omit<ZenSkillPageRegistration, 'hostDomain' | 'mode' | 'slot'>> = [
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
  {
    slug: 'insights',
    component: ZenSkillInsights,
    icon: Lightbulb,
    i18nLabelKey: 'zenskill.insights.pageTitle',
  },
  {
    slug: 'profile',
    component: ZenSkillProfile,
    icon: User,
    i18nLabelKey: 'zenskill.profile.title',
  },
  {
    slug: 'skill-graph',
    component: ZenSkillSkillGraph,
    icon: Network,
    i18nLabelKey: 'zenskill.skillGraph.title',
  },
  {
    slug: 'skill-market',
    component: SkillMarketPage,
    icon: Store,
    i18nLabelKey: 'zenskill.market.title',
  },
  {
    slug: 'collaboration',
    component: ZenSkillCollaboration,
    icon: GitBranch,
    i18nLabelKey: 'zenskill.collaboration.title',
  },
  {
    slug: 'learning-path',
    component: LearningPathPage,
    icon: BookOpen,
    i18nLabelKey: 'zenskill.learningPath.title',
  },
  {
    slug: 'zenloop',
    component: ZenloopStandalonePage,
    icon: RefreshCw,
    i18nLabelKey: 'zenskill.zenloop.title',
  },
  {
    // 修炼域（第十八批 D 段 D2）—— 设计真相源 ardot `6:372`「修炼域 · Info_Page」。
    // ★ 与 `zenloop` 页分工：zenloop 是**引擎运维视图**，修炼域是**用户向成长页**
    //   （见 `docs/spec_zenskill_four_domains_v1_20261025.md` §5）。
    slug: 'cultivation',
    component: CultivationPage,
    icon: Sprout,
    i18nLabelKey: 'zenskill.cultivation.title',
  },
]

/**
 * 完整注册表 = 组件侧 × 视图元数据侧（按 slug 关联）。
 *
 * ★ 若某个 slug 在 zenskill-views.ts 里漏登记 ⇒ hostDomain/mode 兜底为
 *   'settings' + 'page'（**不崩、不丢页**），并由 view-registry.test.ts 判红。
 */
export const ZENSKILL_PAGES: ZenSkillPageRegistration[] = PAGE_COMPONENTS.map((page) => {
  const spec = resolveViewSpec(page.slug)
  return {
    ...page,
    hostDomain: spec?.hostDomain ?? 'settings',
    mode: spec?.mode ?? 'page',
    slot: spec?.slot,
  }
})

/** Resolve a page registration by route slug; falls back to the first page. */
export function resolveZenSkillPage(pageSlug?: string): ZenSkillPageRegistration | undefined {
  return ZENSKILL_PAGES.find((p) => p.slug === pageSlug) ?? ZENSKILL_PAGES[0]
}
