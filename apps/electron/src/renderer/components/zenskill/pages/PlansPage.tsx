/**
 * PlansPage — 画像 · 计划（D4.2 设计页 `user-plans`，4 件）
 *
 * 与「画像」主页的分工：主页看**全貌**（雷达/境界/成就），本页只看**计划**——
 * 里程碑时间轴、逾期转化、里程碑↔待办的绑定、计划健康读数。
 *
 * 数据与写入全部走 MCP：
 *   读  goal_progress / action_list(pending)
 *   写  action_add（里程碑转 P0 待办）/ action_done（待办勾完回流）
 * 目标本身的新建与编辑仍在画像页（goal_set / goal_update），本页只读，
 * 避免两个入口同时写同一张表。
 */
import React, { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { CalendarClock, AlertTriangle, Link2, Activity, ArrowUpRight } from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

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

interface ActionEntry {
  action_id?: string
  title?: string
  status?: string
  due_date?: string
  priority?: string
}

interface ActionData {
  actions?: ActionEntry[]
}

interface PlansPageProps {
  workspaceId?: string
}

/** 里程碑状态：完成 / 逾期 / 进行 / 未开始 */
type MilestoneState = 'done' | 'overdue' | 'active' | 'idle'

const STATE_LABEL: Record<MilestoneState, string> = {
  done: '完成', overdue: '逾期', active: '进行', idle: '未开始',
}

const STATE_CLASS: Record<MilestoneState, string> = {
  done: 'bg-success/15 text-success-text',
  overdue: 'bg-destructive/12 text-destructive',
  active: 'bg-accent/12 text-accent',
  idle: 'bg-muted text-neutral',
}

const DIM_LABEL: Record<string, string> = {
  proficiency: '熟练度', stability: '稳定性', satisfaction: '满意度',
  responsiveness: '响应力', memory: '记忆力',
}

/** 里程碑 → 待办 的标题前缀，用作绑定键（不新开字段，靠约定） */
const bindingTag = (g: GoalEntry) => `[计划] ${DIM_LABEL[g.dimension ?? ''] ?? g.dimension ?? '目标'}`

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function stateOf(g: GoalEntry): MilestoneState {
  const pct = typeof g.progress_pct === 'number'
    ? g.progress_pct
    : (typeof g.current_score === 'number' && typeof g.target_score === 'number' && g.target_score > g.start_score!)
      ? (g.current_score - (g.start_score ?? 0)) / (g.target_score - (g.start_score ?? 0)) * 100
      : 0
  if (g.status === 'completed' || pct >= 100) return 'done'
  if (g.deadline && g.deadline < todayISO()) return 'overdue'
  if (pct > 0 || g.current_score != (g.start_score ?? g.current_score)) return 'active'
  return 'idle'
}

export const PlansPage: React.FC<PlansPageProps> = ({ workspaceId }) => {
  const { t } = useTranslation()
  const goals = useMcpTool<GoalProgressData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'goal_progress', {})
  const actions = useMcpTool<ActionData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'action_list',
    { status: 'pending', limit: 100 })
  const [busy, setBusy] = useState<string | null>(null)

  const goalList = useMemo(() => {
    const d = extractMcpJson(goals.data) as GoalProgressData | null
    return d?.active ?? []
  }, [goals.data])

  const actionList = useMemo(() => {
    const d = extractMcpJson(actions.data) as ActionData | null
    return d?.actions ?? []
  }, [actions.data])

  const rows = useMemo(() => goalList.map((g) => {
    const key = bindingTag(g)
    const bound = actionList.filter((a) => (a.title ?? '').startsWith(key))
    return { goal: g, state: stateOf(g), key, bound }
  }), [goalList, actionList])

  const runTool = useCallback(async (tool: string, args: Record<string, unknown>, okMsg: string) => {
    if (!workspaceId) return false
    setBusy(tool)
    try {
      const result = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, tool, args)
      const data = extractMcpJson(result) as { ok?: boolean; success?: boolean; message?: string } | null
      if (data?.ok === false || data?.success === false) {
        toast.error(t('zenskill.toast.toolFailed'), { description: data.message })
        return false
      }
      toast.success(okMsg)
      return true
    } catch {
      toast.error(t('zenskill.toast.toolFailed'))
      return false
    } finally {
      setBusy(null)
    }
  }, [workspaceId, t])

  // C2 逾期转化：把逾期里程碑落成 P0 待办（due 今天，标题带绑定前缀）
  const convert = (g: GoalEntry) => runTool('action_add', {
    title: `${bindingTag(g)} · 逾期转化`,
    priority: 'P0',
    skill_id: 'zenskill-core',
    due_date: todayISO(),
  }, '已转为 P0 待办')

  // C3 联动：勾完待办即视为里程碑推进（回调后 action_done）
  const doneAction = (a: ActionEntry) => runTool('action_done', { action_id: a.action_id }, '待办已完成')

  const overdue = rows.filter((r) => r.state === 'overdue')
  const withTodo = rows.filter((r) => r.bound.length > 0).length
  const loading = goals.loading || actions.loading
  const failed = !!goals.error || !!actions.error

  if (!workspaceId) {
    return <div className="p-6 text-[13px] text-neutral">未连接 ZenSkill 工作区。</div>
  }

  return (
    <div className="mx-auto flex w-full max-w-[1080px] flex-col gap-4 p-4">
      {/* C1 里程碑时间轴 */}
      <section className="rounded-[14px] border border-border bg-card p-4">
        <header className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-accent" />
            <h1 className="text-[15px] font-semibold text-foreground">计划</h1>
            <span className="text-[11.5px] text-neutral">里程碑 · {rows.length} 项</span>
          </div>
          <span className="text-[11px] text-neutral">目标的新建与编辑在「画像」页</span>
        </header>

        {loading && <p className="text-[12.5px] text-neutral">载入中…</p>}
        {failed && <p className="text-[12.5px] text-destructive">读取失败，稍后重试。</p>}
        {!loading && !failed && rows.length === 0 && (
          <p className="text-[12.5px] text-neutral">还没有目标。到「画像 → 目标管理」新建第一个。</p>
        )}

        {rows.length > 0 && (
          <ul className="flex flex-col">
            {rows.map(({ goal, state, bound }, i) => (
              <li key={goal.goal_id ?? i}
                  className="flex items-start gap-3 border-l-2 pl-3 py-2"
                  style={{ borderColor: state === 'overdue' ? 'var(--destructive)' : state === 'done' ? 'var(--success)' : 'var(--border)' }}>
                <span className={`shrink-0 rounded-full px-2 py-[2px] text-[11px] ${STATE_CLASS[state]}`}>
                  {STATE_LABEL[state]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="truncate text-[13px] font-medium text-foreground">
                      {DIM_LABEL[goal.dimension ?? ''] ?? goal.dimension ?? '目标'}
                    </span>
                    <span className="text-[11px] text-neutral">
                      {typeof goal.progress_pct === 'number' ? `${Math.round(goal.progress_pct)}%` : ''}
                      {goal.deadline ? ` · 截止 ${goal.deadline}` : ''}
                    </span>
                  </div>
                  <div className="mt-1 h-[4px] w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-accent"
                         style={{ width: `${Math.max(0, Math.min(100, goal.progress_pct ?? 0))}%` }} />
                  </div>
                </div>
                {state === 'overdue' && (
                  <button type="button"
                          disabled={busy === 'action_add'}
                          onClick={() => void convert(goal)}
                          className="shrink-0 rounded-md border border-border px-2 py-1 text-[11.5px] text-accent hover:bg-accent/10 disabled:opacity-50">
                    转 P0 待办
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* C2 逾期转化 · 提示 + 动作 */}
      {overdue.length > 0 && (
        <section className="rounded-[14px] border border-destructive/30 bg-destructive/5 p-4">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <h2 className="text-[13.5px] font-semibold text-foreground">有 {overdue.length} 个里程碑逾期</h2>
          </div>
          <p className="text-[12.5px] text-neutral">
            建议转成 P0 待办并置顶「今日」；不想转的可以保留里程碑本身，只把提醒交给你。
          </p>
          <div className="mt-2 flex gap-2">
            <button type="button"
                    disabled={busy === 'action_add'}
                    onClick={() => void Promise.all(overdue.map((r) => convert(r.goal))).then(() => { /* 已由 toast 反馈 */ })}
                    className="rounded-md bg-accent px-2.5 py-1 text-[12px] text-white disabled:opacity-50">
              全部转 P0 待办
            </button>
            <button type="button"
                    onClick={() => toast.info('已忽略本次提醒（里程碑保留）')}
                    className="rounded-md border border-border px-2.5 py-1 text-[12px] text-neutral">
              保留里程碑
            </button>
          </div>
        </section>
      )}

      {/* C3 里程碑 ↔ 待办 绑定 */}
      <section className="rounded-[14px] border border-border bg-card p-4">
        <div className="mb-2 flex items-center gap-2">
          <Link2 className="h-4 w-4 text-accent" />
          <h2 className="text-[13.5px] font-semibold text-foreground">里程碑 ↔ 待办</h2>
          <span className="text-[11px] text-neutral">标题前缀「[计划] 」即视为绑定</span>
        </div>
        {rows.length === 0 && <p className="text-[12.5px] text-neutral">无里程碑可绑定。</p>}
        {rows.map(({ goal, key, bound }, i) => (
          <div key={goal.goal_id ?? i} className="border-t border-border py-2 first:border-t-0">
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] text-foreground">{key}</span>
              <span className="text-[11px] text-neutral">{bound.length} 条待办</span>
            </div>
            {bound.map((a) => (
              <div key={a.action_id} className="mt-1 flex items-center gap-2 pl-2">
                <button type="button"
                        aria-label="完成待办"
                        disabled={busy === 'action_done'}
                        onClick={() => void doneAction(a)}
                        className="h-3 w-3 rounded-sm border border-border hover:border-success" />
                <span className="truncate text-[11.5px] text-neutral">{a.title}</span>
              </div>
            ))}
            {bound.length === 0 && (
              <p className="mt-1 text-[11px] text-neutral">未绑定。点上方「转 P0 待办」可自动建一条。</p>
            )}
          </div>
        ))}
      </section>

      {/* C4 计划健康 */}
      <section className="rounded-[14px] border border-border bg-card p-4">
        <div className="mb-2 flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent" />
          <h2 className="text-[13.5px] font-semibold text-foreground">计划健康</h2>
        </div>
        <div className="flex gap-6">
          <div>
            <div className="text-[20px] font-semibold text-foreground">{withTodo}/{rows.length || 0}</div>
            <div className="text-[11px] text-neutral">有对应待办</div>
          </div>
          <div>
            <div className="text-[20px] font-semibold text-destructive">{overdue.length}</div>
            <div className="text-[11px] text-neutral">逾期</div>
          </div>
          <div>
            <div className="text-[20px] font-semibold text-success">
              {rows.filter((r) => r.state === 'done').length}
            </div>
            <div className="text-[11px] text-neutral">已完成</div>
          </div>
        </div>
        {rows.length > 0 && withTodo < rows.length && (
          <p className="mt-2 flex items-center gap-1 text-[11.5px] text-neutral">
            <ArrowUpRight className="h-3 w-3" />
            缺口 {rows.length - withTodo} 项：补一条待办，或明确「只看不做」。
          </p>
        )}
      </section>
    </div>
  )
}
