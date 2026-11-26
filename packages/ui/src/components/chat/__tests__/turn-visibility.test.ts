/**
 * Visibility predicate tests for completed turns.
 *
 * Upstream hides a turn whose activities are all errors / empty intermediates
 * and which has no response text. Our fork narrows that: only turns whose
 * errors are user-interrupted ('Interrupted' marker) stay hidden; a real tool
 * failure must remain visible in history so the error result is reachable.
 */

import { describe, it, expect } from 'bun:test'
import { shouldHideInterruptedOnlyTurn, type AssistantTurn } from '../turn-utils'

function makeTurn(overrides: Partial<AssistantTurn>): AssistantTurn {
  return {
    type: 'assistant',
    turnId: 'test-turn',
    activities: [],
    isStreaming: false,
    isComplete: true,
    timestamp: Date.now(),
    ...overrides,
  }
}

function toolActivity(
  status: 'completed' | 'error' | 'running',
  error?: string,
  toolName = 'read'
): AssistantTurn['activities'][number] {
  return {
    id: `act-${toolName}-${status}-${error ?? 'ok'}`,
    type: 'tool',
    status,
    toolName,
    timestamp: Date.now(),
    error,
  }
}

describe('shouldHideInterruptedOnlyTurn', () => {
  it('keeps a real tool failure visible in history (not hidden)', () => {
    const turn = makeTurn({
      activities: [toolActivity('error', '错误：文件 a_missing.txt 不存在：cs coldstart error marker')],
    })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(false)
  })

  it('still hides a turn interrupted by the user (running activities marked Interrupted)', () => {
    const turn = makeTurn({
      activities: [toolActivity('error', 'Interrupted')],
    })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(true)
  })

  it('keeps the turn visible when a real failure is mixed with an interruption', () => {
    const turn = makeTurn({
      activities: [
        toolActivity('error', 'Interrupted'),
        toolActivity('error', 'File not found: a_missing.txt'),
      ],
    })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(false)
  })

  it('keeps a completed tool turn visible (baseline unchanged)', () => {
    const turn = makeTurn({
      activities: [toolActivity('completed')],
    })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(false)
  })

  it('does not hide on its own for an empty-activities turn (handled by the empty gate)', () => {
    const turn = makeTurn({ activities: [] })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(false)
  })

  it('keeps a turn with response text visible even when tools errored', () => {
    const turn = makeTurn({
      activities: [toolActivity('error', 'File not found: a_missing.txt')],
      response: { text: '助手已尝试读取文件，返回错误结果。', isStreaming: false },
    })
    expect(shouldHideInterruptedOnlyTurn(turn)).toBe(false)
  })
})
