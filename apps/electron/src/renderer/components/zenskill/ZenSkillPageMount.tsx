/**
 * ZenSkillPageMount — render delegate for MainContentPanel's zenskill branch.
 *
 * Resolves the requested page slug against the ZenSkill page registry (L1)
 * and renders the registered component. Unknown or missing slugs fall back
 * to the first registered page.
 */
import { resolveZenSkillPage } from './zenskill-registry'

interface ZenSkillPageMountProps {
  pageSlug?: string
  workspaceId?: string
}

export function ZenSkillPageMount({ pageSlug, workspaceId }: ZenSkillPageMountProps) {
  const registration = resolveZenSkillPage(pageSlug)
  if (!registration) return null
  const Page = registration.component
  return <Page workspaceId={workspaceId} />
}
