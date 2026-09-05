/**
 * GtdWorkspace — ZenSkill top-level GTD workspace page (L2).
 *
 * Full-page counterpart of the ZenSkillDataPanel GTD tab: Inbox capture
 * flow / Actions / Calendar / Projects, switched by in-page tabs. Data is
 * fetched through the useMcpTool L3 hook (JSON extraction + zenskill:changed
 * auto-refresh); write tools are called directly and rely on the
 * zenskill:changed broadcast to refresh, never manual refetches.
 *
 * Calendar: real month grid via calendar_month (defensive reads — the
 * shape is contract-pending), selected-day detail with calendar_add /
 * calendar_delete, and calendar_suggest slots (hook parked until the user
 * asks for suggestions, mirroring MemoryBrowser's parked search pattern).
 */
import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { toast } from 'sonner'
import { Zap, Inbox, Circle, CalendarDays, FolderKanban } from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { InboxPanel } from '../panels/InboxPanel'
import { ActionsPanel, type ActionStatusFilter } from '../panels/ActionsPanel'
import { CalendarPanel, type CalendarScope } from '../panels/CalendarPanel'
import { ProjectsPanel } from '../panels/ProjectsPanel'
import type {
  GtdAction,
  GtdCalendarEvent,
  GtdCalendarMonthData,
  GtdCalendarSuggestion,
} from '../panels/types'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

type GtdTab = 'inbox' | 'actions' | 'calendar' | 'projects'

interface InboxData { count?: number; items?: { id: string; text?: string; raw_text?: string; status?: string }[] }
interface ActionData { count?: number; items?: GtdAction[] }
interface CalendarListData { count?: number; events?: GtdCalendarEvent[] }
/** calendar_suggest post-fix shape is {suggestions}; items kept as a pre-fix fallback */
interface SuggestData { suggestions?: GtdCalendarSuggestion[]; items?: GtdCalendarSuggestion[] }
interface ProjectData { count?: number; items?: { id: string; name: string; status?: string; progress?: number }[] }

/** Write-tool payload — ok:false means the backend rejected the operation */
interface WriteToolPayload { ok?: boolean; message?: string; result_type?: string }

