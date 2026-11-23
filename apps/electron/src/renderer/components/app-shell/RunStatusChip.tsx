/**
 * RunStatusChip — compact status chip for the current swarm run (P2-4; P3-4 detail rows).
 *
 * Lives inside the existing chat input badge row; no new page or route.
 * Self-gates on channel availability and per-session atom state:
 * - channel absent / feature disabled on the server → renders nothing
 * - no observed run → renders nothing
 * - subtask count unknown → placeholder `—` (never a fabricated 0)
 * - detail rows are deduplicated by `subtaskId`; distinct count comes from the
 *   authoritative `run:status` summary, never from event counts
 * - cancel goes through `run:cancel`, then reconciles from `run:status`;
 *   no optimistic terminal flip.
 */

import * as React from 'react'
import { useAtomValue, useSetAtom } from 'jotai'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, XCircle, Square, AlertTriangle } from 'lucide-react'
import { Spinner } from '@craft-agent/ui'
import { RPC_CHANNELS } from '@craft-agent/shared/protocol'
import { runStateAtomFamily, runIdForSession } from '@/atoms/run'
import {
  runStateFromStatusDto,
  isTerminalRunStatus,
  type RunState,
  type RunSubtaskEntry,
} from '@/event-processor/handlers/run'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface RunStatusChipProps {
  sessionId: string
}

const STATUS_LABEL_KEYS: Record<string, string> = {
  queued: 'chat.runStatusQueued',
  pending: 'chat.runStatusQueued',
  ready: 'chat.runStatusQueued',
  running: 'chat.runStatusRunning',
  succeeded: 'chat.runStatusSucceeded',
  failed: 'chat.runStatusFailed',
  cancelled: 'chat.runStatusCancelled',
  timed_out: 'chat.runStatusTimedOut',
  skipped_by_cancel: 'chat.runStatusSkipped',
}

function StatusIcon({ status, small = false }: { status: RunState['status'] | string; small?: boolean }) {
  const size = small ? 'h-3 w-3' : 'h-3.5 w-3.5'
  switch (status) {
    case 'succeeded':
      return <CheckCircle2 className={cn(size, 'text-green-600 dark:text-green-500')} />
    case 'failed':
      return <XCircle className={cn(size, 'text-destructive')} />
    case 'cancelled':
      return <Square className={cn(size, 'opacity-60')} />
    case 'timed_out':
      return <AlertTriangle className={cn(size, 'text-amber-600 dark:text-amber-500')} />
    case 'skipped_by_cancel':
      return <Square className={cn(size, 'opacity-40')} />
    default:
      return <Spinner className={small ? 'text-xs' : 'text-xs'} />
  }
}

function SubtaskRow({ entry }: { entry: RunSubtaskEntry }) {
  const { t } = useTranslation()
  const labelKey = STATUS_LABEL_KEYS[entry.status]
  const statusLabel = labelKey ? t(labelKey) : entry.status || t('common.unknown')
  return (
    <div
      data-testid="run-subtask-row"
      data-subtask-id={entry.subtaskId}
      className="flex items-center gap-1.5 text-[11px] opacity-70 select-none"
    >
      <StatusIcon status={entry.status} small />
      <span data-testid="run-subtask-status" className="opacity-80">{statusLabel}</span>
      <span data-testid="run-subtask-attempt" className="tabular-nums opacity-60">
        #{entry.attempt || 1}
      </span>
      {entry.capabilityId && (
        <span data-testid="run-subtask-capability" className="truncate opacity-50">
          {entry.capabilityId}
        </span>
      )}
    </div>
  )
}

export function RunStatusChip({ sessionId }: RunStatusChipProps) {
  const { t } = useTranslation()
  const state = useAtomValue(runStateAtomFamily(sessionId))
  const setState = useSetAtom(runStateAtomFamily(sessionId))
  const [cancelling, setCancelling] = React.useState(false)

  const available = window.electronAPI.isChannelAvailable(RPC_CHANNELS.run.STATUS)
  const runId = available ? runIdForSession(sessionId) : undefined

  // Hydrate late: if the chip mounts after the run already started (or events
  // were missed), reconcile from the authoritative `run:status` once.
  React.useEffect(() => {
    if (!available || state || !runId) return
    let alive = true
    window.electronAPI.getRunStatus(runId)
      .then((snap) => { if (alive) setState(() => runStateFromStatusDto(snap)) })
      .catch(() => {})
    return () => { alive = false }
  }, [available, state, runId, setState])

  // Events never carry the distinct summary total: once event-derived rows exist
  // but the count is still unknown, reconcile the authoritative status once.
  React.useEffect(() => {
    if (!available || !state?.runId || state.subtaskTotal !== undefined) return
    let alive = true
    const timer = setTimeout(() => {
      window.electronAPI.getRunStatus(state!.runId)
        .then((snap) => { if (alive) setState(() => runStateFromStatusDto(snap)) })
        .catch(() => {})
    }, 500)
    return () => { alive = false; clearTimeout(timer) }
  }, [available, state?.runId, state?.subtaskTotal, setState])

  if (!available || !state) return null

  const terminal = state.terminal || isTerminalRunStatus(state.status)

  const handleCancel = async () => {
    if (terminal || cancelling) return
    setCancelling(true)
    try {
      await window.electronAPI.cancelRun(state.runId)
      // Reconcile from the authoritative status RPC — do not flip to terminal optimistically.
      const snapshot = await window.electronAPI.getRunStatus(state.runId)
      setState(() => runStateFromStatusDto(snapshot))
    } catch {
      toast.error(t('chat.runCancelFailed'))
    } finally {
      setCancelling(false)
    }
  }

  const labelKey = state.status ? STATUS_LABEL_KEYS[state.status] : undefined
  const statusLabel = labelKey ? t(labelKey) : (state.status ?? t('common.unknown'))

  return (
    <div
      data-testid="run-status-chip"
      className={cn(
        'flex flex-col gap-1 rounded-[8px] p-1.5',
        'transition-all shadow-minimal bg-white dark:bg-white/10',
      )}
    >
      <div className="flex items-center gap-1.5 h-[30px] pl-1 pr-1 text-xs font-medium shrink-0 select-none">
        <StatusIcon status={state.status} />
        <span data-testid="run-status" className="opacity-70">{statusLabel}</span>
        <span data-testid="run-subtasks" className="opacity-60 tabular-nums">
          {state.subtaskTotal === undefined
            ? '—'
            : t('chat.runSubtasksCount', { count: state.subtaskTotal })}
        </span>
        {!terminal && (
          <button
            data-testid="run-cancel"
            type="button"
            onClick={handleCancel}
            disabled={cancelling}
            title={t('chat.runCancel')}
            aria-label={t('chat.runCancel')}
            className="opacity-60 hover:opacity-100 disabled:opacity-40"
          >
            <Square className="h-3 w-3" />
          </button>
        )}
      </div>
      {state.subtasks.length > 0 && (
        <div data-testid="run-subtask-list" className="flex flex-col gap-0.5 pl-1">
          {state.subtasks.map((entry) => (
            <SubtaskRow key={entry.subtaskId} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}
