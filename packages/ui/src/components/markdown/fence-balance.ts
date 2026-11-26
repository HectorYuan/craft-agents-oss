/**
 * Streaming fence-balance tolerance (display-only).
 *
 * During streaming a code fence may arrive before its closing line. A
 * half-closed fence makes CommonMark treat every later paragraph as code
 * content, which can leave the UI hanging on an open code block.
 *
 * This module detects an unclosed fence and produces a *render-only* copy
 * with a synthetic closing fence appended so the block visually completes.
 * The original message text — and anything persisted — is never mutated.
 * When the real closing fence arrives, the source becomes balanced again and
 * the helper returns the original string unchanged, re-rendering from source.
 *
 * Semantics note: input that leaves a fence open through the end of the
 * message violates CommonMark: per the standard, everything after the
 * opener belongs to the code block. We deliberately do **not** perform
 * line-level guessing to pull later paragraphs out of the block (that would
 * misclassify legitimate code). The tolerance only closes the visual block.
 */

/** Fence line: up to 3 spaces indent, then 3+ backticks or tildes. */
const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})/

type FenceChar = '`' | '~'

interface FenceScan {
  /** Number of fence toggles (open + close) recognized. */
  fenceCount: number
  /** Marker char of the open fence, or null when the content is balanced. */
  openChar: FenceChar | null
  /** Length of the open fence marker (CommonMark: closer ≥ opener length). */
  openLen: number
}

function scanFenceLines(content: string): FenceScan {
  let openChar: FenceChar | null = null
  let openLen = 0
  let fenceCount = 0

  for (const raw of content.split('\n')) {
    const match = FENCE_LINE.exec(raw)
    if (!match) continue
    const marker: string = match[1] ?? ''
    const ch = marker.charAt(0) as FenceChar

    if (openChar === null) {
      openChar = ch
      openLen = marker.length
      fenceCount += 1
    } else if (ch === openChar) {
      // A matching fence closes the current block.
      openChar = null
      openLen = 0
      fenceCount += 1
    }
    // A different marker while inside a fence is plain code content, ignored.
  }

  return { fenceCount, openChar, openLen }
}

/**
 * Count recognized code-fence lines (openers and closers) in the content.
 */
export function countFenceLines(content: string): number {
  return scanFenceLines(content).fenceCount
}

/**
 * Whether the content's fences are balanced (every opener has a closer).
 */
export function isFenceBalanced(content: string): boolean {
  return scanFenceLines(content).openChar === null
}

/**
 * Return a render-only copy of the content with a synthetic closing fence
 * appended when an opener is still unmatched.
 *
 * - Balanced content: the original string reference is returned unchanged.
 * - Unbalanced content: a closing fence matching the opener's marker is
 *   appended; the input string itself is not mutated.
 *
 * Never pass persisted message content through this function as a write-back;
 * it exists solely for display.
 */
export function withBalancedFence(content: string): string {
  const { openChar, openLen } = scanFenceLines(content)
  if (openChar === null) return content

  const closing = openChar.repeat(openLen)
  const prefix = content.endsWith('\n') ? '' : '\n'
  return `${content}${prefix}${closing}\n`
}
