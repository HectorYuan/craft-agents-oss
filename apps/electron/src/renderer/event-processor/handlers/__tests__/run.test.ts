import { describe, expect, it } from 'bun:test'
import {
  reduceRunState,
  runStateFromStatusDto,
  classifyRunEventType,
  isTerminalRunStatus,
} from '../run'
import type { RunEventEnvelope } from '../../../../shared/types'

function env(type: string, overrides: Partial<RunEventEnvelope> = {}): RunEventEnvelope {
  return {
    runId: 'run-1',
    seq: 1,
    ts: 1700000000000,
    type,
    payload: {},
    prevHash: '',
    subtaskId: '',
    depth: 0,
    ...overrides,
  }
}

describe('classifyRunEventType', () => {
  it('recognizes the two swarm prefixes', () => {
    expect(classifyRunEventType('swarm.run.started')).toBe('run')
    expect(classifyRunEventType('swarm.subtask.registered')).toBe('subtask')
  })

  it('returns null for unknown prefixes without throwing', () => {
    expect(classifyRunEventType('approval.approved')).toBeNull()
    expect(classifyRunEventType('cap.evaluate')).toBeNull()
    expect(classifyRunEventType('session:event')).toBeNull()
  })
})

describe('reduceRunState', () => {
  it('seeds a running state from swarm.run.started with the session id', () => {
    const next = reduceRunState(null, env('swarm.run.started', {
      payload: { sessionId: 'session-1', surface: 'chat' },
    }))

    expect(next).not.toBeNull()
    expect(next?.runId).toBe('run-1')
    expect(next?.status).toBe('running')
    expect(next?.sessionId).toBe('session-1')
    expect(next?.terminal).toBe(false)
    expect(next?.subtaskTotal).toBeUndefined()
  })

  it('replaces the previous run state when a new started event arrives', () => {
    const prev = reduceRunState(null, env('swarm.run.started', { runId: 'run-old', payload: { sessionId: 'session-1' } }))
    const next = reduceRunState(prev, env('swarm.run.started', { runId: 'run-new', payload: { sessionId: 'session-1' } }))

    expect(next?.runId).toBe('run-new')
    expect(next?.subtaskTotal).toBeUndefined()
  })

  it('counts registered subtasks, leaving the count undefined before the first observation', () => {
    const started = reduceRunState(null, env('swarm.run.started', { payload: { sessionId: 'session-1' } }))
    expect(started?.subtaskTotal).toBeUndefined()

    const afterFirst = reduceRunState(started, env('swarm.subtask.registered'))
    expect(afterFirst?.subtaskTotal).toBe(1)

    const afterSecond = reduceRunState(afterFirst, env('swarm.subtask.registered', { seq: 2 }))
    expect(afterSecond?.subtaskTotal).toBe(2)
  })

  it('maps terminal run events to their terminal status', () => {
    const started = reduceRunState(null, env('swarm.run.started', { payload: { sessionId: 'session-1' } }))

    const succeeded = reduceRunState(started, env('swarm.run.succeeded', { seq: 2 }))
    expect(succeeded?.status).toBe('succeeded')
    expect(succeeded?.terminal).toBe(true)

    const failed = reduceRunState(started, env('swarm.run.failed', { seq: 2, payload: { reason: 'boom' } }))
    expect(failed?.status).toBe('failed')
    expect(failed?.terminal).toBe(true)
    expect(failed?.errorReason).toBe('boom')

    const cancelled = reduceRunState(started, env('swarm.run.cancelled', { seq: 2 }))
    expect(cancelled?.status).toBe('cancelled')
    expect(cancelled?.terminal).toBe(true)

    const timedOut = reduceRunState(started, env('swarm.run.timed_out', { seq: 2 }))
    expect(timedOut?.status).toBe('timed_out')
    expect(timedOut?.terminal).toBe(true)
  })

  it('ignores unknown event types and returns the previous reference unchanged', () => {
    const prev = reduceRunState(null, env('swarm.run.started', { payload: { sessionId: 'session-1' } }))

    const approval = reduceRunState(prev, env('approval.approved', { seq: 2 }))
    expect(approval).toBe(prev)

    const cap = reduceRunState(prev, env('cap.evaluate', { seq: 3 }))
    expect(cap).toBe(prev)
  })

  it('ignores malformed envelopes without throwing', () => {
    const prev = reduceRunState(null, env('swarm.run.started', { payload: { sessionId: 'session-1' } }))
    expect(reduceRunState(prev, env('swarm.run.failed', { runId: '' }))).toBe(prev)
    expect(reduceRunState(prev, null as unknown as RunEventEnvelope)).toBe(prev)
  })

  it('keeps the status for a non-terminal interrupted event and bumps the timestamp', () => {
    const started = reduceRunState(null, env('swarm.run.started', { payload: { sessionId: 'session-1' }, ts: 1000 }))
    const interrupted = reduceRunState(started, env('swarm.run.interrupted', { seq: 2, ts: 2000 }))

    expect(interrupted?.status).toBe('running')
    expect(interrupted?.terminal).toBe(false)
    expect(interrupted?.updatedAt).toBe(2000)
  })
})

describe('runStateFromStatusDto', () => {
  it('carries the authoritative summary and derives the terminal flag', () => {
    const state = runStateFromStatusDto({
      runId: 'run-1',
      status: 'succeeded',
      sessionId: 'session-1',
      errorReason: null,
      subtaskSummary: { total: 3, byStatus: { succeeded: 3 } },
    })

    expect(state.runId).toBe('run-1')
    expect(state.status).toBe('succeeded')
    expect(state.terminal).toBe(true)
    expect(state.subtaskTotal).toBe(3)
    expect(state.subtaskByStatus).toEqual({ succeeded: 3 })
  })

  it('leaves the subtask count undefined when the summary is absent (placeholder, not 0)', () => {
    const state = runStateFromStatusDto({
      runId: 'run-1',
      status: 'running',
    })

    expect(state.subtaskTotal).toBeUndefined()
    expect(state.terminal).toBe(false)
  })
})

describe('isTerminalRunStatus', () => {
  it('recognizes the four terminal statuses', () => {
    expect(isTerminalRunStatus('succeeded')).toBe(true)
    expect(isTerminalRunStatus('failed')).toBe(true)
    expect(isTerminalRunStatus('cancelled')).toBe(true)
    expect(isTerminalRunStatus('timed_out')).toBe(true)
    expect(isTerminalRunStatus('running')).toBe(false)
    expect(isTerminalRunStatus('queued')).toBe(false)
    expect(isTerminalRunStatus(null)).toBe(false)
  })
})
