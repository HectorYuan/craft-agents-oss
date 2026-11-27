/**
 * GenericToolResultCard — 通用工具结果内联卡片。
 *
 * 渲染在 TurnCard 工具活动行下方（经 `renderToolResultCard` 钩子），覆盖
 * GTD 家族以外的普通工具（write / echo / long_stdout 等）：工具名 + 状态 +
 * 截断后的结果正文，isError 活动用 destructive 色区分。
 *
 * 上游 WS 已在 8000 字符处截断结果；本卡片在展示侧再折叠到 DISPLAY_LIMIT，
 * 超长加「已截断」标记，不改动消息本身。空结果返回 null（不占位）。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { formatDuration } from '@craft-agent/ui'

/** 展示侧折叠阈值（字符）；超过即省略号截断并标注。 */
const DISPLAY_LIMIT = 1200

interface GenericToolResultCardProps {
  /** 工具名（展示在卡片头部） */
  toolName: string
  /** 工具结果正文（已为上游截断后的文本） */
  resultText: string
  /** 活动是否为错误态 */
  isError?: boolean
  /** 错误活动的剥离后错误文本（可选，优先于正文展示） */
  errorText?: string
  /** O1-1: 完成耗时（毫秒）；缺省/非法不渲染耗时，不显示 NaN */
  durationMs?: number
}

export function GenericToolResultCard({
  toolName,
  resultText,
  isError = false,
  errorText,
  durationMs,
}: GenericToolResultCardProps) {
  const { t } = useTranslation()
  const trimmed = resultText.trim()
  if (!trimmed) return null

  const truncated = trimmed.length > DISPLAY_LIMIT
  const body = truncated ? `${trimmed.slice(0, DISPLAY_LIMIT)}…` : trimmed
  const shownError = (errorText || '').trim()
  const shownDuration = typeof durationMs === 'number' && Number.isFinite(durationMs) && durationMs >= 0
    ? formatDuration(durationMs)
    : undefined

  return (
    <div
      data-testid="generic-tool-result-card"
      className={cn(
        'mt-0.5 inline-flex max-w-full flex-col gap-0.5 rounded-md border border-border/60 bg-background px-2.5 py-1.5 text-left text-xs',
        isError && 'border-destructive/40 bg-destructive/5'
      )}
    >
      <span className="flex items-center gap-1.5 min-w-0">
        <span className={cn('shrink-0', isError ? 'text-destructive' : 'text-success')}>
          {isError ? '✕' : '✓'}
        </span>
        <span className="truncate font-medium text-foreground">{toolName}</span>
        {shownDuration && (
          <span className="ml-auto shrink-0 tabular-nums text-muted-foreground/70">
            {shownDuration}
          </span>
        )}
        {isError && shownError && (
          <span className="ml-auto shrink-0 rounded-[4px] border border-destructive/30 bg-destructive/10 px-1.5 py-px text-badge font-medium text-destructive">
            {t('common.error')}
          </span>
        )}
      </span>
      <div
        className={cn(
          'whitespace-pre-wrap break-all leading-[18px] text-muted-foreground',
          isError && 'text-destructive/90'
        )}
      >
        {shownError || body}
      </div>
      {truncated && (
        <span className="text-[10px] text-muted-foreground/70">{t('common.resultTruncated')}</span>
      )}
    </div>
  )
}