interface GtdWorkspaceProps {
  initialTab?: string
  workspaceId?: string
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function localTodayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function TabSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1.5 pt-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted/60 animate-pulse"
          style={{ width: `${72 - i * 12}%` }}
        />
      ))}
    </div>
  )
}

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
function notifyActionDone(result: unknown, t: TFunction): void {
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

export function GtdWorkspace({ workspaceId, initialTab }: GtdWorkspaceProps) {
  const { t } = useTranslation()
  const validTabs: GtdTab[] = ['inbox','actions','calendar','projects']; const [activeTab, setActiveTab] = useState<GtdTab>(validTabs.includes(initialTab as GtdTab) ? (initialTab as GtdTab) : 'inbox')
  const [actionStatus, setActionStatus] = useState<ActionStatusFilter>('pending')
  const [calendarScope, setCalendarScope] = useState<CalendarScope>('month')
  const [monthCursor, setMonthCursor] = useState(() => {
    const d = new Date()
    return { year: d.getFullYear(), month: d.getMonth() + 1 }
  })
  const [selectedDate, setSelectedDate] = useState(localTodayIso)
  const [suggestActive, setSuggestActive] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const sourceSlug = ZENSKILL_SOURCE_SLUG
  const inbox = useMcpTool<InboxData>(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 50 })
  const actions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: actionStatus, limit: 50 })
  // Pending actions feed the calendar sidebar (filtered by due_date client-side)
  const dueActions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: 'pending', limit: 100 })
  const calendarToday = useMcpTool<CalendarListData>(workspaceId, sourceSlug, 'calendar_list', { scope: 'today' })
  // Month payload for the grid — parked while the today flat list is shown
  const calendarMonth = useMcpTool<GtdCalendarMonthData>(
    calendarScope === 'today' ? undefined : workspaceId,
    sourceSlug,
    'calendar_month',
    { year: monthCursor.year, month: monthCursor.month },
  )
  // Suggestion slots — parked until "suggest slots" is toggled on
  const suggest = useMcpTool<SuggestData>(
    suggestActive ? workspaceId : undefined,
    sourceSlug,
    'calendar_suggest',
    {},
  )
  const projects = useMcpTool<ProjectData>(workspaceId, sourceSlug, 'project_list', { status: 'active' })

  const runTool = useCallback(async (tool: string, args: Record<string, unknown>) => {
    if (!workspaceId) return
    setBusyId(String(args.action_id ?? args.item_id ?? args.event_id ?? args.project_id ?? tool))
    try {
      // Refresh is driven by the zenskill:changed broadcast (subscribed in
      // useMcpTool) — no manual refetch here, mirroring DataPanel behavior.
      const result = await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, args)
      if (tool === 'action_done') {
        notifyActionDone(result, t)
        return
      }
      const data = extractMcpJson(result) as WriteToolPayload | null
      if (data?.ok === false) {
        toast.error(t('zenskill.toast.toolFailed'), {
          description: typeof data.message === 'string' ? data.message : undefined,
        })
        return
      }
      // Lightweight success feedback for ops whose effect is only visible
      // after the zenskill:changed refresh lands
      if (tool === 'inbox_clarify') {
        toast.success(t('zenskill.toast.clarified', {
          type: typeof data?.result_type === 'string' && data.result_type ? data.result_type : '?',
        }))
      } else if (tool === 'inbox_archive') {
        toast.success(t('zenskill.toast.archived'))
      } else if (tool === 'action_delete') {
        toast.success(t('zenskill.toast.deletedAction'))
      } else if (tool === 'calendar_delete') {
        toast.success(t('zenskill.toast.deletedEvent'))
      }
    } finally {
      setBusyId(null)
    }
  }, [workspaceId, sourceSlug, t])

  const capture = useCallback((text: string) => {
    void runTool('gtd_capture', { text })
  }, [runTool])

  const addAction = useCallback(({ title, priority, dueDate }: { title: string; priority: string; dueDate: string }) => {
    const args: Record<string, unknown> = { title, priority }
    if (dueDate) args.due_date = dueDate
    void runTool('action_add', args)
  }, [runTool])

  const editAction = useCallback(({ actionId, title, priority, dueDate }: { actionId: string; title: string; priority: string; dueDate: string }) => {
    const args: Record<string, unknown> = { action_id: actionId, title, priority }
    if (dueDate) args.due_date = dueDate
    void runTool('action_update', args)
  }, [runTool])

  const addEvent = useCallback(({ date, title, timeStr }: { date: string; title: string; timeStr: string }) => {
    const args: Record<string, unknown> = { date, title }
    if (timeStr) args.time_str = timeStr
    void runTool('calendar_add', args)
  }, [runTool])

  const deleteEvent = useCallback((eventId: string) => {
    void runTool('calendar_delete', { event_id: eventId })
  }, [runTool])

  const prevMonth = useCallback(() => {
    setMonthCursor((c) => (c.month === 1 ? { year: c.year - 1, month: 12 } : { ...c, month: c.month - 1 }))
  }, [])
  const nextMonth = useCallback(() => {
    setMonthCursor((c) => (c.month === 12 ? { year: c.year + 1, month: 1 } : { ...c, month: c.month + 1 }))
  }, [])

  // Derived calendar data — every read defensive (contract pending)
  const todayIso = localTodayIso()
  const monthData = calendarMonth.data
  const monthEvents = monthData?.events ?? []
  const dayEvents = monthEvents.filter((e) => e?.date === selectedDate)
  const dayActions = (dueActions.data?.items ?? []).filter((a) => a?.due_date === selectedDate)
  const suggestRaw = suggest.data as unknown
  const suggestions: GtdCalendarSuggestion[] = Array.isArray(suggestRaw)
    ? (suggestRaw as GtdCalendarSuggestion[])
    : ((suggestRaw as SuggestData | null)?.suggestions ?? (suggestRaw as SuggestData | null)?.items ?? [])
  const monthTotal = monthData?.days
    ? Object.values(monthData.days).reduce((sum, n) => sum + (typeof n === 'number' ? n : 0), 0)
    : monthEvents.length
  const calendarCount = calendarScope === 'today'
    ? (calendarToday.data?.count ?? (calendarToday.data?.events ?? []).length)
    : monthTotal

  const error = inbox.error ?? actions.error ?? calendarToday.error ?? calendarMonth.error ?? projects.error

  const tabs: { key: GtdTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: 'inbox', label: t('zenskill.gtd.tab.inbox'), icon: Inbox },
    { key: 'actions', label: t('zenskill.gtd.tab.actions'), icon: Circle },
    { key: 'calendar', label: t('zenskill.gtd.tab.calendar'), icon: CalendarDays },
    { key: 'projects', label: t('zenskill.gtd.tab.projects'), icon: FolderKanban },
  ]

  const busy = inbox.loading || actions.loading || calendarToday.loading || calendarMonth.loading || projects.loading

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/30 shrink-0">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-accent" />
          <div>
            <div className="text-sm font-medium">{t('zenskill.gtd.title')}</div>
            <div className="text-[11px] text-muted-foreground">{t('zenskill.gtd.subtitle')}</div>
          </div>
        </div>
        {busy && (
          <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden" title={t('zenskill.gtd.loading')}>
            <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
          </div>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-destructive bg-destructive/5 rounded p-2">{error}</div>
      )}

      {/* Tab bar */}
      <div className="px-5 pt-2 border-b border-border/30 flex gap-1 shrink-0">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              activeTab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-4">
          {activeTab === 'inbox' && (
            inbox.loading && !inbox.data ? <TabSkeleton rows={4} /> : (
              <InboxPanel
                variant="full"
                items={inbox.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                onClarify={(itemId) => runTool('inbox_clarify', { item_id: itemId })}
                onArchive={(itemId) => runTool('inbox_archive', { item_id: itemId })}
                onCaptureSubmit={capture}
                captureDisabled={!workspaceId || busyId === 'gtd_capture'}
                capturePlaceholder={t('zenskill.gtd.capture.placeholder')}
              />
            )
          )}

          {activeTab === 'actions' && (
            actions.loading && !actions.data ? <TabSkeleton rows={4} /> : (
              <ActionsPanel
                variant="full"
                actions={actions.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                status={actionStatus}
                onStatusChange={setActionStatus}
                onAdd={addAction}
                addDisabled={!workspaceId || busyId === 'action_add'}
                onDone={(actionId) => runTool('action_done', { action_id: actionId })}
                onMarkNext={(actionId) => runTool('action_mark_next', { action_id: actionId })}
                onDelete={(actionId) => runTool('action_delete', { action_id: actionId })}
                onEdit={editAction}
                editDisabled={!workspaceId}
                projects={projects.data?.items ?? []}
                statusLabels={{
                  pending: t('zenskill.gtd.actions.status.pending'),
                  next: t('zenskill.gtd.actions.status.next'),
                  done: t('zenskill.gtd.actions.status.done'),
                }}
              />
            )
          )}

          {activeTab === 'calendar' && (
            (calendarScope === 'today'
              ? calendarToday.loading && !calendarToday.data
              : calendarMonth.loading && !calendarMonth.data) ? <TabSkeleton rows={6} /> : (
              <CalendarPanel
                variant="full"
                events={calendarToday.data?.events ?? []}
                count={calendarCount}
                scope={calendarScope}
                onScopeChange={setCalendarScope}
                scopeLabels={{
                  month: t('zenskill.gtd.calendar.scope.month'),
                  today: t('zenskill.gtd.calendar.scope.today'),
                  week: t('zenskill.gtd.calendar.scope.week'),
                }}
                monthData={monthData}
                monthYear={monthCursor}
                onPrevMonth={prevMonth}
                onNextMonth={nextMonth}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                dayEvents={dayEvents}
                dayActions={dayActions}
                onAddEvent={addEvent}
                addEventDisabled={!workspaceId || busyId === 'calendar_add'}
                onDeleteEvent={deleteEvent}
                suggestions={suggestions}
                suggestActive={suggestActive}
                suggestLoading={suggest.loading}
                onToggleSuggest={() => setSuggestActive((v) => !v)}
                busyId={busyId}
              />
            )
          )}

          {activeTab === 'projects' && (
            projects.loading && !projects.data ? <TabSkeleton rows={3} /> : (
              <ProjectsPanel
                variant="full"
                projects={projects.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                onDone={(projectId) => runTool('project_done', { project_id: projectId })}
                onAddProject={({ name, outcome }) => runTool('project_add', outcome ? { name, outcome } : { name })}
                addProjectDisabled={!workspaceId || busyId === 'project_add'}
                workspaceId={workspaceId}
                sourceSlug={sourceSlug}
              />
            )
          )}
        </div>
      </div>
    </div>
  )
}
