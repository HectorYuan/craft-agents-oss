/**
 * ZenSkillPageMount — render delegate for MainContentPanel's zenskill branch.
 *
 * Resolves the requested page slug against the ZenSkill page registry (L1)
 * and renders the registered component. Unknown or missing slugs fall back
 * to the first registered page.
 */
import { resolveZenSkillPage } from './zenskill-registry'
import './brand/zenskill-brand.css'

interface ZenSkillPageMountProps {
  pageSlug?: string;
  tab?: string
  workspaceId?: string
  onNavigateToChat?: (message: string) => void
}

export function ZenSkillPageMount({ pageSlug, tab, workspaceId, onNavigateToChat }: ZenSkillPageMountProps) {
  const registration = resolveZenSkillPage(pageSlug)
  if (!registration) return null
  const Page = registration.component
  // .zs-scope: 品牌语义覆盖容器 (brand/zenskill-brand.css) — 仅 zenskill 页面品牌化, 上游紫保留
  return (
    <div className="zs-scope">
      <Page workspaceId={workspaceId} initialTab={tab} onNavigateToChat={onNavigateToChat} />
    </div>
  )
}
