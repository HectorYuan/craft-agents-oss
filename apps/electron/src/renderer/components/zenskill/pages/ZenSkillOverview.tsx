/**
 * ZenSkillOverview — ZenSkill 侧边栏默认页面
 *
 * 用户点击侧边栏 "ZenSkill" 时立即看到数据概览。
 * 复用 Phase 1 提取的 CompanionCard / EnergyBar / HabitHeatmap 组件。
 */
import React, { useCallback, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Zap, TrendingUp, Share2 } from 'lucide-react'
import { toast } from 'sonner'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { CompanionCard, type CompanionSummary } from '../panels/CompanionCard'
import { EnergyBar } from '../panels/EnergyBar'
import { PageToChatBridge } from '../PageToChatBridge'
import { HabitHeatmap } from '../panels/HabitHeatmap'
import { RadarChart } from '../panels/RadarChart'
import { filterScores } from '../panels/GrowthCard'
import { InsightsPanel } from '../panels/InsightsPanel'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { ZS } from '../panels/tokens'

const ZENSKILL_SOURCE_SLUG = 'zenskill'

interface ShareCardPayload {
  image_base64?: string
  mime?: string
  html_path?: string
  png_path?: string
}

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

  // 核心数据：立即加载
  const companion = useMcpTool<CompanionSummary>(workspaceId, ZENSKILL_SOURCE_SLUG, 'companion_summary', {})
  const review = useMcpTool<ReviewData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'daily_review', {})
  const dashboard = useMcpTool<DashboardData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'dashboard_summary', {})
  const energy = useMcpTool<{ status?: { level?: string; pct?: number } }>(workspaceId, ZENSKILL_SOURCE_SLUG, 'energy_level', {})

  // 次要数据：延迟 500ms 加载（parked hook 模式）
  const [secondaryLoaded, setSecondaryLoaded] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSecondaryLoaded(true), 500)
    return () => clearTimeout(timer)
  }, [])

  const habits = useMcpTool<HabitsData>(secondaryLoaded ? workspaceId : undefined, ZENSKILL_SOURCE_SLUG, 'habit_analyze', { days: 7 })
  const growth = useMcpTool<GrowthData>(secondaryLoaded ? workspaceId : undefined, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})
  const achievements = useMcpTool<{
    badges?: { id: string; icon?: string; title?: string; name?: string; progress?: number; detail?: string }[]
    locked?: { id: string; icon?: string; title?: string; name?: string; progress?: number }[]
    completion_rate?: number
  }>(secondaryLoaded ? workspaceId : undefined, ZENSKILL_SOURCE_SLUG, 'achievement_list', {})
  const insights = useMcpTool<{
    items?: { type?: string; title?: string; content?: string; level?: string }[]
  }>(secondaryLoaded ? workspaceId : undefined, ZENSKILL_SOURCE_SLUG, 'proactive_insight', {})

  const isLoading = companion.loading || review.loading || habits.loading || dashboard.loading || energy.loading
  const hasError = companion.error || review.error || habits.error || dashboard.error || energy.error
  const anyData = companion.data || review.data || habits.data || dashboard.data

  const firstHabitCompleted = habits.data?.habits?.[0]?.completed

  // MVP-1 PageToChatBridge prompt — energy / todo snapshot as a planning
  // request; companion_summary is the richest source, energy/daily_review
  // are the fallbacks. All reads defensive (contracts pending).
  const buildBridgePrompt = useCallback((data: {
    companion?: CompanionSummary | null
    energy?: { status?: { level?: string; pct?: number } } | null
    review?: { inbox?: { pending?: number }; actions?: { completed?: number } } | null
  }) => {
    const energy = data.companion?.energy ?? data.energy?.status
    const level = typeof energy?.level === 'string' ? energy.level : '未知'
    const pct = typeof energy?.pct === 'number' ? Math.round(energy.pct * 100) : null
    const pendingActions = data.companion?.pending_actions ?? 0
    const inboxPending = data.companion?.inbox_pending ?? data.review?.inbox?.pending ?? 0
    const doneToday = data.review?.actions?.completed ?? 0

    return `我正在查看 ZenSkill 总览页。当前能量状态：${level}` +
      (pct !== null ? `（${pct}%）` : '') +
      `，待处理行动 ${pendingActions} 个，收件箱待整理 ${inboxPending} 条，今日已完成 ${doneToday} 项。` +
      ` 帮我规划接下来的安排。`
  }, [])

  // Day 1 share button — share_card is a write tool (generates + saves files
  // server-side), so it is called directly on click instead of through
  // useMcpTool (which fetches on mount and refetches on every zenskill:changed
  // broadcast, regenerating the card each time). The payload carries the
  // rendered image as base64 (PNG, falling back to SVG) — open it as a Blob
  // URL preview.
  const [sharing, setSharing] = useState(false)
  const handleShare = useCallback(async () => {
    if (!workspaceId || sharing) return
    setSharing(true)
    let url: string | null = null
    try {
      const result = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'share_card', { format: 'html' })
      const data = extractMcpJson(result) as ShareCardPayload | null
      const base64 = data?.image_base64
      const mime = data?.mime || 'image/svg+xml'
      if (!base64) {
        toast.error(t('zenskill.toast.toolFailed'))
        return
      }
      const bin = atob(base64)
      const bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
      url = URL.createObjectURL(new Blob([bytes], { type: mime }))
      window.open(url, '_blank')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('zenskill.toast.toolFailed'))
    } finally {
      // Reclaim the Blob URL once the preview window has had time to load it
      if (url) setTimeout(() => URL.revokeObjectURL(url as string), 60_000)
      setSharing(false)
    }
  }, [workspaceId, sharing, t])

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
          <div className="flex items-center gap-3">
            {isLoading && !anyData && (
              <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
                <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
              </div>
            )}
            <button
              type="button"
              onClick={() => void handleShare()}
              disabled={!workspaceId || sharing}
              title={t('zenskill.overview.share')}
              aria-label={t('zenskill.overview.share')}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-accent disabled:opacity-40"
            >
              <Share2 className={`h-3.5 w-3.5 ${sharing ? 'animate-pulse text-accent' : ''}`} />
            </button>
            <PageToChatBridge
              pageName="ZenSkill Overview"
              workspaceId={workspaceId}
              contextData={{ companion: companion.data, energy: energy.data, review: review.data }}
              buildPrompt={buildBridgePrompt}
            />
          </div>
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
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
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
            <ErrorBoundary componentName="RadarChart">
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
            </ErrorBoundary>
          )}

          {/* Achievements + Insights 两栏布局 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Achievements */}
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

            {/* Proactive insights */}
            {insights.data && (insights.data.items?.length ?? 0) > 0 && (
              <ErrorBoundary componentName="InsightsPanel">
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
              </ErrorBoundary>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
