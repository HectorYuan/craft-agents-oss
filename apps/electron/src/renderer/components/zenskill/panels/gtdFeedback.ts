/**
 * gtdFeedback — shared growth-feedback toast for action_done completions.
 *
 * Extracted from GtdWorkspace so the chat-inline completion button
 * (GtdToolResultCard) surfaces exactly the same feedback — completion,
 * energy spend, newly unlocked achievements — without pulling the whole
 * GTD page module into the chat chunk.
 */
import type { TFunction } from 'i18next'
import { toast } from 'sonner'
import { extractMcpJson } from '@/hooks/zenskill/useMcpTool'

interface ActionDonePayload {
  ok?: boolean
  title?: string
  message?: string
  energy_invested?: number
  energy_pool?: { remaining?: number; max?: number }
  new_achievements?: unknown[]
}

/** Strip a leading emoji/icon token from backend achievement strings ("🔥 首个行动") */
function stripLeadingIcon(name: string): string {
  return name.replace(/^[^\p{L}\p{N}]+\s*/u, '').trim()
}

/**
 * Growth feedback toast for action_done — closes the cultivation loop by
 * surfacing the completion, the energy spend, and any newly unlocked
 * achievements right where the user clicked "done".
 */
export function notifyActionDone(result: unknown, t: TFunction): void {
  const data = extractMcpJson(result) as ActionDonePayload | null
  if (!data) return
  if (data.ok === false) {
    toast.error(t('zenskill.toast.actionFailed'), { description: data.message })
    return
  }
  const title = data.title || data.message
  if (!title) return
  const pool = data.energy_pool
  const energyText = typeof data.energy_invested === 'number' && typeof pool?.remaining === 'number'
    ? t('zenskill.toast.energy', { invested: data.energy_invested, remaining: pool.remaining, max: pool.max ?? '?' })
    : undefined
  toast.success(t('zenskill.toast.actionDone', { title }), energyText ? { description: energyText } : undefined)
  const unlocks = Array.isArray(data.new_achievements) ? data.new_achievements : []
  for (const unlock of unlocks) {
    if (typeof unlock !== 'string' || !unlock.trim()) continue
    const name = stripLeadingIcon(unlock)
    toast.success(t('zenskill.toast.achievement', { name: name || unlock }))
  }
}
