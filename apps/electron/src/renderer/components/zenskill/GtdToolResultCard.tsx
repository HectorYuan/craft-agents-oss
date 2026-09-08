/**
 * GtdToolResultCard — structured inline card for ZenSkill GTD tool results
 * in the chat transcript.
 *
 * Rendered through TurnCard's `renderToolResultCard` hook from ChatDisplay
 * when the tool name matches a GTD family. Parses the tool_result JSON
 * defensively (results are truncated at 8000 chars upstream in ws_server.py
 * and may not be valid JSON — falls back to plain text). Clicking the card
 * deep-links to the matching GTD workspace tab (zenskill/gtd?tab=...).
 *
 * MVP-0: the card is an immutable snapshot of the creation-time tool result
 * (message immutability), but a live status overlay is layered on top via
 * useGtdEntityStatus — a status badge top-right, plus an inline "complete"
 * button for pending/next actions so the loop "agent creates in chat →
 * user completes in chat" closes without leaving the conversation. The
 * completion triggers zenskill:changed, the hook refetches and the badge
 * flips to done. Only applies to action-family cards carrying an entity id
 * and a workspaceId; everything else renders as the plain snapshot.
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { navigate, routes } from '@/lib/navigate'
import { useGtdEntityStatus } from '@/hooks/zenskill/useGtdEntityStatus'
import { ZENSKILL_SOURCE_SLUG } from './zenskill-registry'
import { notifyActionDone } from './panels/gtdFeedback'

interface GtdToolResultCardProps {
  toolName: string
  resultText: string
  /** Live-status layer — absent (e.g. legacy call sites) keeps snapshot-only behavior */
  workspaceId?: string
  sourceSlug?: string
}

type GtdTab = 'inbox' | 'actions' | 'calendar' | 'projects'

/**
 * Loose GTD tool matching — Mode B (agent sessions) names carry the MCP
 * prefix (`mcp__zenskill-4__action_add`) while Mode C (companion bridge)
 * uses bare names (`action_add`), so substring match by design.
 */
export function isGtdToolName(toolName?: string): boolean {
  if (!toolName) return false
  const n = toolName.toLowerCase()
  return n.includes('gtd_') || n.includes('inbox_') || n.includes('action_') || n.includes('calendar_') || n.includes('project_')
}

function gtdTabForTool(toolName: string): GtdTab {
  const n = toolName.toLowerCase()
  if (n.includes('calendar_')) return 'calendar'
  if (n.includes('project_')) return 'projects'
  if (n.includes('action_')) return 'actions'
  return 'inbox'
}

type ToolKind = 'action_add' | 'action_done' | 'gtd_capture' | 'inbox_clarify' | 'calendar_add' | 'action_mark_next' | 'project_add' | 'generic'

function toolKind(toolName: string): ToolKind {
  const n = toolName.toLowerCase()
  if (n.includes('action_done')) return 'action_done'
  if (n.includes('action_add')) return 'action_add'
  if (n.includes('action_mark_next')) return 'action_mark_next'
  if (n.includes('gtd_capture')) return 'gtd_capture'
  if (n.includes('inbox_clarify')) return 'inbox_clarify'
  if (n.includes('calendar_add')) return 'calendar_add'
  if (n.includes('project_add')) return 'project_add'
  return 'generic'
}

function parseResultObject(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    // Truncated / non-JSON result — caller falls back to plain text
  }
  return null
}

function str(data: Record<string, unknown>, key: string): string {
  const v = data[key]
  return typeof v === 'string' ? v : ''
}

function num(data: Record<string, unknown>, key: string): number | undefined {
  const v = data[key]
  return typeof v === 'number' ? v : undefined
}

function truncate(text: string, max = 200): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

/** Strip a leading emoji/icon token from backend achievement strings ("🔥 First Steps") */
function stripLeadingIcon(name: string): string {
  return name.replace(/^[^\p{L}\p{N}]+\s*/u, '').trim()
}

/** Entity id carried by action-family tool results; empty string → undefined */
function actionEntityId(kind: ToolKind, data: Record<string, unknown> | null): string | undefined {
  if (!data) return undefined
  if (kind === 'action_add') return str(data, 'id') || str(data, 'action_id') || undefined
  if (kind === 'action_done') return str(data, 'action_id') || undefined
  if (kind === 'action_mark_next') return str(data, 'action_id') || str(data, 'id') || undefined
  return undefined
}

function DetailRow({ label, value }: { label?: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      {label && <span className="shrink-0 text-[10px] text-muted-foreground/70">{label}</span>}
      <span className="truncate text-foreground/80">{value}</span>
    </div>
  )
}

