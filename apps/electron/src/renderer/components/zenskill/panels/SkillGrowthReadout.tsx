/**
 * SkillGrowthReadout.tsx — 技能域的**域特有读数条**：成长契约（第二十一批 B 段）
 *
 * ★ 为什么是「域特有」而不是并进通用读数条
 * ----------------------------------------
 * `DomainReadout` 读的是**四域共用的四种量纲**（轮次 / 能量点 / 注意力分钟 / 委派比例），
 * 它的注释里已经写明：「★ 各域的**特有内容**（项目行动 / 技能成长）由各自页面另外挂，
 * 不塞进这条读数条」⇒ 本组件就是那句话的兑现。
 *
 * ★ 口径来源
 * ---------
 * 设计稿「技能域 · 设计稿」写着「**ZenSkill 13 字段（等级 / 里程碑 / 使用记录）**」——
 * 这三要素在运行时**早就有**（`core/skill_profile.py` 的 `SkillProfile`：
 * `level` / `level_progress` / `get_milestones()` / `get_recent_events()`），
 * 此前缺的只是**只读出口** ⇒ 第二十一批 B 段新增 MCP 只读工具 `skill_growth`。
 *
 * ★ 量纲纪律
 * ---------
 * 成长契约是**等级名 + 计数**（等级 / 里程碑几个 / 用过几次）——
 * **不是**能量点、**不是**注意力分钟 ⇒ 绝不与四种量纲混算或相加。
 *
 * ★ 读不到 ≠ 读到 0
 * ----------------
 * - 技能不存在 / 没有 ZenSkill 数据源 ⇒ 走 `ReadoutStrip` 的「无权限 / 出错」态；
 * - 技能存在但**还没有里程碑、没有使用记录** ⇒ 这两格**不出现**
 *   （是「确实还没有」，不是「读不到」）⇒ 绝不用 0 冒充。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'
import { ReadoutStrip, type ReadoutCell } from './ReadoutStrip'
import { isNoDataSourceError } from './errors'

export interface SkillGrowthData {
  ok?: boolean
  available?: boolean
  skill_id?: string
  name?: string
  level?: string
  level_progress?: number
  total_interactions?: number
  success_count?: number
  fail_count?: number
  success_rate?: number
  last_interaction_at?: string
  milestones?: { level?: string; achieved_at?: string; description?: string }[]
  events?: { action?: string; created_at?: string; success?: boolean }[]
  error?: string
}

export type GrowthTranslate = (
  key: string,
  fallback: string,
  opts?: Record<string, unknown>,
) => string

/**
 * 纯函数：把成长契约载荷拼成读数格（**可测**：等级/里程碑/使用记录各占一格）。
 *
 * ★ 里程碑与使用记录**只在有数据时出现** —— 空数组 ⇒ 该格不出现（不是 0）。
 */
export function buildGrowthCells(
  data: SkillGrowthData | null,
  t: GrowthTranslate,
): ReadoutCell[] {
  if (!data || data.available === false) return []
  const cells: ReadoutCell[] = []

  if (data.level) {
    const progress = typeof data.level_progress === 'number' ? data.level_progress : undefined
    cells.push({
      label: t('zenskill.readout.skillLevel', '等级'),
      value: data.level,
      hint:
        progress !== undefined
          ? t('zenskill.readout.skillProgress', '进度 {p}%', {
              p: Math.round(progress * 100),
            })
          : undefined,
    })
  }

  const milestones = data.milestones ?? []
  if (milestones.length > 0) {
    const latest = milestones[milestones.length - 1]?.achieved_at ?? ''
    cells.push({
      label: t('zenskill.readout.skillMilestones', '里程碑'),
      value: t('zenskill.readout.skillMilestoneCount', '{n} 个', { n: milestones.length }),
      hint: latest || undefined,
    })
  }

  const total = data.total_interactions ?? 0
  if (total > 0) {
    const rate = typeof data.success_rate === 'number' ? data.success_rate : undefined
    cells.push({
      label: t('zenskill.readout.skillUsage', '使用记录'),
      value: t('zenskill.readout.skillUsageCount', '{n} 次', { n: total }),
      hint:
        rate !== undefined
          ? t('zenskill.readout.skillSuccessRate', '成功率 {p}%', {
              p: Math.round(rate * 100),
            })
          : undefined,
    })
  }

  return cells
}

export function SkillGrowthReadout({
  workspaceId,
  skillSlug,
}: {
  workspaceId?: string
  skillSlug?: string
}) {
  const { t } = useTranslation()

  const growth = useMcpTool<SkillGrowthData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'skill_growth',
    { skill_id: skillSlug ?? '' },
  )

  // ★ 没有工作区 / 没有技能 ⇒ 连数据源都连不上 ⇒ **不渲染**（不是「无权限」）
  if (!workspaceId || !skillSlug) return null

  const translate: GrowthTranslate = (key, fallback, opts) =>
    t(key, { defaultValue: fallback, ...(opts ?? {}) }) as string

  const cells = buildGrowthCells(growth.data, translate)

  const error = growth.error ?? null
  const noAccess = error ? isNoDataSourceError(error) : false
  const realError = noAccess ? null : error

  if (realError || noAccess || growth.loading) {
    return (
      <ReadoutStrip
        cells={cells}
        loading={growth.loading}
        error={realError}
        noAccess={noAccess}
        onRetry={() => growth.refresh()}
      />
    )
  }

  if (cells.length === 0) return null

  return <ReadoutStrip cells={cells} />
}
