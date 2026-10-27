/**
 * ReviewBar — compact energy ring + daily review numbers, shown between
 * the GtdWorkspace header and the tab bar (B04/B15/B16).
 *
 * Left: SVG ring indicator (16px) + "能量 {level} {pct}%"
 * Right: done today / pending / overdue counts with icons
 *
 * Data is loaded once on workspace entry via useMcpTool; the component
 * is pure presentational.
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, Clock, AlertTriangle } from 'lucide-react'

export interface ReviewBarProps {
  /** 0..1 fraction or null when unknown */
  energyPct: number | null
  /** Energy level label from backend (e.g. "high", "low") */
  energyLevel?: string
  /** Current energy points */
  currentEnergy?: number | null
  /** Max energy points */
  maxEnergy?: number | null
  /** Actions completed today */
  doneToday?: number
  /** Inbox items pending */
  pendingCount?: number
  /** Overdue action count */
  overdueCount?: number
  /** One-line daily review message */
  message?: string
}

/**
 * 16px SVG ring —— 环的**长度**表示能量比例（`filled`）。
 *
 * ★ 第二十一批 D 段：原实现用 **4 档阈值色**（红/橙/黄/绿）表达能量档位 ⇒
 *   ① 违反「**色相不承载档位**」（第十九批 E 段裁定）；
 *   ② 且那 4 个 hex 是**能量四档的另一份副本**，色值还与品牌真相源
 *      （`brand/zs-colors.ts` 的 success / warning / energy-low / danger）**不一致**
 *      ⇒ 同一概念两份副本 + 两套色值。
 * ⇒ 改为**中性色**（`currentColor`，继承所在处的文字色）：环只表示「有多少」，
 *   档位由**文字**承载（能量读数条上的「能量 · 点」与档位文字）。
 */
function EnergyRing({ pct, size = 16 }: { pct: number; size?: number }) {
  const r = 6
  const c = 2 * Math.PI * r
  const filled = Math.min(Math.max(pct, 0), 1)
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" className="shrink-0">
      <circle cx="8" cy="8" r={r} fill="none" stroke="currentColor" strokeOpacity={0.15} strokeWidth="2" />
      <circle
        cx="8"
        cy="8"
        r={r}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - filled)}
        strokeLinecap="round"
        transform="rotate(-90 8 8)"
      />
    </svg>
  )
}

export function ReviewBar({
  energyPct,
  energyLevel,
  currentEnergy,
  maxEnergy,
  doneToday = 0,
  pendingCount = 0,
  overdueCount = 0,
  message,
}: ReviewBarProps) {
  const { t } = useTranslation()
  const pctDisplay = energyPct !== null ? Math.round(energyPct * 100) : null
  const levelLabel = energyLevel
    ? t(`zenskill.gtd.review.energyLevel.${energyLevel}`, energyLevel)
    : ''

  return (
    <div className="flex items-center gap-4 px-5 py-2 border-b border-border/30 bg-muted/5 text-xs shrink-0">
      {/* Left: energy ring + text */}
      <span className="flex items-center gap-1.5 shrink-0" title={t('zenskill.gtd.actions.energy')}>
        {energyPct !== null ? (
          <EnergyRing pct={energyPct} />
        ) : (
          <span className="h-2 w-2 rounded-full bg-muted-foreground/40 shrink-0" />
        )}
        <span className="tabular-nums">
          {t('zenskill.gtd.review.energy', {
            level: levelLabel || (currentEnergy ?? '?'),
            pct: pctDisplay ?? '?',
          })}
        </span>
      </span>

      <span className="h-3 w-px bg-border/60 shrink-0" />

      {/* Right: done / pending / overdue counts */}
      <div className="flex items-center gap-3 shrink-0 tabular-nums">
        <span className="text-muted-foreground flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3 text-success/60" />
          {t('zenskill.gtd.review.doneToday')}{' '}
          <span className={`font-medium ${doneToday > 0 ? 'text-success-text' : 'text-muted-foreground'}`}>{doneToday}</span>
        </span>
        <span className="text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3 text-info/60" />
          {t('zenskill.gtd.review.pending')}{' '}
          <span className={`font-medium ${pendingCount > 0 ? 'text-info' : 'text-muted-foreground'}`}>{pendingCount}</span>
        </span>
        <span className="text-muted-foreground flex items-center gap-1">
          <AlertTriangle className="h-3 w-3 text-destructive-text/60" />
          {t('zenskill.gtd.review.overdue')}{' '}
          <span className={`font-medium ${overdueCount > 0 ? 'text-destructive-text' : 'text-muted-foreground'}`}>{overdueCount}</span>
        </span>
      </div>

      {message && (
        <>
          <span className="h-3 w-px bg-border/60 shrink-0" />
          <span className="truncate text-muted-foreground/70 min-w-0" title={message}>
            {message}
          </span>
        </>
      )}
    </div>
  )
}
