/**
 * Swarm run event handlers (P2-4 minimal wiring; P3-4 subtask detail rows).
 *
 * Pure reducer mapping `run:event` envelopes (`swarm.run.*` / `swarm.subtask.*`)
 * onto a per-run renderer state. Unknown or malformed envelopes are ignored
 * gracefully — the reducer never throws and never fabricates a status/count.
 *
 * Subtask detail rows are keyed by `subtaskId` (attempt-derived rows do not
 * duplicate a line). The distinct count (`subtaskTotal`) is taken from the
 * authoritative `run:status.subtaskSummary.total` only — events never sum
 * into the total. Missing data stays `undefined`/empty, never a fake 0.
 */

import type {
  RunEventEnvelope,
  RunStatus,
  RunStatusDto,
  RunSubtaskSnapshot,
  RunSubtaskSummary,
} from '../../../shared/types'

/** One deduplicated subtask row for the chip detail list. */
export interface RunSubtaskEntry {
  subtaskId: string
  status: string
  attempt: number
  capabilityId: string
}

/** Per-session mirror of the current run's lifecycle state. */
export interface RunState {
  runId: string
  /** Run lifecycle status; `null` until the first authoritative signal. */
  status: RunStatus | null
  sessionId?: string
  /** Deduplicated subtask detail rows, keyed by `subtaskId`. */
  subtasks: RunSubtaskEntry[]
  /** Distinct subtask count from `run:status` summary; `undefined` = unknown. */
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

/** Subtask status carried by a `swarm.subtask.*` event. */
const SUBTASK_EVENT_STATUS: Record<string, string> = {
  'swarm.subtask.registered': 'queued',
  'swarm.subtask.started': 'running',
  'swarm.subtask.succeeded': 'succeeded',
  'swarm.subtask.failed': 'failed',
  'swarm.subtask.timed_out': 'timed_out',
}

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

function payloadText(payload: Record<string, unknown>, key: string): string {
  const v = payload[key]
  return typeof v === 'string' && v.length > 0 ? v : ''
}

function payloadAttempt(payload: Record<string, unknown>): number {
  const v = payload.attempt
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : 1
}

/**
 * Upsert a subtask row, deduplicated by `subtaskId`. Later attempts win; the
 * first-seen row keeps its place in the list order.
 */
function upsertSubtask(rows: RunSubtaskEntry[], entry: RunSubtaskEntry): RunSubtaskEntry[] {
  const idx = rows.findIndex((r) => r.subtaskId === entry.subtaskId)
  if (idx < 0) return [...rows, entry]
  const next = rows.slice()
  const prev = next[idx]
  next[idx] = {
    subtaskId: entry.subtaskId,
    status: entry.status || prev.status,
    attempt: Math.max(prev.attempt, entry.attempt),
    capabilityId: entry.capabilityId || prev.capabilityId,
  }
  return next
}

/** Dedupe authoritative DTO rows by `subtaskId`; the highest attempt wins. */
function dedupeSubtasks(rows: RunSubtaskSnapshot[] | undefined): RunSubtaskEntry[] {
  if (!rows) return []
  const byId = new Map<string, RunSubtaskEntry>()
  for (const r of rows) {
    if (typeof r.subtaskId !== 'string' || !r.subtaskId) continue
    const attempt = typeof r.attempt === 'number' && r.attempt > 0 ? r.attempt : 1
    const capabilityId = typeof r.capabilityId === 'string' ? r.capabilityId : ''
    const status = typeof r.status === 'string' ? r.status : ''
    const existing = byId.get(r.subtaskId)
    if (!existing || attempt >= existing.attempt) {
      byId.set(r.subtaskId, { subtaskId: r.subtaskId, status, attempt, capabilityId })
    }
  }
  return [...byId.values()]
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
      subtasks: [],
      terminal: false,
      errorReason: null,
      updatedAt: ts,
    }
  }

  const base: RunState = prev ?? {
    runId: env.runId,
    status: null,
    subtasks: [],
    terminal: false,
    updatedAt: ts,
  }

  const subtaskStatus = SUBTASK_EVENT_STATUS[env.type]
  if (subtaskStatus) {
    const subtaskId = payloadText(payload, 'subtaskId') || (env.subtaskId ?? '')
    if (!subtaskId) return base
    const entry: RunSubtaskEntry = {
      subtaskId,
      status: subtaskStatus,
      attempt: payloadAttempt(payload),
      capabilityId: payloadText(payload, 'capabilityId'),
    }
    return {
      ...base,
      subtasks: upsertSubtask(base.subtasks, entry),
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
    subtasks: dedupeSubtasks(dto.subtasks),
    subtaskTotal: summary?.total,
    subtaskByStatus: summary?.byStatus,
    terminal: isTerminalRunStatus(dto.status),
    errorReason: dto.errorReason ?? null,
    updatedAt: dto.updatedAt,
  }
}
