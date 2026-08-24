/**
 * ZenSkillDataPanel — Shows GTD inbox, memory, skill summary,
 * energy level, growth stats, achievements, and habits.
 * Embedded in SourceInfoPage for the zenskill-4 MCP source.
 */

import React, { useState, useEffect, useCallback } from 'react'
import { Inbox, Brain, Zap, RefreshCw, ChevronRight, Trophy, Target, Activity, Flame, Check, ArrowRight, Trash2, Archive, Wand2, Circle } from 'lucide-react'

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
  installed_skills: number
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

interface GtdAction {
  id: string
  title: string
  priority?: string
  status?: string
  due_date?: string
}

const PRIORITY_COLOR: Record<string, string> = {
  P0: 'bg-red-500/15 text-red-400',
  P1: 'bg-orange-500/15 text-orange-400',
  P2: 'bg-yellow-500/15 text-yellow-400',
  P3: 'bg-muted text-muted-foreground',
}

export function ZenSkillDataPanel({ workspaceId, sourceSlug, onGtdItemClick }: ZenSkillDataPanelProps) {
  const [gtdItems, setGtdItems] = useState<GtdItem[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [energy, setEnergy] = useState<string | null>(null)
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [habits, setHabits] = useState<Habit[]>([])
  const [actions, setActions] = useState<GtdAction[]>([])
  const [doneActions, setDoneActions] = useState<GtdAction[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)
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
      const [gtdResult, memResult, dashResult, energyResult, achieveResult, habitResult, actionResult, doneResult] = await Promise.allSettled([
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'memory_list', { skill_id: 'all', n: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'dashboard_summary', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'energy_level', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'achievement_list', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'habit_list', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'action_list', { status: 'pending', limit: 20 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'action_list', { status: 'done', limit: 3 }),
      ])

      const gtdData = extractJson(gtdResult.status === 'fulfilled' ? gtdResult.value : null)
      if (gtdData) setGtdItems(gtdData.items || [])

      const memData = extractJson(memResult.status === 'fulfilled' ? memResult.value : null)
      if (memData) setMemories(memData.items || [])

      const dashData = extractJson(dashResult.status === 'fulfilled' ? dashResult.value : null)
      if (dashData) {
        setDashboard({
          active_skills: dashData.active_skills || 0,
          installed_skills: dashData.installed_skills || dashData.active_skills || 0,
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

      const actionData = extractJson(actionResult.status === 'fulfilled' ? actionResult.value : null)
      if (actionData) setActions(actionData.items || [])

      const doneData = extractJson(doneResult.status === 'fulfilled' ? doneResult.value : null)
      if (doneData) setDoneActions(doneData.items || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [workspaceId, sourceSlug])

  const runTool = useCallback(async (tool: string, args: Record<string, unknown>) => {
    setBusyId(String(args.action_id ?? args.item_id ?? tool))
    setError(null)
    try {
      await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, args)
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${tool}`)
    } finally {
      setBusyId(null)
    }
  }, [workspaceId, sourceSlug, fetchData])

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
          <div className="text-lg font-semibold">{dashboard?.installed_skills ?? '—'}</div>
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
                className="flex items-center gap-1 text-xs rounded px-2 py-1 hover:bg-muted/50 group"
              >
                <button
                  className="flex items-center gap-2 flex-1 truncate text-left"
                  onClick={() => onGtdItemClick?.(item.text || item.raw_text || '')}
                  title="Click to discuss in chat"
                >
                  <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="truncate flex-1">{item.text || item.raw_text}</span>
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                  title="Clarify (auto-classify)"
                  disabled={busyId === item.id}
                  onClick={() => runTool('inbox_clarify', { item_id: item.id })}
                >
                  <Wand2 className="h-3 w-3" />
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                  title="Archive"
                  disabled={busyId === item.id}
                  onClick={() => runTool('inbox_archive', { item_id: item.id })}
                >
                  <Archive className="h-3 w-3" />
                </button>
              </div>
            ))}
            {gtdItems.length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">+{gtdItems.length - 5} more</div>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Circle className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            Actions ({actions.length})
          </span>
        </div>
        {actions.length === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">No pending actions</div>
        ) : (
          <div className="space-y-1">
            {actions.slice(0, 8).map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-1.5 text-xs rounded px-2 py-1 hover:bg-muted/50 group"
              >
                <span
                  className={`text-[9px] px-1 py-px rounded shrink-0 ${PRIORITY_COLOR[a.priority || 'P2'] || PRIORITY_COLOR.P2}`}
                >
                  {a.priority || 'P2'}
                </span>
                <span className="truncate flex-1">{a.title}</span>
                {a.due_date && (
                  <span className="text-[10px] text-muted-foreground shrink-0">{a.due_date.slice(5)}</span>
                )}
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400 shrink-0"
                  title="Done"
                  disabled={busyId === a.id}
                  onClick={() => runTool('action_done', { action_id: a.id })}
                >
                  <Check className="h-3 w-3" />
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                  title="Mark as next"
                  disabled={busyId === a.id}
                  onClick={() => runTool('action_mark_next', { action_id: a.id })}
                >
                  <ArrowRight className="h-3 w-3" />
                </button>
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/20 text-muted-foreground hover:text-red-400 shrink-0"
                  title="Delete"
                  disabled={busyId === a.id}
                  onClick={() => runTool('action_delete', { action_id: a.id })}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
            {actions.length > 8 && (
              <div className="text-xs text-muted-foreground pl-5">+{actions.length - 8} more</div>
            )}
          </div>
        )}
        {doneActions.length > 0 && (
          <div className="mt-1.5 pl-5 space-y-0.5">
            {doneActions.slice(0, 3).map((a) => (
              <div key={a.id} className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
                <Check className="h-2.5 w-2.5 text-green-500/60 shrink-0" />
                <span className="truncate line-through decoration-muted-foreground/40">{a.title}</span>
              </div>
            ))}
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
