/**
 * ZenSkillSourceMount — L0 mount point for the ZenSkill Data section on the
 * source detail page. Renders ZenSkillDataPanel (GTD inbox, memory, and
 * system status) when the inspected source is the zenskill-4 MCP source.
 */
import { Info_Section } from '@/components/info'
import { ZenSkillDataPanel } from './ZenSkillDataPanel'

interface ZenSkillSourceMountProps {
  sourceType: string
  sourceSlug: string
  workspaceId?: string
}

export function ZenSkillSourceMount({ sourceType, sourceSlug, workspaceId }: ZenSkillSourceMountProps) {
  if (sourceType !== 'mcp' || sourceSlug !== 'zenskill-4' || !workspaceId) return null

  return (
    <Info_Section
      title="ZenSkill Data"
      description="GTD inbox, memory, and system status"
    >
      <ZenSkillDataPanel
        workspaceId={workspaceId}
        sourceSlug={sourceSlug}
        onGtdItemClick={(text) => {
          // Navigate to a new session with the GTD item as context
          const msg = `关于这个待办: "${text}" — 帮我分析一下`
          window.dispatchEvent(new CustomEvent('zenskill:navigate', { detail: { action: 'new-session', message: msg } }))
        }}
      />
    </Info_Section>
  )
}
