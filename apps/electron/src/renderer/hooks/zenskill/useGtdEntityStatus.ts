/**
 * useGtdEntityStatus — live status for a GTD entity rendered inside a chat
 * GtdToolResultCard. The card itself is an immutable snapshot of the tool
 * result; this hook layers the current backend state on top so badges and
 * inline actions stay truthful as the entity changes elsewhere (GTD page,
 * agent, other cards).
 *
 * Dispatch by entityType (Day 1 interaction deepening):
 * - `action`   -> `action_status` batch read tool (one cheap call per refresh);
 *   an id reported in `missing` is "deleted" (the backend physically removes
 *   actions on delete).
 * - `inbox`    -> `gtd_inbox_list` (limit 100) filtered by id → item status.
 * - `calendar` -> `calendar_list` (scope week) filtered by event id → a found
 *   event is reported as "scheduled" (calendar events carry no status field).
 * - `project`  -> `project_list` (active) filtered by id → item status.
 *
 * Every type is its own query instance, so one family failing to resolve
 * (error/empty payload) never affects the others — a failed query leaves the
 * card on its immutable snapshot instead of claiming a bogus state.
 * Absence from a list response is NOT treated as deletion for inbox/calendar/
 * project: the lists are filtered/truncated server-side, so absence is
 * inconclusive and the hook stays idle.
 *
 * entityId may be undefined (legacy cards created before ids were carried
 * in tool results) — the hook then stays idle and returns null data.
 */
import { useMcpTool } from './useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '@/components/zenskill/zenskill-registry'

export type GtdEntityType = 'action' | 'inbox' | 'calendar' | 'project'

export interface GtdEntityStatusResult {
  status: string | undefined
  data: GtdEntityData | null
  loading: boolean
}

export interface GtdEntityData {
  id: string
  status: string
  title?: string
}

interface ActionStatusPayload {
  count?: number
  items?: GtdEntityData[]
  missing?: string[]
}

interface ListPayload {
  items?: Record<string, unknown>[]
}

const IDLE: GtdEntityStatusResult = { status: undefined, data: null, loading: false }

/** Calendar events have no status field — presence in a list means scheduled */
const CALENDAR_FOUND_STATUS = 'scheduled'

/** Defensive field readers for the list-tool payloads (contracts pending) */
function itemStr(item: Record<string, unknown> | undefined, key: string): string {
  const v = item?.[key]
  return typeof v === 'string' ? v : ''
}

function findInList(payload: ListPayload | null, entityId: string): Record<string, unknown> | undefined {
  return payload?.items?.find((i) => i && typeof i === 'object' && itemStr(i, 'id') === entityId)
}

export function useGtdEntityStatus(
  workspaceId: string | undefined,
  entityType: GtdEntityType,
  entityId: string | undefined,
): GtdEntityStatusResult {
  // Hook order must stay unconditional — disable via a falsy workspaceId,
  // which useMcpTool already treats as "idle, no fetch". Each entityType is
  // exactly one of the four queries; the other three stay parked.
  const active = Boolean(workspaceId) && Boolean(entityId)
  const ws = active ? workspaceId : undefined

  const actionRes = useMcpTool<ActionStatusPayload>(
    entityType === 'action' ? ws : undefined,
    ZENSKILL_SOURCE_SLUG,
    'action_status',
    { ids: entityId ? [entityId] : [] },
  )
  const inboxRes = useMcpTool<ListPayload>(
    entityType === 'inbox' ? ws : undefined,
    ZENSKILL_SOURCE_SLUG,
    'gtd_inbox_list',
    { limit: 100 },
  )
  const calendarRes = useMcpTool<ListPayload>(
    entityType === 'calendar' ? ws : undefined,
    ZENSKILL_SOURCE_SLUG,
    'calendar_list',
    { scope: 'week' },
  )
  const projectRes = useMcpTool<ListPayload>(
    entityType === 'project' ? ws : undefined,
    ZENSKILL_SOURCE_SLUG,
    'project_list',
    { status: 'active' },
  )

  if (!active || entityId === undefined) return IDLE

  if (entityType === 'action') {
    const payload = actionRes.data
    if (!payload) return IDLE
    const item = payload.items?.find((i) => i && i.id === entityId)
    if (item) return { status: item.status, data: item, loading: actionRes.loading }
    // Successful response without the id — entity was physically deleted.
    // Only trust this when the fetch settled and the backend did not error.
    const vanished = !actionRes.loading && !actionRes.error && Array.isArray(payload.missing) && payload.missing.includes(entityId)
    if (vanished) return { status: 'deleted', data: null, loading: false }
    return IDLE
  }

  const res = entityType === 'inbox' ? inboxRes : entityType === 'calendar' ? calendarRes : projectRes
  const item = findInList(res.data, entityId)
  if (!item) return IDLE
  const status = entityType === 'calendar' ? CALENDAR_FOUND_STATUS : itemStr(item, 'status')
  const title = itemStr(item, 'title') || itemStr(item, 'name') || itemStr(item, 'text') || itemStr(item, 'raw_text')
  return { status: status || undefined, data: { id: entityId, status, title: title || undefined }, loading: res.loading }
}
