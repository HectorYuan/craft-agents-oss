/**
 * useZenSkillChanged — Subscribe to zenskill:changed broadcasts for a
 * specific MCP source slug. The callback is kept in a ref so the
 * subscription is not torn down and rebuilt on every render; cleanup
 * happens on unmount or when sourceSlug changes.
 *
 * The broadcast payload may carry the changed entity's id (`entity_id`,
 * attached by the Python ws_server for write-tool results — contract
 * pending). It is extracted defensively from both payload shapes and
 * forwarded to the callback; existing callbacks that ignore the argument
 * are unaffected.
 */
import { useEffect, useRef } from 'react'

export interface ZenSkillChangedInfo {
  /** Changed entity id from the broadcast payload, when present */
  entityId?: string
}

export function useZenSkillChanged(sourceSlug: string, onChanged: (info?: ZenSkillChangedInfo) => void): void {
  const cbRef = useRef(onChanged)
  cbRef.current = onChanged

  useEffect(() => {
    if (!window.electronAPI?.onZenSkillChanged) return
    const cleanup = window.electronAPI.onZenSkillChanged((_wsId, data) => {
      // Mode C args may arrive as [{sourceSlug,...}] (array) or {sourceSlug,...}
      // (unwrapped). Single-source setup: always refresh on any zenskill:changed.
      const d = data as Record<string, unknown>
      const first = Array.isArray(d) ? d[0] as Record<string, unknown> | undefined : undefined
      const slug = d?.sourceSlug ?? first?.sourceSlug as string | undefined
      if (!slug || slug === sourceSlug) {
        // Day 1: forward entity_id (payload[0]?.entity_id defensively) so
        // consumers can target the exact entity — ignored by older callbacks.
        const entityIdRaw = d?.entity_id ?? first?.entity_id
        const entityId = typeof entityIdRaw === 'string' && entityIdRaw ? entityIdRaw : undefined
        cbRef.current({ entityId })
      }
    })
    return cleanup
  }, [sourceSlug])
}
