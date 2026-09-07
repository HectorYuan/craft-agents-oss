/**
 * ZenSkillProfile — 九区用户画像页
 *
 * 展示用户成长全貌：Header + 五维雷达图 + 境界进度 + 活跃热力图 +
 * 成就墙 + 习惯追踪 + 成长趋势 + 能量历史。
 * 数据全部来自 useMcpTool。
 */
import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { User, Flame, Target, TrendingUp, Zap, Award, BarChart3, Activity } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { RadarChart } from '../panels/RadarChart'
import { filterScores } from '../panels/GrowthCard'
import { EnergyBar } from '../panels/EnergyBar'
import { ZS } from '../panels/tokens'

const ZENSKILL_SOURCE_SLUG = 'zenskill'

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

interface HabitData {
  habits?: { completed?: Record<string, boolean>; streak?: number }[]
}

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
  const energy = useMcpTool<EnergyData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'energy_level', {})
  const review = useMcpTool<ReviewData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'daily_review', {})

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

  const streak = habits.data?.habits?.[0]?.streak ?? 0
  const firstHabitCompleted = habits.data?.habits?.[0]?.completed
  const heatmapData = useMemo(() => {
    return generateHeatmapData(habits.data?.habits ?? [])
  }, [habits.data])

  // Trend: last 100 snapshots → proficiency values
  const trendValues = useMemo(() => {
    const snapshots = growth.data?.snapshots ?? []
    return snapshots.slice(-100).map((s) => s.scores?.proficiency ?? 50)
  }, [growth.data])

  const energyLevel = energy.data?.status?.level ?? '—'
  const energyPct = energy.data?.status?.pct ?? 0
  const energySuggestions = energy.data?.suggestions ?? []

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
          {isLoading && (
            <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
              <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
            </div>
          )}
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

          {/* 6. Habit tracking: streak + 28-day grid */}
          <div className={`${ZS.card}`}>
            <div className={ZS.sectionHeader}>
              <Flame className="h-3.5 w-3.5 text-orange-400" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.profile.habits', 'Habits')}
              </span>
              {streak > 0 && (
                <span className="text-[10px] text-orange-400 ml-auto">
                  🔥 {streak} {t('zenskill.profile.streak', 'day streak')}
                </span>
              )}
            </div>
            {firstHabitCompleted ? (
              <div className="flex flex-wrap gap-0.5">
                {Object.entries(firstHabitCompleted).slice(-28).map(([day, ok]) => (
                  <span
                    key={day}
                    title={day}
                    className={`h-3 w-3 rounded-[3px] ${ok ? 'bg-green-500/70' : 'bg-muted/60'}`}
                  />
                ))}
              </div>
            ) : (
              <div className={ZS.emptyState}>{t('zenskill.profile.habitsEmpty', 'No habit data yet')}</div>
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
