/**
 * DomainReadout.tsx — 四域共用的 ZenSkill 读数条（第十九批 D 段）
 *
 * ★ 为什么三个域共用一个组件
 * ------------------------
 * 三个域（会话 / 项目 / 技能）读的是**同一组量纲** ⇒ 一个组件通吃，
 * 不做「会话版 / 项目版 / 技能版」三份复制（同一概念三个名字的老问题）。
 * ★ 各域的**特有内容**（项目行动 / 技能成长）由各自页面另外挂，不塞进这条读数条。
 *
 * ★ 为什么会话域落在 ChatPage（而不是「会话信息页」）
 * ----------------------------------------------
 * 实测：craft 只有 `ProjectInfoPage` / `SkillInfoPage` / `SourceInfoPage`，
 * **没有「会话信息页」** ⇒ 稿上的「会话 · Info_Page」在运行时**没有对应页面**。
 * ⇒ 会话域的落点只能是**对话页本身**：读数条挂在 `PanelHeader` 与 `ChatDisplay` 之间
 * ⇒ ★ 好处：读数出现在**用户真正工作的地方**（这正是「四种量纲在用户工作的地方看不见」
 *   这个根因的正解）。
 *
 * ★ 读什么（**分列不相加**）
 * -----------------------
 *   轮次   —— `zenloop_status`（概念 / 通道）⇒ 无量纲
 *   能量   —— `companion_summary.energy`（current / max）⇒ **点**
 *   注意力 —— `attention_status.status.remaining_minutes` ⇒ **分钟**
 *
 * ★ 「至多」的含义：会话侧读不到近期深度占用时，注意力值只是**上限**
 *   ⇒ 标注「至多」（与 GTD 工作台同一口径，第十八批 C 段既定）。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'
import { ReadoutStrip, type ReadoutCell } from './ReadoutStrip'
import { isNoDataSourceError } from './errors'

export interface ZenloopStatusData {
  active?: number
  by_channel?: Record<string, number>
  top?: { id: string; channel: string; maturity: string; concept: string }[]
  message?: string
}

export interface EnergyLevelData {
  status?: {
    level?: string
    pct?: number
    current_energy?: number
    max_energy?: number
    /** ★ 第二十批 B 段：待结算的被动恢复量（点）—— 读数已含它 */
    pending_recovery?: number
    stored_energy?: number
    recovery_rate?: number
  }
  message?: string
}

export interface DelegationStatusData {
  status?: {
    total?: number
    agent_created?: number
    ratio?: number
    available?: boolean
  }
  message?: string
}

export interface AttentionStatusData {
  status?: {
    remaining_minutes?: number
    available_minutes?: number
    session_available?: boolean
    session_window?: number
  }
  message?: string
}

/** 翻译函数签名（与 i18next 的 `t` 兼容；由组件用包装函数传入） */
export type ReadoutTranslate = (
  key: string,
  fallback: string,
  opts?: Record<string, unknown>,
) => string

/**
 * 纯函数：从三个读数载荷拼出读数格（**量纲在这里被钉死**）。
 *
 * ★ 为什么抽成纯函数：量纲纪律（能量 = 点 / 注意力 = 分钟）必须**可测** ——
 *   「点」和「分钟」分别挂在哪个格上，是产品最容易错、测试最容易漏的地方。
 *   ⇒ 单测直接断言 `energyCell.unit === '点'`、`attentionCell.unit === '分钟'`。
 */
