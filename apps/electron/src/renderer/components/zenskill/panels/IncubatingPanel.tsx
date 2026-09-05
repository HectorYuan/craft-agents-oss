/**
 * IncubatingPanel — ZenLoop incubating pool (fifth GTD tab, full variant).
 *
 * Fetches incubating_list through the useMcpTool L3 hook (zenskill:changed
 * auto-refresh) and groups entries by channel (reflect / consolidate /
 * insight / purify). Each entry shows its concept and a maturity progress
 * bar; entries at >=80% maturity get a one-click incubating_promote button
 * (full variant) — promote relies on the zenskill:changed broadcast for
 * refresh, like every other write.
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { Sprout, TrendingUp } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import type { GtdIncubatingItem } from './types'

const CHANNELS = ['reflect', 'consolidate', 'insight', 'purify'] as const
/** Backend gate: incubating_promote rejects maturity < 0.8 */
const PROMOTE_THRESHOLD_PCT = 80

interface IncubatingData {
  count?: number
  items?: GtdIncubatingItem[]
  message?: string
}

interface ChannelGroup {
  key: string
  label: string
  items: GtdIncubatingItem[]
}

export interface IncubatingPanelProps {
  variant?: 'compact' | 'full'
  showHeader?: boolean
  /** full variant: enables the internal incubating_list fetch + promote */
  workspaceId?: string
  sourceSlug?: string
  busyId?: string | null
  onPromote?: (itemId: string) => void
}

function IncubatingEntry({
  item,
  isFull,
  busyId,
  onPromote,
}: {
  item: GtdIncubatingItem
  isFull: boolean
  busyId?: string | null
  onPromote?: (itemId: string) => void
}) {
  const { t } = useTranslation()
  const pct = Math.round(Math.min(Math.max(item.maturity ?? 0, 0), 1) * 100)
  const mature = pct >= PROMOTE_THRESHOLD_PCT
  return (
    <div className="text-xs rounded px-2 py-1 hover:bg-muted/50 group">
      <div className="flex items-center gap-1.5">
        <span className="truncate flex-1" title={item.raw_concept}>{item.raw_concept}</span>
        <span className="text-[9px] text-muted-foreground/60 tabular-nums shrink-0" title={t('zenskill.gtd.incubating.maturity')}>
          {pct}%
        </span>
        {isFull && mature && onPromote && (
          <button
            className="flex items-center gap-0.5 px-1 py-0.5 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 shrink-0 text-[10px] disabled:opacity-40"
            title={t('zenskill.gtd.incubating.promote')}
            disabled={busyId === item.id}
            onClick={() => onPromote(item.id)}
          >
            <TrendingUp className="h-3 w-3" />
            {t('zenskill.gtd.incubating.promote')}
          </button>
        )}
      </div>
      <div className="flex items-center mt-1">
        <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
          <div
            className={`h-full rounded transition-all ${mature ? 'bg-green-500/70' : 'bg-accent/70'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export function IncubatingPanel({
  variant = 'compact',
  showHeader = true,
  workspaceId,
  sourceSlug,
  busyId,
  onPromote,
}: IncubatingPanelProps) {
  const { t } = useTranslation()
  const isFull = variant === 'full'
  // Parked while workspaceId is absent; sourceSlug '' is safe because the hook
  // short-circuits before using it (parked-hook pattern).
  const incubating = useMcpTool<IncubatingData>(
    workspaceId ? (sourceSlug ?? '') : undefined,
    sourceSlug ?? '',
    'incubating_list',
    { limit: 100 },
  )
  const items = incubating.data?.items ?? []

  const groups: ChannelGroup[] = CHANNELS.map((channel) => ({
    key: channel,
    label: t(`zenskill.gtd.incubating.channel.${channel}`),
    items: items.filter((i) => (i.channel || '') === channel),
  }))
  const other = items.filter((i) => !(CHANNELS as readonly string[]).includes(i.channel ?? ''))
  if (other.length > 0) {
    groups.push({ key: 'other', label: 'other', items: other })
  }

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <Sprout className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            {t('zenskill.gtd.tab.incubating')} ({items.length})
          </span>
        </div>
      )}
      {incubating.loading && !incubating.data ? (
        <div className="space-y-1.5 pl-2">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-3 rounded bg-muted/60 animate-pulse"
              style={{ width: `${70 - i * 15}%` }}
            />
          ))}
        </div>
      ) : incubating.error && !incubating.data ? (
        <div className="text-[11px] text-destructive/80 italic pl-2" title={incubating.error}>{incubating.error}</div>
      ) : (
        <>
          <div className="space-y-3">
            {groups.map((g) => (
              <div key={g.key}>
                <div className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground px-2 pt-0.5">
                  {g.label}
                  <span className="text-muted-foreground/60">({g.items.length})</span>
                </div>
                {g.items.length === 0 ? (
                  <div className="text-xs text-muted-foreground italic pl-5 py-0.5">
                    {t('zenskill.gtd.incubating.empty')}
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    {g.items.map((item) => (
                      <IncubatingEntry
                        key={item.id}
                        item={item}
                        isFull={isFull}
                        busyId={busyId}
                        onPromote={onPromote}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground/60 pl-2 pt-2.5">
            <Sprout className="h-3 w-3 shrink-0" />
            {t('zenskill.gtd.incubating.zenloopHint')}
          </div>
        </>
      )}
    </div>
  )
}
