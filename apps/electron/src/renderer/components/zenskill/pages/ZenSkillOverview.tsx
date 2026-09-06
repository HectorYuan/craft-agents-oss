/**
 * ZenSkillOverview — ZenSkill 侧边栏默认页面
 *
 * 用户点击侧边栏 "ZenSkill" 时立即看到数据概览。
 * 复用 Phase 1 提取的 CompanionCard / EnergyBar / HabitHeatmap 组件。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { Zap, TrendingUp } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { CompanionCard, type CompanionSummary } from '../panels/CompanionCard'
import { EnergyBar } from '../panels/EnergyBar'
import { HabitHeatmap } from '../panels/HabitHeatmap'
import { RadarChart } from '../panels/RadarChart'
import { filterScores } from '../panels/GrowthCard'
import { InsightsPanel } from '../panels/InsightsPanel'
import { ZS } from '../panels/tokens'

const ZENSKILL_SOURCE_SLUG = 'zenskill'

interface DashboardData {
  active_skills?: number
  installed_skills?: number
  today_sessions?: number
}

interface ReviewData {
  message?: string
  actions?: { completed?: number }
  inbox?: { pending?: number }
}

interface HabitsData {
  habits?: { completed?: Record<string, boolean> }[]
}

interface GrowthSkill {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

interface GrowthData {
  skills?: GrowthSkill[]
}

interface ZenSkillOverviewProps {
  workspaceId?: string
  initialTab?: string
  onNavigateToChat?: (msg: string) => void
}

export function ZenSkillOverview({ workspaceId, onNavigateToChat }: ZenSkillOverviewProps) {
  const { t } = useTranslation()

  const companion = useMcpTool<CompanionSummary>(workspaceId, ZENSKILL_SOURCE_SLUG, 'companion_summary', {})
  const review = useMcpTool<ReviewData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'daily_review', {})
  const habits = useMcpTool<HabitsData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'habit_analyze', { days: 7 })
  const dashboard = useMcpTool<DashboardData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'dashboard_summary', {})
  const energy = useMcpTool<{ status?: { level?: string; pct?: number } }>(workspaceId, ZENSKILL_SOURCE_SLUG, 'energy_level', {})
  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})
  const achievements = useMcpTool<{
    badges?: { id: string; icon?: string; title?: string; name?: string; progress?: number; detail?: string }[]
    locked?: { id: string; icon?: string; title?: string; name?: string; progress?: number }[]
    completion_rate?: number
  }>(workspaceId, ZENSKILL_SOURCE_SLUG, 'achievement_list', {})
  const insights = useMcpTool<{
    items?: { type?: string; title?: string; content?: string; level?: string }[]
  }>(workspaceId, ZENSKILL_SOURCE_SLUG, 'proactive_insight', {})

  const isLoading = companion.loading || review.loading || habits.loading || dashboard.loading || energy.loading
  const hasError = companion.error || review.error || habits.error || dashboard.error || energy.error
  const anyData = companion.data || review.data || habits.data || dashboard.data

  const firstHabitCompleted = habits.data?.habits?.[0]?.completed

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.overview.title', 'Overview')}</div>
              <div className={ZS.subtitle}>{t('zenskill.overview.subtitle', 'Your daily overview')}</div>
            </div>
          </div>
          {isLoading && !anyData && (
            <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
              <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {hasError && !anyData && (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>
          {companion.error || review.error || habits.error || dashboard.error || energy.error}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* Loading skeleton */}
          {isLoading && !anyData && (
            <div className="space-y-3">
              <div className={`${ZS.skeleton} w-48`} />
              <div className={`${ZS.skeleton} w-32`} />
              <div className={`${ZS.skeleton} w-64`} />
            </div>
          )}

          {/* Companion card */}
          {companion.data && (
            <CompanionCard
              companion={companion.data}
              dailyReviewMsg={review.data?.message}
              onNavigateToChat={onNavigateToChat}
            />
          )}

          {/* Stats grid */}
          {dashboard.data && (
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className={ZS.card}>
                <div className="text-muted-foreground">{t('zenskill.overview.skills', 'Skills')}</div>
                <div className="text-lg font-semibold">
                  {dashboard.data.installed_skills ?? dashboard.data.active_skills ?? 0}
                </div>
              </div>
              <div className={ZS.card}>
                <div className="text-muted-foreground">{t('zenskill.overview.sessions', 'Sessions')}</div>
                <div className="text-lg font-semibold">
                  {dashboard.data.today_sessions ?? 0}
                </div>
              </div>
              <div className={ZS.card}>
                <div className="text-muted-foreground flex items-center gap-1">
                  {t('zenskill.overview.energy', 'Energy')}
                </div>
                <div className="text-lg font-semibold capitalize">
                  {energy.data?.status?.level ?? '—'}
                </div>
              </div>
            </div>
          )}

          {/* Energy bar (if companion not available but energy is) */}
          {!companion.data && energy.data?.status && (
            <div className={ZS.card}>
              <EnergyBar
                level={energy.data.status.level ?? 'unknown'}
                pct={energy.data.status.pct ?? 0}
              />
            </div>
          )}

          {/* Habit heatmap */}
          {firstHabitCompleted && (
            <div className={ZS.card}>
              <div className={ZS.sectionHeader}>
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.overview.habits', 'Habits')}
                </span>
              </div>
              <HabitHeatmap completed={firstHabitCompleted} days={7} />
            </div>
          )}

          {/* Growth radar chart — first skill with scores */}
          {growth.data?.skills?.[0]?.scores && (
            <div className={ZS.card}>
              <div className={ZS.sectionHeader}>
                <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.overview.growth', 'Growth')} — {growth.data.skills[0].skill_id}
                </span>
                <span className={ZS.micro + ' text-muted-foreground/60 ml-auto'}>
                  {growth.data.skills[0].level}
                </span>
              </div>
              <div className="flex justify-center">
                <RadarChart scores={filterScores(growth.data.skills[0].scores)} size={180} />
              </div>
            </div>
          )}

          {/* Achievements — unlocked badges + next to unlock */}
          {achievements.data && (achievements.data.badges?.length ?? 0) > 0 && (
            <div className={ZS.card}>
              <div className={ZS.sectionHeader}>
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.overview.achievements', 'Achievements')} ({achievements.data.badges!.length}/{(achievements.data.badges?.length ?? 0) + (achievements.data.locked?.length ?? 0)})
                </span>
                {achievements.data.completion_rate != null && (
                  <span className={ZS.micro + ' text-muted-foreground/60 ml-auto'}>
                    {Math.round(achievements.data.completion_rate * 100)}%
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                {achievements.data.badges!.slice(0, 8).map((b) => (
                  <span key={b.id} className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent inline-flex items-center gap-1"
                    title={b.detail}>
                    {b.icon || '🏅'} {b.title || b.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Proactive insights — 使用 InsightsPanel 组件 */}
          {insights.data && (insights.data.items?.length ?? 0) > 0 && (
            <div className={ZS.card}>
              <InsightsPanel
                insights={insights.data.items!.map(item => ({
                  type: item.type || 'info',
                  title: item.title || '',
                  content: item.content || '',
                  level: item.level || 'low',
                  id: item.title,
                }))}
                maxItems={5}
                variant="compact"
                showHeader={false}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
