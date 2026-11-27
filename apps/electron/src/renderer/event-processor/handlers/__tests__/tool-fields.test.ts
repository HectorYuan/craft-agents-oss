/**
 * O1-1：tool_start 起始时刻 / tool_result 完成耗时字段落消息，以及旧事件缺字段回退。
 *
 * 经公共 processEvent 派发，保证事件到消息的接线不会只停留在 handler 层。
 */

import { describe, expect, it } from 'bun:test'
import { processEvent } from '../../processor'
import type { AgentEvent, SessionState } from '../../types'

const SESSION_ID = 'session-1'

function makeState(messages: unknown[] = []): SessionState {
  return {
    session: { id: SESSION_ID, messages, lastMessageAt: 1, isProcessing: true },
    streaming: null,
  } as unknown as SessionState
}

function apply(state: SessionState, event: AgentEvent): SessionState {
  return processEvent(state, event).state
}

describe('O1-1 tool 起始/耗时字段', () => {
  it('tool_start 携带 startedAt', () => {
    const state = apply(makeState(), {
      type: 'tool_start',
      sessionId: SESSION_ID,
      toolUseId: 't1',
      toolName: 'read',
      toolInput: { path: 'a.txt' },
      startedAt: 1_700_000_001_000,
      timestamp: 1_700_000_001_000,
    } as AgentEvent)
    const msg = state.session.messages.find(m => m.toolUseId === 't1')
    expect(msg?.startedAt).toBe(1_700_000_001_000)
  })

  it('tool_result 携带 durationMs', () => {
    let state = apply(makeState(), {
      type: 'tool_start',
      sessionId: SESSION_ID,
      toolUseId: 't1',
      toolName: 'read',
      toolInput: { path: 'a.txt' },
      timestamp: 1_700_000_001_000,
    } as AgentEvent)
    state = apply(state, {
      type: 'tool_result',
      sessionId: SESSION_ID,
      toolUseId: 't1',
      result: 'ok',
      durationMs: 2_500,
      timestamp: 1_700_000_003_500,
    } as AgentEvent)
    const msg = state.session.messages.find(m => m.toolUseId === 't1')
    expect(msg?.durationMs).toBe(2_500)
  })

  it('旧事件缺字段：消息对应字段为 undefined，不抛错、不造耗时', () => {
    let state = apply(makeState(), {
      type: 'tool_start',
      sessionId: SESSION_ID,
      toolUseId: 't1',
      toolName: 'read',
      timestamp: 1_700_000_001_000,
    } as AgentEvent)
    state = apply(state, {
      type: 'tool_result',
      sessionId: SESSION_ID,
      toolUseId: 't1',
      result: 'ok',
      timestamp: 1_700_000_003_500,
    } as AgentEvent)
    const msg = state.session.messages.find(m => m.toolUseId === 't1')
    expect(msg?.startedAt).toBeUndefined()
    expect(msg?.durationMs).toBeUndefined()
  })
})
