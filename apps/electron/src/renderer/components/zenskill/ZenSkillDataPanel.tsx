/**
 * ZenSkillDataPanel — Shows GTD inbox, memory, skill summary,
 * energy level, growth stats, achievements, and habits.
 * Embedded in SourceInfoPage for the zenskill-4 MCP source.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { toast } from 'sonner'
import { Inbox, Brain, Zap, RefreshCw, ChevronRight, Trophy, Target, Activity, Flame, Check, Search, TrendingUp, Lightbulb } from 'lucide-react'
import { InboxPanel } from './panels/InboxPanel'
import { ActionsPanel } from './panels/ActionsPanel'
import { CalendarPanel } from './panels/CalendarPanel'
import { ProjectsPanel } from './panels/ProjectsPanel'
import type { GtdItem, GtdAction } from './panels/types'

interface ZenSkillDataPanelProps {
  workspaceId: string
  sourceSlug: string
  onGtdItemClick?: (text: string) => void
}

interface MemoryItem {
  id: string
  content: string
  skill_id?: string
  timestamp?: string
  created_at?: string
  action?: string
  date?: string
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
  name?: string
  title?: string
  icon?: string
  tier?: string
  description?: string
  unlocked?: boolean
  progress?: number
  detail?: string
}

interface Habit {
  id: string
  name?: string
  title?: string
  completion_rate?: number
  streak?: number
  target?: number
  best_streak?: number
  risk?: string
  completed?: Record<string, boolean>
}

interface CompanionSummary {
  mood: string
  energy: { level: string; pct: number; current: number; max: number }
  inbox_pending: number
  pending_actions: number
  due_today: number
  overdue: number
  top_insight?: { type: string; title: string; content: string } | null
}

interface SkillCategory {
  name: string
  count: number
  skills: { skill_id: string; name: string; description: string; usage_count: number; level: string }[]
}

interface GrowthSkill {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

export function ZenSkillDataPanel({ workspaceId, sourceSlug, onGtdItemClick }: ZenSkillDataPanelProps) {
  const [gtdItems, setGtdItems] = useState<GtdItem[]>([])
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [energy, setEnergy] = useState<string | null>(null)
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [lockedAchievements, setLockedAchievements] = useState<Achievement[]>([])
  const [achieveRate, setAchieveRate] = useState(0)
  const [habits, setHabits] = useState<Habit[]>([])
  const [actions, setActions] = useState<GtdAction[]>([])
  const [doneActions, setDoneActions] = useState<GtdAction[]>([])
  const [growth, setGrowth] = useState<GrowthSkill[]>([])
  const [companion, setCompanion] = useState<CompanionSummary | null>(null)
  const [dailyReviewMsg, setDailyReviewMsg] = useState<string | null>(null)
  const [projects, setProjects] = useState<{ id: string; name: string; status?: string; progress?: number }[]>([])
  const [calendarEvents, setCalendarEvents] = useState<{ date: string; time: string; title: string }[]>([])
  const [calendarCount, setCalendarCount] = useState(0)
  const [goals, setGoals] = useState<{ dimension?: string; target?: number; current?: number }[]>([])
  const [skillCategories, setSkillCategories] = useState<SkillCategory[]>([])
  const [totalSkills, setTotalSkills] = useState(0)
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [memQuery, setMemQuery] = useState('')
  const [memResults, setMemResults] = useState<MemoryItem[] | null>(null)
  const memSearchRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [activeTab, setActiveTab] = useState<'today' | 'gtd' | 'memory' | 'skills'>('today')

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
      const [gtdResult, memResult, dashResult, energyResult, achieveResult, habitResult, actionResult, doneResult, growthResult, companionResult, skillBrowseResult, dailyReviewResult, projectResult, calendarResult, goalResult] = await Promise.allSettled([
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'memory_list', { skill_id: 'all', n: 10 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'dashboard_summary', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'energy_level', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'achievement_list', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'habit_analyze', { days: 7 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'action_list', { status: 'pending', limit: 20 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'action_list', { status: 'done', limit: 3 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'growth_dashboard', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'companion_summary', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'skill_browse', { limit: 3 }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'daily_review', {}),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, "project_list", { status: "active" }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, "calendar_list", { scope: "today" }),
        window.electronAPI.callMcpTool(workspaceId, sourceSlug, "goal_progress", {}),
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
      if (achieveData) {
        setAchievements(achieveData.badges || [])
        setLockedAchievements(achieveData.locked || [])
        setAchieveRate(achieveData.completion_rate || 0)
      }

      const habitData = extractJson(habitResult.status === 'fulfilled' ? habitResult.value : null)
      if (habitData) setHabits(habitData.habits || [])

      const actionData = extractJson(actionResult.status === 'fulfilled' ? actionResult.value : null)
      if (actionData) setActions(actionData.items || [])

      const doneData = extractJson(doneResult.status === 'fulfilled' ? doneResult.value : null)
      if (doneData) setDoneActions(doneData.items || [])

      const growthData = extractJson(growthResult.status === 'fulfilled' ? growthResult.value : null)
      if (growthData) setGrowth(growthData.skills || [])

      const companionData = extractJson(companionResult.status === 'fulfilled' ? companionResult.value : null)
      if (companionData) {
        setCompanion(companionData)
        // 陪伴感主动推送（频控：同类 24h 内只推一次）
        const alertKey = `companion-alert-${companionData.mood?.slice(0, 8) ?? 'default'}`
        const lastAlert = sessionStorage.getItem(alertKey)
        if (!lastAlert || Date.now() - Number(lastAlert) > 24 * 3600 * 1000) {
          sessionStorage.setItem(alertKey, String(Date.now()))
          if (companionData.overdue > 0) {
            toast.warning(`⚠ ${companionData.overdue} 个行动已逾期`, {
              description: companionData.mood,
            })
          } else if (companionData.energy.level === 'critical') {
            toast.info('⚡ 能量不足，建议休息一下', {
              description: companionData.mood,
            })
          }
        }
        // Extract suggestions from energy_level advice
        const eAdvice = energyData?.advice
        if (eAdvice?.suggestions?.length) setSuggestions(eAdvice.suggestions.slice(0, 2))
        else if (companionData.overdue) setSuggestions([`${companionData.overdue} 个行动已逾期，建议先处理`])
        else if (companionData.inbox_pending > 5) setSuggestions([`收件箱有 ${companionData.inbox_pending} 条待处理，建议定期清空`])
      }

      const skillBrowseData = extractJson(skillBrowseResult.status === 'fulfilled' ? skillBrowseResult.value : null)
      if (skillBrowseData) {
        setSkillCategories(skillBrowseData.categories || [])
        setTotalSkills(skillBrowseData.total || 0)
      }

      const reviewData = extractJson(dailyReviewResult.status === 'fulfilled' ? dailyReviewResult.value : null)
      if (reviewData?.message) setDailyReviewMsg(reviewData.message)
      const projectData = extractJson(projectResult.status === "fulfilled" ? projectResult.value : null)
      if (projectData) setProjects((projectData.items || []).slice(0, 5))
      const calendarData = extractJson(calendarResult.status === "fulfilled" ? calendarResult.value : null)
      if (calendarData) { setCalendarEvents((calendarData.events || []).slice(0, 5)); setCalendarCount(calendarData.count || 0) }
      const goalData = extractJson(goalResult.status === "fulfilled" ? goalResult.value : null)
      if (goalData) setGoals((goalData.items || goalData.goals || []).slice(0, 5))
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
      // 刷新统一由 zenskill:changed 广播驱动（runTool 的工具都在 WRITE_TOOLS 内），
      // 不在此手动 fetchData——避免双重刷新
      await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, args)
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${tool}`)
    } finally {
      setBusyId(null)
    }
  }, [workspaceId, sourceSlug])

  // Debounced memory search
  const searchMemories = useCallback((query: string) => {
    if (memSearchRef.current) clearTimeout(memSearchRef.current)
    memSearchRef.current = setTimeout(async () => {
      const q = query.trim()
      if (!q) { setMemResults(null); return }
      try {
        const res = await window.electronAPI.callMcpTool(workspaceId, sourceSlug, 'memory_search', { query: q, n: 8 })
        const parsed = extractJson(res)
        if (parsed?.items) setMemResults(parsed.items)
      } catch { setMemResults(null) }
    }, 300)
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


  // zenskill:navigate handler
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.message && onGtdItemClick) onGtdItemClick(detail.message)
    }
    window.addEventListener("zenskill:navigate", handler)
    return () => window.removeEventListener("zenskill:navigate", handler)
  }, [onGtdItemClick])
  return (
    <div className="space-y-4 p-3">
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

      {/* Tab Bar */}
      <div className="flex gap-0.5 border-b border-border/30 -mx-3 px-3">
        {([
          { key: 'today', label: 'Today', icon: Zap },
          { key: 'gtd', label: 'GTD', icon: Inbox },
          { key: 'memory', label: 'Memory', icon: Brain },
          { key: 'skills', label: 'Skills', icon: TrendingUp },
        ] as const).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="h-3 w-3" />
            {label}
          </button>
        ))}
      </div>

      {/* === TODAY TAB === */}
      {activeTab === 'today' && (<div className="space-y-4">

      {/* Companion: mood + energy bar + urgency */}
      {companion && (
        <div className="rounded border border-border/30 p-2 space-y-1.5">
          <div className="text-xs text-muted-foreground">{companion.mood}</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded bg-muted/60 overflow-hidden">
              <div
                className={`h-full rounded transition-all ${
                  companion.energy.pct > 0.7 ? 'bg-green-500/70'
                    : companion.energy.pct > 0.3 ? 'bg-yellow-500/70'
                    : companion.energy.pct > 0.1 ? 'bg-orange-500/70'
                    : 'bg-red-500/70'
                }`}
                style={{ width: `${Math.round(companion.energy.pct * 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-muted-foreground w-8 text-right shrink-0">
              {Math.round(companion.energy.pct * 100)}%
            </span>
          </div>
          {(companion.overdue > 0 || companion.due_today > 0) && (
            <div className="flex gap-3 text-[10px]">
              {companion.overdue > 0 && (
                <span className="text-red-400">⚠ {companion.overdue} overdue</span>
              )}
              {companion.due_today > 0 && (
                <span className="text-yellow-400">📅 {companion.due_today} due today</span>
              )}
            </div>
          )}
          {companion.top_insight && (
            <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70">
              <Lightbulb className="h-3 w-3 mt-px shrink-0 text-yellow-500/60" />
              <span>💡 {companion.top_insight.title}</span>
            </div>
          )}
          {suggestions.length > 0 && (
            <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70">
              <Lightbulb className="h-3 w-3 mt-px shrink-0 text-yellow-500/60" />
              <span>{suggestions[0]}</span>
            </div>
          )}
          {dailyReviewMsg && (
            <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70 border-t border-border/30 pt-1.5 mt-1.5">
              <span className="shrink-0">📊</span>
              <span className="truncate" title={dailyReviewMsg}>{dailyReviewMsg}</span>
            </div>
          )}
        </div>
      )}

      {/* Dashboard + Energy */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground">Skills</div>
          <div className="text-lg font-semibold">
            {dashboard ? dashboard.installed_skills
              : <span className={`inline-block w-8 h-5 rounded bg-muted/60 ${loading ? 'animate-pulse' : ''}`} />}
          </div>
        </div>
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground">Sessions</div>
          <div className="text-lg font-semibold">
            {dashboard ? dashboard.today_sessions
              : <span className={`inline-block w-8 h-5 rounded bg-muted/60 ${loading ? 'animate-pulse' : ''}`} />}
          </div>
        </div>
        <div className="rounded border border-border/30 p-2">
          <div className="text-muted-foreground flex items-center gap-1">
            <Activity className="h-3 w-3" /> Energy
          </div>
          <div className="text-lg font-semibold capitalize">
            {energy ? energy
              : <span className={`inline-block w-10 h-5 rounded bg-muted/60 ${loading ? 'animate-pulse' : ''}`} />}
          </div>
        </div>
      </div>

      {/* Growth */}
      {growth.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">Growth ({growth.length})</span>
          </div>
          <div className="space-y-1.5">
            {growth.slice(0, 3).map((g) => (
              <div key={g.skill_id} className="text-xs rounded px-2 py-1 hover:bg-muted/50">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{g.skill_id}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[9px] px-1 py-px rounded bg-accent/10 text-accent">{g.level}</span>
                    <span className="text-[10px] text-muted-foreground">{g.usage_count ?? 0}次</span>
                    <span className="text-[10px] text-green-500/80">{Math.round((g.success_rate ?? 0) * 100)}%</span>
                  </div>
                </div>
                {g.scores && (
                  <div className="flex items-center gap-1 mt-1">
                    {Object.entries(g.scores).map(([k, v]) => (
                      <div key={k} className="flex-1" title={`${k}: ${v}`}>
                        <div className="h-1 rounded bg-muted/60 overflow-hidden">
                          <div className="h-full bg-accent/70" style={{ width: `${v}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      </div>)}


      {/* === GTD TAB === */}
      {activeTab === 'gtd' && (<div className="space-y-4">

      {/* GTD Inbox */}
      <InboxPanel
        items={gtdItems}
        busyId={busyId}
        maxItems={5}
        onItemClick={onGtdItemClick}
        onClarify={(itemId) => runTool('inbox_clarify', { item_id: itemId })}
        onArchive={(itemId) => runTool('inbox_archive', { item_id: itemId })}
      />

      {/* Actions */}
      <ActionsPanel
        actions={actions}
        doneActions={doneActions}
        busyId={busyId}
        maxItems={8}
        doneMaxItems={3}
        onDone={(actionId) => runTool('action_done', { action_id: actionId })}
        onMarkNext={(actionId) => runTool('action_mark_next', { action_id: actionId })}
        onDelete={(actionId) => runTool('action_delete', { action_id: actionId })}
        confirmDeleteId={confirmDeleteId}
        onConfirmDeleteIdChange={setConfirmDeleteId}
      />

      {/* Calendar */}
      <CalendarPanel events={calendarEvents} count={calendarCount} />

      {/* Projects */}
      <ProjectsPanel projects={projects} maxItems={5} />

      </div>)}

      {/* === MEMORY TAB === */}
      {activeTab === 'memory' && (<div className="space-y-4">

      {/* Memory */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Brain className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Memory ({memResults ? memResults.length : memories.length})</span>
        </div>
        <div className="relative mb-1.5">
          <Search className="h-3 w-3 text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            value={memQuery}
            onChange={(e) => { setMemQuery(e.target.value); searchMemories(e.target.value) }}
            placeholder="Search memories..."
            className="w-full text-xs bg-muted/40 rounded pl-6 pr-2 py-1 outline-none focus:ring-1 focus:ring-accent/40"
          />
        </div>
        {(memResults ? memResults.length : memories.length) === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">No memories stored</div>
        ) : (
          <div className="space-y-1">
            {(memResults ?? memories).slice(0, 5).map((item, i) => (
              <div key={item.id || `${item.skill_id}-${i}`} className="text-xs rounded px-2 py-1 hover:bg-muted/50">
                <div className="truncate">{item.content}</div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  {item.action && (
                    <span className="text-[9px] px-1 py-px rounded bg-accent/10 text-accent shrink-0">{item.action}</span>
                  )}
                  <span className="text-[10px] text-muted-foreground shrink-0">{item.skill_id}</span>
                  {item.date && (
                    <span className="text-[10px] text-muted-foreground/60 shrink-0 ml-auto">{item.date}</span>
                  )}
                </div>
              </div>
            ))}
            {(memResults ?? memories).length > 5 && (
              <div className="text-xs text-muted-foreground pl-5">+{(memResults ?? memories).length - 5} more</div>
            )}
          </div>
        )}
      </div>

      {/* Achievements */}
      {achievements.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Trophy className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">
              Achievements ({achievements.length}/{achievements.length + lockedAchievements.length})
            </span>
            {achieveRate > 0 && (
              <span className="text-[9px] text-muted-foreground/60 ml-auto">{Math.round(achieveRate * 100)}%</span>
            )}
          </div>
          {/* Unlocked badges */}
          <div className="flex flex-wrap gap-1 mb-1">
            {achievements.map((a) => (
              <span
                key={a.id}
                className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent inline-flex items-center gap-1"
                title={`${a.description}\n${a.detail || ''}`}
              >
                <span>{a.icon || '🏅'}</span>
                {a.title || a.name}
              </span>
            ))}
          </div>
          {/* Locked badges with progress (closest to unlocking first) */}
          {lockedAchievements.length > 0 && lockedAchievements.some(a => (a.progress ?? 0) > 0) && (
            <div className="space-y-1 mt-1.5">
              {lockedAchievements
                .filter(a => (a.progress ?? 0) > 0)
                .slice(0, 3)
                .map((a) => (
                  <div key={a.id} className="flex items-center gap-1.5 text-[10px]" title={a.description}>
                    <span className="text-muted-foreground/40">{a.icon || '🔒'}</span>
                    <span className="text-muted-foreground/70 truncate flex-1">{a.title || a.name}</span>
                    <div className="w-10 h-1 rounded bg-muted/60 overflow-hidden shrink-0">
                      <div className="h-full bg-accent/40" style={{ width: `${Math.round((a.progress ?? 0) * 100)}%` }} />
                    </div>
                    <span className="text-muted-foreground/50 w-7 text-right shrink-0">{Math.round((a.progress ?? 0) * 100)}%</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}



      </div>)}

      {/* === SKILLS TAB === */}
      {activeTab === 'skills' && (<div className="space-y-4">

      {/* Goals */}
      <div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <Target className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">Goals ({goals.length})</span>
        </div>
        {goals.length === 0 ? (
          <div className="text-xs text-muted-foreground italic pl-5">暂无目标</div>
        ) : (
          <div className="space-y-0.5">
            {goals.slice(0, 5).map((g, i) => (
              <div key={i} className="text-xs rounded px-2 py-0.5 flex items-center gap-1.5">
                <Target className="h-3 w-3 text-accent/60 shrink-0" />
                <span className="truncate flex-1">{g.dimension || "goal"}</span>
                <span className="text-[10px] text-muted-foreground shrink-0">{g.current ?? 0}/{g.target ?? "-"}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Skills Browse */}
      {skillCategories.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-sm">🧩</span>
            <span className="text-xs font-medium text-muted-foreground">Skills ({totalSkills})</span>
          </div>
          <div className="space-y-0.5">
            {skillCategories.slice(0, 5).map((cat) => {
              const expanded = expandedCats.has(cat.name)
              return (
                <div key={cat.name}>
                  <button
                    className="flex items-center gap-1.5 w-full text-left text-xs rounded px-2 py-1 hover:bg-muted/50"
                    onClick={() => {
                      const next = new Set(expandedCats)
                      if (next.has(cat.name)) next.delete(cat.name)
                      else next.add(cat.name)
                      setExpandedCats(next)
                    }}
                  >
                    <ChevronRight className={`h-3 w-3 text-muted-foreground transition-transform ${expanded ? 'rotate-90' : ''}`} />
                    <span className="font-medium truncate">{cat.name}</span>
                    <span className="text-[10px] text-muted-foreground/60 ml-auto shrink-0">{cat.count}</span>
                  </button>
                  {expanded && (
                    <div className="pl-5 space-y-0.5">
                      {cat.skills.map((s) => (
                        <div
                          key={s.skill_id}
                          className="text-[11px] rounded px-2 py-0.5 hover:bg-muted/50 cursor-pointer group"
                          onClick={() => onGtdItemClick?.(`帮我了解一下 ${s.name} 这个技能`)}
                          title={s.description}
                        >
                          <span className="truncate block">{s.name}</span>
                          <div className="flex items-center gap-1.5">
                            {s.usage_count > 0 && (
                              <span className="text-[9px] text-muted-foreground/60">{s.usage_count}次</span>
                            )}
                            <span className="text-[9px] text-muted-foreground/40 truncate flex-1">{s.description}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
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
          <div className="space-y-1.5">
            {habits.slice(0, 4).map((h) => (
              <div key={h.id} className="text-xs rounded px-2 py-1 hover:bg-muted/50 group">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{h.title || h.name || h.id}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {(h.streak ?? 0) > 0 && (
                      <span className="text-[10px] text-orange-500">🔥{h.streak}</span>
                    )}
                    <span className="text-[10px] text-muted-foreground">
                      {Math.round((h.completion_rate ?? 0) * 100)}%
                    </span>
                    <button
                      className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400"
                      title="Check in"
                      disabled={busyId === h.id}
                      onClick={() => runTool('habit_check', { habit_id: h.id })}
                    >
                      <Check className="h-3 w-3" />
                    </button>
                  </div>
                </div>
                {h.completed && (
                  <div className="flex items-center gap-0.5 mt-1" title="Last 7 days">
                    {Object.entries(h.completed).map(([day, ok]) => (
                      <span
                        key={day}
                        title={day}
                        className={`h-2.5 w-2.5 rounded-[3px] ${ok ? 'bg-green-500/70' : 'bg-muted/60'}`}
                      />
                    ))}
                    <span className="text-[9px] text-muted-foreground/60 ml-1">7d</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      </div>)}
    </div>
  )
}
