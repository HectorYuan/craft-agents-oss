import { describe, expect, it } from 'bun:test'
import { processEvent } from '../../processor'
import { handleApprovalRequested } from '../session'
import { pushPermissionRequest } from '../../helpers'
import type { AgentEvent, SessionState } from '../../types'

const SESSION_ID = 'session-1'

function makeState(messages: any[] = []): SessionState {
  return {
    session: {
      id: SESSION_ID,
      messages,
      lastMessageAt: 1,
      isProcessing: true,
    } as any,
    streaming: null,
  }
}

function approvalEvent(overrides: Record<string, unknown> = {}): AgentEvent {
  return {
    type: 'approval.requested',
    sessionId: SESSION_ID,
    request: {
      requestId: 'apv-abc12345',
      capId: 'approval',
      toolName: 'write_file',
      argsPreview: '{"path": "/tmp/p5-allow-marker", "content": "p5 allow marker\\n"}',
      timeoutMs: 300000,
      runId: 'run-4fb120335c64',
      subtaskId: '',
      depth: 0,
      ...overrides,
    },
  } as AgentEvent
}

describe('approval.requested mapping (P5-1)', () => {
  it('routes through the processor into a legacy permission_request effect', () => {
    const result = processEvent(makeState(), approvalEvent())

    expect(result.effects).toHaveLength(1)
    expect(result.effects[0].type).toBe('permission_request')
  })

  it('normalizes bridge fields onto the PermissionRequest shape', () => {
    const result = handleApprovalRequested(makeState(), approvalEvent() as any)
    const request = result.effects[0] as { type: 'permission_request'; request: any }

    expect(request.request.requestId).toBe('apv-abc12345')
    expect(request.request.toolName).toBe('write_file')
    // argsPreview fills both description and the command preview block
    expect(request.request.description).toBe(
      '{"path": "/tmp/p5-allow-marker", "content": "p5 allow marker\\n"}',
    )
    expect(request.request.command).toBe(
      '{"path": "/tmp/p5-allow-marker", "content": "p5 allow marker\\n"}',
    )
    // timeoutMs 300000 -> 300s TTL
    expect(request.request.approvalTtlSeconds).toBe(300)
    // bridge traceability fields preserved for audit/reply correlation
    expect(request.request.timeoutMs).toBe(300000)
    expect(request.request.runId).toBe('run-4fb120335c64')
    expect(request.request.subtaskId).toBe('')
    expect(request.request.depth).toBe(0)
    expect(request.request.capId).toBe('approval')
  })

  it('falls back to a tool-name description when argsPreview is absent', () => {
    const result = handleApprovalRequested(
      makeState(),
      approvalEvent({ argsPreview: undefined }) as any,
    )
    const request = result.effects[0] as { type: 'permission_request'; request: any }

    expect(request.request.description).toBe('write_file requires approval')
    expect(request.request.command).toBeUndefined()
    expect(request.request.approvalTtlSeconds).toBe(300)
  })

  it('clamps a non-positive timeout to a zero TTL', () => {
    const result = handleApprovalRequested(
      makeState(),
      approvalEvent({ timeoutMs: 0 }) as any,
    )
    const request = result.effects[0] as { type: 'permission_request'; request: any }

    expect(request.request.approvalTtlSeconds).toBe(0)
  })

  it('leaves session state untouched (effect-only mapping)', () => {
    const state = makeState([{ id: 'u1', role: 'user', content: 'hi', timestamp: 1 }])
    const result = processEvent(state, approvalEvent())

    expect(result.state.session.messages).toHaveLength(1)
    expect(result.state.session.messages[0].id).toBe('u1')
  })
})

describe('pushPermissionRequest idempotency', () => {
  it('appends a request with a new requestId', () => {
    const queue: any[] = [{ requestId: 'perm-0001', toolName: 'bash' }]
    const next = pushPermissionRequest(queue, { requestId: 'apv-0002', toolName: 'write_file' } as any)

    expect(next).toHaveLength(2)
    expect(next[1].requestId).toBe('apv-0002')
  })

  it('returns the original queue reference when requestId is already present', () => {
    const existing = { requestId: 'apv-0002', toolName: 'write_file' } as any
    const queue: any[] = [{ requestId: 'perm-0001', toolName: 'bash' }, existing]
    const next = pushPermissionRequest(queue, existing)

    expect(next).toBe(queue)
    expect(next).toHaveLength(2)
  })

  it('deduplicates a bridge replay against an already-queued legacy request', () => {
    const queue: any[] = [{ requestId: 'apv-abc12345', toolName: 'write_file' }]
    const replay = {
      requestId: 'apv-abc12345',
      toolName: 'write_file',
      description: 'replayed duplicate',
    } as any
    const next = pushPermissionRequest(queue, replay)

    expect(next).toBe(queue)
    expect(next).toHaveLength(1)
  })
})
