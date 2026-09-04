/**
 * useMcpTool — L3 data hook for ZenSkill MCP tools.
 *
 * Wraps window.electronAPI.callMcpTool with:
 * - JSON extraction from MCP content blocks (inner.content[0].text),
 *   matching the pattern established in ZenSkillDataPanel
 * - Auto refresh on zenskill:changed broadcast (matched by sourceSlug);
 *   write tools should be called directly by consumers — the resulting
 *   broadcast drives refresh through this hook, no manual refetch
 * - Debounced refresh (bursts of broadcasts coalesce into one fetch)
 *   and unmount cleanup for subscriptions and pending timers
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useZenSkillChanged } from './useZenSkillChanged'

export interface UseMcpToolResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refresh: () => void
}

type McpToolResponse = { success?: boolean; result?: unknown; error?: string }

/**
 * Extract the JSON payload from an MCP tool response.
 * Shared by useMcpTool and consumers that call write tools directly.
 */
export function extractMcpJson(result: unknown): any {
  const res = result as McpToolResponse | null | undefined
  if (!res?.success) return null
  const inner = res.result as { content?: Array<{ text?: string }> } | null | undefined
  if (!inner) return null
  const text = inner.content?.[0]?.text
  if (typeof text === 'string') {
    try { return JSON.parse(text) } catch { return null }
  }
  return inner
}

export function useMcpTool<T = any>(
  workspaceId: string | undefined | null,
  sourceSlug: string,
  tool: string,
  args: Record<string, unknown> = {},
): UseMcpToolResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // args objects are typically recreated per render; serialize to a stable dep key
  const argsKey = JSON.stringify(args)
  const mountedRef = useRef(true)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchData = useCallback(async () => {
    if (!workspaceId) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, JSON.parse(argsKey))
      if (!mountedRef.current) return
      const parsed = extractMcpJson(result)
      if (parsed !== null) setData(parsed as T)
      const errText = (result as McpToolResponse | null)?.error
      if (errText) setError(errText)
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : `Failed to run ${tool}`)
      }
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [workspaceId, sourceSlug, tool, argsKey])

  const refresh = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      debounceRef.current = null
      if (mountedRef.current) void fetchData()
    }, 200)
  }, [fetchData])

  useEffect(() => {
    mountedRef.current = true
    void fetchData()
    return () => {
      mountedRef.current = false
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }
  }, [fetchData])

  useZenSkillChanged(sourceSlug, refresh)

  return { data, loading, error, refresh }
}
