/**
 * RunStatusChip — compact status chip for the current swarm run (P2-4).
 *
 * Lives inside the existing chat input badge row; no new page or route.
 * Self-gates on channel availability and per-session atom state:
 * - channel absent / feature disabled on the server → renders nothing
 * - no observed run → renders nothing
 * - subtask count unknown → placeholder `—` (never a fabricated 0)
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
} from '@/event-processor/handlers/run'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface RunStatusChipProps {
  sessionId: string
}

const STATUS_LABEL_KEYS: Record<string, string> = {
  queued: 'chat.runStatusQueued',
  running: 'chat.runStatusRunning',
  succeeded: 'chat.runStatusSucceeded',
  failed: 'chat.runStatusFailed',
  cancelled: 'chat.runStatusCancelled',
  timed_out: 'chat.runStatusTimedOut',
}

function StatusIcon({ status }: { status: RunState['status'] }) {
  switch (status) {
    case 'succeeded':
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-600 dark:text-green-500" />
    case 'failed':
      return <XCircle className="h-3.5 w-3.5 text-destructive" />
    case 'cancelled':
      return <Square className="h-3 w-3 opacity-60" />
    case 'timed_out':
      return <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-500" />
    default:
      return <Spinner className="text-xs" />
  }
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
        'h-[30px] pl-2.5 pr-2 text-xs font-medium rounded-[8px]',
        'flex items-center gap-1.5 shrink-0 select-none',
        'transition-all shadow-minimal bg-white dark:bg-white/10',
      )}
    >
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
  )
}
