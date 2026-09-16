/**
 * Tests for ZenskillAgent engine-session resume wiring (C1)
 *
 * The model's conversation context lives in the engine subprocess's own
 * session file (~/.zenskill/agent/sessions/{sid}.jsonl); the host
 * session.jsonl is UI-only. These tests cover the host-side capture logic:
 * - engine sessionId reported in RPC responses is captured and forwarded to
 *   the host via onSdkSessionIdUpdate (which persists header.sdkSessionId)
 * - duplicate reports are deduplicated
 * - a sid identical to the host-held value is not reported back
 *
 * Constructing the full subprocess is out of scope here (see
 * resumeEngineSession); we drive handleLine directly.
 */
import { describe, it, expect } from 'bun:test'
import { ZenskillAgent } from '../backend/zenskill-agent.ts'

function createAgent(sessionSdkSessionId?: string): {
  agent: ZenskillAgent
  updates: string[]
} {
  const updates: string[] = []
  const agent = new ZenskillAgent({
    workspace: { rootPath: '/tmp/zenskill-test-ws', name: 'test-ws' },
    skipConfigWatcher: true,
    session: { id: 'host-session-1', sdkSessionId: sessionSdkSessionId },
    onSdkSessionIdUpdate: (sid: string) => updates.push(sid),
  } as any)
  return { agent, updates }
}

function promptResponse(sessionId: string): string {
  return JSON.stringify({
    id: 'turn-1', type: 'response', command: 'prompt',
    success: true, data: { started: true, sessionId },
  })
}

describe('ZenskillAgent engine session capture', () => {
  it('captures sessionId from prompt response and reports it to the host', () => {
    const { agent, updates } = createAgent(undefined)
    ;(agent as any).handleLine(promptResponse('engine-abc'))
    expect(updates).toEqual(['engine-abc'])
  })

  it('deduplicates repeated reports of the same sid', () => {
    const { agent, updates } = createAgent(undefined)
    ;(agent as any).handleLine(promptResponse('engine-abc'))
    ;(agent as any).handleLine(promptResponse('engine-abc'))
    expect(updates).toEqual(['engine-abc'])
  })

  it('does not report a sid identical to the host-held sdkSessionId', () => {
    const { agent, updates } = createAgent('engine-persisted')
    ;(agent as any).handleLine(promptResponse('engine-persisted'))
    expect(updates).toEqual([])
  })

  it('ignores responses without a sessionId payload', () => {
    const { agent, updates } = createAgent(undefined)
    ;(agent as any).handleLine(JSON.stringify({
      id: 'r1', type: 'response', command: 'set_model', success: true,
    }))
    expect(updates).toEqual([])
  })
})
