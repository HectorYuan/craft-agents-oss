/**
 * ActionsPanel — GTD next-action list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab, with the confirm-to-delete interaction kept
 * intact (controlled via confirmDeleteId/onConfirmDeleteIdChange so the
 * parent can keep its existing state; uncontrolled otherwise).
 *
 * full variant (GtdWorkspace): pending/next/done status switch, priority
 * filter, grouping (none / by due date / by project), inline editing
 * (title + priority + due date via action_update), energy_required chips,
 * and an action_add form.
 */
import React, { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Circle, Check, ArrowRight, Trash2, Plus, Pencil, X, CircleDashed } from 'lucide-react'
import { PRIORITY_COLOR, energyChipClass, parseIsoDate, weekKey, type GtdAction } from './types'

export type ActionStatusFilter = 'pending' | 'next' | 'done'
export type ActionGroupMode = 'none' | 'due' | 'project'
export type ActionPriorityFilter = 'all' | 'P0' | 'P1' | 'P2' | 'P3'

export interface ActionsPanelProps {
  actions: GtdAction[]
  /** compact variant: recently-done actions rendered as a trailing list */
  doneActions?: GtdAction[]
  busyId?: string | null
  /** Rows to render before the "+N more" overflow line (default 8) */
  maxItems?: number
  /** compact variant: rows of doneActions to render (default 3) */
  doneMaxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onDone?: (actionId: string) => void
  onMarkNext?: (actionId: string) => void
  onDelete?: (actionId: string) => void
  /** Confirm-to-delete state; controlled when onConfirmDeleteIdChange is provided */
  confirmDeleteId?: string | null
  onConfirmDeleteIdChange?: (id: string | null) => void
  /** full variant: status filter (controlled) */
  status?: ActionStatusFilter
  onStatusChange?: (status: ActionStatusFilter) => void
  /** full variant: action_add form submit */
  onAdd?: (input: { title: string; priority: string; dueDate: string }) => void
  addDisabled?: boolean
  statusLabels?: Partial<Record<ActionStatusFilter, string>>
  /** full variant: inline edit submit (action_update) */
  onEdit?: (input: { actionId: string; title: string; priority: string; dueDate: string }) => void
  editDisabled?: boolean
  /** full variant: project list for by-project grouping (name lookup) */
  projects?: { id: string; name: string }[]
}

const STATUS_FILTERS: ActionStatusFilter[] = ['pending', 'next', 'done']
const GROUP_MODES: ActionGroupMode[] = ['none', 'due', 'project']
const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const

type DueBucket = 'overdue' | 'today' | 'tomorrow' | 'thisWeek' | 'later' | 'nodate'
const DUE_BUCKETS: DueBucket[] = ['overdue', 'today', 'tomorrow', 'thisWeek', 'later', 'nodate']

function dueBucketOf(due: string | undefined, todayIso: string): DueBucket {
  if (!due) return 'nodate'
  const d = parseIsoDate(due)
  const t = parseIsoDate(todayIso)
  if (!d || !t) return 'nodate'
  if (d.getTime() < t.getTime()) return 'overdue'
  const diffDays = Math.round((d.getTime() - t.getTime()) / 86400000)
  if (diffDays <= 1) return diffDays === 1 ? 'tomorrow' : 'today'
  if (weekKey(d) === weekKey(t)) return 'thisWeek'
  return 'later'
}

interface ActionGroup {
  key: string
  label: string
  items: GtdAction[]
  danger?: boolean
}

function buildDueGroups(actions: GtdAction[], todayIso: string, labels: Record<DueBucket, string>): ActionGroup[] {
  const byBucket = new Map<DueBucket, GtdAction[]>()
  for (const a of actions) {
    const bucket = dueBucketOf(a.due_date, todayIso)
    const list = byBucket.get(bucket) ?? []
    list.push(a)
    byBucket.set(bucket, list)
  }
  return DUE_BUCKETS.filter((b) => (byBucket.get(b)?.length ?? 0) > 0).map((b) => ({
    key: b,
    label: labels[b],
    items: byBucket.get(b) ?? [],
    danger: b === 'overdue',
  }))
}

