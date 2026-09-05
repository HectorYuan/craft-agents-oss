/**
 * ZenSkillDataPanel — Shows GTD inbox, memory, skill summary,
 * energy level, growth stats, achievements, and habits.
 * Embedded in SourceInfoPage for the zenskill-4 MCP source.
 *
 * C1 迁移：15 个手动 callMcpTool → useMcpTool hook；
 * 内联可视化代码替换为 panels/ 下的复用组件；字符串 i18n 化。
 */
import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Inbox, Brain, Zap, RefreshCw, ChevronRight, Target, Activity, Search, TrendingUp } from 'lucide-react'
import { InboxPanel } from './panels/InboxPanel'
import { ActionsPanel } from './panels/ActionsPanel'
import { CalendarPanel } from './panels/CalendarPanel'
import { ProjectsPanel } from './panels/ProjectsPanel'
import { CompanionCard, type CompanionSummary } from './panels/CompanionCard'
import { EnergyBar } from './panels/EnergyBar'
import { AchievementGrid } from './panels/AchievementGrid'
import { HabitList, type Habit } from './panels/HabitList'
import { GrowthCard, type GrowthSkill } from './panels/GrowthCard'
import { ZS } from './panels/tokens'
import type { GtdItem, GtdAction } from './panels/types'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'

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
  active_skills?: number
  installed_skills?: number
  today_sessions?: number
}

interface AchievementData {
  badges?: Achievement[]
  locked?: Achievement[]
  completion_rate?: number
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

interface SkillCategory {
  name: string
  count: number
  skills: { skill_id: string; name: string; description: string; usage_count: number; level: string }[]
}

interface EnergyData {
  status?: { level?: string; pct?: number; current_energy?: number; max_energy?: number }
  advice?: { suggestions?: string[] }
}

interface GoalData {
  items?: { dimension?: string; target?: number; current?: number }[]
  goals?: { dimension?: string; target?: number; current?: number }[]
}

type TabKey = 'today' | 'gtd' | 'memory' | 'skills'

export function ZenSkillDataPanel({ workspaceId, sourceSlug, onGtdItemClick }: ZenSkillDataPanelProps) {
  const { t } = useTranslation()
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set())
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [memQuery, setMemQuery] = useState('')
  const [activeTab, setActiveTab] = useState<TabKey>('today')