export function buildReadoutCells(
  loop: ZenloopStatusData | null,
  energy: EnergyLevelData | null,
  attention: AttentionStatusData | null,
  delegation: DelegationStatusData | null,
  t: ReadoutTranslate,
): ReadoutCell[] {
  const cells: ReadoutCell[] = []

  const concept = loop?.top?.[0]?.concept
  const channel = loop?.top?.[0]?.channel
  const activeCount = loop?.active ?? 0
  if (concept || activeCount > 0) {
    cells.push({
      label: t('zenskill.readout.loop', '轮次'),
      value: concept
        ? String(concept)
        : t('zenskill.readout.loopCount', '{n} 条在跑', { n: activeCount }),
      hint: channel ?? undefined,
    })
  }

  // ★ 能量读**规范口径** `energy_level`（不是 companion_summary 的那份）：
  //   它带 `pending_recovery` ⇒ 能显示「恢复中 +N/小时」，也能直接吃到
  //   第二十批 B 段的**投影值**（读到的是此刻真实值，不是落盘值）。
  const es = energy?.status
  if (es && typeof es.current_energy === 'number') {
    const pending = es.pending_recovery ?? 0
    cells.push({
      label: t('zenskill.readout.energy', '能量'),
      value: `${es.current_energy} / ${es.max_energy ?? 0}`,
      unit: t('zenskill.unit.point', '点'),
      hint:
        pending > 0
          ? t('zenskill.readout.energyRecovering', '恢复中 +{n} 点', { n: pending })
          : undefined,
    })
  }

  // ★ 智能体承担（**比例**）—— 第四种量纲，独立一格，**不与点/分钟混算**
  const ds = delegation?.status
  if (ds && ds.available && typeof ds.ratio === 'number') {
    cells.push({
      label: t('zenskill.readout.delegation', '智能体承担'),
      value: `${Math.round(ds.ratio * 100)}%`,
      hint: t('zenskill.readout.delegationHint', '{n} / {total} 项由智能体接下', {
        n: ds.agent_created ?? 0,
        total: ds.total ?? 0,
      }),
    })
  }

  const st = attention?.status
  if (st && typeof st.remaining_minutes === 'number') {
    // ★ 会话侧读不到近期深度占用 ⇒ 该值只是**上限**
    const upperBound = st.session_available === false
    cells.push({
      label: t('zenskill.readout.attention', '注意力'),
      value: `${st.remaining_minutes}`,
      unit: t('zenskill.unit.minute', '分钟'),
      prefix: upperBound ? t('zenskill.readout.atMost', '至多') : undefined,
      hint: upperBound
        ? t(
            'zenskill.readout.attentionUpperHint',
            '近期深度占用暂时读不到，此值为上限',
          )
        : undefined,
    })
  }

  return cells
}

export function DomainReadout({ workspaceId }: { workspaceId?: string }) {
  const { t } = useTranslation()

  const loop = useMcpTool<ZenloopStatusData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'zenloop_status', {})
  const energy = useMcpTool<EnergyLevelData>(
    workspaceId, ZENSKILL_SOURCE_SLUG, 'energy_level', {},
  )
  const attention = useMcpTool<AttentionStatusData>(
    workspaceId, ZENSKILL_SOURCE_SLUG, 'attention_status', {},
  )
  const delegation = useMcpTool<DelegationStatusData>(
    workspaceId, ZENSKILL_SOURCE_SLUG, 'delegation_status', {},
  )

  // ★ 没有工作区 ⇒ 什么数据源都连不上 ⇒ **不渲染**（不是「无权限」）
  if (!workspaceId) return null

  const translate: ReadoutTranslate = (key, fallback, opts) =>
    t(key, { defaultValue: fallback, ...(opts ?? {}) }) as string

  const cells = buildReadoutCells(loop.data, energy.data, attention.data, delegation.data, translate)

  const errors = [loop.error, energy.error, attention.error, delegation.error].filter(
    Boolean,
  ) as string[]
  const noAccess = errors.some(isNoDataSourceError)
  const error = errors.find((e) => !isNoDataSourceError(e)) ?? null
  const loading = loop.loading || energy.loading || attention.loading || delegation.loading

  if (error || noAccess || loading) {
    return (
      <ReadoutStrip
        cells={cells}
        loading={loading}
        error={error}
        noAccess={noAccess}
        onRetry={() => {
          loop.refresh()
          energy.refresh()
          attention.refresh()
          delegation.refresh()
        }}
      />
    )
  }

  if (cells.length === 0) return null

  return <ReadoutStrip cells={cells} />
}
