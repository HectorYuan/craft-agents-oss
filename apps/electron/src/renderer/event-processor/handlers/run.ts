/**
 * Swarm run event handlers (P2-4 minimal wiring).
 *
 * Pure reducer mapping `run:event` envelopes (`swarm.run.*` / `swarm.subtask.*`)
 * onto a per-run renderer state. Unknown or malformed envelopes are ignored
 * gracefully — the reducer never throws and never fabricates a status/count.
 */

import type {
  RunEventEnvelope,
  RunStatus,
  RunStatusDto,
  RunSubtaskSummary,
} from '../../../shared/types'

/** Per-session mirror of the current run's lifecycle state. */
export interface RunState {
  runId: string
  /** Run lifecycle status; `null` until the first authoritative signal. */
  status: RunStatus | null
  sessionId?: string
  /** Subtask count from `run:status` summary, or observed registered events.
   *  `undefined` = unknown (rendered as a placeholder, never a fake 0). */
  subtaskTotal?: number
  subtaskByStatus?: Record<string, number>
  terminal: boolean
  errorReason?: string | null
  updatedAt?: number
}

const RUN_TERMINAL: ReadonlySet<string> = new Set([
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
])

export function isTerminalRunStatus(status: string | null | undefined): boolean {
  return status != null && RUN_TERMINAL.has(status)
}

/** Classify a swarm event type; `null` for anything outside the two known prefixes. */
export function classifyRunEventType(type: string): 'run' | 'subtask' | null {
  if (type.startsWith('swarm.run.')) return 'run'
  if (type.startsWith('swarm.subtask.')) return 'subtask'
  return null
}

/** Map a terminal `swarm.run.*` event to its status; non-terminal events return null. */
function terminalStatusOf(type: string): RunStatus | null {
  switch (type) {
    case 'swarm.run.succeeded':
      return 'succeeded'
    case 'swarm.run.failed':
      return 'failed'
    case 'swarm.run.cancelled':
      return 'cancelled'
    case 'swarm.run.timed_out':
      return 'timed_out'
    default:
      return null
  }
}

/**
 * Reduce the current run state with one envelope.
 *
 * Returns the previous state unchanged for unknown types, malformed envelopes,
 * or events that carry no lifecycle signal. A fresh `swarm.run.started` replaces
 * any previous run recorded for this session.
 */
export function reduceRunState(prev: RunState | null, env: RunEventEnvelope): RunState | null {
  if (!env || typeof env.runId !== 'string' || env.runId.length === 0) return prev
  if (classifyRunEventType(env.type) === null) return prev

  const ts = typeof env.ts === 'number' ? env.ts : Date.now()
  const payload = env.payload ?? {}

  if (env.type === 'swarm.run.started') {
    const sessionId = typeof payload.sessionId === 'string' && payload.sessionId.length > 0
      ? payload.sessionId
      : prev?.sessionId
    return {
      runId: env.runId,
      status: 'running',
      sessionId,
      terminal: false,
      errorReason: null,
      updatedAt: ts,
    }
  }

  const base: RunState = prev ?? {
    runId: env.runId,
    status: null,
    terminal: false,
    updatedAt: ts,
  }

  if (env.type === 'swarm.subtask.registered') {
    return {
      ...base,
      subtaskTotal: (base.subtaskTotal ?? 0) + 1,
      updatedAt: ts,
    }
  }

  const terminalStatus = terminalStatusOf(env.type)
  if (terminalStatus) {
    const errorReason = terminalStatus === 'failed'
      ? (typeof payload.reason === 'string' ? payload.reason : base.errorReason ?? null)
      : base.errorReason ?? null
    return {
      ...base,
      status: terminalStatus,
      terminal: true,
      errorReason,
      updatedAt: ts,
    }
  }

  // Known but non-terminal events (e.g. `swarm.run.interrupted`): keep state,
  // just bump the observed timestamp.
  return { ...base, updatedAt: ts }
}

/** Build renderer state from an authoritative `run:status` DTO. */
export function runStateFromStatusDto(dto: RunStatusDto): RunState {
  const summary: RunSubtaskSummary | undefined = dto.subtaskSummary
  return {
    runId: dto.runId,
    status: (dto.status as RunStatus) ?? null,
    sessionId: dto.sessionId ?? undefined,
    subtaskTotal: summary?.total,
    subtaskByStatus: summary?.byStatus,
    terminal: isTerminalRunStatus(dto.status),
    errorReason: dto.errorReason ?? null,
    updatedAt: dto.updatedAt,
  }
}
