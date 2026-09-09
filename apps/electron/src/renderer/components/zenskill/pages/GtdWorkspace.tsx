/**
 * GtdWorkspace — ZenSkill top-level GTD workspace page (L2).
 *
 * Full-page counterpart of the ZenSkillDataPanel GTD tab: Inbox capture
 * flow / Actions / Calendar / Projects / Incubating, switched by in-page
 * tabs, with a compact Review Bar (energy + daily_review numbers) between
 * the header and the tab bar, plus a ProgressionBar strip (task_progressions
 * suggestions, MVP-2a) right below it. Data is fetched through the useMcpTool L3
 * hook (JSON extraction + zenskill:changed auto-refresh); write tools are
 * called directly and rely on the zenskill:changed broadcast to refresh,
 * never manual refetches.
 *
 * Clarify is a two-step interaction: the InboxPanel Wand2 button opens the
 * ClarifyModal, and the confirmed category (plus optional existing-action
 * target) is sent to inbox_clarify, which creates the downstream object.
 *
 * Calendar: real month grid via calendar_month (defensive reads — the
 * shape is contract-pending), selected-day detail with calendar_add /
 * calendar_delete, and calendar_suggest slots (hook parked until the user
 * asks for suggestions, mirroring MemoryBrowser's parked search pattern).
 *
 * Day 4 governance: a compact proactivity selector (active / quiet /
 * ritual_only) sits between the ReviewBar and the ProgressionBar. The
 * current mode is read through the progression_mode MCP tool and passed
 * down to ProgressionBar, which filters suggestion density accordingly
 * (quiet = high priority only, ritual_only = time-based rituals).
 */
import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Zap, Inbox, Circle, CalendarDays, FolderKanban, Sprout } from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { notifyActionDone } from '../panels/gtdFeedback'
import { PageToChatBridge } from '../PageToChatBridge'
import { InboxPanel } from '../panels/InboxPanel'
import { ActionsPanel, type ActionStatusFilter } from '../panels/ActionsPanel'
import { CalendarPanel, type CalendarScope } from '../panels/CalendarPanel'
import { ProjectsPanel } from '../panels/ProjectsPanel'
import { IncubatingPanel } from '../panels/IncubatingPanel'
import { ClarifyModal, type ClarifyResultType } from '../panels/ClarifyModal'
import { ReviewBar } from '../panels/ReviewBar'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { ProgressionBar } from '../panels/ProgressionBar'
import type {
  GtdAction,
  GtdCalendarEvent,
  GtdCalendarMonthData,
  GtdCalendarSuggestion,
  GtdItem,
  TaskProgression,
} from '../panels/types'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

type GtdTab = 'inbox' | 'actions' | 'calendar' | 'projects' | 'incubating'

interface InboxData { count?: number; items?: { id: string; text?: string; raw_text?: string; status?: string }[] }
/** inbox_suggest payload — B09: item_id → suggested classification */
interface InboxSuggestData { count?: number; items?: { item_id: string; text?: string; suggested_type: string }[] }
interface ActionData { count?: number; items?: GtdAction[] }
interface CalendarListData { count?: number; events?: GtdCalendarEvent[] }
/** calendar_suggest post-fix shape is {suggestions}; items kept as a pre-fix fallback */
interface SuggestData { suggestions?: GtdCalendarSuggestion[]; items?: GtdCalendarSuggestion[] }
interface ProjectData { count?: number; items?: { id: string; name: string; status?: string; progress?: number }[] }
/** energy_level payload — status.pct is a 0..1 fraction, all reads defensive */
interface EnergyLevelData {
  status?: { current_energy?: number; max_energy?: number; pct?: number; level?: string }
  message?: string
}
/** daily_review payload (contract-pending, defensive reads) */
interface DailyReviewData {
  inbox?: { processed?: number; pending?: number }
  actions?: { completed?: number; added?: number }
  message?: string
}
/** task_progressions payload (MVP-2a) — backend tool runs in parallel, defensive reads */
interface ProgressionsData { count?: number; progressions?: TaskProgression[] }

