/**
 * ActionsPanel — GTD next-action list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab, with the confirm-to-delete interaction kept
 * intact (controlled via confirmDeleteId/onConfirmDeleteIdChange so the
 * parent can keep its existing state; uncontrolled otherwise).
 *
 * full variant (GtdWorkspace): adds a pending/next/done status switch, an
 * action_add form (title + priority + due date), and progress display.
 */
import React, { useRef, useState } from 'react'
import { Circle, Check, ArrowRight, Trash2, Plus } from 'lucide-react'
import { PRIORITY_COLOR, type GtdAction } from './types'

export type ActionStatusFilter = 'pending' | 'next' | 'done'

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
}

const STATUS_FILTERS: ActionStatusFilter[] = ['pending', 'next', 'done']

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
}: ActionsPanelProps) {
  const isFull = variant === 'full'
  const isDoneView = isFull && status === 'done'

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

  const submitAdd = () => {
    const title = formTitle.trim()
    if (!title || addDisabled) return
    onAdd?.({ title, priority: formPriority, dueDate: formDueDate })
    setFormTitle('')
    setFormDueDate('')
  }

  const labelFor = (key: ActionStatusFilter) => statusLabels?.[key] ?? key

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <Circle className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            Actions ({actions.length})
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
              {['P0', 'P1', 'P2', 'P3'].map((p) => (
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
      {actions.length === 0 ? (
        <div className="text-xs text-muted-foreground italic pl-5">No pending actions</div>
      ) : (
        <div className="space-y-1">
          {actions.slice(0, maxItems).map((a) => (
            <div
              key={a.id}
              className="flex items-center gap-1.5 text-xs rounded px-2 py-1 hover:bg-muted/50 group"
            >
              {!isDoneView && (
                <span
                  className={`text-[9px] px-1 py-px rounded shrink-0 ${PRIORITY_COLOR[a.priority || 'P2'] || PRIORITY_COLOR.P2}`}
                >
                  {a.priority || 'P2'}
                </span>
              )}
              <span className={`truncate flex-1 ${isDoneView ? 'line-through decoration-muted-foreground/40 text-muted-foreground' : ''}`}>
                {a.title}
              </span>
              {a.due_date && !isDoneView && (
                <span className="text-[10px] text-muted-foreground shrink-0">{a.due_date.slice(5)}</span>
              )}
              {!isDoneView && (
                <>
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
            </div>
          ))}
          {actions.length > maxItems && (
            <div className="text-xs text-muted-foreground pl-5">+{actions.length - maxItems} more</div>
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
