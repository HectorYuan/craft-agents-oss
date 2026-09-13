/**
 * ZenloopStandalonePage — ZenLoop 独立页面
 *
 * 展示 ZenLoop 循环状态、孵化池概览、手动触发入口。
 * 数据源：zenloop_status + incubating_list MCP 工具。
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Sprout, Play, Pause } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { IncubatingPanel } from '../panels/IncubatingPanel'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

interface ZenloopStatusData {
  active?: number
  by_channel?: Record<string, number>
  top?: { id: string; channel: string; maturity: number; concept: string }[]
  message?: string
}

interface ZenloopStandalonePageProps {
  workspaceId?: string
  initialTab?: string
  onNavigateToChat?: (msg: string) => void
}

const CHANNEL_COLORS: Record<string, string> = {
  reflect: 'bg-blue-500/15 text-blue-400',
  consolidate: 'bg-purple-500/15 text-purple-400',
  insight: 'bg-yellow-500/15 text-yellow-400',
  purify: 'bg-green-500/15 text-green-400',
}

export function ZenloopStandalonePage({ workspaceId }: ZenloopStandalonePageProps) {
  const { t } = useTranslation()
  const [busyId, setBusyId] = useState<string | null>(null)

  const status = useMcpTool<ZenloopStatusData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'zenloop_status',
    {},
  )

  const runCycle = async (loopType: string) => {
    if (!workspaceId) return
    setBusyId(loopType)
    try {
      await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'zenloop_bridge_run', {})
    } finally {
      setBusyId(null)
    }
  }

  const byChannel = status.data?.by_channel ?? {}
  const topItems = status.data?.top ?? []
  const totalActive = status.data?.active ?? 0

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.zenloop.title', 'ZenLoop')}</div>
              <div className={ZS.subtitle}>{t('zenskill.zenloop.subtitle', '自动化反思循环')}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* Loading */}
          {status.loading && !status.data && (
            <div className="space-y-3">
              <div className={`${ZS.skeleton} w-48`} />
              <div className={`${ZS.skeleton} w-64`} />
            </div>
          )}

          {/* Error */}
          {status.error && (
            <div className={ZS.errorBanner}>{status.error}</div>
          )}

          {/* Status overview */}
          {status.data && (
            <div className={ZS.card}>
              <div className={ZS.sectionHeader}>
                <Sprout className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.zenloop.status', '状态概览')}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div className="text-center">
                  <div className="text-lg font-semibold">{totalActive}</div>
                  <div className="text-[10px] text-muted-foreground">活跃条目</div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-semibold">{Object.keys(byChannel).length}</div>
                  <div className="text-[10px] text-muted-foreground">通道数</div>
                </div>
              </div>

              {/* Channel breakdown */}
              <div className="flex gap-2 mt-3 flex-wrap">
                {Object.entries(byChannel).map(([channel, count]) => (
                  <span
                    key={channel}
                    className={`text-[10px] px-2 py-0.5 rounded ${CHANNEL_COLORS[channel] || 'bg-muted text-muted-foreground'}`}
                  >
                    {channel}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className={ZS.card}>
            <div className={ZS.sectionHeader}>
              <Play className="h-3.5 w-3.5 text-muted-foreground" />
              <span className={ZS.body + ' font-medium text-muted-foreground'}>
                {t('zenskill.zenloop.actions', '手动触发')}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {['reflection', 'consolidation', 'insight', 'purification'].map((type) => (
                <button
                  key={type}
                  onClick={() => runCycle(type)}
                  disabled={busyId !== null}
                  className="px-3 py-2 rounded border border-border/30 text-xs hover:bg-muted/50 disabled:opacity-40 transition-colors"
                >
                  {busyId === type ? (
                    <RefreshCw className="h-3 w-3 animate-spin mx-auto" />
                  ) : (
                    t(`zenskill.zenloop.cycle.${type}`, type)
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Incubating pool */}
          <ErrorBoundary componentName="IncubatingPanel">
            <IncubatingPanel
              variant="full"
              workspaceId={workspaceId}
              sourceSlug={ZENSKILL_SOURCE_SLUG}
              busyId={busyId}
              onPromote={(itemId) => {
                setBusyId(itemId)
                window.electronAPI.callMcpTool(workspaceId!, ZENSKILL_SOURCE_SLUG, 'incubating_promote', { item_id: itemId })
                  .finally(() => setBusyId(null))
              }}
            />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  )
}
