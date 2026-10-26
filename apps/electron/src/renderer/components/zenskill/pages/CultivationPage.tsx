/**
 * CultivationPage — 修炼域（第十八批 D 段 D2）
 *
 * 设计真相源：ardot `6:372`「修炼域 · Info_Page」（容器 `6:432`）。
 * ★ 本页是**设计稿的运行时投影**：三区主体 + 三张卡的结构照抄稿子，
 *   但每个读数都来自**真数据**（MCP 工具），不写死、不占位。
 *
 * 页面结构（稿 `6:432` 自上而下）：
 *   Hero          当前回路 · <概念>            （`6:373`）
 *   Section       当前回路                     （`6:376`）主区
 *   Section       轮次看板 · 阶段分布           （`6:384`）侧区 A
 *   Section       成长 · 修炼                   （`6:389`）侧区 B
 *   Card          今日习惯                     （`17:151`）
 *   Card          每日一思                     （`17:157`）
 *   Section       同修建议                     （`6:401`）
 *
 * 数据源（全部 MCP 只读 + 一个写）：
 *   zenloop_status     当前回路 / 通道分布
 *   task_progressions  进行中动作
 *   growth_dashboard   技能等级 / 五维能力
 *   achievement_list   境界里程碑 / 成就
 *   companion_summary  能量 / 洞察
 *   habit_analyze      今日习惯（含能量点 / 注意力分钟两套量纲）
 *   habit_check        打卡（唯一写操作）
 *   daily_thought      每日一思引文（逐字，出处可核）
 *   persona_mode       人称模式 + 同修建议行（按当前人称取变体）
 *
 * ★ 量纲纪律：能量 = **点**，注意力 = **分钟**，两者**不相加、不换算**
 *   （真相源 `specs/design/attention_budget.json`）。
 * ★ 空状态一律给**下一步动作**（不写「暂无数据」）。
 * ★ 加载/错误态复用 craft 既有形态：Spinner（不用 shimmer 条）+ 错误卡。
 */
import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Sparkles,
  Target,
  ListChecks,
  Trophy,
  Quote,
  Lightbulb,
  RefreshCw,
  CircleDot,
} from 'lucide-react'
import { Spinner } from '@craft-agent/ui'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { EnergyBar } from '../panels/EnergyBar'
import { GrowthCard, filterScores } from '../panels/GrowthCard'
import { AchievementGrid } from '../panels/AchievementGrid'
import { CompanionCard } from '../panels/CompanionCard'
import { isNoDataSourceError } from '../panels/errors'
import { LoadingBlock, ErrorBlock, NoDataSourceBlock } from '../panels/stateBlocks'
import { HabitList, type Habit } from '../panels/HabitList'
import { IncubatingPanel } from '../panels/IncubatingPanel'
import { RadarChart } from '../panels/RadarChart'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

/* ------------------------------------------------------------------ 数据形状 */

interface ZenloopStatusData {
  active?: number
  by_channel?: Record<string, number>
  top?: { id: string; channel: string; maturity: number; concept: string }[]
  message?: string
}

interface ProgressionData {
  progressions?: { trigger?: string; suggestion?: string; prompt?: string; priority?: string }[]
}

interface GrowthData {
  count?: number
  skills?: {
    skill_id: string
    level?: string
    usage_count?: number
    success_rate?: number
    scores?: Record<string, number>
  }[]
}

interface AchievementData {
  badges?: {
    id: string
    title?: string
    tier?: string
    icon?: string
    description?: string
    unlocked?: boolean
    progress?: number
    detail?: string
  }[]
  locked?: {
    id: string
    title?: string
    tier?: string
    icon?: string
    description?: string
    progress?: number
    detail?: string
  }[]
  completion_rate?: number
}

interface CompanionData {
  mood?: string
  greeting?: string
  energy?: { level: string; pct: number; current: number; max: number }
  top_insight?: { type: string; title: string; content: string } | null
  inbox_pending?: number
  pending_actions?: number
  due_today?: number
  overdue?: number
}

