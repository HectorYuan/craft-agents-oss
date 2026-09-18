/**
 * ZenloopStandalonePage — ZenLoop 独立页面
 *
 * 展示 ZenLoop 循环状态、孵化池概览、手动触发入口。
 * 数据源：zenloop_status + incubating_list MCP 工具。
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { RefreshCw, Sprout, Play, Pause, Lightbulb } from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { IncubatingPanel } from '../panels/IncubatingPanel'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

interface ToolOutcome { ok?: boolean; executed?: number; message?: string }

interface ZenloopStatusData {
  active?: number
  by_channel?: Record<string, number>
  top?: { id: string; channel: string; maturity: number; concept: string }[]
  message?: string
}

interface InsightItem {
  id?: string
  type?: string
  title?: string
  content?: string
  level?: string
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
  const [incubatingRefresh, setIncubatingRefresh] = useState(0)

  const status = useMcpTool<ZenloopStatusData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'zenloop_status',
    {},
  )

  // W3.3: insights feed（复用 proactive_insight 洞察数据）
  const insights = useMcpTool<{ items?: InsightItem[] }>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'proactive_insight',
    {},
  )

  // zenloop_run / zenloop_bridge_run are not write tools backend-side, so no
  // zenskill:changed broadcast follows — refresh the reads manually here.
  const runCycle = async (tool: string, args: Record<string, unknown>, busyKey: string) => {
    if (!workspaceId) return
    setBusyId(busyKey)
    try {
      const result = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, tool, args)
      const data = extractMcpJson(result) as ToolOutcome | null
      if (data?.ok === false) {
        toast.error(t('zenskill.toast.toolFailed'), {
          description: typeof data.message === 'string' ? data.message : undefined,
        })
      } else {
        toast.success(t('zenskill.zenloop.runDone', '循环执行完成'), {
          description: typeof data?.message === 'string' ? data.message : undefined,
        })
      }
      status.refresh()
      setIncubatingRefresh((n) => n + 1)
    } catch {
      toast.error(t('zenskill.toast.toolFailed'))
    } finally {
      setBusyId(null)
    }
  }

  const runLoop = (loopType: string) => runCycle('zenloop_run', { loop_type: loopType }, loopType)
  const runBridge = () => runCycle('zenloop_bridge_run', {}, 'bridge')

  const batchPromote = async (itemIds: string[]) => {
    if (!workspaceId || itemIds.length === 0) return
    setBusyId('batch-promote')
    let promoted = 0
    let failed = 0
    try {
      for (const itemId of itemIds) {
        try {
          const result = await window.electronAPI.callMcpTool(
            workspaceId, ZENSKILL_SOURCE_SLUG, 'incubating_promote', { item_id: itemId },
          )
          const data = extractMcpJson(result) as ToolOutcome | null
          if (!data || data.ok === false) failed += 1
          else promoted += 1
        } catch {
          failed += 1
        }
      }
    } finally {
      setBusyId(null)
    }
    if (failed > 0) {
      toast.error(t('zenskill.toast.batchPromotePartial', {
        promoted,
        failed,
        defaultValue: '{{promoted}} 项已提升，{{failed}} 项失败',
      }))
    } else {
      toast.success(t('zenskill.toast.batchPromoted', {
        n: promoted,
        defaultValue: '已批量提升 {{n}} 项',
      }))
    }
    setIncubatingRefresh((n) => n + 1)
  }

  const byChannel = status.data?.by_channel ?? {}
  const topItems = status.data?.top ?? []
  const totalActive = status.data?.active ?? 0

  return (
    // min-w-0 + overflow-x-hidden keep the page strictly inside the main
    // content panel — a wide child must never extend the page box over the
    // left sidebar (TC-08b: sidebar clicks were swallowed by the page layer).
    <div className="flex flex-col h-full min-w-0 overflow-x-hidden">
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
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="space-y-4">
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
                  <div className="text-xs text-muted-foreground">活跃条目</div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-semibold">{Object.keys(byChannel).length}</div>
                  <div className="text-xs text-muted-foreground">通道数</div>
                </div>
              </div>

              {/* Channel breakdown */}
              <div className="flex gap-2 mt-3 flex-wrap">
                {Object.entries(byChannel).map(([channel, count]) => (
                  <span
                    key={channel}
                    className={`text-xs px-2 py-0.5 rounded ${CHANNEL_COLORS[channel] || 'bg-muted text-muted-foreground'}`}
                  >
                    {channel}: {count}
                  </span>
                ))}
              </div>

              {/* W3.3: 通道成熟度看板（top 条目 + 进度条） */}
              {topItems.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <div className="text-xs text-muted-foreground font-medium">通道明细</div>
                  {topItems.slice(0, 6).map((item) => (
                    <div key={item.id} className="flex items-center gap-2 text-sm">
                      <span className={`px-1.5 py-0.5 rounded text-xs shrink-0 ${CHANNEL_COLORS[item.channel] || 'bg-muted text-muted-foreground'}`}>
                        {item.channel}
                      </span>
                      <span className="flex-1 truncate text-muted-foreground">{item.concept}</span>
                      <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden shrink-0">
                        <div
                          className="h-full rounded-full bg-accent/60 transition-all"
                          style={{ width: `${Math.round(item.maturity * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground w-8 text-right shrink-0">
                        {Math.round(item.maturity * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* W3.3: Insights feed */}
          {insights.data?.items && insights.data.items.length > 0 && (
            <div className={ZS.card}>
              <div className={ZS.sectionHeader}>
                <Lightbulb className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {t('zenskill.zenloop.insights', '循环洞察')}
                </span>
              </div>
              <div className="space-y-2 mt-2">
                {insights.data.items.slice(0, 5).map((item, i) => (
                  <div key={item.id || i} className="text-sm flex items-start gap-1.5">
                    <span className={`px-1.5 py-0.5 rounded text-xs shrink-0 ${
                      item.type === 'celebration' ? 'bg-green-500/15 text-green-400' :
                      item.type === 'warning' ? 'bg-red-500/15 text-red-400' :
                      'bg-blue-500/15 text-blue-400'
                    }`}>
                      {item.type || 'info'}
                    </span>
                    <div className="min-w-0">
                      <div className="font-medium truncate">{item.title}</div>
                      {item.content && (
                        <div className="text-muted-foreground line-clamp-2">{item.content}</div>
                      )}
                    </div>
                  </div>
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
                  onClick={() => runLoop(type)}
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
            <button
              onClick={runBridge}
              disabled={busyId !== null}
              className="mt-2 w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded border border-border/30 text-xs hover:bg-muted/50 disabled:opacity-40 transition-colors"
            >
              {busyId === 'bridge' ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Sprout className="h-3 w-3" />
              )}
              {t('zenskill.zenloop.bridgeRun', 'GTD 联动桥')}
            </button>
          </div>

          {/* Incubating pool */}
          <ErrorBoundary componentName="IncubatingPanel">
            <IncubatingPanel
              variant="full"
              workspaceId={workspaceId}
              sourceSlug={ZENSKILL_SOURCE_SLUG}
              busyId={busyId}
              refreshSignal={incubatingRefresh}
              onPromote={(itemId) => {
                setBusyId(itemId)
                window.electronAPI.callMcpTool(workspaceId!, ZENSKILL_SOURCE_SLUG, 'incubating_promote', { item_id: itemId })
                  .finally(() => setBusyId(null))
              }}
              onBatchPromote={(itemIds) => void batchPromote(itemIds)}
            />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  )
}
