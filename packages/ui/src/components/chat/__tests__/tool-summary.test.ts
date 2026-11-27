/**
 * Tests for collapsed-header tool summary (P0-A).
 *
 * The collapsed TurnCard header shows `N 步骤 · 工具名摘要`:
 * - ≤3 tools: list all; >3: first 3 + "等 N 个" suffix (composed in TurnCard).
 * - Each entry = tool name + first path/command-class input fragment (≤40 chars).
 * - Mixed success+failure turn: failure tone wins (allFailed === true).
 * - Missing input: name only, no fabricated hint.
 */

import { describe, it, expect } from 'bun:test'
import {
  summarizeToolActivities,
  summarizeToolInput,
  type ToolSummaryEntry,
} from '../turn-utils'
import type { ActivityItem } from '../TurnCard'

let counter = 0

function makeTool(overrides: Partial<ActivityItem> = {}): ActivityItem {
  counter += 1
  return {
    id: `act-${counter}`,
    type: 'tool',
    status: 'completed',
    toolName: 'read',
    toolInput: { path: 'a_write.txt' },
    timestamp: Date.now(),
    ...overrides,
  }
}

describe('summarizeToolActivities', () => {
  it('single completed tool: one entry, completed tone, input hint present', () => {
    const turn = summarizeToolActivities([makeTool()])
    expect(turn.totalTools).toBe(1)
    expect(turn.hasFailure).toBe(false)
    expect(turn.entries).toEqual<ToolSummaryEntry[]>([
      { toolName: 'read', inputHint: 'a_write.txt' },
    ])
  })

  it('single failed tool: failure tone, error input hint present', () => {
    const turn = summarizeToolActivities([
      makeTool({
        status: 'error',
        toolInput: { path: 'a_missing.txt' },
        error: 'File not found',
      }),
    ])
    expect(turn.totalTools).toBe(1)
    expect(turn.hasFailure).toBe(true)
    expect(turn.entries[0].inputHint).toBe('a_missing.txt')
  })

  it('mixed success + failure: failure tone wins (allFailed true)', () => {
    const turn = summarizeToolActivities([
      makeTool({ id: 'ok', toolName: 'read', toolInput: { path: 'ok.txt' } }),
      makeTool({
        id: 'bad',
        status: 'error',
        toolName: 'read',
        toolInput: { path: 'bad.txt' },
        error: 'File not found',
      }),
    ])
    expect(turn.totalTools).toBe(2)
    expect(turn.hasFailure).toBe(true)
  })

  it('more than 3 tools: entries capped at 3, totalTools keeps full count', () => {
    const tools = Array.from({ length: 5 }, (_, i) =>
      makeTool({ id: `t-${i}`, toolInput: { path: `file-${i}.txt` } }),
    )
    const turn = summarizeToolActivities(tools)
    expect(turn.totalTools).toBe(5)
    expect(turn.entries).toHaveLength(3)
    expect(turn.entries.map(e => e.inputHint)).toEqual([
      'file-0.txt',
      'file-1.txt',
      'file-2.txt',
    ])
  })

  it('plan/intermediate activities are excluded from the tool summary', () => {
    const turn = summarizeToolActivities([
      makeTool({ type: 'plan', toolName: 'TodoWrite', toolInput: undefined }),
      makeTool({ type: 'intermediate', content: 'thinking', toolInput: undefined }),
      makeTool({ toolName: 'read', toolInput: { path: 'a_write.txt' } }),
    ])
    expect(turn.totalTools).toBe(1)
    expect(turn.entries).toHaveLength(1)
  })

  it('no tool input: entry keeps tool name with empty hint (no fabrication)', () => {
    const turn = summarizeToolActivities([
      makeTool({ toolName: 'list_dir', toolInput: undefined }),
    ])
    expect(turn.entries[0]).toEqual({ toolName: 'list_dir', inputHint: '' })
  })
})

describe('summarizeToolInput', () => {
  it('prefers path-class fields over arbitrary string values', () => {
    expect(summarizeToolInput({ file_path: 'src/index.ts', note: 'hello' })).toBe('src/index.ts')
    expect(summarizeToolInput({ command: 'git status', cwd: '/repo' })).toBe('git status')
  })

  it('falls back to the first string-valued field', () => {
    expect(summarizeToolInput({ pattern: '*.md' })).toBe('*.md')
    expect(summarizeToolInput({ skill: 'commit' })).toBe('commit')
  })

  it('truncates hints longer than 40 characters', () => {
    const longPath = '/repo/src/' + 'x'.repeat(60)
    const hint = summarizeToolInput({ path: longPath })
    expect(hint.length).toBeLessThanOrEqual(40)
  })

  it('returns empty string for undefined or non-string input', () => {
    expect(summarizeToolInput(undefined)).toBe('')
    expect(summarizeToolInput({ a: 1, b: true })).toBe('')
  })
})