interface HabitAnalyzeData {
  days?: number
  habits?: {
    id: string
    title: string
    target: number
    completed: Record<string, boolean>
    streak: number
    best_streak: number
    completion_rate: number
    risk: string
    energy_cost: number
    attention_cost: number
    cadence: string
    reserve: boolean
  }[]
  today?: {
    date: string
    reserved_energy: number
    reserved_attention: number
    spent_energy: number
    spent_attention: number
    due: { id: string; title: string; energy_cost: number; attention_cost: number }[]
  }
}

interface DailyThoughtData {
  ok?: boolean
  date?: string
  text?: string
  source?: string
  chapter?: string
  author?: string
  theme?: string
  message?: string
}

interface PersonaData {
  mode?: string
  mode_name?: string
  current_lines?: Record<string, string>
  message?: string
}

/** 稿 `6:404` = 修炼域 · 建议卡（真相源 `copy_terminology.json` 的 spokenLines 键） */
const ADVICE_LINE_ID = '6:404'

/** 通道顺序 = 稿 `6:387` 的排列：反思 · 巩固 · 洞见 · 净化 */
const CHANNEL_ORDER = ['reflect', 'consolidate', 'insight', 'purify'] as const

/* ------------------------------------------------------------------ 小部件 */

/** 稿里的区块标题（15px / SemiBold）+ 内容卡（radius 8 + shadow-minimal） */
function Section({
  icon,
  title,
  children,
}: {
  icon?: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-1.5">
        {icon}
        <h2 className="text-[15px] font-semibold text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  )
}

/** 稿 `6:378` / `6:386` 的内容卡：radius 8 + 双层阴影（shadow-minimal） */
function ContentCard({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={`rounded-[8px] bg-card shadow-minimal px-4 py-4 ${className}`}
    >
      {children}
    </div>
  )
}

/** 稿 `17:151` / `17:157` 的卡：radius 8 + 双层阴影 */
function DesignCard({
  title,
  icon,
  children,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="rounded-[8px] bg-card shadow-minimal px-3 py-2.5 space-y-1.5">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="text-[11.25px] font-semibold text-foreground">{title}</span>
      </div>
      {children}
    </div>
  )
}

/** 稿 `6:391` 的 Info_Table 行：左标签 120 宽 + 右值 */
function TableRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center gap-0 px-[15px] py-[9.375px]">
      <span className="w-[120px] shrink-0 text-[13.125px] text-muted-foreground">{label}</span>
      <span className="flex-1 text-[13.125px] text-foreground">{value}</span>
    </div>
  )
}

/** 稿 `6:403` 的 Info_Alert：琥珀底 + 描边（craft 的 --info 是琥珀） */
function AlertBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[8px] border border-info/30 bg-info/5 px-[15px] py-[11.25px]">
      {children}
    </div>
  )
}

/**
 * 「工作区没有 ZenSkill 数据源」的判定 → 见 `panels/errors.ts`（纯函数，可被测试导入）。
 * ★ 这**不是故障** —— 重试无用 ⇒ 不能落进错误卡（会误报为故障 + 给出无用的「重试」）。
 */

/* ------------------------------------------------------------------ 页面 */