function buildProjectGroups(actions: GtdAction[], projects: { id: string; name: string }[], inboxLabel: string): ActionGroup[] {
  const groups: ActionGroup[] = []
  const inbox: GtdAction[] = []
  const projectIds = new Set(projects.map((p) => p.id))
  for (const p of projects) {
    const items = actions.filter((a) => a.project_id === p.id)
    if (items.length > 0) groups.push({ key: `project:${p.id}`, label: p.name, items })
  }
  for (const a of actions) {
    if (!a.project_id || !projectIds.has(a.project_id)) inbox.push(a)
  }
  if (inbox.length > 0) groups.push({ key: 'inbox', label: inboxLabel, items: inbox })
  return groups
}

export function ActionsPanel({
  actions,
  doneActions,
  busyId,
  maxItems = 8,
  doneMaxItems = 3,
  variant = 'compact',
  showHeader = true,
  onDone,
  onMarkNext,
  onDelete,
  confirmDeleteId,
  onConfirmDeleteIdChange,
  status,
  onStatusChange,
  onAdd,
  addDisabled,
  statusLabels,
  onEdit,
  editDisabled,
  projects,
}: ActionsPanelProps) {
  const isFull = variant === 'full'
  const isDoneView = isFull && status === 'done'
  const { t } = useTranslation()

  // Confirm-to-delete: controlled by the parent when it passes the change
  // handler (ZenSkillDataPanel keeps its existing top-level state);
  // otherwise managed internally (GtdWorkspace). A ref tracks the latest
  // value so the delayed "cancel confirm" callback sees fresh state in
  // both modes.
  const [internalConfirmId, setInternalConfirmId] = useState<string | null>(null)
  const isControlled = onConfirmDeleteIdChange !== undefined
  const activeConfirmId = isControlled ? (confirmDeleteId ?? null) : internalConfirmId
  const confirmIdRef = useRef<string | null>(activeConfirmId)
  confirmIdRef.current = activeConfirmId
  type ConfirmIdUpdate = string | null | ((cur: string | null) => string | null)
  const setConfirmId = (update: ConfirmIdUpdate) => {
    const next = typeof update === 'function' ? update(confirmIdRef.current) : update
    if (isControlled) onConfirmDeleteIdChange(next)
    else setInternalConfirmId(next)
  }

  // full variant: action_add form state
  const [formTitle, setFormTitle] = useState('')
  const [formPriority, setFormPriority] = useState('P2')
  const [formDueDate, setFormDueDate] = useState('')

  // full variant: priority filter + grouping + inline edit (client-side)
  const [priorityFilter, setPriorityFilter] = useState<ActionPriorityFilter>('all')
  const [groupMode, setGroupMode] = useState<ActionGroupMode>('none')
  const [editing, setEditing] = useState<{ id: string; title: string; priority: string; dueDate: string } | null>(null)

  const submitAdd = () => {
    const title = formTitle.trim()
    if (!title || addDisabled) return
    onAdd?.({ title, priority: formPriority, dueDate: formDueDate })
    setFormTitle('')
    setFormDueDate('')
  }

  const startEdit = (a: GtdAction) => {
    setEditing({ id: a.id, title: a.title, priority: a.priority || 'P2', dueDate: a.due_date ?? '' })
  }

  const saveEdit = () => {
    if (!editing) return
    const title = editing.title.trim()
    if (!title || editDisabled) { setEditing(null); return }
    onEdit?.({ actionId: editing.id, title, priority: editing.priority, dueDate: editing.dueDate })
    setEditing(null)
  }

  const labelFor = (key: ActionStatusFilter) => statusLabels?.[key] ?? key
  const dueLabels: Record<DueBucket, string> = {
    overdue: t('zenskill.gtd.actions.group.overdue'),
    today: t('zenskill.gtd.actions.group.today'),
    tomorrow: t('zenskill.gtd.actions.group.tomorrow'),
    thisWeek: t('zenskill.gtd.actions.group.thisWeek'),
    later: t('zenskill.gtd.actions.group.later'),
    nodate: t('zenskill.gtd.actions.group.noDate'),
  }

  const filtered = isFull && priorityFilter !== 'all'
    ? actions.filter((a) => (a.priority || 'P2') === priorityFilter)
    : actions

  const todayIso = (() => {
    const d = new Date()
    const p = (n: number) => (n < 10 ? `0${n}` : String(n))
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
  })()

  const groups: ActionGroup[] | null = !isFull || groupMode === 'none' ? null : groupMode === 'due'
    ? buildDueGroups(filtered, todayIso, dueLabels)
    : buildProjectGroups(filtered, projects ?? [], t('zenskill.gtd.actions.group.inbox'))

  const renderRow = (a: GtdAction) => {
    const energy = typeof a.energy_required === 'number' && Number.isFinite(a.energy_required) ? a.energy_required : null
    return (
      <div
        key={a.id}
        className="flex items-center gap-1.5 text-xs rounded px-2 py-1 hover:bg-muted/50 group"
      >
        {isFull && !isDoneView && editing && editing.id === a.id ? (
          <div className="flex items-center gap-1 flex-1 min-w-0">
            <input
              value={editing.title}
              autoFocus
              onChange={(e) => setEditing({ ...editing, title: e.target.value })}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing) return
                if (e.key === 'Enter') saveEdit()
                if (e.key === 'Escape') setEditing(null)
              }}
              className="flex-1 min-w-0 text-xs bg-muted/40 rounded px-1.5 py-0.5 outline-none focus:ring-1 focus:ring-accent/40"
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
              onClick={saveEdit}
              disabled={editDisabled || busyId === editing.id || !editing.title.trim()}
              className="p-0.5 rounded hover:bg-green-500/20 text-green-400 disabled:opacity-40 shrink-0"
              title={t('zenskill.gtd.actions.editSave')}
            >
              <Check className="h-3 w-3" />
            </button>
            <button
              onClick={() => setEditing(null)}
              className="p-0.5 rounded hover:bg-muted/60 text-muted-foreground shrink-0"
              title={t('zenskill.gtd.actions.editCancel')}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <>
            {!isDoneView && (
              <span
                className={`text-[9px] px-1 py-px rounded shrink-0 ${PRIORITY_COLOR[a.priority || 'P2'] || PRIORITY_COLOR.P2}`}
              >
                {a.priority || 'P2'}
              </span>
            )}
            <span
              className={`truncate flex-1 ${isDoneView ? 'line-through decoration-muted-foreground/40 text-muted-foreground' : ''} ${isFull && !isDoneView ? 'cursor-text' : ''}`}
              onClick={isFull && !isDoneView ? () => startEdit(a) : undefined}
              title={a.title}
            >
              {a.title}
            </span>
            {!isDoneView && energy !== null && (
              <span
                className={`text-[9px] px-1 py-px rounded shrink-0 tabular-nums ${energyChipClass(energy)}`}
                title={t('zenskill.gtd.actions.energy')}
              >
                ⚡{energy}
              </span>
            )}
            {isFull && (a.created_by === 'agent' || a.created_by === 'user') && (
              <span
                className="text-[9px] px-1 py-px rounded shrink-0 bg-muted/60 text-muted-foreground/70"
                title={t('zenskill.gtd.actions.source', { origin: a.created_by })}
              >
                {a.created_by}
              </span>
            )}
            {a.due_date && !isDoneView && (
              <span className="text-[10px] text-muted-foreground shrink-0">{a.due_date.slice(5)}</span>
            )}
            {!isDoneView && (
              <>
                {isFull && onEdit && (
                  <button
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                    title={t('zenskill.gtd.actions.edit')}
                    disabled={busyId === a.id}
                    onClick={() => startEdit(a)}
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400 shrink-0"
                  title="Done"
                  disabled={busyId === a.id}
                  onClick={() => onDone?.(a.id)}
                >
                  <Check className="h-3 w-3" />
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                  title="Mark as next"
                  disabled={busyId === a.id}
                  onClick={() => onMarkNext?.(a.id)}
                >
                  <ArrowRight className="h-3 w-3" />
                </button>
                <button
                  className={`opacity-0 group-hover:opacity-100 p-0.5 rounded shrink-0 ${
                    activeConfirmId === a.id
                      ? 'bg-red-500/25 text-red-400'
                      : 'hover:bg-red-500/20 text-muted-foreground hover:text-red-400'
                  }`}
                  title={activeConfirmId === a.id ? '点击再次确认删除' : 'Delete'}
                  disabled={busyId === a.id}
                  onClick={() => {
                    if (activeConfirmId === a.id) {
                      setConfirmId(null)
                      onDelete?.(a.id)
                    } else {
                      setConfirmId(a.id)
                      setTimeout(() => setConfirmId((cur) => (cur === a.id ? null : cur)), 3000)
                    }
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </>
            )}
            {isDoneView && (
              <Check className="h-2.5 w-2.5 text-green-500/60 shrink-0" />
            )}
          </>
        )}
      </div>
    )
  }

  const renderGrouped = (gs: ActionGroup[]) => (
    <div className="space-y-0.5">
      {gs.map((g) => (
        <div key={g.key}>
          <div className={`flex items-center gap-1 text-[10px] font-medium px-2 pt-1.5 ${g.danger ? 'text-red-400' : 'text-muted-foreground'}`}>
            {g.label}
            <span className="text-muted-foreground/60">({g.items.length})</span>
          </div>
          {g.items.map(renderRow)}
        </div>
      ))}
    </div>
  )

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <Circle className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            Actions ({isFull ? filtered.length : actions.length})
          </span>
        </div>
      )}
      {isFull && (
        <div className="space-y-1.5 mb-1.5">
          <div className="flex items-center gap-0.5">
            {STATUS_FILTERS.map((key) => (
              <button
                key={key}
                onClick={() => onStatusChange?.(key)}
                className={`px-2 py-1 text-[11px] rounded transition-colors ${
                  status === key
                    ? 'bg-accent/15 text-accent'
                    : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                }`}
              >
                {labelFor(key)}
              </button>
            ))}
            <select
              value={priorityFilter}
              onChange={(e) => setPriorityFilter(e.target.value as ActionPriorityFilter)}
              className="ml-auto text-[11px] bg-muted/40 rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground"
            >
              <option value="all">{t('zenskill.gtd.actions.priority.all')}</option>
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-0.5">
            {GROUP_MODES.map((mode) => (
              <button
                key={mode}
                onClick={() => setGroupMode(mode)}
                className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                  groupMode === mode
                    ? 'bg-accent/15 text-accent'
                    : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                }`}
              >
                {t(`zenskill.gtd.actions.group.${mode}`)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <input
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) submitAdd()
              }}
              placeholder="New action title..."
              disabled={addDisabled}
              className="flex-1 text-xs bg-muted/40 rounded px-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
            />
            <select
              value={formPriority}
              onChange={(e) => setFormPriority(e.target.value)}
              disabled={addDisabled}
              className="text-xs bg-muted/40 rounded px-1 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <input
              type="date"
              value={formDueDate}
              onChange={(e) => setFormDueDate(e.target.value)}
              disabled={addDisabled}
              className="text-xs bg-muted/40 rounded px-1.5 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground disabled:opacity-50"
            />
            <button
              onClick={submitAdd}
              disabled={addDisabled || !formTitle.trim()}
              className="p-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40 shrink-0"
              title="Add action (action_add)"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
      {filtered.length === 0 ? (
        isFull ? (
          <div className="flex flex-col items-center gap-1 py-3 text-muted-foreground/60">
            <CircleDashed className="h-4 w-4" />
            <span className="text-[11px] italic">No pending actions</span>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground italic pl-5">No pending actions</div>
        )
      ) : groups ? (
        renderGrouped(groups)
      ) : (
        <div className="space-y-1">
          {filtered.slice(0, maxItems).map(renderRow)}
          {filtered.length > maxItems && (
            <div className="text-xs text-muted-foreground pl-5">+{filtered.length - maxItems} more</div>
          )}
        </div>
      )}
      {!isFull && doneActions && doneActions.length > 0 && (
        <div className="mt-1.5 pl-5 space-y-0.5">
          {doneActions.slice(0, doneMaxItems).map((a) => (
            <div key={a.id} className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
              <Check className="h-2.5 w-2.5 text-green-500/60 shrink-0" />
              <span className="truncate line-through decoration-muted-foreground/40">{a.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
