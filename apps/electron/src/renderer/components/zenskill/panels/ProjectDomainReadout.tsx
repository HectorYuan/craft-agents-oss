/**
 * ProjectDomainReadout.tsx — 技能/项目页的**项目域特有读数**（第二十一批 B 段）
 *
 * ★ 为什么要有这个组件（整合的「呈现」那一半）
 * ------------------------------------------------
 * ★ 「项目路径 ↔ 项目实体」**在设计层早已是一体**：
 *   · craft 侧项目 = 目录 `{workspace_root}/projects/{slug}/`（`server/projects_store.py`）；
 *   · GTD 侧项目 = 实体 `GTDProject`，其中 **`craft_project_slug` 字段早就有**（D2-4 加的）
 *     ⇒ 二者天然对应 ⇒ ★ **缺的不是「映射方案」，是「接线」**：
 *       ① 字段此前**没有写入点**（`project_add` 不透传）⇒ 孤儿字段：存得进、设不了；
 *       ② 此前**没有按 slug 查的出口** ⇒ 即便设了也读不到 ⇒ 后端补 `project_status`；
 *       ③ 呈现侧由本组件消费 ⇒ ★ 就是这里。
 *
 * ★ 与通用读数条（`DomainReadout`）的分工
 * ---------------------------------------
 * `DomainReadout` 读的是**四域共用的四种量纲**（回路 / 能量点 / 注意力分钟 / 委派比例）；
 * ★ 本组件读的是**这个项目自己的进度与下一步行动**（域特有）⇒ 两者**分列不相加**。
 *
 * ★ 读不到 ≠ 读到 0
 * ------------------
 * - 没有关联的 GTD 项目 / 关联到多个（歧义）⇒ `available=false`
 *   ⇒ ★ 显示「还没有关联的 GTD 项目」，**不是**「0%」；
 * - 关联到了但该项目**还没有行动** ⇒ `available=true` 且 `progress.total=0`
 *   ⇒ ★ 显示「0 / 0 行动完成」（这是**确实还没有行动**，与上面不同）。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'
import { ReadoutStrip, type ReadoutCell } from './ReadoutStrip'
import { isNoDataSourceError } from './errors'

export interface ProjectStatusData {
  ok?: boolean
  available?: boolean
  ambiguous?: boolean
  project_id?: string
  name?: string
  outcome?: string
  status?: string
  craft_project_slug?: string
  progress?: { done?: number; total?: number; progress?: number; available?: boolean }
  next_actions?: { id?: string; title?: string; energy_required?: number; priority?: string }[]
  message?: string
  error?: string
}

export type ProjectTranslate = (
  key: string,
  fallback: string,
  opts?: Record<string, unknown>,
) => string

/**
 * 纯函数：把项目域载荷拼成读数格（**可单测**）。
 *
 * ★ 只有 `available === true` 才产出读数格 ⇒ 「读不到」与「确实是 0」不混。
 */
export function buildProjectCells(
  data: ProjectStatusData | null,
  t: ProjectTranslate,
): ReadoutCell[] {
  if (!data || data.available !== true) return []
  const p = data.progress
  if (!p || typeof p.progress !== 'number') return []
  const done = p.done ?? 0
  const total = p.total ?? 0
  return [
    {
      label: t('zenskill.readout.projectProgress', '进度'),
      value: `${Math.round(p.progress * 100)}%`,
      hint:
        total > 0
          ? t('zenskill.readout.projectProgressCount', '{done} / {total} 行动完成', {
              done,
              total,
            })
          : t('zenskill.readout.projectNoActions', '还没有行动'),
    },
  ]
}

export function ProjectDomainReadout({
  workspaceId,
  projectSlug,
}: {
  workspaceId?: string
  projectSlug?: string
}) {
  const { t } = useTranslation()

  const status = useMcpTool<ProjectStatusData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'project_status',
    { craft_project_slug: projectSlug ?? '', limit: 5 },
  )

  // ★ 没有工作区 / 没有项目 slug ⇒ 连数据源都连不上 ⇒ **不渲染**（不是「无权限」）
  if (!workspaceId || !projectSlug) return null

  const translate: ProjectTranslate = (key, fallback, opts) =>
    t(key, { defaultValue: fallback, ...(opts ?? {}) }) as string

  const cells = buildProjectCells(status.data, translate)
  const error = status.error ?? null
  const noAccess = error ? isNoDataSourceError(error) : false
  const realError = noAccess ? null : error

  // ★ 「没有关联的 GTD 项目」/「关联到多个，无法确定」⇒ 显式说明（**不是 0%**）
  const unlinked =
    status.data && status.data.available === false
      ? status.data.ambiguous
        ? t(
            'zenskill.readout.projectAmbiguous',
            '这个 craft 项目关联了多个 GTD 项目，无法确定是哪个',
          )
        : t('zenskill.readout.projectNoLink', '还没有关联的 GTD 项目')
      : null

  if (realError || noAccess || status.loading) {
    return (
      <ReadoutStrip
        cells={cells}
        loading={status.loading}
        error={realError}
        noAccess={noAccess}
        onRetry={() => status.refresh()}
      />
    )
  }

  const actions = status.data?.next_actions ?? []

  return (
    <div>
      {cells.length > 0 ? <ReadoutStrip cells={cells} /> : null}
      {unlinked ? (
        <div className="px-4 py-3 text-xs text-muted-foreground">{unlinked}</div>
      ) : null}
      {actions.length > 0 ? (
        <div className="px-4 py-2">
          <div className="mb-1 text-xs text-muted-foreground">
            {t('zenskill.readout.projectNextActions', '下一步行动 · 按能量排序')}
          </div>
          <ul className="space-y-0.5">
            {actions.map((a) => (
              <li key={a.id ?? a.title} className="flex items-baseline gap-2 text-xs">
                <span className="truncate text-foreground">{a.title}</span>
                <span className="shrink-0 text-muted-foreground">
                  {t('zenskill.readout.projectEnergy', '能量 {n} 点', {
                    n: a.energy_required ?? 0,
                  })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
