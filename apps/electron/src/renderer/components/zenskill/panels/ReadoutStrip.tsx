/**
 * ReadoutStrip.tsx — ZenSkill **读数条**（第十九批 D 段）
 *
 * ★ 量纲纪律（本组件存在的唯一理由）
 * --------------------------------
 * 四种量纲**互不相加、不换算**：能量 = 点 / 注意力 = 分钟 / 智能体承担 = 比例 /
 * 系统了解度 = 误差 ⇒ 一条读数条里出现多个量纲时，**必须分列 + 各带自己的单位**，
 * 绝不能并成一句「能量 62% · 注意力 30 分钟」（那会让读者把两种单位加在一起）。
 * ⇒ 所以每个 cell 都**自带 unit**，渲染时单位跟着数值走，不做合并。
 *
 * ★ 五态统一在这里处理（与 `stateBlocks.tsx` 同源）
 * --------------------------------------------
 * 加载 / 错 / 无权限 三态由本组件判定并渲染；「空」由调用方给出（各域的空态句不同）。
 *
 * ★ 本组件**不承载**「能量占比」这类比例以外的隐式换算：比例型读数（如进度 %）
 *   明确写 unit="%"，与「点」「分钟」区分开。
 */
import React from 'react'
import { LoadingBlock, ErrorBlock, NoDataSourceBlock } from './stateBlocks'

export interface ReadoutCell {
  /** 读数名（如「轮次」「能量」「注意力」） */
  label: string
  /** 读数值（**不带单位**） */
  value: string
  /** 单位 —— ★ 缺了就是量纲缺失，调用方必须给 */
  unit?: string
  /** 数值前缀提示（如「至多」—— 该值只是上限） */
  prefix?: string
  /** 补充说明（鼠标悬停/次要信息） */
  hint?: string
}

export interface ReadoutStripProps {
  /** 读数格；**空数组 = 无数据**（由调用方决定空态文案） */
  cells: ReadoutCell[]
  loading?: boolean
  error?: string | null
  /** 工作区没有 ZenSkill 数据源（**不是故障**） */
  noAccess?: boolean
  onRetry?: () => void
  className?: string
}

export function ReadoutStrip({
  cells,
  loading,
  error,
  noAccess,
  onRetry,
  className,
}: ReadoutStripProps) {
  if (noAccess) return <NoDataSourceBlock />
  if (error) return <ErrorBlock message={error} onRetry={onRetry} />
  if (loading && cells.length === 0) return <LoadingBlock />
  if (cells.length === 0) return null

  return (
    <div
      className={
        className ??
        'flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2 border-b border-border/30 text-xs'
      }
    >
      {cells.map((c) => (
        <span key={c.label} className="inline-flex items-baseline gap-1" title={c.hint}>
          <span className="text-muted-foreground">{c.label}</span>
          <span className="text-foreground">
            {c.prefix ? `${c.prefix} ` : ''}
            {c.value}
            {c.unit ? <span className="text-muted-foreground"> {c.unit}</span> : null}
          </span>
        </span>
      ))}
    </div>
  )
}
