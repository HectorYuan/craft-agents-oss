/**
 * ZenSkillDataPanel — Shows GTD inbox, memory, skill summary,
 * energy level, growth stats, achievements, and habits.
 * Embedded in SourceInfoPage for the zenskill-4 MCP source.
 */

import React, { useState, useEffect, useCallback } from 'react'
import { Inbox, Brain, Zap, RefreshCw, ChevronRight, Trophy, Target, Activity, Flame } from 'lucide-react'

interface ZenSkillDataPanelProps {
  workspaceId: string
  sourceSlug: string
  onGtdItemClick?: (text: string) => void
}

interface GtdItem {
  id: string
  text: string
  raw_text?: string
  status: string
  created_at?: string
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

interface Achievement {
  id: string
  name: string
  description?: string
  unlocked?: boolean
}

interface Habit {
  id: string
  name?: string
  title?: string
  completion_rate?: number
  streak?: number
  target?: number
}

export function ZenSkillDataPanel({ workspaceId, sourceSlug, onGtdItemClick }: ZenSkillDataPanelProps) {
  const [gtdItems, setGtdItems] = useState<GtdItem[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [energy, setEnergy] = useState<string | null>(null)
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [habits, setHabits] = useState<Habit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [gtdResult, memResult, dashResult, energyResult, achieveResult, habitResult] = await Promise.allSettled([
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'memory_list', { n: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'dashboard_summary', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'energy_level', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'achievement_list', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'habit_list', {}),
      ])

      const gtdData = extractJson(gtdResult.status === 'fulfilled' ? gtdResult.value : null)
      if (gtdData) setGtdItems(gtdData.items || [])

      const memData = extractJson(memResult.status === 'fulfilled' ? memResult.value : null)
      if (memData) setMemories(memData.items || [])

      const dashData = extractJson(dashResult.status === 'fulfilled' ? dashResult.value : null)
      if (dashData) {
        setDashboard({
          active_skills: dashData.active_skills || 0,
          today_sessions: dashData.today_sessions || 0,
          total_memories: memData?.count || 0,
          total_gtd_items: gtdData?.count || 0,
        })
      }

      const energyData = extractJson(energyResult.status === 'fulfilled' ? energyResult.value : null)
      if (energyData) {
        // energy_level returns {status: {level: "high"}, message: "..."}
        const level = energyData.status?.level || energyData.level || energyData.energy || null
        setEnergy(level)
      }

      const achieveData = extractJson(achieveResult.status === 'fulfilled' ? achieveResult.value : null)
      if (achieveData) setAchievements(achieveData.badges || achieveData.items || achieveData.achievements || [])

      const habitData = extractJson(habitResult.status === 'fulfilled' ? habitResult.value : null)
      if (habitData) setHabits(habitData.items || habitData.habits || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [workspaceId, sourceSlug])

  useEffect(() => { fetchData() }, [fetchData])

  // Real-time sync on zenskill:changed events
  useEffect(() => {
    if (!window.electronAPI?.onZenSkillChanged) return
    const cleanup = window.electronAPI.onZenSkillChanged((_wsId, data) => {
      if (data.sourceSlug === sourceSlug) fetchData()
    })
    return cleanup
  }, [fetchData, sourceSlug])

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

      {/* Dashboard + Energy */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground">Skills</div>
          <div className="text-lg font-semibold">{dashboard?.active_skills ?? '—'}</div>
        </div>
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground">Sessions</div>
          <div className="text-lg font-semibold">{dashboard?.today_sessions ?? '—'}</div>
        </div>
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground flex items-center gap-1">
            <Activity className="h-3 w-3" /> Energy
          </div>
          <div className="text-lg font-semibold capitalize">{energy ?? '—'}</div>
        </div>
      </div>

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
                onClick={() => onGtdItemClick?.(item.text || item.raw_text || '')}
                title="Click to discuss in chat"
              >
                <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="truncate flex-1">{item.text || item.raw_text}</span>
              </div>
            ))}
            {gtdItems.length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">+{gtdItems.length - 5} more</div>
            )}
          </div>
        )}
      </div>

      {/* Memory */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Brain className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Memory ({memories.length})</span>
        </div>
        {memories.length === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">No memories stored</div>
        ) : (
          <div className="space-y-1">
            {memories.slice(0, 5).map((item) => (
              <div key={item.id} className="text-xs rounded px-2 py-1 hover:bg-muted/50 cursor-pointer">
                <span className="truncate block">{item.content}</span>
                {item.skill_id && <span className="text-[10px] text-muted-foreground">{item.skill_id}</span>}
              </div>
            ))}
            {memories.length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">+{memories.length - 5} more</div>
            )}
          </div>
        )}
      </div>

      {/* Achievements */}
      {achievements.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Trophy className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">Achievements ({achievements.length})</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {achievements.slice(0, 6).map((a) => (
              <span
                key={a.id}
                className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent"
                title={a.description}
              >
                {a.name}
              </span>
            ))}
            {achievements.length > 6 && (
              <span className="text-[10px] text-muted-foreground">+{achievements.length - 6}</span>
            )}
          </div>
        </div>
      )}

      {/* Habits */}
      {habits.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Flame className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">Habits ({habits.length})</span>
          </div>
          <div className="space-y-1">
            {habits.slice(0, 4).map((h) => (
              <div key={h.id} className="flex items-center justify-between text-xs rounded px-2 py-1">
                <span className="truncate">{h.name || h.title || h.id}</span>
                <div className="flex items-center gap-2 shrink-0">
                  {h.streak != null && h.streak > 0 && (
                    <span className="text-[10px] text-orange-500">🔥{h.streak}</span>
                  )}
                  {h.completion_rate != null && (
                    <span className="text-[10px] text-muted-foreground">{Math.round(h.completion_rate * 100)}%</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
