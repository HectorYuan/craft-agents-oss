/**
 * 侧边栏条目构造 —— 按**宿主域**分组（会话 / 项目 / 技能 / 今日 / 设置）。
 *
 * ★ 为什么这个模块单独存在（而不是写在 AppShell 里）
 *   本仓有一条「冲突面预算」门禁（`scripts/check_conflict_budget.sh`）：
 *   **上游文件**里每出现一行含 "zenskill" 的字样都要占预算。
 *   ⇒ 把构造逻辑放在这里（路径含 zenskill ⇒ **豁免**），
 *     AppShell 只需 1 行 import ⇒ **上游分歧面最小化**。
 *   ★ 真相源（组件与元数据）：`./zenskill-views.ts` + `./zenskill-registry.ts`
 *   ★ 设计文档：`docs/spec_zenskill_domain_architecture_v1_20261031.md` §5.2
 *
 * 三条不变式：
 * 1. **分组顺序固定** —— 做事 → 推进 → 学会 → 今日 → 运维（不是字母序）
 * 2. **`mode` 决定是否列出** —— 'panel'/'quick' 不进侧边栏（可直达），'page'/'tab' 进
 * 3. **旧 slug 全部仍可路由** —— 点击目标与改造前逐字一致（零回归）
 */
import type { LucideIcon } from 'lucide-react'
import type { SidebarItem } from '@/components/app-shell/LeftSidebar'
import type { NavigateOptions, Route } from '@/lib/navigate'
import { ZENSKILL_PAGES } from './zenskill-registry'
import { groupViewsByHostDomain, isSidebarVisibleMode } from './zenskill-views'

type Translate = (key: string) => string
type Navigate = (route: Route, options?: NavigateOptions) => void

interface NavigationSnapshot {
  navigator?: string
  details?: { type?: string; pageSlug?: string } | null
}

interface DomainGroupedEntry {
  id: string
  title: string
  icon: LucideIcon
  variant: 'default' | 'ghost'
  onClick: () => void
  sectionLabel?: string
}

/**
 * 构造按宿主域分组的侧边栏条目。
 *
 * @param t        翻译函数
 * @param navigate 路由跳转
 * @param navState 当前导航状态（用于高亮当前页）
 */
export function buildDomainGroupedNavItems(
  t: Translate,
  navigate: Navigate,
  navState: NavigationSnapshot,
): SidebarItem[] {
  const groups = groupViewsByHostDomain(
    ZENSKILL_PAGES
      .map((p) => ({ slug: p.slug, hostDomain: p.hostDomain, mode: p.mode, slot: p.slot }))
      // 'panel' 在宿主页内部、'quick' 靠命令面板直达 ⇒ 两者都不占侧边栏位
      .filter((v) => isSidebarVisibleMode(v.mode)),
  )

  const entries: DomainGroupedEntry[] = []
  for (const group of groups) {
    const groupLabel = t(group.labelKey)
    group.views.forEach((view, indexInGroup) => {
      const page = ZENSKILL_PAGES.find((p) => p.slug === view.slug)
      if (!page) return
      const isActive =
        navState.navigator === 'zenskill' &&
        navState.details?.type === 'zenskill-page' &&
        navState.details.pageSlug === page.slug
      entries.push({
        id: `nav:zenskill:${page.slug}`,
        title: t(page.i18nLabelKey),
        icon: page.icon,
        variant: isActive ? 'default' : 'ghost',
        onClick: () => navigate((page.routeBuilder?.() ?? `zenskill/${page.slug}`) as Route),
        // 分组标题挂在**组首项**上（渲染在按钮之上，不可交互）
        sectionLabel: indexInGroup === 0 ? groupLabel : undefined,
      })
    })
  }
  return entries
}
