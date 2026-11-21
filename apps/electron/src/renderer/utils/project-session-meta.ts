/**
 * Project ↔ session aggregation helpers (D4.2.1 · F02 / F03 / F05)
 *
 * Pure functions over `sessionMetaMapAtom` entries so the same口径 can be
 * unit-tested and reused by the project list, the project detail Overview and
 * the session list:
 *
 * - A session counts for a project only when `meta.projectId` matches the
 *   project's `config.id` exactly and the session is not archived.
 * - "最近活跃" uses `lastMessageAt`, falling back to `updatedAt` when the
 *   former is absent. Missing timestamps are skipped — never treated as 0.
 * - A stale binding (project deleted, or blank/whitespace-only projectId)
 *   resolves to "no project": no stripe, no chip, the existing no-project bucket.
 */
import type { SessionMeta } from '../atoms/sessions'

/** Project option shape consumed by the session list and its project submenu. */
export interface ProjectBindingOption {
  id: string
  slug?: string
  name: string
  color?: string
}

/** Active timestamp for ordering / recency: `lastMessageAt`, fallback `updatedAt`. */
export function sessionActiveAt(meta: SessionMeta): number | undefined {
  const fallback = (meta as { updatedAt?: number }).updatedAt
  return meta.lastMessageAt ?? fallback
}

/**
 * Sessions bound to one project, excluding archived ones.
 * Returns an empty array for an empty/unknown project id.
 */
export function sessionsForProject(
  metaMap: Map<string, SessionMeta>,
  projectId: string | undefined | null,
): SessionMeta[] {
  if (!projectId) return []
  const result: SessionMeta[] = []
  for (const meta of metaMap.values()) {
    if (meta.isArchived === true) continue
    if (meta.projectId !== projectId) continue
    result.push(meta)
  }
  return result
}

/**
 * Newest active timestamp across the given sessions.
 * `undefined` when the set is empty or none carries a timestamp (display `—`,
 * not a fabricated 0).
 */
export function maxActiveAt(metas: SessionMeta[]): number | undefined {
  let max: number | undefined
  for (const meta of metas) {
    const at = sessionActiveAt(meta)
    if (at === undefined) continue
    if (max === undefined || at > max) max = at
  }
  return max
}

/** Most recent sessions first, capped to `limit` (newest first by active time). */
export function recentProjectSessions(metas: SessionMeta[], limit: number): SessionMeta[] {
  if (limit <= 0) return []
  return metas
    .map((meta) => ({ meta, at: sessionActiveAt(meta) }))
    .sort((a, b) => (b.at ?? 0) - (a.at ?? 0))
    .slice(0, limit)
    .map((entry) => entry.meta)
}

/**
 * Resolve a session's bound project against the current project list.
 *
 * Matching is exact on `config.id` (`proj_{slug}` shape), per the D4.2.0
 * contract freeze. Unbound (missing / blank) and stale (deleted project)
 * bindings resolve to `undefined`; the row then keeps the existing
 * "no project" presentation — colorless stripe slot, no project name chip.
 */
export function resolveSessionProject(
  meta: SessionMeta,
  projects: ProjectBindingOption[] | undefined,
): ProjectBindingOption | undefined {
  const pid = meta.projectId?.trim()
  if (!pid) return undefined
  return projects?.find((p) => p.id === pid)
}

/** Unified no-data placeholder (U+2014). Missing keys never render as 0. */
export const METRIC_PLACEHOLDER = '—'

/**
 * Token total for the metric card: `tokenUsage.totalTokens`, falling back to
 * `inputTokens + outputTokens`. `undefined` when the whole block is absent or
 * neither field carries a number. Cost (`costUsd`) is deliberately excluded.
 */
export function tokenTotal(meta: SessionMeta): number | undefined {
  const usage = meta.tokenUsage
  if (!usage) return undefined
  if (typeof usage.totalTokens === 'number') return usage.totalTokens
  const hasInput = typeof usage.inputTokens === 'number'
  const hasOutput = typeof usage.outputTokens === 'number'
  if (!hasInput && !hasOutput) return undefined
  return (hasInput ? usage.inputTokens : 0) + (hasOutput ? usage.outputTokens : 0)
}

/** Message count for the card: a real 0 renders "0"; a missing key → placeholder. */
export function formatMessageCount(meta: SessionMeta): string {
  return meta.messageCount === undefined ? METRIC_PLACEHOLDER : String(meta.messageCount)
}

/** Token total, thousands-separated; placeholder when absent. */
export function formatTokenTotal(meta: SessionMeta): string {
  const total = tokenTotal(meta)
  if (total === undefined) return METRIC_PLACEHOLDER
  return total.toLocaleString('en-US')
}

/** Model id as provided; blank / whitespace / missing → placeholder. No display-name mapping. */
export function formatModel(meta: SessionMeta): string {
  const model = meta.model?.trim()
  return model ? model : METRIC_PLACEHOLDER
}

/**
 * Title prefill when converting a session to an action: the first user message
 * preview takes priority, falling back to the session name. Blank / whitespace
 * on both sides resolves to `''` — the dialog submit gate then blocks on the
 * title, mirroring the existing add-action form.
 */
export function actionTitleFromSession(meta: SessionMeta): string {
  const preview = meta.preview?.trim()
  if (preview) return preview
  const name = meta.name?.trim()
  return name ?? ''
}

/**
 * Source link resolution for an action card (F06).
 * - `none`: no `source_session_id` (missing / blank) → render no chip at all.
 * - `unlinked`: id present but the session is gone from the meta map → muted
 *   "未关联" chip, no navigation.
 * - `linked`: id present and the session exists → clickable chip, back-link to it.
 */
export type ActionSourceRef =
  | { state: 'none' }
  | { state: 'linked'; sessionId: string; name: string }
  | { state: 'unlinked'; sessionId: string }

export function resolveActionSource(
  sourceSessionId: string | undefined,
  metaMap: Map<string, SessionMeta>,
): ActionSourceRef {
  const sid = sourceSessionId?.trim()
  if (!sid) return { state: 'none' }
  const meta = metaMap.get(sid)
  if (!meta) return { state: 'unlinked', sessionId: sid }
  const name = meta.name?.trim() || meta.preview?.trim() || sid
  return { state: 'linked', sessionId: sid, name }
}
