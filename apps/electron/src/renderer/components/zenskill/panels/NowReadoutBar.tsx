/**
 * NowReadoutBar.tsx — 会话页「此刻」三格读数卡（第二十三批，试点）
 *
 * ★ 与 ReadoutStrip 的关系
 * -----------------------
 * ReadoutStrip 是三域共用的横条读数（保留不动，另两个域仍在用）；
 * 本组件是会话页 ready 态的卡片化展示：能量 / 注意力 / 回路三格，
 * 量纲纪律沿用 buildReadoutCells 的口径——点、分钟、无量纲，互不相加。
 *
 * ★ 纯展示组件：数据由 DomainReadout 的既有 MCP  hooks 传入，
 *   本组件不直接取数、不新增数据源。
 *
 * ★ 样式只用 Tailwind + shadcn 语义变量，零硬编码 hex。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import type {
  ZenloopStatusData,
  EnergyLevelData,
  AttentionStatusData,
  DelegationStatusData,
} from './DomainReadout'

export interface NowReadoutBarProps {
  loop: ZenloopStatusData | null
  energy: EnergyLevelData | null
  attention: AttentionStatusData | null
  delegation: DelegationStatusData | null
}

/** 五段点阵：按点亮段数渲染（n 自动夹到 0..5）。 */
function DotMeter({ lit, tone = 'primary' }: { lit: number; tone?: 'primary' | 'muted' }) {
  const n = Math.max(0, Math.min(5, Math.round(lit)))
  return (
    <span className="inline-flex items-center gap-1">
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={
            i < n
              ? tone === 'primary'
                ? 'h-1.5 w-3.5 rounded-sm bg-primary'
                : 'h-1.5 w-3.5 rounded-sm bg-foreground/60'
              : 'h-1.5 w-3.5 rounded-sm bg-border'
          }
        />
      ))}
    </span>
  )
}

function CellLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-[11px] text-muted-foreground">{children}</div>
}

export function NowReadoutBar({ loop, energy, attention, delegation }: NowReadoutBarProps) {
  const { t } = useTranslation()

  // ── 能量格 ──────────────────────────────────────────────
  const es = energy?.status
  const current = es?.current_energy
  const max = es?.max_energy ?? 0
  const pct =
    typeof es?.pct === 'number'
      ? es.pct
      : typeof current === 'number' && max > 0
        ? current / max
        : 0
  const pending = es?.pending_recovery ?? 0

  // ── 注意力格 ────────────────────────────────────────────
  const st = attention?.status
  const remaining = st?.remaining_minutes
  const upperBound = st?.session_available === false
  const available = st?.available_minutes
  const attentionLit =
    typeof remaining === 'number'
      ? typeof available === 'number' && available > 0
        ? (remaining / available) * 5
        : 5
      : 0

  // ── 回路格 ──────────────────────────────────────────────
  const concept = loop?.top?.[0]?.concept
  const channel = loop?.top?.[0]?.channel
  const activeCount = loop?.active ?? 0
  const loopText = concept
    ? String(concept)
    : t('zenskill.readout.loopCount', '{n} 条在跑', { n: activeCount })

  // ── 委派（比例量纲，作回路格底部小字，不与点/分钟混算）──
  const ds = delegation?.status
  const ratioPct =
    ds?.available && typeof ds.ratio === 'number' ? Math.round(ds.ratio * 100) : null

  return (
    <div className="grid grid-cols-3 gap-3 rounded-lg border border-border/30 bg-card p-3">
      {/* 能量 */}
      <div className="min-w-0">
        <CellLabel>{t('zenskill.readout.energy', '能量')}</CellLabel>
        {typeof current === 'number' ? (
          <>
            <div className="flex items-baseline gap-1.5">
              <span className="text-lg font-semibold tabular-nums leading-none">{current}</span>
              <span className="text-[11px] text-muted-foreground">
                / {max} {t('zenskill.unit.point', '点')}
              </span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct * 100}%` }} />
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {pending > 0
                ? t('zenskill.readout.energyRecovering', '恢复中 +{n} 点', { n: pending })
                : t('zenskill.readout.energyUsed', '已用 {n} 点', { n: max - current })}
            </div>
          </>
        ) : (
          <span className="text-[11px] italic text-muted-foreground">
            {t('zenskill.state.empty', '暂无读数')}
          </span>
        )}
      </div>

      {/* 注意力 */}
      <div className="min-w-0">
        <CellLabel>{t('zenskill.readout.attention', '注意力')}</CellLabel>
        {typeof remaining === 'number' ? (
          <>
            <span
              className={
                upperBound
                  ? 'inline-flex items-center rounded-full border border-info/40 px-2 py-0.5 text-[11px] text-info'
                  : 'inline-flex items-center rounded-full border border-border/40 px-2 py-0.5 text-[11px] text-foreground/80'
              }
              title={upperBound ? t('zenskill.readout.atMost', '至多') : undefined}
            >
              {upperBound ? `${t('zenskill.readout.atMost', '至多')} ` : ''}
              {remaining} {t('zenskill.unit.minute', '分钟')}
            </span>
            <div className="mt-2">
              <DotMeter lit={attentionLit} />
            </div>
            <div className="mt-1.5 text-[11px] text-muted-foreground">
              {upperBound
                ? t('zenskill.readout.attentionUpperHint', '近期深度占用暂时读不到，此值为上限')
                : t('zenskill.readout.attentionAvailable', '深度块可用')}
            </div>
          </>
        ) : (
          <span className="text-[11px] italic text-muted-foreground">
            {t('zenskill.state.empty', '暂无读数')}
          </span>
        )}
      </div>

      {/* 回路 */}
      <div className="min-w-0">
        <CellLabel>{t('zenskill.readout.loop', '回路')}</CellLabel>
        <span className="inline-flex items-center rounded-full border border-border/40 px-2 py-0.5 text-[11px] text-foreground/80">
          {loopText}
        </span>
        <div className="mt-2">
          <DotMeter lit={activeCount} tone={concept ? 'muted' : 'primary'} />
        </div>
        <div className="mt-1.5 text-[11px] text-muted-foreground">
          {channel ?? t('zenskill.readout.loopIdle', '暂无在跑回路')}
          {ratioPct !== null ? ` · ${t('zenskill.readout.delegation', '智能体承担')} ${ratioPct}%` : ''}
        </div>
      </div>
    </div>
  )
}