/** progression_mode payload (Day 4) — query without mode, defensive reads */
interface ProgressionModeData { mode?: string; message?: string }

/** Day 4 proactivity modes — drives ProgressionBar suggestion density */
type ProgressionMode = 'active' | 'quiet' | 'ritual_only'

const PROGRESSION_MODES: ProgressionMode[] = ['active', 'quiet', 'ritual_only']

/** i18n key suffix per mode (ritual_only maps to the camelCase locale key) */
function modeLabelKey(mode: ProgressionMode): string {
  return `zenskill.progression.mode.${mode === 'ritual_only' ? 'ritualOnly' : mode}`
}

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

export function GtdWorkspace({ workspaceId, initialTab }: GtdWorkspaceProps) {
  const { t } = useTranslation()
  const validTabs: GtdTab[] = ['inbox','actions','calendar','projects','incubating']; const [activeTab, setActiveTab] = useState<GtdTab>(validTabs.includes(initialTab as GtdTab) ? (initialTab as GtdTab) : 'inbox')
  const [actionStatus, setActionStatus] = useState<ActionStatusFilter>('pending')
  const [calendarScope, setCalendarScope] = useState<CalendarScope>('month')
  const [monthCursor, setMonthCursor] = useState(() => {
    const d = new Date()
    return { year: d.getFullYear(), month: d.getMonth() + 1 }
  })
  const [selectedDate, setSelectedDate] = useState(localTodayIso)
  const [suggestActive, setSuggestActive] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  /** B01: inbox item currently open in the ClarifyModal (null = closed) */
  const [clarifyItem, setClarifyItem] = useState<GtdItem | null>(null)

  const sourceSlug = ZENSKILL_SOURCE_SLUG
  const inbox = useMcpTool<InboxData>(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 50 })
  const actions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: actionStatus, limit: 50 })
  // Pending actions feed the calendar sidebar (filtered by due_date client-side)
  const dueActions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: 'pending', limit: 100 })
  // B06: suggested next actions (top of the pending view)
  const nextActions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: 'next', limit: 3 })
  const calendarToday = useMcpTool<CalendarListData>(workspaceId, sourceSlug, 'calendar_list', { scope: 'today' })
  // B13: week-scope feed for the ActionsPanel scheduled-state icons (today alone
  // would miss actions scheduled later in the week); failure is non-fatal
  const calendarWeek = useMcpTool<CalendarListData>(workspaceId, sourceSlug, 'calendar_list', { scope: 'week' })
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
  // B04+B15+B16: Review Bar data (energy + daily review), refreshed by zenskill:changed
  const energyLevel = useMcpTool<EnergyLevelData>(workspaceId, sourceSlug, 'energy_level', {})
  const dailyReview = useMcpTool<DailyReviewData>(workspaceId, sourceSlug, 'daily_review', {})
  // B09: AI classification suggestions for unprocessed inbox items (read-only)
  const inboxSuggest = useMcpTool<InboxSuggestData>(workspaceId, sourceSlug, 'inbox_suggest', { limit: 50 })
  // MVP-2a: progression suggestions for the ReviewBar strip (layer 3); the
  // backend tool runs in parallel — errors land in .error and collapse to
  // "no suggestions" (ProgressionBar hidden), never a visible failure
  const progressions = useMcpTool<ProgressionsData>(workspaceId, sourceSlug, 'task_progressions', { limit: 3 })
  // Day 4: progression proactivity (active/quiet/ritual_only) — queried via
  // progression_mode; the selector below writes through the same tool
  const progressionMode = useMcpTool<ProgressionModeData>(workspaceId, sourceSlug, 'progression_mode', {})
  // Optimistic override keeps the selector responsive: progression_mode is
  // classified as a read tool backend-side, so no zenskill:changed refresh
  // is expected after a set — the chosen mode is applied locally right away
  const [modeOverride, setModeOverride] = useState<string | null>(null)
  const progressionModeValue: ProgressionMode =
    modeOverride === 'quiet' || modeOverride === 'ritual_only' || modeOverride === 'active'
      ? modeOverride
      : (progressionMode.data?.mode === 'quiet' || progressionMode.data?.mode === 'ritual_only'
        ? progressionMode.data.mode
        : 'active')

  // Day 4: switch proactivity via progression_mode {mode}; on failure revert
  // the optimistic override and surface the backend error
  const setProgressionMode = useCallback((mode: ProgressionMode) => {
    setModeOverride(mode)
    if (!workspaceId) return
    window.electronAPI
      .callMcpTool(workspaceId, sourceSlug, 'progression_mode', { mode })
      .then((result) => {
        const data = extractMcpJson(result) as (WriteToolPayload & { ok?: boolean }) | null
        if (data?.ok === false) {
          throw new Error(typeof data.message === 'string' ? data.message : 'mode rejected')
        }
      })
      .catch(() => {
        setModeOverride(null)
        toast.error(t('zenskill.toast.toolFailed'))
      })
  }, [workspaceId, sourceSlug, t])

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
      if (tool === 'gtd_capture') {
        toast.success(t('zenskill.toast.captured'))
      } else if (tool === 'inbox_clarify') {
        const rawType = typeof data?.result_type === 'string' && data.result_type ? data.result_type : '?'
        const knownType = (['action', 'project', 'calendar', 'reference'] as const).includes(rawType as ClarifyResultType)
        toast.success(t('zenskill.toast.clarified', {
          type: knownType ? t(`zenskill.modal.clarify.type.${rawType}`) : rawType,
        }))
      } else if (tool === 'inbox_archive') {
        toast.success(t('zenskill.toast.archived'))
      } else if (tool === 'action_delete') {
        toast.success(t('zenskill.toast.deletedAction'))
      } else if (tool === 'calendar_delete') {
        toast.success(t('zenskill.toast.deletedEvent'))
      } else if (tool === 'calendar_add' && args.action_id) {
        // B13: only the action-scheduling path toasts (plain calendar_add from
        // the CalendarPanel form has its own visible row already)
        toast.success(t('zenskill.toast.scheduled', { date: String(args.date ?? '') }))
      } else if (tool === 'incubating_promote') {
        toast.success(t('zenskill.toast.promoted'))
      }
    } finally {
      setBusyId(null)
    }
  }, [workspaceId, sourceSlug, t])

  const capture = useCallback((text: string) => {
    void runTool('gtd_capture', { text })
  }, [runTool])

  const addAction = useCallback(({ title, priority, dueDate, energyRequired, projectId, contexts, repeatRule }: {
    title: string
    priority: string
    dueDate: string
    energyRequired?: number
    projectId?: string
    /** raw comma-separated contexts from the form; split into a list for the backend */
    contexts?: string
    repeatRule?: string
  }) => {
    const args: Record<string, unknown> = { title, priority, skill_id: 'zenskill-core' }
    if (dueDate) args.due_date = dueDate
    if (typeof energyRequired === 'number') args.energy_required = energyRequired
    if (projectId) args.project_id = projectId
    const contextList = (contexts ?? '')
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean)
    if (contextList.length > 0) args.contexts = contextList
    if (repeatRule) args.repeat_rule = repeatRule
    void runTool('action_add', args)
  }, [runTool])

  // B13: schedule an action to the calendar (backend links via action_id)
  const scheduleAction = useCallback(({ actionId, title, date }: { actionId: string; title: string; date: string }) => {
    void runTool('calendar_add', { date, title, action_id: actionId })
  }, [runTool])

  // B10: batch-classify every unprocessed inbox item by its AI suggestion.
  // Sequential awaits keep busyId/toast feedback ordered; each clarify
  // triggers a zenskill:changed refresh which is debounced by useMcpTool.
  const batchClassify = useCallback(async () => {
    const suggestions = inboxSuggest.data?.items ?? []
    if (!workspaceId || suggestions.length === 0) return
    for (const s of suggestions) {
      await runTool('inbox_clarify', { item_id: s.item_id, result_type: s.suggested_type })
    }
  }, [inboxSuggest.data, workspaceId, runTool])

  // B01: two-step clarify confirm — target_id links an existing action,
  // omitting it lets the backend create the downstream object
  const confirmClarify = useCallback((itemId: string, resultType: ClarifyResultType, targetId?: string) => {
    const args: Record<string, unknown> = { item_id: itemId, result_type: resultType }
    if (targetId) args.target_id = targetId
    setClarifyItem(null)
    void runTool('inbox_clarify', args)
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

  // B09: item_id → suggested classification lookup for the inbox list
  const suggestionMap: Record<string, string> = {}
  for (const s of inboxSuggest.data?.items ?? []) {
    suggestionMap[s.item_id] = s.suggested_type
  }

  // B13: action_id → scheduled date (today + week feeds merged; later entries win)
  const scheduledMap: Record<string, string> = {}
  for (const e of [...(calendarToday.data?.events ?? []), ...(calendarWeek.data?.events ?? [])]) {
    if (e?.action_id) scheduledMap[e.action_id] = e.date
  }

  const error = inbox.error ?? actions.error ?? calendarToday.error ?? calendarMonth.error ?? projects.error

  const tabs: { key: GtdTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: 'inbox', label: t('zenskill.gtd.tab.inbox'), icon: Inbox },
    { key: 'actions', label: t('zenskill.gtd.tab.actions'), icon: Circle },
    { key: 'calendar', label: t('zenskill.gtd.tab.calendar'), icon: CalendarDays },
    { key: 'projects', label: t('zenskill.gtd.tab.projects'), icon: FolderKanban },
    { key: 'incubating', label: t('zenskill.gtd.tab.incubating'), icon: Sprout },
  ]

  const busy = inbox.loading || actions.loading || calendarToday.loading || calendarMonth.loading || projects.loading

  // Review Bar derived values — every read defensive (contract pending)
  const energyStatus = energyLevel.data?.status
  const currentEnergy = typeof energyStatus?.current_energy === 'number' ? energyStatus.current_energy : null
  const maxEnergy = typeof energyStatus?.max_energy === 'number' ? energyStatus.max_energy : null
  const energyPct = typeof energyStatus?.pct === 'number'
    ? energyStatus.pct
    : currentEnergy !== null && maxEnergy ? currentEnergy / Math.max(maxEnergy, 1) : null
  const energyLevelLabel = typeof energyStatus?.level === 'string' ? energyStatus.level : undefined
  const doneToday = dailyReview.data?.actions?.completed ?? 0
  const pendingCount = dailyReview.data?.inbox?.pending ?? 0
  const overdueCount = (dueActions.data?.items ?? []).filter(
    (a) => a?.due_date && a.due_date < todayIso,
  ).length
  const reviewMessage = typeof dailyReview.data?.message === 'string' ? dailyReview.data.message.slice(0, 60) : ''

  // MVP-2a: defensively extract valid suggestions — an entry needs suggestion
  // text to be actionable; prompt/priority checks happen inside ProgressionBar
  const progressionItems: TaskProgression[] = (
    Array.isArray(progressions.data?.progressions) ? progressions.data.progressions : []
  ).filter((p) => typeof p?.suggestion === 'string' && p.suggestion.trim() !== '')

  // MVP-1 PageToChatBridge prompt — page-data snapshot framed as a planning
  // request. due_date reads use localTodayIso (same convention as the
  // ReviewBar overdue count), not the UTC slice.
  const buildBridgePrompt = useCallback((data: {
    actions?: GtdAction[]
    inbox?: { status?: string }[]
    calendar?: GtdCalendarEvent[]
  }) => {
    const pending = (data.actions ?? []).filter((a) => a?.status === 'pending')
    const overdue = pending.filter((a) => a?.due_date && a.due_date < todayIso)
    const inboxCount = (data.inbox ?? []).filter((i) => i?.status === 'unprocessed')
    const dueToday = pending.filter((a) => a?.due_date === todayIso)
    const todayEvents = data.calendar?.length ?? 0

    return `我正在查看 GTD 工作台。当前有 ${pending.length} 个待处理行动，` +
      `${overdue.length} 个逾期，${inboxCount.length} 条收件箱待整理` +
      (todayEvents > 0 ? `，今天有 ${todayEvents} 项日程` : '') +
      `。` +
      (dueToday.length > 0 ? `今天有 ${dueToday.length} 项到期：${dueToday.map((a) => a.title).join('、')}。` : '') +
      ` 帮我规划下一步。`
  }, [todayIso])

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
        <div className="flex items-center gap-3">
          {busy && (
            <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden" title={t('zenskill.gtd.loading')}>
              <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
            </div>
          )}
          <PageToChatBridge
            pageName="GTD Workspace"
            workspaceId={workspaceId}
            contextData={{
              actions: dueActions.data?.items,
              inbox: inbox.data?.items,
              calendar: calendarToday.data?.events,
            }}
            buildPrompt={buildBridgePrompt}
          />
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-destructive bg-destructive/5 rounded p-2">{error}</div>
      )}

      {/* B04+B15+B16: ReviewBar — energy ring + daily review numbers */}
      <ReviewBar
        energyPct={energyPct}
        energyLevel={energyLevelLabel}
        currentEnergy={currentEnergy}
        maxEnergy={maxEnergy}
        doneToday={doneToday}
        pendingCount={pendingCount}
        overdueCount={overdueCount}
        message={reviewMessage}
      />

      {/* Day 4: progression proactivity — three-mode selector controlling the
          suggestion density of the ProgressionBar below (active = all,
          quiet = high priority only, ritual_only = time-based rituals) */}
      {workspaceId && (
        <div
          role="radiogroup"
          aria-label={t('zenskill.progression.mode.modeLabel')}
          className="mx-5 mt-2 flex items-center justify-end gap-1.5 shrink-0 text-[11px]"
        >
          <span className="text-muted-foreground">{t('zenskill.progression.mode.modeLabel')}</span>
          {PROGRESSION_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={progressionModeValue === mode}
              onClick={() => setProgressionMode(mode)}
              className={`rounded-full border px-2 py-0.5 transition-colors ${
                progressionModeValue === mode
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border/40 text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(modeLabelKey(mode))}
            </button>
          ))}
        </div>
      )}

      {/* MVP-2a: progression suggestions — one-line cards under the ReviewBar,
          hidden entirely when the backend tool has nothing to offer */}
      <ProgressionBar
        workspaceId={workspaceId}
        progressions={progressionItems}
        mode={progressionModeValue}
      />

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
                onClarifyRequest={(item) => setClarifyItem(item)}
                onArchive={(itemId) => runTool('inbox_archive', { item_id: itemId })}
                suggestions={suggestionMap}
                onBatchClassify={() => void batchClassify()}
                batchClassifyDisabled={!workspaceId || busyId !== null || (inboxSuggest.data?.count ?? 0) === 0}
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
                nextActions={nextActions.data?.items ?? []}
                onSchedule={scheduleAction}
                scheduledDates={scheduledMap}
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

          {activeTab === 'incubating' && (
            <ErrorBoundary componentName="IncubatingPanel">
              <IncubatingPanel
                variant="full"
                workspaceId={workspaceId}
                sourceSlug={sourceSlug}
                busyId={busyId}
                onPromote={(itemId) => runTool('incubating_promote', { item_id: itemId })}
              />
            </ErrorBoundary>
          )}
        </div>
      </div>

      {/* B01: two-step inbox clarify modal */}
      <ClarifyModal
        item={clarifyItem}
        pendingActions={dueActions.data?.items ?? []}
        busy={busyId === clarifyItem?.id}
        onConfirm={confirmClarify}
        onClose={() => setClarifyItem(null)}
      />
    </div>
  )
}
