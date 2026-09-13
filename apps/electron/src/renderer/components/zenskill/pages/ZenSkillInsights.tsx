/**
 * ZenSkillInsights — 独立全页洞察展示
 *
 * 从 ZenSkillOverview 的 InsightsPanel 子组件抽离为独立页面。
 * 支持按类型/优先级筛选，展示所有 proactive_insight 列表。
 */
import React, { useCallback, useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Lightbulb, Filter, AlertTriangle, Info, CheckCircle } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { InsightsPanel, type Insight } from '../panels/InsightsPanel'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { PageToChatBridge } from '../PageToChatBridge'
import { ZS } from '../panels/tokens'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

interface InsightsData {
  items?: { type?: string; title?: string; content?: string; level?: string }[]
}

interface ZenSkillInsightsProps {
  workspaceId?: string
}

type FilterType = 'all' | string
type FilterLevel = 'all' | 'high' | 'medium' | 'low'

const TYPE_OPTIONS: { value: FilterType; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
  { value: 'success', label: 'Success' },
]

const LEVEL_OPTIONS: { value: FilterLevel; label: string }[] = [
  { value: 'all', label: 'All Levels' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

export function ZenSkillInsights({ workspaceId }: ZenSkillInsightsProps) {
  const { t } = useTranslation()
  const insights = useMcpTool<InsightsData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'proactive_insight', {})

  const [typeFilter, setTypeFilter] = useState<FilterType>('all')
  const [levelFilter, setLevelFilter] = useState<FilterLevel>('all')

  const filteredInsights = useMemo(() => {
    const items = insights.data?.items ?? []
    return items.filter((item) => {
      if (typeFilter !== 'all' && item.type !== typeFilter) return false
      if (levelFilter !== 'all' && item.level !== levelFilter) return false
      return true
    })
  }, [insights.data, typeFilter, levelFilter])

  const mappedInsights: Insight[] = filteredInsights.map((item) => ({
    type: item.type || 'info',
    title: item.title || '',
    content: item.content || '',
    level: item.level || 'low',
    id: item.title,
  }))

  const isLoading = insights.loading && !insights.data
  const hasError = insights.error && !insights.data

  // Day 1 PageToChatBridge prompt — insights snapshot as a processing request
  const buildBridgePrompt = useCallback((data: { items?: { title?: string }[] }) => {
    const items = data.items ?? []
    if (items.length === 0) return ''
    const topTitle = typeof items[0]?.title === 'string' ? items[0].title : ''
    return `我有 ${items.length} 条洞察。` +
      (topTitle ? `最新：${topTitle}。` : '') +
      `帮我处理第一条。`
  }, [])

  return (
    <div className="flex flex-col h-full">
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.insights.pageTitle', 'Insights')}</div>
              <div className={ZS.subtitle}>{t('zenskill.insights.pageSubtitle', 'All proactive insights')}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isLoading && (
              <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
                <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
              </div>
            )}
            <PageToChatBridge
              pageName="Insights"
              workspaceId={workspaceId}
              contextData={{ items: insights.data?.items }}
              buildPrompt={buildBridgePrompt}
            />
          </div>
        </div>
      </div>

      {hasError && (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>{insights.error}</div>
      )}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <div className="flex gap-1">
              {TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setTypeFilter(opt.value)}
                  className={`text-[10px] px-2 py-1 rounded transition-colors ${
                    typeFilter === opt.value
                      ? 'bg-accent/20 text-accent'
                      : 'text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <div className="w-px h-3 bg-border/30" />
            <div className="flex gap-1">
              {LEVEL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setLevelFilter(opt.value)}
                  className={`text-[10px] px-2 py-1 rounded transition-colors ${
                    levelFilter === opt.value
                      ? 'bg-accent/20 text-accent'
                      : 'text-muted-foreground hover:bg-muted/50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Stats */}
          <div className="text-[10px] text-muted-foreground">
            {t('zenskill.insights.showing', 'Showing')} {filteredInsights.length} / {(insights.data?.items ?? []).length} {t('zenskill.insights.insights', 'insights')}
          </div>

          {/* Content */}
          {isLoading && (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className={`${ZS.skeleton} w-full`} />
              ))}
            </div>
          )}

          {!isLoading && mappedInsights.length === 0 && (
            <div className={ZS.emptyState}>{t('zenskill.insights.empty', 'No insights match the selected filters')}</div>
          )}

          {mappedInsights.length > 0 && (
            <ErrorBoundary componentName="InsightsPanel">
              <InsightsPanel
                insights={mappedInsights}
                maxItems={mappedInsights.length}
                variant="full"
                showHeader={false}
              />
            </ErrorBoundary>
          )}
        </div>
      </div>
    </div>
  )
}