export function CultivationPage({
  workspaceId,
  onNavigateToChat,
}: {
  workspaceId?: string
  initialTab?: string
  onNavigateToChat?: (msg: string) => void
}) {
  const { t } = useTranslation()
  const [busyHabit, setBusyHabit] = useState<string | null>(null)

  /* 主区：当前回路 */
  const loop = useMcpTool<ZenloopStatusData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'zenloop_status', {})
  // ★ peek=true：**只看不推** —— 推进建议的主动推送额度属于 GTD 工作台，
  //   本页只展示同一批建议，不该替它消耗频控额度（DAILY_LIMIT=3 + 24h 冷却）。
  const actions = useMcpTool<ProgressionData>(
    workspaceId, ZENSKILL_SOURCE_SLUG, 'task_progressions', { limit: 3, peek: true },
  )

  /* 侧区 B：成长 */
  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})
  const achievements = useMcpTool<AchievementData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'achievement_list', {})
  const companion = useMcpTool<CompanionData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'companion_summary', {})

  /* 三张卡 */
  const habits = useMcpTool<HabitAnalyzeData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'habit_analyze', { days: 7 })
  const thought = useMcpTool<DailyThoughtData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'daily_thought', {})
  const persona = useMcpTool<PersonaData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'persona_mode', { action: 'status' })

  /* ---- 当前回路：概念 + 通道分布 ---- */
  const topConcept = loop.data?.top?.[0]?.concept?.trim() || ''
  const byChannel = loop.data?.by_channel ?? {}
  const channelCount = Object.keys(byChannel).length
  const activeCount = loop.data?.active ?? 0

  /* ---- 回合看板：按稿 `6:387` 的顺序列通道 ---- */
  const channelLine = CHANNEL_ORDER.filter((c) => (byChannel[c] ?? 0) > 0)
    .map((c) => `${t(`zenskill.gtd.incubating.channel.${c}`)} · ${byChannel[c]}`)
    .join('　')

  /* ---- 成长：境界 / 技能等级 / 能量 ---- */
  const skills = growth.data?.skills ?? []
  const levelCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const s of skills) {
      const lv = s.level || '—'
      counts.set(lv, (counts.get(lv) ?? 0) + 1)
    }
    return [...counts.entries()].map(([lv, n]) => `${lv} ${n}`).join(' · ')
  }, [skills])

  const unlockedBadges = achievements.data?.badges ?? []
  const lockedBadges = achievements.data?.locked ?? []
  /** 下一个境界里程碑：level_* 且有进度 */
  const nextRealm = lockedBadges.find(
    (b) => b.id?.startsWith('level_') && (b.progress ?? 0) > 0,
  )
  const currentRealm = skills[0]?.level || '—'

  /* ---- 今日习惯：今日该做的（due）+ 今日已完成的 ---- */
  const habitRows = useMemo(() => {
    const list = habits.data?.habits ?? []
    const todayIso = habits.data?.today?.date ?? ''
    const dueIds = new Set((habits.data?.today?.due ?? []).map((d) => d.id))
    return list
      .filter((h) => dueIds.has(h.id) || h.completed?.[todayIso])
      .map((h) => ({
        id: h.id,
        title: h.title,
        streak: h.streak,
        completion_rate: h.completion_rate,
        completed: h.completed ?? {},
        completed_today: Boolean(h.completed?.[todayIso]),
        energy_cost: h.energy_cost,
        attention_cost: h.attention_cost,
      }))
  }, [habits.data])

  /** 量纲脚注：今日**已预留 + 已实扣**，两个单位分开写、不相加 */
  const habitTotals = useMemo(() => {
    const today = habits.data?.today
    return {
      energy: (today?.reserved_energy ?? 0) + (today?.spent_energy ?? 0),
      attention: (today?.reserved_attention ?? 0) + (today?.spent_attention ?? 0),
    }
  }, [habits.data])

  /** 同修建议行：按**当前人称**取变体（真相源 spokenLines['6:404']） */
  const adviceLine = persona.data?.current_lines?.[ADVICE_LINE_ID] ?? ''

  /** 陪伴卡入参：面板要的是**必填字段**，缺项补默认值（不伪造读数） */
  const companionSummary = useMemo(() => {
    if (!companion.data) return null
    return {
      mood: companion.data.mood ?? '',
      energy: companion.data.energy ?? { level: 'medium', pct: 0, current: 0, max: 0 },
      inbox_pending: companion.data.inbox_pending ?? 0,
      pending_actions: companion.data.pending_actions ?? 0,
      due_today: companion.data.due_today ?? 0,
      overdue: companion.data.overdue ?? 0,
      top_insight: companion.data.top_insight ?? null,
    }
  }, [companion.data])

  /* ---- 打卡（唯一写操作） ---- */
  const checkIn = async (habitId: string) => {
    if (!workspaceId) return
    setBusyHabit(habitId)
    try {
      const result = await window.electronAPI.callMcpTool(
        workspaceId,
        ZENSKILL_SOURCE_SLUG,
        'habit_check',
        { habit_id: habitId },
      )
      const data = extractMcpJson(result) as { ok?: boolean; message?: string } | null
      if (data?.ok === false) {
        toast.error(t('zenskill.toast.toolFailed'), { description: data?.message })
      } else {
        toast.success(t('zenskill.cultivation.habit.checked', '已打卡'))
      }
      habits.refresh()
    } catch {
      toast.error(t('zenskill.toast.toolFailed'))
    } finally {
      setBusyHabit(null)
    }
  }

  const pageLoading =
    loop.loading && !loop.data && growth.loading && !growth.data && habits.loading && !habits.data

  // ★ 无权限态（稿 `24:20` SystemMessage/system）：工作区没有 ZenSkill 数据源
  //   ⇒ 整页只给这一态，不逐块报错（8 块同样的错误卡 = 噪声）。
  const noDataSource = [
    loop.error,
    actions.error,
    growth.error,
    achievements.error,
    companion.error,
    habits.error,
    thought.error,
    persona.error,
  ].some(isNoDataSourceError)

  const header = (
    <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-accent" />
        <div>
          <div className={ZS.title}>{t('zenskill.cultivation.title', '修炼域')}</div>
          <div className={ZS.subtitle}>
            {t('zenskill.cultivation.subtitle', '和智能体一起，把成长变成看得见的回路')}
          </div>
        </div>
      </div>
    </div>
  )

  if (noDataSource) {
    return (
      <div className="flex flex-col h-full min-w-0 overflow-x-hidden">
        {header}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="mx-auto w-full max-w-[840px] space-y-5">
            <NoDataSourceBlock />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-w-0 overflow-x-hidden">
      {/* Header */}
      {header}

      {/* Content —— 稿 `6:432`：单列、内容区 840 居中 */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto w-full max-w-[840px] space-y-5">
          {pageLoading && <LoadingBlock label={t('zenskill.state.loading', '读取中')} />}

          {/* Hero（稿 6:373） */}
          <div className="space-y-0.5">
            <div className="text-[15px] font-semibold text-foreground">
              {topConcept
                ? t('zenskill.cultivation.hero.loopNamed', '当前回路 · {{concept}}', { concept: topConcept })
                : t('zenskill.cultivation.hero.loop', '当前回路')}
            </div>
            <div className="text-[13.125px] text-muted-foreground">
              {activeCount > 0
                ? t('zenskill.cultivation.hero.active', '{{n}} 条在跑 · {{channels}} 个通道', {
                    n: activeCount,
                    channels: channelCount,
                  })
                : t('zenskill.cultivation.hero.idle', '现在没有在跑的回路 —— 去「ZenLoop」启动一轮')}
            </div>
          </div>

          {/* Section 当前回路（主区，稿 6:376） */}
          <Section
            icon={<Target className="h-3.5 w-3.5 text-muted-foreground" />}
            title={t('zenskill.cultivation.section.loop', '当前回路')}
          >
            <ContentCard>
              {loop.error && <ErrorBlock message={loop.error} onRetry={loop.refresh} />}
              {!loop.error && loop.loading && !loop.data && (
                <LoadingBlock label={t('zenskill.state.loading', '读取中')} />
              )}
              {loop.data && (
                <div className="space-y-2">
                  {/* 本轮目标（稿 6:381/6:382） */}
                  <div className="space-y-0.5">
                    <div className="text-[11.25px] font-medium text-muted-foreground">
                      {t('zenskill.cultivation.section.goal', '本轮目标')}
                    </div>
                    <div className="text-[13.125px] font-medium text-foreground">
                      {topConcept || t('zenskill.cultivation.section.goalEmpty', '这一轮还没有目标 —— 去「ZenLoop」定一个')}
                    </div>
                  </div>

                  {/* 进行中动作（稿 6:383）：真数据 = 推进建议 */}
                  <div className="space-y-1">
                    <div className="text-[11.25px] font-medium text-muted-foreground">
                      {t('zenskill.cultivation.section.actions', '进行中动作')}
                    </div>
                    {actions.error && <ErrorBlock message={actions.error} onRetry={actions.refresh} />}
                    {!actions.error && (actions.data?.progressions?.length ?? 0) === 0 && (
                      <div className="text-[13.125px] text-muted-foreground">
                        {t('zenskill.cultivation.section.actionsEmpty', '暂无推进建议 —— 去「项目」域看待办')}
                      </div>
                    )}
                    {(actions.data?.progressions ?? []).map((p, i) => (
                      <div key={`${p.trigger ?? 'p'}-${i}`} className="text-[13.125px] text-foreground">
                        {p.suggestion}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </ContentCard>
          </Section>

          {/* Section 回合看板（侧区 A，稿 6:384） */}
          <Section
            icon={<CircleDot className="h-3.5 w-3.5 text-muted-foreground" />}
            title={t('zenskill.cultivation.section.board', '轮次看板 · 阶段分布')}
          >
            <ContentCard className="space-y-1">
              {loop.error && <ErrorBlock message={loop.error} onRetry={loop.refresh} />}
              {!loop.error && (
                <>
                  <div className="text-[13.125px] text-foreground">
                    {channelLine ||
                      t('zenskill.cultivation.section.boardEmpty', '还没有轮次 —— 去「ZenLoop」启动一轮')}
                  </div>
                  <div className="text-[11.25px] text-muted-foreground">
                    {t(
                      'zenskill.cultivation.section.boardLegend',
                      '轮次状态徽章：进行中 / 还没轮到 / 已完成（沿用母题，不另造）',
                    )}
                  </div>
                </>
              )}
            </ContentCard>
            {/* 孵化池明细（局部降级：面板自己兜住） */}
            <ErrorBoundary componentName="IncubatingPanel">
              <IncubatingPanel
                variant="full"
                workspaceId={workspaceId}
                sourceSlug={ZENSKILL_SOURCE_SLUG}
              />
            </ErrorBoundary>
          </Section>

          {/* Section 成长（侧区 B，稿 6:389） */}
          <Section
            icon={<Trophy className="h-3.5 w-3.5 text-muted-foreground" />}
            title={t('zenskill.cultivation.section.growth', '成长 · 修炼')}
          >
            <ContentCard className="space-y-3">
              {growth.error && <ErrorBlock message={growth.error} onRetry={growth.refresh} />}
              {!growth.error && (
                <>
                  {/* Info_Table 三行（稿 6:391） */}
                  <div className="-mx-[15px] divide-y divide-border/20">
                    <TableRow
                      label={t('zenskill.cultivation.growth.realm', '境界')}
                      value={
                        nextRealm
                          ? t(
                              'zenskill.cultivation.growth.realmNext',
                              '{{current}} → {{next}}（还差 {{pct}}%）',
                              {
                                current: currentRealm,
                                next: nextRealm.title ?? nextRealm.id,
                                pct: Math.round((nextRealm.progress ?? 0) * 100),
                              },
                            )
                          : t('zenskill.cultivation.growth.realmDone', '{{current}}（已到顶）', {
                              current: currentRealm,
                            })
                      }
                    />
                    <TableRow
                      label={t('zenskill.cultivation.growth.levels', '技能等级')}
                      value={
                        levelCounts ||
                        t('zenskill.cultivation.growth.levelsEmpty', '还没有技能记录')
                      }
                    />
                    <TableRow
                      label={t('zenskill.cultivation.growth.energy', '能量')}
                      value={
                        companion.data?.energy
                          ? t(
                              'zenskill.cultivation.growth.energyValue',
                              '{{pct}}% · {{current}}/{{max}} 点',
                              {
                                pct: Math.round((companion.data.energy.pct ?? 0) * 100),
                                current: companion.data.energy.current ?? 0,
                                max: companion.data.energy.max ?? 0,
                              },
                            )
                          : t('zenskill.cultivation.growth.energyUnknown', '读不到')
                      }
                    />
                  </div>

                  {/* 能量条 */}
                  {companion.data?.energy && (
                    <EnergyBar {...companion.data.energy} />
                  )}

                  {/* 技能成长 + 五维雷达 */}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <GrowthCard
                      skills={skills}
                      maxItems={3}
                      onNavigateToChat={onNavigateToChat}
                    />
                    {skills[0]?.scores && (
                      <div className="flex flex-col items-center">
                        <RadarChart scores={filterScores(skills[0].scores)} size={168} />
                        <span className="text-[11.25px] text-muted-foreground">
                          {skills[0].skill_id}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* 成就 */}
                  <AchievementGrid
                    unlocked={unlockedBadges}
                    locked={lockedBadges}
                    completionRate={achievements.data?.completion_rate ?? 0}
                    onNavigateToChat={onNavigateToChat}
                  />
                </>
              )}
            </ContentCard>
          </Section>

          {/* Card 今日习惯（稿 17:151） */}
          <DesignCard
            title={t('zenskill.cultivation.card.habits.title', '今日习惯')}
            icon={<ListChecks className="h-3.5 w-3.5 text-muted-foreground" />}
          >
            {habits.error && <ErrorBlock message={habits.error} onRetry={habits.refresh} />}
            {!habits.error && habits.loading && !habits.data && (
              <LoadingBlock label={t('zenskill.state.loading', '读取中')} />
            )}
            {!habits.error && habitRows.length === 0 && (
              <div className="text-[11.25px] text-muted-foreground">
                {t(
                  'zenskill.cultivation.card.habits.empty',
                  '今天还没有该打卡的习惯 —— 去「设置 · ZenSkill」加一个',
                )}
              </div>
            )}
            {habitRows.length > 0 && (
              <>
                <HabitList
                  habits={habitRows as unknown as Habit[]}
                  maxItems={4}
                  onCheckIn={busyHabit ? undefined : (id: string) => void checkIn(id)}
                />
                {/* 脚注·量纲（稿 17:156）：两个量纲分开写，不相加 */}
                <div className="text-[11.25px] text-muted-foreground">
                  {t(
                    'zenskill.cultivation.card.habits.footnote',
                    '占 {{energy}} 点能量 · {{attention}} 分钟注意力',
                    { energy: habitTotals.energy, attention: habitTotals.attention },
                  )}
                </div>
              </>
            )}
          </DesignCard>

          {/* Card 每日一思（稿 17:157） */}
          <DesignCard
            title={t('zenskill.cultivation.card.thought.title', '每日一思')}
            icon={<Quote className="h-3.5 w-3.5 text-muted-foreground" />}
          >
            {thought.error && <ErrorBlock message={thought.error} onRetry={thought.refresh} />}
            {!thought.error && thought.loading && !thought.data && (
              <LoadingBlock label={t('zenskill.state.loading', '读取中')} />
            )}
            {!thought.error && thought.data?.ok && thought.data.text && (
              <>
                {/* 引文：逐字（真相源 copy_poetry.json），出处可核 */}
                <div className="text-[15px] text-foreground">{thought.data.text}</div>
                <div className="text-[11.25px] text-muted-foreground">
                  {t('zenskill.cultivation.card.thought.source', '《{{source}}》{{chapter}}', {
                    source: thought.data.source ?? '',
                    chapter: thought.data.chapter ?? '',
                  })}
                </div>
                {/* 注解位：稿上是 d16 专属样例；运行时用引文**主题词**承接同一槽位 */}
                {thought.data.theme && (
                  <div className="text-[11.25px] text-muted-foreground/80">
                    {t('zenskill.cultivation.card.thought.theme', '主题 · {{theme}}', {
                      theme: thought.data.theme,
                    })}
                  </div>
                )}
              </>
            )}
            {!thought.error && thought.data && !thought.data.ok && (
              <div className="text-[11.25px] text-muted-foreground">
                {thought.data.message ?? t('zenskill.cultivation.card.thought.empty', '今天没有引文')}
              </div>
            )}
          </DesignCard>

          {/* Section 同修建议（稿 6:401） */}
          <Section
            icon={<Lightbulb className="h-3.5 w-3.5 text-muted-foreground" />}
            title={t('zenskill.cultivation.section.advice', '同修建议')}
          >
            <div className="space-y-2">
              {persona.error && <ErrorBlock message={persona.error} onRetry={persona.refresh} />}
              {!persona.error && (
                <AlertBox>
                  {adviceLine ? (
                    <div className="text-[13.125px] text-foreground">{adviceLine}</div>
                  ) : (
                    <div className="text-[13.125px] text-muted-foreground">
                      {t(
                        'zenskill.cultivation.section.adviceEmpty',
                        '还没有建议 —— 先记一条想法或打一次卡',
                      )}
                    </div>
                  )}
                </AlertBox>
              )}

              {/* 陪伴感摘要：能量 / 洞察 / 待办 */}
              {companionSummary && (
                <ErrorBoundary componentName="CompanionCard">
                  <CompanionCard
                    companion={companionSummary}
                    onNavigateToChat={onNavigateToChat}
                  />
                </ErrorBoundary>
              )}

              <div className="text-[11.25px] text-muted-foreground">
                {t(
                  'zenskill.cultivation.section.adviceScope',
                  '任务和行动项在「项目」域，这里只放成长与过程',
                )}
              </div>
            </div>
          </Section>
        </div>
      </div>
    </div>
  )
}
