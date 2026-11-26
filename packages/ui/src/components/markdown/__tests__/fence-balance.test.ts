/**
 * Tests for fence-balance.ts — display-only streaming fence tolerance.
 */

import { describe, it, expect } from 'bun:test'
import { countFenceLines, isFenceBalanced, withBalancedFence } from '../fence-balance'

describe('countFenceLines / isFenceBalanced', () => {
  it('treats plain text as balanced with no fences', () => {
    expect(countFenceLines('Hello world\n\n- item')).toBe(0)
    expect(isFenceBalanced('Hello world')).toBe(true)
  })

  it('balances a complete backtick fence with a language tag', () => {
    const md = ['```ts', 'const x = 1', '```'].join('\n')
    expect(countFenceLines(md)).toBe(2)
    expect(isFenceBalanced(md)).toBe(true)
  })

  it('detects an unclosed backtick fence', () => {
    const md = ['```text', 'body line one', 'second paragraph'].join('\n')
    expect(countFenceLines(md)).toBe(1)
    expect(isFenceBalanced(md)).toBe(false)
  })

  it('detects an unclosed tilde fence', () => {
    const md = ['~~~', 'tilde code body'].join('\n')
    expect(countFenceLines(md)).toBe(1)
    expect(isFenceBalanced(md)).toBe(false)
  })

  it('balances two consecutive complete blocks', () => {
    const md = ['```js', 'a', '```', '', '```py', 'b', '```'].join('\n')
    expect(countFenceLines(md)).toBe(4)
    expect(isFenceBalanced(md)).toBe(true)
  })

  it('detects an unmatched opener after a complete block', () => {
    const md = ['```js', 'a', '```', '', '```ts', 'open body'].join('\n')
    expect(countFenceLines(md)).toBe(3)
    expect(isFenceBalanced(md)).toBe(false)
  })

  it('recognizes an opener with up to 3 leading spaces', () => {
    const md = ['   ```text', 'indented opener body'].join('\n')
    expect(countFenceLines(md)).toBe(1)
    expect(isFenceBalanced(md)).toBe(false)
  })

  it('does not treat a 4-space-indented fence as a fence', () => {
    const md = ['    ```text', 'content'].join('\n')
    expect(countFenceLines(md)).toBe(0)
    expect(isFenceBalanced(md)).toBe(true)
  })

  it('ignores a different marker inside an open fence', () => {
    // Backticks opened; a tilde line inside is code content, not a toggle.
    const md = ['```', '~~~ this is code content', 'still inside'].join('\n')
    expect(countFenceLines(md)).toBe(1)
    expect(isFenceBalanced(md)).toBe(false)
  })

  it('closes a backtick opener from a matching backtick closer only', () => {
    const md = ['```', 'body', '~~~'].join('\n')
    expect(countFenceLines(md)).toBe(1)
    expect(isFenceBalanced(md)).toBe(false)
  })
})

describe('withBalancedFence', () => {
  it('returns the original reference for balanced content', () => {
    const md = ['```ts', 'x', '```'].join('\n')
    expect(withBalancedFence(md)).toBe(md)
    expect(isFenceBalanced(md)).toBe(true)
  })

  it('appends a matching backtick closing fence to an unclosed block', () => {
    const md = ['```text', 'body'].join('\n')
    const out = withBalancedFence(md)
    expect(out).toBe(md + '\n```\n')
    expect(isFenceBalanced(out)).toBe(true)
    // Source is not mutated.
    expect(md).toBe(['```text', 'body'].join('\n'))
  })

  it('appends a tilde closing fence for a tilde opener', () => {
    const md = ['~~~', 'body'].join('\n')
    expect(withBalancedFence(md)).toBe(md + '\n~~~\n')
  })

  it('matches the opener marker length for a long fence', () => {
    // CommonMark: closer must be at least as long as the opener.
    const md = ['`````', 'body'].join('\n')
    expect(withBalancedFence(md)).toBe(md + '\n`````\n')
  })

  it('does not double the newline when the source already ends with one', () => {
    const md = '```text\nbody\n'
    expect(withBalancedFence(md)).toBe('```text\nbody\n```\n')
  })

  it('renders correctly once the real closer arrives (balanced round-trip)', () => {
    const streaming = ['```ts', 'const x = 1'].join('\n')
    const patched = withBalancedFence(streaming)
    expect(isFenceBalanced(patched)).toBe(true)

    const settled = ['```ts', 'const x = 1', '```'].join('\n')
    // Balanced source: helper returns it unchanged, re-rendering from source.
    expect(withBalancedFence(settled)).toBe(settled)
    expect(isFenceBalanced(settled)).toBe(true)
  })
})