  // ─── L3 数据层：15 个 useMcpTool ───
  const inboxData = useMcpTool<{ count?: number; items?: GtdItem[] }>(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 10 })
  const memData = useMcpTool<{ count?: number; items?: MemoryItem[] }>(workspaceId, sourceSlug, 'memory_list', { skill_id: 'all', n: 10 })
  const dashData = useMcpTool<DashboardData>(workspaceId, sourceSlug, 'dashboard_summary', {})
  const energyData = useMcpTool<EnergyData>(workspaceId, sourceSlug, 'energy_level', {})
  const achieveData = useMcpTool<AchievementData>(workspaceId, sourceSlug, 'achievement_list', {})
  const habitData = useMcpTool<{ habits?: Habit[] }>(workspaceId, sourceSlug, 'habit_analyze', { days: 7 })
  const actionData = useMcpTool<{ items?: GtdAction[] }>(workspaceId, sourceSlug, 'action_list', { status: 'pending', limit: 20 })
  const doneData = useMcpTool<{ items?: GtdAction[] }>(workspaceId, sourceSlug, 'action_list', { status: 'done', limit: 3 })
  const growthData = useMcpTool<{ skills?: GrowthSkill[] }>(workspaceId, sourceSlug, 'growth_dashboard', {})
  const companionData = useMcpTool<CompanionSummary>(workspaceId, sourceSlug, 'companion_summary', {})
  const skillBrowseData = useMcpTool<{ total?: number; categories?: SkillCategory[] }>(workspaceId, sourceSlug, 'skill_browse', { limit: 3 })
  const reviewData = useMcpTool<{ message?: string }>(workspaceId, sourceSlug, 'daily_review', {})
  const projectData = useMcpTool<{ items?: { id: string; name: string; status?: string; progress?: number }[] }>(workspaceId, sourceSlug, 'project_list', { status: 'active' })
  const calendarData = useMcpTool<{ count?: number; events?: { date: string; time: string; title: string }[] }>(workspaceId, sourceSlug, 'calendar_list', { scope: 'today' })
  const goalData = useMcpTool<GoalData>(workspaceId, sourceSlug, 'goal_progress', {})

  // 搜索 — parked hook（query 为空时不请求）
  const memSearch = useMcpTool<{ items?: MemoryItem[] }>(
    memQuery.trim() ? workspaceId : undefined,
    sourceSlug,
    'memory_search',
    { query: memQuery.trim(), n: 8 },
  )

  const gtdItems = inboxData.data?.items ?? []
  const memories = memData.data?.items ?? []
  const actions = actionData.data?.items ?? []
  const doneActions = doneData.data?.items ?? []
  const habits = habitData.data?.habits ?? []
  const growth = growthData.data?.skills ?? []
  const goals = (goalData.data?.items ?? goalData.data?.goals ?? []).slice(0, 5)
  const projects = (projectData.data?.items ?? []).slice(0, 5)
  const calendarEvents = (calendarData.data?.events ?? []).slice(0, 5)
  const calendarCount = calendarData.data?.count ?? 0
  const skillCategories = skillBrowseData.data?.categories ?? []
  const totalSkills = skillBrowseData.data?.total ?? 0
  const suggestions = energyData.data?.advice?.suggestions?.slice(0, 2) ?? []

  const loading = inboxData.loading || dashData.loading || companionData.loading
  const error = inboxData.error || dashData.error || companionData.error || achieveData.error
  const memResults = memQuery.trim() ? (memSearch.data?.items ?? null) : null

  // 陪伴感主动推送（频控：同类 24h 内只推一次）
  useEffect(() => {
    const c = companionData.data
    if (!c) return
    const alertKey = `companion-alert-${c.mood?.slice(0, 8) ?? 'default'}`
    const lastAlert = sessionStorage.getItem(alertKey)
    if (!lastAlert || Date.now() - Number(lastAlert) > 24 * 3600 * 1000) {
      sessionStorage.setItem(alertKey, String(Date.now()))
      if (c.overdue > 0) {
        toast.warning(`⚠ ${c.overdue} 个行动已逾期`, { description: c.mood })
      } else if (c.energy.level === 'critical') {
        toast.info('⚡ 能量不足，建议休息一下', { description: c.mood })
      }
    }
  }, [companionData.data])

  const runTool = async (tool: string, args: Record<string, unknown>) => {
    setBusyId(String(args.action_id ?? args.item_id ?? tool))
    try {
      // 刷新统一由 zenskill:changed 广播驱动（useMcpTool 内置订阅）
      await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, args)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : `Failed to run ${tool}`)
    } finally {
      setBusyId(null)
    }
  }

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
          <span className={ZS.title}>ZenSkill Data</span>
        </div>
      </div>

      {error && (
        <div className={ZS.errorBanner}>{error}</div>
      )}

      {/* Tab Bar */}
      <div className="flex gap-0.5 border-b border-border/30 -mx-3 px-3">
        {([
          { key: 'today', label: t('zenskill.panel.tab.today', 'Today'), icon: Zap },
          { key: 'gtd', label: t('zenskill.panel.tab.gtd', 'GTD'), icon: Inbox },
          { key: 'memory', label: t('zenskill.panel.tab.memory', 'Memory'), icon: Brain },
          { key: 'skills', label: t('zenskill.panel.tab.skills', 'Skills'), icon: TrendingUp },
        ] as const).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === key ? ZS.tabActive : ZS.tabInactive
            }`}
          >
            <Icon className="h-3 w-3" />
            {label}
          </button>
        ))}
      </div>

      {/* === TODAY TAB === */}
      {activeTab === 'today' && (<div className="space-y-4">
        {companionData.data && (
          <CompanionCard
            companion={companionData.data}
            suggestions={suggestions}
            dailyReviewMsg={reviewData.data?.message}
            onNavigateToChat={onGtdItemClick}
          />
        )}

        {/* Dashboard + Energy */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className={ZS.card}>
            <div className="text-muted-foreground">{t('zenskill.panel.stats.skills', 'Skills')}</div>
            <div className="text-lg font-semibold">
              {dashData.data ? (dashData.data.installed_skills ?? dashData.data.active_skills ?? 0)
                : <span className={`inline-block w-8 h-5 rounded bg-muted/60 ${dashData.loading ? 'animate-pulse' : ''}`} />}
            </div>
          </div>
          <div className={ZS.card}>
            <div className="text-muted-foreground">{t('zenskill.panel.stats.sessions', 'Sessions')}</div>
            <div className="text-lg font-semibold">
              {dashData.data ? (dashData.data.today_sessions ?? 0)
                : <span className={`inline-block w-8 h-5 rounded bg-muted/60 ${dashData.loading ? 'animate-pulse' : ''}`} />}
            </div>
          </div>
          <div className={ZS.card}>
            <div className="text-muted-foreground flex items-center gap-1">
              <Activity className="h-3 w-3" /> {t('zenskill.panel.stats.energy', 'Energy')}
            </div>
            <div className="text-lg font-semibold capitalize">
              {energyData.data?.status?.level
                ?? <span className={`inline-block w-10 h-5 rounded bg-muted/60 ${energyData.loading ? 'animate-pulse' : ''}`} />}
            </div>
          </div>
        </div>

        {/* Energy bar */}
        {energyData.data?.status && (
          <div className={ZS.card}>
            <EnergyBar
              level={energyData.data.status.level ?? 'unknown'}
              pct={energyData.data.status.pct ?? 0}
              current={energyData.data.status.current_energy}
              max={energyData.data.status.max_energy}
            />
          </div>
        )}

        {/* Growth */}
        <GrowthCard skills={growth} maxItems={3} onNavigateToChat={onGtdItemClick} />
      </div>)}

      {/* === GTD TAB === */}
      {activeTab === 'gtd' && (<div className="space-y-4">
        <InboxPanel
          items={gtdItems}
          busyId={busyId}
          maxItems={5}
          onItemClick={onGtdItemClick}
          onClarify={(itemId) => runTool('inbox_clarify', { item_id: itemId })}
          onArchive={(itemId) => runTool('inbox_archive', { item_id: itemId })}
        />

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

        <CalendarPanel events={calendarEvents} count={calendarCount} />

        <ProjectsPanel projects={projects} maxItems={5} />
      </div>)}

      {/* === MEMORY TAB === */}
      {activeTab === 'memory' && (<div className="space-y-4">
        {/* Memory list + search */}
        <div>
          <div className={ZS.sectionHeader}>
            <Brain className="h-3.5 w-3.5 text-muted-foreground" />
            <span className={ZS.body + ' font-medium text-muted-foreground'}>
              {t('zenskill.panel.memory.title', 'Memory')} ({memResults ? memResults.length : memories.length})
            </span>
          </div>
          <div className="relative mb-1.5">
            <Search className="h-3 w-3 text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2" />
            <input
              value={memQuery}
              onChange={(e) => setMemQuery(e.target.value)}
              placeholder={t('zenskill.panel.memory.searchPlaceholder', 'Search memories...')}
              className="w-full text-xs bg-muted/40 rounded pl-6 pr-2 py-1 outline-none focus:ring-1 focus:ring-accent/40"
            />
          </div>
          {(memResults ? memResults.length : memories.length) === 0 ? (
            <div className={ZS.emptyState + ' pl-5'}>{t('zenskill.panel.memory.empty', 'No memories stored')}</div>
          ) : (
            <div className="space-y-1">
              {(memResults ?? memories).slice(0, 5).map((item, i) => (
                <div key={item.id || `${item.skill_id}-${i}`} className={ZS.hoverRow}>
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
                <div className={ZS.body + ' text-muted-foreground pl-5'}>
                  +{(memResults ?? memories).length - 5} more
                </div>
              )}
            </div>
          )}
        </div>

        {/* Achievements */}
        {achieveData.data && (
          <AchievementGrid
            unlocked={achieveData.data.badges ?? []}
            locked={achieveData.data.locked ?? []}
            completionRate={achieveData.data.completion_rate ?? 0}
            onNavigateToChat={onGtdItemClick}
          />
        )}
      </div>)}

      {/* === SKILLS TAB === */}
      {activeTab === 'skills' && (<div className="space-y-4">
        {/* Goals */}
        <div>
          <div className={ZS.sectionHeader}>
            <Target className="h-3.5 w-3.5 text-muted-foreground" />
            <span className={ZS.body + ' font-medium text-muted-foreground'}>
              {t('zenskill.panel.goals.title', 'Goals')} ({goals.length})
            </span>
          </div>
          {goals.length === 0 ? (
            <div className={ZS.emptyState + ' pl-5'}>{t('zenskill.panel.goals.empty', '暂无目标')}</div>
          ) : (
            <div className="space-y-0.5">
              {goals.map((g, i) => (
                <div key={i} className={ZS.body + ' rounded px-2 py-0.5 flex items-center gap-1.5'}>
                  <Target className="h-3 w-3 text-accent/60 shrink-0" />
                  <span className="truncate flex-1">{g.dimension || 'goal'}</span>
                  <span className="text-[10px] text-muted-foreground shrink-0">{g.current ?? 0}/{g.target ?? '-'}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Skills Browse */}
        {skillCategories.length > 0 && (
          <div>
            <div className={ZS.sectionHeader}>
              <span className="text-sm">🧩</span>
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.panel.skills.title', 'Skills')} ({totalSkills})
              </span>
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
        <HabitList habits={habits} maxItems={4} onCheckIn={(id) => runTool('habit_check', { habit_id: id })} />
      </div>)}
    </div>
  )
}
