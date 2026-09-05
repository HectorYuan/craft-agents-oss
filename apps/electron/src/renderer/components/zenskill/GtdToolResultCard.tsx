/**
 * GtdToolResultCard — structured inline card for ZenSkill GTD tool results
 * in the chat transcript.
 *
 * Rendered through TurnCard's `renderToolResultCard` hook from ChatDisplay
 * when the tool name matches a GTD family. Parses the tool_result JSON
 * defensively (results are truncated at 8000 chars upstream in ws_server.py
 * and may not be valid JSON — falls back to plain text). Clicking the card
 * deep-links to the matching GTD workspace tab (zenskill/gtd?tab=...).
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { navigate, routes } from '@/lib/navigate'

interface GtdToolResultCardProps {
  toolName: string
  resultText: string
}

type GtdTab = 'inbox' | 'actions' | 'calendar'

/**
 * Loose GTD tool matching — Mode B (agent sessions) names carry the MCP
 * prefix (`mcp__zenskill-4__action_add`) while Mode C (companion bridge)
 * uses bare names (`action_add`), so substring match by design.
 */
export function isGtdToolName(toolName?: string): boolean {
  if (!toolName) return false
  const n = toolName.toLowerCase()
  return n.includes('gtd_') || n.includes('inbox_') || n.includes('action_') || n.includes('calendar_')
}

function gtdTabForTool(toolName: string): GtdTab {
  const n = toolName.toLowerCase()
  if (n.includes('calendar_')) return 'calendar'
  if (n.includes('action_')) return 'actions'
  return 'inbox'
}

type ToolKind = 'action_add' | 'action_done' | 'gtd_capture' | 'inbox_clarify' | 'calendar_add' | 'action_mark_next' | 'generic'

function toolKind(toolName: string): ToolKind {
  const n = toolName.toLowerCase()
  if (n.includes('action_done')) return 'action_done'
  if (n.includes('action_add')) return 'action_add'
  if (n.includes('action_mark_next')) return 'action_mark_next'
  if (n.includes('gtd_capture')) return 'gtd_capture'
  if (n.includes('inbox_clarify')) return 'inbox_clarify'
  if (n.includes('calendar_add')) return 'calendar_add'
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

function DetailRow({ label, value }: { label?: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      {label && <span className="shrink-0 text-[10px] text-muted-foreground/70">{label}</span>}
      <span className="truncate text-foreground/80">{value}</span>
    </div>
  )
}

export function GtdToolResultCard({ toolName, resultText }: GtdToolResultCardProps) {
  const { t } = useTranslation()

  if (!resultText) return null
  const data = parseResultObject(resultText)
  const kind = toolKind(toolName)
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

  return (
    <button
      type="button"
      title={t('zenskill.card.openInGtd')}
      onClick={(e) => {
        e.stopPropagation()
        navigate(routes.view.zenskillGtd(tab))
      }}
      className="mt-0.5 inline-flex max-w-full flex-col gap-0.5 rounded-md border border-border/60 bg-background px-2.5 py-1.5 text-left text-xs hover:border-accent/40 hover:bg-accent/5 transition-colors"
    >
      <span className="flex items-center gap-1.5 min-w-0">
        <span className="shrink-0 text-accent">{icon}</span>
        <span className="truncate font-medium text-foreground">{headline}</span>
      </span>
      {details.map((row, i) => (
        <DetailRow key={i} label={row.label} value={row.value} />
      ))}
    </button>
  )
}
