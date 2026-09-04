/**
 * useZenSkillChanged — Subscribe to zenskill:changed broadcasts for a
 * specific MCP source slug. The callback is kept in a ref so the
 * subscription is not torn down and rebuilt on every render; cleanup
 * happens on unmount or when sourceSlug changes.
 */
import { useEffect, useRef } from 'react'

export function useZenSkillChanged(sourceSlug: string, onChanged: () => void): void {
  const cbRef = useRef(onChanged)
  cbRef.current = onChanged

  useEffect(() => {
    if (!window.electronAPI?.onZenSkillChanged) return
    const cleanup = window.electronAPI.onZenSkillChanged((_wsId, data) => {
      if (data.sourceSlug === sourceSlug) cbRef.current()
    })
    return cleanup
  }, [sourceSlug])
}
