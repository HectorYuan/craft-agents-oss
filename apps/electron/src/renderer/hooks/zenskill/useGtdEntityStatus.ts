/**
 * useGtdEntityStatus — live status for a GTD entity rendered inside a chat
 * GtdToolResultCard. The card itself is an immutable snapshot of the tool
 * result; this hook layers the current backend state on top so badges and
 * inline actions stay truthful as the entity changes elsewhere (GTD page,
 * agent, other cards).
 *
 * Mechanics: queries `action_status` (batch read tool, one cheap call per
 * refresh) via useMcpTool — which already subscribes to zenskill:changed
 * and coalesces bursts with a 200ms debounce — then picks the requested id
 * out of the payload. An id that is absent from a successful response is
 * reported as "deleted": the backend physically removes actions on delete,
 * so a once-created id that no longer resolves is treated as gone.
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

const IDLE: GtdEntityStatusResult = { status: undefined, data: null, loading: false }

export function useGtdEntityStatus(
  workspaceId: string | undefined,
  entityType: GtdEntityType,
  entityId: string | undefined,
): GtdEntityStatusResult {
  // Hook order must stay unconditional — disable via a falsy workspaceId,
  // which useMcpTool already treats as "idle, no fetch".
  const enabled = Boolean(workspaceId) && Boolean(entityId) && entityType === 'action'
  const res = useMcpTool<ActionStatusPayload>(
    enabled ? workspaceId : undefined,
    ZENSKILL_SOURCE_SLUG,
    'action_status',
    { ids: entityId ? [entityId] : [] },
  )

  if (!enabled || !res.data || entityId === undefined) return IDLE
  const payload = res.data
  const item = payload.items?.find((i) => i && i.id === entityId)
  if (item) return { status: item.status, data: item, loading: res.loading }
  // Successful response without the id — entity was physically deleted.
  // Only trust this when the fetch settled and the backend did not error.
  const vanished = !res.loading && !res.error && Array.isArray(payload.missing) && payload.missing.includes(entityId)
  if (vanished) return { status: 'deleted', data: null, loading: false }
  return IDLE
}