export function GtdToolResultCard({ toolName, resultText, workspaceId, sourceSlug }: GtdToolResultCardProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)

  // Hooks run before any early return; for non-action cards entityId is
  // undefined so the live-status hook stays idle.
  const data = resultText ? parseResultObject(resultText) : null
  const kind = toolKind(toolName)
  const entityId = actionEntityId(kind, data)
  const live = useGtdEntityStatus(workspaceId, 'action', entityId)

  if (!resultText) return null
  const tab = gtdTabForTool(toolName)

  let icon = '✦'
  let headline = ''
  const details: { label?: string; value: string }[] = []

  if (kind === 'action_add') {
    icon = '✓'
    headline = str(data ?? {}, 'title') || t('zenskill.card.actionAdded')
    const priority = str(data ?? {}, 'priority')
    if (priority) details.push({ label: t('zenskill.card.priority'), value: priority })
    const due = str(data ?? {}, 'due_date')
    if (due) details.push({ label: t('zenskill.card.due'), value: due })
  } else if (kind === 'action_done') {
    icon = '✓'
    headline = str(data ?? {}, 'title') || t('zenskill.card.actionCompleted')
    const invested = num(data ?? {}, 'energy_invested')
    const pool = data?.energy_pool as { remaining?: unknown; max?: unknown } | undefined
    const remaining = typeof pool?.remaining === 'number' ? pool.remaining : undefined
    const max = typeof pool?.max === 'number' ? pool.max : undefined
    if (invested !== undefined && remaining !== undefined) {
      details.push({ value: t('zenskill.card.energy', { invested, remaining, max: max ?? '?' }) })
    }
    const unlocks = Array.isArray(data?.new_achievements) ? (data?.new_achievements as unknown[]) : []
    for (const unlock of unlocks) {
      if (typeof unlock !== 'string') continue
      details.push({ value: `🏅 ${stripLeadingIcon(unlock)}` })
    }
  } else if (kind === 'gtd_capture') {
    icon = '📥'
    headline = t('zenskill.card.captured')
    const item = data?.item as { text?: unknown; raw_text?: unknown } | undefined
    const text = typeof item?.text === 'string' ? item.text : typeof item?.raw_text === 'string' ? item.raw_text : ''
    if (text) details.push({ value: truncate(text, 120) })
  } else if (kind === 'inbox_clarify') {
    icon = '🧭'
    headline = t('zenskill.card.clarified', { type: str(data ?? {}, 'result_type') || '?' })
    const target = str(data ?? {}, 'target') || str(data ?? {}, 'target_id')
    if (target) details.push({ value: `→ ${target}` })
  } else if (kind === 'calendar_add') {
    icon = '📅'
    headline = t('zenskill.card.eventCreated')
    const event = data?.event as { date?: unknown; time_str?: unknown; title?: unknown } | undefined
    const date = typeof event?.date === 'string' ? event.date : ''
    const time = typeof event?.time_str === 'string' ? event.time_str : ''
    const title = typeof event?.title === 'string' ? event.title : ''
    if (date || time) details.push({ value: [date, time].filter(Boolean).join(' ') })
    if (title) details.push({ value: truncate(title, 120) })
  } else if (kind === 'project_add') {
    icon = '📁'
    headline = t('zenskill.card.projectCreated')
    const project = data?.project as { name?: unknown } | undefined
    const name = str(data ?? {}, 'name') || (typeof project?.name === 'string' ? project.name : '')
    if (name) details.push({ value: truncate(name, 120) })
    const outcome = str(data ?? {}, 'outcome')
    if (outcome) details.push({ label: t('zenskill.card.projectOutcome'), value: truncate(outcome, 120) })
  } else if (kind === 'action_mark_next') {
    icon = '⏭'
    headline = t('zenskill.card.markedNext')
    const title = str(data ?? {}, 'title')
    if (title) details.push({ value: truncate(title, 120) })
  }

  // Generic family card: headline from backend message, or raw text fallback
  if (!headline && data) {
    icon = '✦'
    headline = truncate(str(data, 'message') || str(data, 'title'), 160)
  }
  if (!headline && !data) {
    icon = '✦'
    headline = truncate(resultText, 160)
  }
  if (!headline) return null

  const liveStatus = live.status
  const showComplete = liveStatus === 'pending' || liveStatus === 'next' || liveStatus === 'done'
  const cardDimmed = liveStatus === 'deleted'

  const handleComplete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!workspaceId || !entityId || busy) return
    setBusy(true)
    try {
      // Completion feedback (energy spend, unlocked achievements) mirrors
      // GtdWorkspace; the zenskill:changed broadcast drives the badge
      // refresh through useGtdEntityStatus — no manual refetch here.
      const result = await window.electronAPI.callMcpTool(
        workspaceId,
        sourceSlug || ZENSKILL_SOURCE_SLUG,
        'action_done',
        { action_id: entityId, energy_invested: 5 },
      )
      notifyActionDone(result, t)
    } catch {
      toast.error(t('zenskill.toast.actionFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      title={t('zenskill.card.openInGtd')}
      onClick={(e) => {
        e.stopPropagation()
        navigate(routes.view.zenskillGtd(tab))
      }}
      className={`mt-0.5 inline-flex max-w-full flex-col gap-0.5 rounded-md border border-border/60 bg-background px-2.5 py-1.5 text-left text-xs hover:border-accent/40 hover:bg-accent/5 transition-colors cursor-pointer ${cardDimmed ? 'opacity-50' : ''}`}
    >
      <span className="flex items-center gap-1.5 min-w-0">
        <span className="shrink-0 text-accent">{icon}</span>
        <span className="truncate font-medium text-foreground">{headline}</span>
        {liveStatus === 'next' && (
          <span className="ml-auto shrink-0 rounded-full border border-purple-500/30 bg-purple-500/10 px-1.5 py-px text-[10px] font-medium text-purple-600 dark:text-purple-400">
            {t('zenskill.card.statusNext')}
          </span>
        )}
        {liveStatus === 'done' && (
          <span className="ml-auto shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-px text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
            {t('zenskill.card.statusDone')}
          </span>
        )}
        {liveStatus === 'deleted' && (
          <span className="ml-auto shrink-0 rounded-full border border-border/60 bg-muted px-1.5 py-px text-[10px] font-medium text-muted-foreground">
            {t('zenskill.card.statusDeleted')}
          </span>
        )}
      </span>
      {details.map((row, i) => (
        <DetailRow key={i} label={row.label} value={row.value} />
      ))}
      {showComplete && workspaceId && entityId && (
        <span className="pt-0.5">
          <button
            type="button"
            disabled={busy || liveStatus === 'done'}
            onClick={handleComplete}
            className="inline-flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[11px] font-medium text-emerald-600 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50 dark:text-emerald-400"
          >
            ✓ {t('zenskill.card.completeAction')}
          </button>
        </span>
      )}
    </div>
  )
}
