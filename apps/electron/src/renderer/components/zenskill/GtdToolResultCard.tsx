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
 * useGtdEntityStatus — a status badge top-right, plus inline action buttons
 * so the loop "agent creates in chat → user acts in chat" closes without
 * leaving the conversation (Day 1 interaction deepening):
 * - action_add / action_mark_next: [complete] [edit] — edit expands an
 *   inline editor (title/priority/due_date → action_update), mirroring the
 *   ActionsPanel inline-edit pattern;
 * - gtd_capture: [clarify] (inbox_clarify) [archive] (inbox_archive);
 * - calendar_add: [delete] with click-again confirm (calendar_delete);
 * - project_add: [complete] (project_done).
 * Buttons need an entity id and a workspaceId; everything else renders as
 * the plain snapshot. Live status may hide buttons for entities that already
 * settled (archived inbox item / done project / done action).
 */
import React, { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { navigate, routes } from '@/lib/navigate'
import { useGtdEntityStatus, type GtdEntityType } from '@/hooks/zenskill/useGtdEntityStatus'
import { extractMcpJson } from '@/hooks/zenskill/useMcpTool'
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

/** Nested {item|event} object from a tool result, read defensively */
function nestedObject(data: Record<string, unknown> | null, key: string): Record<string, unknown> | undefined {
  const v = data?.[key]
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined
}

/**
 * Entity id carried by GTD tool results (Day 1: all write kinds carry one);
 * empty string → undefined. Field layout per backend contract:
 * action_add/{mark_next} → id|action_id, action_done → action_id,
 * gtd_capture → item.id, inbox_clarify → item_id, calendar_add → event.id,
 * project_add → id|project_id.
 */
function gtdEntityId(kind: ToolKind, data: Record<string, unknown> | null): string | undefined {
  if (!data) return undefined
  switch (kind) {
    case 'action_add':
    case 'action_mark_next':
      return str(data, 'id') || str(data, 'action_id') || undefined
    case 'action_done':
      return str(data, 'action_id') || undefined
    case 'gtd_capture':
      return str(nestedObject(data, 'item') ?? {}, 'id') || undefined
    case 'inbox_clarify':
      return str(data, 'item_id') || undefined
    case 'calendar_add':
      return str(nestedObject(data, 'event') ?? {}, 'id') || str(data, 'event_id') || undefined
    case 'project_add':
      return str(data, 'id') || str(data, 'project_id') || undefined
    default:
      return undefined
  }
}

/** Live-status entityType for a card kind — non-GTD kinds return undefined */
function entityTypeForKind(kind: ToolKind): GtdEntityType | undefined {
  if (kind === 'action_add' || kind === 'action_done' || kind === 'action_mark_next') return 'action'
  if (kind === 'gtd_capture' || kind === 'inbox_clarify') return 'inbox'
  if (kind === 'calendar_add') return 'calendar'
  if (kind === 'project_add') return 'project'
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

const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const

interface EditState {
  title: string
  priority: string
  dueDate: string
}

export function GtdToolResultCard({ toolName, resultText, workspaceId, sourceSlug }: GtdToolResultCardProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<EditState | null>(null)
  // calendar delete: click-again confirm (same pattern as ActionsPanel delete)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Hooks run before any early return; for kinds without a live layer
  // entityType is undefined so the live-status hook stays idle.
  const data = resultText ? parseResultObject(resultText) : null
  const kind = toolKind(toolName)
  const entityId = gtdEntityId(kind, data)
  const entityType = entityTypeForKind(kind)
  const live = useGtdEntityStatus(
    workspaceId,
    entityType ?? 'action',
    entityType ? entityId : undefined,
  )

  if (!resultText) return null
  const tab = gtdTabForTool(toolName)

  let icon = '✦'
  let headline = ''
  const details: { label?: string; value: string }[] = []

  if (kind === 'action_add') {
    icon = '✓'
    headline = live.data?.title || str(data ?? {}, 'title') || t('zenskill.card.actionAdded')
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
  const canAct = Boolean(workspaceId) && Boolean(entityId)
  const showComplete = liveStatus === 'pending' || liveStatus === 'next' || liveStatus === 'done'
  // Edit + project-done stay available while the entity has not settled;
  // unknown live status (legacy cards / failed lookup) keeps them visible.
  const showEdit = canAct && entityType === 'action' && (kind === 'action_add' || kind === 'action_mark_next') && liveStatus !== 'done'
  const showProjectDone = canAct && kind === 'project_add' && liveStatus !== 'done'
  // inbox buttons collapse once the item settled (clarified/archived)
  const showInboxActions = canAct && kind === 'gtd_capture' && (!liveStatus || liveStatus === 'unprocessed')
  const showCalendarDelete = canAct && kind === 'calendar_add'
  const cardDimmed = liveStatus === 'deleted'

  const disarmDelete = () => {
    if (confirmTimerRef.current) {
      clearTimeout(confirmTimerRef.current)
      confirmTimerRef.current = null
    }
    setConfirmingDelete(false)
  }

  const runTool = async (tool: string, args: Record<string, unknown>) => {
    if (!workspaceId || !entityId || busy) return
    setBusy(true)
    try {
      return await window.electronAPI.callMcpTool(
        workspaceId,
        sourceSlug || ZENSKILL_SOURCE_SLUG,
        tool,
        args,
      )
    } catch {
      toast.error(t('zenskill.toast.toolFailed'))
      return undefined
    } finally {
      setBusy(false)
    }
  }

  const handleComplete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    disarmDelete()
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

  const handleClarify = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const result = await runTool('inbox_clarify', { item_id: entityId })
    if (result) {
      const parsed = extractMcpJson(result) as { ok?: boolean; result_type?: string } | null
      if (parsed?.ok === false) toast.error(t('zenskill.toast.toolFailed'))
      else toast.success(t('zenskill.toast.clarified', { type: parsed?.result_type ?? '-' }))
    }
  }

  const handleArchive = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const result = await runTool('inbox_archive', { item_id: entityId })
    if (result) {
      const parsed = extractMcpJson(result) as { ok?: boolean } | null
      if (parsed?.ok === false) toast.error(t('zenskill.toast.toolFailed'))
      else toast.success(t('zenskill.toast.archived'))
    }
  }

  const handleDeleteEvent = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirmingDelete) {
      // First click: arm the confirm, auto-disarm after 3s
      setConfirmingDelete(true)
      if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current)
      confirmTimerRef.current = setTimeout(() => setConfirmingDelete(false), 3000)
      return
    }
    disarmDelete()
    const result = await runTool('calendar_delete', { event_id: entityId })
    if (result) {
      const parsed = extractMcpJson(result) as { ok?: boolean } | null
      if (parsed?.ok === false) toast.error(t('zenskill.toast.toolFailed'))
      else toast.success(t('zenskill.toast.deletedEvent'))
    }
  }

  const handleProjectDone = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const result = await runTool('project_done', { project_id: entityId })
    if (result) {
      const parsed = extractMcpJson(result) as { ok?: boolean; name?: string } | null
      if (parsed?.ok === false) toast.error(t('zenskill.toast.toolFailed'))
      else toast.success(t('zenskill.toast.actionDone', { title: parsed?.name ?? '' }))
    }
  }

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    disarmDelete()
    setEditing({
      title: live.data?.title || str(data ?? {}, 'title') || '',
      priority: str(data ?? {}, 'priority') || 'P2',
      dueDate: str(data ?? {}, 'due_date') || '',
    })
  }

  const saveEdit = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!editing || !editing.title.trim() || busy) return
    const args: Record<string, unknown> = {
      action_id: entityId,
      title: editing.title.trim(),
      priority: editing.priority,
    }
    if (editing.dueDate) args.due_date = editing.dueDate
    const result = await runTool('action_update', args)
    if (result) {
      const parsed = extractMcpJson(result) as { ok?: boolean } | null
      if (parsed?.ok === false) toast.error(t('zenskill.toast.toolFailed'))
    }
    setEditing(null)
  }

  const btnBase = 'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50'

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

      {/* Inline editor (action kinds) — clicks must not deep-link the card */}
      {editing && entityType === 'action' && (
        <div
          className="flex flex-wrap items-center gap-1 pt-0.5"
          onClick={(e) => e.stopPropagation()}
        >
          <input
            value={editing.title}
            autoFocus
            onChange={(e) => setEditing({ ...editing, title: e.target.value })}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return
              if (e.key === 'Enter') void saveEdit(e as unknown as React.MouseEvent)
              if (e.key === 'Escape') setEditing(null)
            }}
            className="min-w-0 flex-1 text-xs bg-muted/40 rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-accent/40"
          />
          <select
            value={editing.priority}
            onChange={(e) => setEditing({ ...editing, priority: e.target.value })}
            className="text-xs bg-muted/40 rounded px-0.5 py-0.5 outline-none focus:ring-1 focus:ring-accent/40"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <input
            type="date"
            value={editing.dueDate}
            onChange={(e) => setEditing({ ...editing, dueDate: e.target.value })}
            className="text-xs bg-muted/40 rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground"
          />
          <button
            type="button"
            disabled={busy || !editing.title.trim()}
            onClick={saveEdit}
            className={`${btnBase} border-emerald-500/40 bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400`}
          >
            ✓ {t('zenskill.card.edit')}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setEditing(null)
            }}
            className={`${btnBase} border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/70`}
          >
            ✕ {t('zenskill.gtd.actions.editCancel')}
          </button>
        </div>
      )}

      {(showComplete || showEdit || showInboxActions || showCalendarDelete || showProjectDone) && (
        <span className="flex flex-wrap items-center gap-1 pt-0.5">
          {showComplete && workspaceId && entityId && (
            <button
              type="button"
              disabled={busy || liveStatus === 'done'}
              onClick={handleComplete}
              className={`${btnBase} border-emerald-500/40 bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400`}
            >
              ✓ {t('zenskill.card.completeAction')}
            </button>
          )}
          {showEdit && (
            <button
              type="button"
              disabled={busy}
              onClick={startEdit}
              className={`${btnBase} border-accent/40 bg-accent/10 text-accent hover:bg-accent/20`}
            >
              ✏ {t('zenskill.card.edit')}
            </button>
          )}
          {showInboxActions && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={handleClarify}
                className={`${btnBase} border-accent/40 bg-accent/10 text-accent hover:bg-accent/20`}
              >
                {t('zenskill.card.clarify')}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={handleArchive}
                className={`${btnBase} border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/70`}
              >
                {t('zenskill.card.archive')}
              </button>
            </>
          )}
          {showCalendarDelete && (
            <button
              type="button"
              disabled={busy}
              onClick={handleDeleteEvent}
              className={`${btnBase} ${
                confirmingDelete
                  ? 'border-red-500/50 bg-red-500/20 text-red-600 dark:text-red-400'
                  : 'border-red-500/40 bg-red-500/10 text-red-600 hover:bg-red-500/20 dark:text-red-400'
              }`}
            >
              {confirmingDelete ? t('zenskill.card.deleteConfirm') : t('zenskill.card.delete')}
            </button>
          )}
          {showProjectDone && (
            <button
              type="button"
              disabled={busy || liveStatus === 'done'}
              onClick={handleProjectDone}
              className={`${btnBase} border-emerald-500/40 bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 dark:text-emerald-400`}
            >
              ✓ {t('zenskill.card.completeAction')}
            </button>
          )}
        </span>
      )}
    </div>
  )
}
