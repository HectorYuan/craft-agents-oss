/**
 * ZenSkill automation event emission (extracted from SessionManager).
 *
 * Fired after ZenSkill MCP write-tools (GTD/memory/skills) mutate state,
 * letting automation rules (prompt/webhook) react to data changes.
 */

import { getWorkspaceByNameOrId } from '@craft-agent/shared/config'
import type { AutomationSystem } from '@craft-agent/shared/automations'

export async function emitZenSkillChangedEvent(args: {
  workspaceId: string
  detail: Record<string, unknown>
  automationSystems: Map<string, AutomationSystem>
  logError: (message: string, error: unknown) => void
}): Promise<void> {
  const { workspaceId, detail, automationSystems, logError } = args
  try {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return
    const automationSystem = automationSystems.get(workspace.rootPath)
    if (!automationSystem) return
    await automationSystem.emit('ZenSkillChanged', {
      workspaceId: workspace.id,
      timestamp: Date.now(),
      data: detail,
    })
  } catch (error) {
    logError('[Automations] Failed to emit ZenSkillChanged:', error)
  }
}
