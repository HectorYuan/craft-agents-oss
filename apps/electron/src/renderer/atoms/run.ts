/**
 * Per-session swarm run state (P2-4 minimal wiring).
 *
 * The atom family mirrors the background-tasks pattern: one entry per session,
 * holding the current run's reducer state. A module-level runId → sessionId
 * index maps later events back to their session (envelopes after `started`
 * carry only `runId`/`subtaskId`).
 */

import { atom } from 'jotai'
import { atomFamily } from 'jotai-family'
import type { RunState } from '../event-processor/handlers/run'

/** Current run state for a session; `null` = no observed run (idle or channel disabled). */
export const runStateAtomFamily = atomFamily(
  (_sessionId: string) => atom<RunState | null>(null),
  (a, b) => a === b,
)

const runSessionIndex = new Map<string, string>()
const sessionRunIndex = new Map<string, string>()

export function recordRunSession(runId: string, sessionId: string): void {
  if (!runId || !sessionId) return
  runSessionIndex.set(runId, sessionId)
  sessionRunIndex.set(sessionId, runId)
}

export function sessionForRun(runId: string): string | undefined {
  return runSessionIndex.get(runId)
}

export function runIdForSession(sessionId: string): string | undefined {
  return sessionRunIndex.get(sessionId)
}
