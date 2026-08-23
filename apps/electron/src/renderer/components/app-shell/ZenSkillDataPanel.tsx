/**
 * ZenSkillDataPanel — Shows GTD inbox, memory, and skill summary
 * for the zenskill-4 MCP source. Embedded in SourceInfoPage.
 */

import React, { useState, useEffect, useCallback } from 'react'
import { Inbox, Brain, Zap, RefreshCw, ChevronRight } from 'lucide-react'

interface ZenSkillDataPanelProps {
  workspaceId: string
  sourceSlug: string
}

interface GtdItem {
  id: string
  text: string
  raw_text?: string
  status: string
  created_at?: string
  created?: string
}

interface MemoryItem {
  id: string
  content: string
  skill_id?: string
  timestamp?: string
  created_at?: string
}

interface DashboardData {
  active_skills: number
  today_sessions: number
  total_memories: number
  total_gtd_items: number
}

export function ZenSkillDataPanel({ workspaceId, sourceSlug }: ZenSkillDataPanelProps) {
  const [gtdItems, setGtdItems] = useState<GtdItem[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [gtdResult, memResult, dashResult] = await Promise.allSettled([
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'memory_list', { n: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'dashboard_summary', {}),
      ])

      // Helper: extract JSON from MCP tool response (content[0].text)
      const extractJson = (result: any): any => {
        if (!result?.success) return null
        const inner = result.result
        if (!inner) return null
        const text = inner.content?.[0]?.text
        if (typeof text === 'string') {
          try { return JSON.parse(text) } catch { return null }
        }
        return inner
      }

      const gtdData = extractJson(gtdResult.status === 'fulfilled' ? gtdResult.value : null)
      if (gtdData) {
        setGtdItems(gtdData.items || [])
      }

      const memData = extractJson(memResult.status === 'fulfilled' ? memResult.value : null)
      if (memData) {
        setMemories(memData.items || [])
      }

      const dashData = extractJson(dashResult.status === 'fulfilled' ? dashResult.value : null)
      if (dashData) {
        setDashboard({
          active_skills: dashData.active_skills || 0,
          today_sessions: dashData.today_sessions || 0,
          total_memories: memData?.count || 0,
          total_gtd_items: gtdData?.count || 0,
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [workspaceId, sourceSlug])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-accent" />
          <span className="text-sm font-medium">ZenSkill Data</span>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="p-1 rounded hover:bg-muted disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="text-xs text-destructive bg-destructive/5 rounded p-2">{error}</div>
      )}

      {/* Dashboard Summary */}
      {dashboard && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded border border-border/30 p-2">
            <div className="text-muted-foreground">Skills</div>
            <div className="text-lg font-semibold">{dashboard.active_skills}</div>
          </div>
          <div className="rounded border border-border/30 p-2">
            <div className="text-muted-foreground">Sessions</div>
            <div className="text-lg font-semibold">{dashboard.today_sessions}</div>
          </div>
        </div>
      )}

      {/* GTD Inbox */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Inbox className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            GTD Inbox ({gtdItems.length})
          </span>
        </div>
        {gtdItems.length === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">No pending items</div>
        ) : (
          <div className="space-y-1">
            {gtdItems.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className="flex items-center gap-2 text-xs rounded px-2 py-1 hover:bg-muted/50 cursor-pointer group"
              >
                <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="truncate flex-1">{item.text || item.raw_text}</span>
              </div>
            ))}
            {gtdItems.length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">
                +{gtdItems.length - 5} more
              </div>
            )}
          </div>
        )}
      </div>

      {/* Memory */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Brain className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            Memory ({memories.length})
          </span>
        </div>
        {memories.length === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">No memories stored</div>
        ) : (
          <div className="space-y-1">
            {memories.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className="text-xs rounded px-2 py-1 hover:bg-muted/50 cursor-pointer group"
              >
                <span className="truncate block">{item.content}</span>
                {item.skill_id && (
                  <span className="text-[10px] text-muted-foreground">{item.skill_id}</span>
                )}
              </div>
            ))}
            {memories.length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">
                +{memories.length - 5} more
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
