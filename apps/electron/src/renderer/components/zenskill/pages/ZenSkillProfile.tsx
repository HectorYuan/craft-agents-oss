/**
 * ZenSkillProfile — 九区用户画像页
 *
 * 展示用户成长全貌：Header + 五维雷达图 + 境界进度 + 活跃热力图 +
 * 成就墙 + 习惯追踪 + 目标管理 + 成长趋势 + 能量历史。
 * 读取全部走 useMcpTool；写入（habit_set / habit_delete / goal_set /
 * goal_update / goal_delete）直接调用 MCP 工具，刷新依赖 zenskill:changed
 * 广播（useMcpTool 内订阅），不做手动 refetch。后端工具并行开发中，
 * 所有 payload 读取均为防御式（可选链 + 字段缺失回退）。
 */
import React, { useCallback, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  User, Flame, Target, TrendingUp, Zap, Award, BarChart3, Activity,
  Plus, Trash2, Pencil, Check, X,
} from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { RadarChart } from '../panels/RadarChart'
import { filterScores } from '../panels/GrowthCard'
import { EnergyBar } from '../panels/EnergyBar'
import { PageToChatBridge } from '../PageToChatBridge'
import { ZS } from '../panels/tokens'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

interface GrowthSkill {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

interface GrowthData {
  skills?: GrowthSkill[]
  realm?: string
  realm_progress?: number
  next_realm?: string
  total_interactions?: number
  interactions_for_next?: number
  snapshots?: { scores?: Record<string, number>; timestamp?: string }[]
}

interface AchievementData {
  badges?: { id: string; icon?: string; title?: string; name?: string; progress?: number; detail?: string }[]
  locked?: { id: string; icon?: string; title?: string; name?: string; progress?: number }[]
  completion_rate?: number
}

/** habit_analyze entry — fields contract-pending, all reads defensive */
interface HabitEntry {
  id?: string
  title?: string
  target?: number
  completed?: Record<string, boolean>
  streak?: number
  completion_rate?: number
  risk?: string
}

interface HabitData {
  habits?: HabitEntry[]
}

/** goal_progress active entry — status/deadline come with goal_update, defensive */
interface GoalEntry {
  goal_id?: string
  dimension?: string
  start_score?: number
  current_score?: number
  target_score?: number
  progress_pct?: number
  status?: string
  deadline?: string
}

interface GoalProgressData {
  active?: GoalEntry[]
  completed_count?: number
  message?: string
}

/** Write-tool payload — ok:false (or success:false, goal_set style) means rejected */
interface WritePayload { ok?: boolean; success?: boolean; message?: string; error?: string }

interface EnergyData {
  status?: { level?: string; pct?: number; current_energy?: number; max_energy?: number }
  suggestions?: string[]
}

interface ReviewData {
  message?: string
  actions?: { completed?: number }
  inbox?: { pending?: number }
}

interface ZenSkillProfileProps {
  workspaceId?: string
}

const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']
const DIM_LABELS: Record<string, string> = {
  proficiency: 'Proficiency',
  stability: 'Stability',
  satisfaction: 'Satisfaction',
  responsiveness: 'Responsiveness',
  memory: 'Memory',
}

/** goal_update accepts these statuses; anything else renders raw (defensive) */
const GOAL_STATUSES = ['active', 'completed', 'cancelled']

function goalStatusBadgeClass(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-500/15 text-green-400'
    case 'cancelled': return 'bg-muted text-muted-foreground'
    default: return 'bg-accent/10 text-accent'
  }
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/** Generate 52 weeks x 7 days of heatmap data from habit snapshots */
function generateHeatmapData(habits: { completed?: Record<string, boolean> }[]): boolean[][] {
  const allDays: boolean[] = []
  for (const h of habits) {
    if (h.completed) {
      const entries = Object.values(h.completed)
      allDays.push(...entries)
    }
  }
  // Pad to 52*7 = 364 cells
  while (allDays.length < 364) allDays.push(false)
  const weeks: boolean[][] = []
  for (let w = 0; w < 52; w++) {
    weeks.push(allDays.slice(w * 7, w * 7 + 7))
  }
  return weeks
}

/** Simple line chart as SVG polyline */
function TrendLine({ values, color = 'currentColor', height = 40, width = 200 }: {
  values: number[]
  color?: string
  height?: number
  width?: number
}) {
  if (values.length < 2) return null
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width
    const y = height - ((v - min) / range) * height
    return `${x},${y}`
  }).join(' ')
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ZenSkillProfile({ workspaceId }: ZenSkillProfileProps) {
  const { t } = useTranslation()

  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})
  const achievements = useMcpTool<AchievementData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'achievement_list', {})
  const habits = useMcpTool<HabitData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'habit_analyze', { days: 28 })
  const goals = useMcpTool<GoalProgressData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'goal_progress', {})
  const energy = useMcpTool<EnergyData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'energy_level', {})
  const review = useMcpTool<ReviewData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'daily_review', {})

  // --- write tools (habit_set / habit_delete / goal_set / goal_update / goal_delete) ---
  const [busyTool, setBusyTool] = useState<string | null>(null)
  const runWrite = useCallback(async (tool: string, args: Record<string, unknown>): Promise<boolean> => {
    if (!workspaceId) return false
    setBusyTool(tool)
    try {
      const result = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, tool, args)
      const data = extractMcpJson(result) as WritePayload | null
      if (data?.ok === false || data?.success === false) {
        const reason = typeof data.message === 'string' ? data.message : typeof data.error === 'string' ? data.error : undefined
        toast.error(t('zenskill.toast.toolFailed'), { description: reason })
        return false
      }
      return true
    } catch {
      toast.error(t('zenskill.toast.toolFailed'))
      return false
    } finally {
      setBusyTool(null)
    }
  }, [workspaceId, t])

  // Two-click delete confirm — shared by habit rows and goal cards
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const confirmRef = useRef<string | null>(null)
  confirmRef.current = confirmDeleteId
  const armDelete = (id: string, onConfirm: () => void) => {
    if (confirmRef.current === id) {
      setConfirmDeleteId(null)
      onConfirm()
    } else {
      setConfirmDeleteId(id)
      setTimeout(() => setConfirmDeleteId((cur) => (cur === id ? null : cur)), 3000)
    }
  }

  // New-habit inline form (habit_set)
  const [habitFormOpen, setHabitFormOpen] = useState(false)
  const [hfTitle, setHfTitle] = useState('')
  const [hfTarget, setHfTarget] = useState('1')
  const [hfAction, setHfAction] = useState('')
  const submitHabit = async () => {
    const title = hfTitle.trim()
    if (!title || busyTool === 'habit_set') return
    const args: Record<string, unknown> = { title, skill_id: 'zenskill-core' }
    const target = parseInt(hfTarget, 10)
    if (Number.isFinite(target) && target > 0) args.target_count = target
    if (hfAction.trim()) args.action_contains = hfAction.trim()
    if (await runWrite('habit_set', args)) {
      toast.success(t('zenskill.toast.habitCreated'))
      setHfTitle('')
      setHfTarget('1')
      setHfAction('')
      setHabitFormOpen(false)
    }
  }
  const deleteHabit = (habitId: string) => {
    armDelete(habitId, () => {
      void runWrite('habit_delete', { habit_id: habitId }).then((ok) => {
        if (ok) toast.success(t('zenskill.toast.habitDeleted'))
      })
    })
  }

  // New-goal inline form (goal_set)
  const [goalFormOpen, setGoalFormOpen] = useState(false)
  const [gfDimension, setGfDimension] = useState<string>(FIVE_DIMS[0])
  const [gfTarget, setGfTarget] = useState('')
  const [gfDeadline, setGfDeadline] = useState('')
  const submitGoal = async () => {
    const target = parseInt(gfTarget, 10)
    if (!Number.isFinite(target) || target <= 0 || busyTool === 'goal_set') return
    const args: Record<string, unknown> = { dimension: gfDimension, target_score: target, skill_id: 'zenskill-core' }
    if (gfDeadline) args.deadline = gfDeadline
    if (await runWrite('goal_set', args)) {
      toast.success(t('zenskill.toast.goalCreated'))
      setGfTarget('')
      setGfDeadline('')
      setGoalFormOpen(false)
    }
  }
  // Goal inline edit (goal_update) — target_score + status per contract
  const [editingGoalId, setEditingGoalId] = useState<string | null>(null)
  const [egTarget, setEgTarget] = useState('')
  const [egStatus, setEgStatus] = useState('active')
  const startGoalEdit = (g: GoalEntry) => {
    setEditingGoalId(g.goal_id ?? null)
    setEgTarget(String(g.target_score ?? ''))
    setEgStatus(typeof g.status === 'string' && GOAL_STATUSES.includes(g.status) ? g.status : 'active')
  }
  const submitGoalEdit = async (goalId: string) => {
    const target = parseInt(egTarget, 10)
    if (!Number.isFinite(target) || target <= 0 || busyTool === 'goal_update') return
    if (await runWrite('goal_update', { goal_id: goalId, target_score: target, status: egStatus })) {
      toast.success(t('zenskill.toast.goalUpdated'))
      setEditingGoalId(null)
    }
  }
  const deleteGoal = (goalId: string) => {
    armDelete(goalId, () => {
      void runWrite('goal_delete', { goal_id: goalId }).then((ok) => {
        if (ok) toast.success(t('zenskill.toast.goalDeleted'))
      })
    })
  }

  const isLoading = growth.loading && !growth.data
  const hasError = growth.error && !growth.data

  // Derived data
  const firstSkill = growth.data?.skills?.[0]
  const radarScores = useMemo(() => {
    if (!firstSkill?.scores) return {} as Record<string, number>
    return filterScores(firstSkill.scores)
  }, [firstSkill])

  const realm = growth.data?.realm ?? '—'
  const realmProgress = growth.data?.realm_progress ?? 0
  const nextRealm = growth.data?.next_realm ?? '—'
  const totalInteractions = growth.data?.total_interactions ?? 0
  const interactionsForNext = growth.data?.interactions_for_next ?? 100

  const badges = achievements.data?.badges ?? []
  const locked = achievements.data?.locked ?? []
  const completionRate = achievements.data?.completion_rate ?? 0

  const habitEntries = useMemo(() => habits.data?.habits ?? [], [habits.data])
  const streak = habitEntries[0]?.streak ?? 0
  const heatmapData = useMemo(() => {
    return generateHeatmapData(habitEntries)
  }, [habitEntries])

  // Trend: last 100 snapshots → proficiency values
  const trendValues = useMemo(() => {
    const snapshots = growth.data?.snapshots ?? []
    return snapshots.slice(-100).map((s) => s.scores?.proficiency ?? 50)
  }, [growth.data])

  const energyLevel = energy.data?.status?.level ?? '—'
  const energyPct = energy.data?.status?.pct ?? 0
  const energySuggestions = energy.data?.suggestions ?? []

  // Day 1 PageToChatBridge prompt — five-dimension snapshot as a planning
  // request; composite/weakest read from the first skill's radar scores.
  const buildBridgePrompt = useCallback((data: { growth?: GrowthData }) => {
    const skill = data.growth?.skills?.[0]
    const scores = skill?.scores ? filterScores(skill.scores) : {}
    const values = Object.values(scores).filter((v) => typeof v === 'number')
    if (values.length === 0) return ''
    const composite = Math.round(values.reduce((a, b) => a + b, 0) / values.length)
    const weakest = Object.entries(scores)
      .filter(([, v]) => typeof v === 'number')
      .sort((a, b) => (a[1] as number) - (b[1] as number))[0]?.[0]
    const realm = data.growth?.realm
    return `我的五维能力：${composite}分` +
      (realm ? `，境界 ${realm}` : '') +
      `。最弱：${weakest ?? '-'}。帮我制定提升计划。`
  }, [])

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.profile.title', 'Profile')}</div>
              <div className={ZS.subtitle}>{t('zenskill.profile.subtitle', 'Your growth journey')}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isLoading && (
              <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
                <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
              </div>
            )}
            <PageToChatBridge
              pageName="Profile"
              workspaceId={workspaceId}
              contextData={{ growth: growth.data }}
              buildPrompt={buildBridgePrompt}
            />
          </div>
        </div>
      </div>

      {hasError && (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>{growth.error}</div>
      )}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* 1. Header: Realm + Score + Energy */}
          <div className={`${ZS.card}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-accent">{realm}</span>
                {nextRealm !== '—' && (
                  <span className="text-[9px] text-muted-foreground">
                    {t('zenskill.profile.nextRealm', 'Next:')} {nextRealm}
                  </span>
                )}
              </div>
              <span className="text-[10px] text-muted-foreground">
                {t('zenskill.profile.interactions', '{{total}} interactions', { total: totalInteractions })}
              </span>
            </div>
            {/* Realm progress bar */}
            <div className="h-1.5 rounded bg-muted/60 overflow-hidden mb-2">
              <div
                className="h-full rounded bg-accent/70 transition-all"
                style={{ width: `${Math.min(realmProgress * 100, 100)}%` }}
              />
            </div>
            <div className="flex items-center gap-1">
              <Zap className="h-3 w-3 text-muted-foreground" />
              <span className="text-[10px] text-muted-foreground">{t('zenskill.profile.energy', 'Energy')}</span>
              <span className="text-[10px] font-medium capitalize">{energyLevel}</span>
              <span className="text-[9px] text-muted-foreground ml-auto">{Math.round(energyPct * 100)}%</span>
            </div>
          </div>

          {/* 2. Five-dimension radar chart */}
          {Object.keys(radarScores).length > 0 && (
            <div className={`${ZS.card}`}>
              <div className={ZS.sectionHeader}>
                <Target className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.profile.radar', 'Five Dimensions')}
                </span>
              </div>
              <div className="flex justify-center">
                <RadarChart scores={radarScores} size={180} />
              </div>
              {/* Score labels */}
              <div className="flex justify-center gap-3 mt-2">
                {FIVE_DIMS.map((dim) => (
                  <div key={dim} className="text-center">
                    <div className="text-[9px] text-muted-foreground">{DIM_LABELS[dim] ?? dim}</div>
                    <div className="text-[10px] font-medium">{radarScores[dim] ?? 0}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 3. Realm progress (detailed) */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.realmProgress', 'Realm Progress')}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="font-medium">{realm}</span>
              <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                <div className="h-full bg-accent/70" style={{ width: `${Math.min(realmProgress * 100, 100)}%` }} />
              </div>
              <span className="text-muted-foreground">
                {totalInteractions}/{interactionsForNext}
              </span>
              {nextRealm !== '—' && <span className="font-medium">{nextRealm}</span>}
            </div>
          </div>

          {/* 4. Activity heatmap (52 weeks) */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Activity className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.activityHeatmap', 'Activity Heatmap')}
              </span>
            </div>
            <div className="overflow-x-auto">
              <div className="flex gap-px" style={{ minWidth: 52 * 10 }}>
                {heatmapData.map((week, w) => (
                  <div key={w} className="flex flex-col gap-px">
                    {week.map((day, d) => (
                      <span
                        key={d}
                        className={`h-2 w-2 rounded-[2px] ${day ? 'bg-green-500/70' : 'bg-muted/40'}`}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 5. Achievement wall */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Award className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.achievements', 'Achievements')} ({badges.length}/{badges.length + locked.length})
              </span>
              {completionRate > 0 && (
                <span className={ZS.micro + ' text-muted-foreground/60 ml-auto'}>
                  {Math.round(completionRate * 100)}%
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-1">
              {badges.map((b) => (
                <span key={b.id} className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent inline-flex items-center gap-1" title={b.detail}>
                  {b.icon || '🏅'} {b.title || b.name}
                </span>
              ))}
              {locked.slice(0, 4).map((b) => (
                <span key={b.id} className="text-[10px] px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground inline-flex items-center gap-1" title={t('zenskill.profile.locked', 'Locked')}>
                  🔒 {b.title || b.name}
                </span>
              ))}
            </div>
          </div>

          {/* 6. Habit tracking: per-habit rows + habit_set/habit_delete management */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Flame className="h-3.5 w-3.5 text-orange-400" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.habits', 'Habits')} ({habitEntries.length})
              </span>
              {streak > 0 && (
                <span className="text-[10px] text-orange-400 ml-auto">
                  🔥 {streak} {t('zenskill.profile.streak', 'day streak')}
                </span>
              )}
            </div>
            {habitEntries.length === 0 ? (
              <div className={ZS.emptyState}>{t('zenskill.profile.habitsEmpty', 'No habit data yet')}</div>
            ) : (
              <div className="space-y-1.5">
                {habitEntries.map((h) => {
                  const habitId = h.id ?? h.title ?? ''
                  if (!habitId) return null
                  const deleting = busyTool === 'habit_delete'
                  return (
                    <div key={habitId} className={ZS.hoverRow}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">{h.title || habitId}</span>
                        <div className="flex items-center gap-2 shrink-0">
                          {(h.streak ?? 0) > 0 && (
                            <span className="text-[10px] text-orange-500">🔥{h.streak}</span>
                          )}
                          <span className="text-[10px] text-muted-foreground tabular-nums">
                            {Math.round((h.completion_rate ?? 0) * 100)}%
                          </span>
                          <button
                            className={`opacity-0 group-hover:opacity-100 p-0.5 rounded shrink-0 ${
                              confirmDeleteId === habitId
                                ? 'bg-red-500/25 text-red-400'
                                : 'hover:bg-red-500/20 text-muted-foreground hover:text-red-400'
                            }`}
                            title={confirmDeleteId === habitId ? t('zenskill.gtd.calendar.deleteConfirm') : t('zenskill.profile.habits.delete')}
                            disabled={deleting || !h.id}
                            onClick={() => h.id && deleteHabit(h.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      {h.completed && (
                        <div className="flex flex-wrap gap-0.5 mt-1">
                          {Object.entries(h.completed).slice(-28).map(([day, ok]) => (
                            <span
                              key={day}
                              title={day}
                              className={`h-2.5 w-2.5 rounded-[3px] ${ok ? 'bg-green-500/70' : 'bg-muted/60'}`}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {/* habit_set inline form + toggle — bottom of the section */}
            {habitFormOpen ? (
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <input
                    value={hfTitle}
                    autoFocus
                    onChange={(e) => setHfTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing) return
                      if (e.key === 'Enter') void submitHabit()
                      if (e.key === 'Escape') setHabitFormOpen(false)
                    }}
                    placeholder={t('zenskill.profile.habits.formTitle')}
                    className={`${ZS.input} flex-1 min-w-0`}
                  />
                  <input
                    type="number"
                    min={1}
                    value={hfTarget}
                    onChange={(e) => setHfTarget(e.target.value)}
                    aria-label={t('zenskill.profile.habits.formTarget')}
                    className={`${ZS.input} w-16 shrink-0 tabular-nums`}
                  />
                  <input
                    value={hfAction}
                    onChange={(e) => setHfAction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing) return
                      if (e.key === 'Enter') void submitHabit()
                      if (e.key === 'Escape') setHabitFormOpen(false)
                    }}
                    placeholder={t('zenskill.profile.habits.formAction')}
                    className={`${ZS.input} flex-1 min-w-0 text-muted-foreground`}
                  />
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => void submitHabit()}
                    disabled={!hfTitle.trim() || busyTool === 'habit_set'}
                    className="flex items-center gap-1 px-2 py-1 text-[11px] rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"
                    title={t('zenskill.profile.habits.addTitle')}
                  >
                    <Check className="h-3 w-3" />
                    {t('zenskill.gtd.actions.editSave', 'Save')}
                  </button>
                  <button
                    onClick={() => setHabitFormOpen(false)}
                    className="flex items-center gap-1 px-2 py-1 text-[11px] rounded text-muted-foreground hover:bg-muted/60"
                    title={t('zenskill.gtd.projects.cancel', 'Cancel')}
                  >
                    <X className="h-3 w-3" />
                    {t('zenskill.gtd.projects.cancel', 'Cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setHabitFormOpen(true)}
                disabled={!workspaceId || busyTool === 'habit_set'}
                className="mt-2 flex items-center gap-1 px-2 py-1 text-[11px] rounded text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
                title={t('zenskill.profile.habits.addTitle')}
              >
                <Plus className="h-3 w-3" />
                {t('zenskill.profile.habits.add')}
              </button>
            )}
          </div>

          {/* 6b. Goal management: goal_progress cards + goal_set/goal_update/goal_delete */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Target className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.goals')} ({goals.data?.active?.length ?? 0})
              </span>
            </div>
            {(goals.data?.active?.length ?? 0) === 0 ? (
              <div className={ZS.emptyState}>{t('zenskill.profile.goals.empty')}</div>
            ) : (
              <div className="space-y-2">
                {(goals.data?.active ?? []).map((g, i) => {
                  const goalId = g.goal_id ?? ''
                  if (!goalId) return null
                  const dimLabel = DIM_LABELS[g.dimension ?? ''] ?? g.dimension ?? '—'
                  const current = typeof g.current_score === 'number' ? g.current_score : 0
                  const target = typeof g.target_score === 'number' ? g.target_score : 0
                  const pct = typeof g.progress_pct === 'number'
                    ? g.progress_pct
                    : target > 0 ? Math.min((current / target) * 100, 100) : 0
                  const rawStatus = typeof g.status === 'string' ? g.status : 'active'
                  const statusLabel = GOAL_STATUSES.includes(rawStatus)
                    ? t(`zenskill.profile.goals.status.${rawStatus}`)
                    : rawStatus
                  return (
                    <div key={goalId || i} className={ZS.hoverRow}>
                      {editingGoalId === goalId ? (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={egTarget}
                            autoFocus
                            onChange={(e) => setEgTarget(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.nativeEvent.isComposing) return
                              if (e.key === 'Enter') void submitGoalEdit(goalId)
                              if (e.key === 'Escape') setEditingGoalId(null)
                            }}
                            aria-label={t('zenskill.profile.goals.editTarget')}
                            className={`${ZS.input} w-16 tabular-nums`}
                          />
                          <select
                            value={egStatus}
                            onChange={(e) => setEgStatus(e.target.value)}
                            aria-label={t('zenskill.profile.goals.editStatus')}
                            className="text-xs bg-muted/40 rounded px-1 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
                          >
                            {GOAL_STATUSES.map((s) => (
                              <option key={s} value={s}>{t(`zenskill.profile.goals.status.${s}`)}</option>
                            ))}
                          </select>
                          <button
                            onClick={() => void submitGoalEdit(goalId)}
                            disabled={busyTool === 'goal_update'}
                            className="p-1 rounded hover:bg-green-500/20 text-green-400 disabled:opacity-40"
                            title={t('zenskill.gtd.actions.editSave', 'Save')}
                          >
                            <Check className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => setEditingGoalId(null)}
                            className="p-1 rounded hover:bg-muted/60 text-muted-foreground"
                            title={t('zenskill.gtd.actions.editCancel', 'Cancel')}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className="truncate font-medium">{dimLabel}</span>
                              <span className={`text-[9px] px-1 py-px rounded shrink-0 ${goalStatusBadgeClass(rawStatus)}`}>
                                {statusLabel}
                              </span>
                              {g.deadline && (
                                <span className="text-[9px] text-muted-foreground shrink-0 tabular-nums">{g.deadline}</span>
                              )}
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                              <span className="text-[10px] text-muted-foreground tabular-nums">
                                {current}/{target}
                              </span>
                              <button
                                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent"
                                title={t('zenskill.profile.goals.edit')}
                                disabled={!workspaceId}
                                onClick={() => startGoalEdit(g)}
                              >
                                <Pencil className="h-3 w-3" />
                              </button>
                              <button
                                className={`opacity-0 group-hover:opacity-100 p-0.5 rounded shrink-0 ${
                                  confirmDeleteId === goalId
                                    ? 'bg-red-500/25 text-red-400'
                                    : 'hover:bg-red-500/20 text-muted-foreground hover:text-red-400'
                                }`}
                                title={confirmDeleteId === goalId ? t('zenskill.gtd.calendar.deleteConfirm') : t('zenskill.profile.goals.delete')}
                                disabled={busyTool === 'goal_delete'}
                                onClick={() => deleteGoal(goalId)}
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                              <div className="h-full bg-accent/70" style={{ width: `${Math.min(pct, 100)}%` }} />
                            </div>
                            <span className="text-[9px] text-muted-foreground tabular-nums">{Math.round(pct)}%</span>
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            {/* goal_set inline form + toggle — bottom of the section */}
            {goalFormOpen ? (
              <div className="mt-2 space-y-1.5">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <select
                    value={gfDimension}
                    onChange={(e) => setGfDimension(e.target.value)}
                    aria-label={t('zenskill.profile.goals.formDimension')}
                    className="text-xs bg-muted/40 rounded px-1 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
                  >
                    {FIVE_DIMS.map((d) => (
                      <option key={d} value={d}>{DIM_LABELS[d] ?? d}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={gfTarget}
                    onChange={(e) => setGfTarget(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing) return
                      if (e.key === 'Enter') void submitGoal()
                      if (e.key === 'Escape') setGoalFormOpen(false)
                    }}
                    placeholder={t('zenskill.profile.goals.formTarget')}
                    className={`${ZS.input} w-20 tabular-nums`}
                  />
                  <input
                    type="date"
                    value={gfDeadline}
                    onChange={(e) => setGfDeadline(e.target.value)}
                    aria-label={t('zenskill.profile.goals.formDeadline')}
                    className={`${ZS.input} w-36 text-muted-foreground`}
                  />
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => void submitGoal()}
                    disabled={!gfTarget || busyTool === 'goal_set'}
                    className="flex items-center gap-1 px-2 py-1 text-[11px] rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"
                    title={t('zenskill.profile.goals.addTitle')}
                  >
                    <Check className="h-3 w-3" />
                    {t('zenskill.gtd.actions.editSave', 'Save')}
                  </button>
                  <button
                    onClick={() => setGoalFormOpen(false)}
                    className="flex items-center gap-1 px-2 py-1 text-[11px] rounded text-muted-foreground hover:bg-muted/60"
                    title={t('zenskill.gtd.projects.cancel', 'Cancel')}
                  >
                    <X className="h-3 w-3" />
                    {t('zenskill.gtd.projects.cancel', 'Cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setGoalFormOpen(true)}
                disabled={!workspaceId || busyTool === 'goal_set'}
                className="mt-2 flex items-center gap-1 px-2 py-1 text-[11px] rounded text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
                title={t('zenskill.profile.goals.addTitle')}
              >
                <Plus className="h-3 w-3" />
                {t('zenskill.profile.goals.add')}
              </button>
            )}
          </div>

          {/* 7. Growth trend (proficiency over last 100 snapshots) */}
          {trendValues.length > 1 && (
            <div className={`${ZS.card}`}>
              <div className={ZS.sectionHeader}>
                <BarChart3 className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.profile.growthTrend', 'Growth Trend')}
                </span>
              </div>
              <div className="flex justify-center">
                <TrendLine values={trendValues} color="hsl(var(--accent))" height={50} width={280} />
              </div>
            </div>
          )}

          {/* 8. Energy history: suggestions + trend */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Zap className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.energyHistory', 'Energy History')}
              </span>
            </div>
            <EnergyBar level={energyLevel} pct={energyPct} />
            {energySuggestions.length > 0 && (
              <div className="mt-2 space-y-1">
                {energySuggestions.slice(0, 3).map((s, i) => (
                  <div key={i} className="text-[10px] text-muted-foreground/80 flex items-start gap-1">
                    <span className="text-accent">•</span> {s}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
