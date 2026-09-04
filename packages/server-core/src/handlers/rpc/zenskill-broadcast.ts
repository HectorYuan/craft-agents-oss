/**
 * ZenSkill write-tool change broadcasting + session-summary episode seam
 * (extracted from sources.ts).
 */

import type { RpcServer } from '@craft-agent/server-core/transport'
import type { ISessionManager } from '../session-manager-interface'

// Broadcast change event for write tools.
// Prefixes cover whole GTD families; READ_TOOLS excludes read tools that
// sit under those prefixes (gtd_inbox_list/gtd_review/... would otherwise
// be misclassified as writes, spamming broadcasts and automation rules).
const WRITE_TOOL_PREFIXES = ['gtd_', 'inbox_', 'action_', 'project_', 'incubating_']
const WRITE_TOOLS_EXACT = ['memory_remember', 'goal_set', 'habit_check', 'skill_install', 'skill_uninstall']
const READ_TOOLS = ['gtd_inbox_list', 'gtd_review', 'action_list', 'project_list', 'incubating_list']

export async function broadcastZenSkillWriteToolChange(args: {
  server: RpcServer
  sessionManager: Pick<ISessionManager, 'emitZenSkillChanged'>
  workspaceId: string
  sourceSlug: string
  toolName: string
  result: unknown
}): Promise<void> {
  const { server, sessionManager, workspaceId, sourceSlug, toolName, result } = args
  const isWriteTool = (n: string) =>
    !READ_TOOLS.includes(n) &&
    (WRITE_TOOLS_EXACT.includes(n) || WRITE_TOOL_PREFIXES.some((p) => n.startsWith(p)))
  if (!isWriteTool(toolName)) return
  // Achievement unlocks ride in the event payload so automation rules
  // and webhooks can react (action_done/habit_check return them).
  const payload: Record<string, unknown> = { type: toolName, sourceSlug }
  try {
    const text = (result as any)?.result?.content?.[0]?.text
    if (typeof text === 'string') {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed?.new_achievements) && parsed.new_achievements.length > 0) {
        payload.newAchievements = parsed.new_achievements
      }
    }
  } catch { /* payload enrichment is best-effort */ }
  try {
    server.push('zenskill:changed', { to: 'workspace', workspaceId }, payload)
  } catch { /* broadcast is best-effort */ }
  // Feed the automation event bus so rules can react to ZenSkill data changes
  try {
    await sessionManager.emitZenSkillChanged(workspaceId, payload)
  } catch { /* automation emit is best-effort */ }
}

export function registerZenSkillSessionSummarySeam(args: {
  sessionManager: Pick<ISessionManager, 'onSessionComplete'>
  log: { info: (message: string) => void; warn: (message: string, error?: unknown) => void }
}): void {
  // WP-C: session summary → ZenSkill episodes. Fire-and-forget on complete:
  // the stop path is hot, so failures only warn and never block completion.
  // Uses the session's own mcpPool (process-local reference on the event) —
  // no workspace/source re-resolution needed here.
  try {
    args.sessionManager.onSessionComplete(async (evt) => {
      if (evt.reason !== 'complete' || !evt.mcpPool) return
      try {
        const def = evt.mcpPool.getProxyToolDefs(['zenskill-4'])
          .find(d => d.name.endsWith('__session_summary'))
        if (!def) return
        await evt.mcpPool.callTool(def.name, {
          message_count: evt.messageCount ?? 0,
          tool_count: evt.toolUseCount ?? 0,
          first_message: evt.firstUserMessage ?? '',
        })
        args.log.info(`Session summary written for ${evt.sessionId}`)
      } catch (err) {
        args.log.warn(`session_summary write failed for ${evt.sessionId} (best-effort):`, err)
      }
    })
  } catch { /* completion seam unavailable — best-effort only */ }
}
