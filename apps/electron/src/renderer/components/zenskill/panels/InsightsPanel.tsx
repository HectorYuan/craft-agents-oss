/**
 * InsightsPanel — 主动洞察面板
 *
 * P2 改进：独立的洞察展示组件，支持：
 * - 洞察列表（按类型/级别分组）
 * - 详情展开/收起
 * - 已读标记
 * - 历史记录（可选）
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Lightbulb, AlertTriangle, Info, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react'
import { ZS } from './tokens'

export interface Insight {
  type: string
  title: string
  content: string
  level: string
  id?: string
  timestamp?: string
  read?: boolean
}

export interface InsightsPanelProps {
  insights: Insight[]
  maxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onMarkRead?: (insightId: string) => void
  onExpand?: (insight: Insight) => void
}

const LEVEL_COLORS: Record<string, string> = {
  high: 'bg-red-500/15 text-red-400',
  medium: 'bg-yellow-500/15 text-yellow-400',
  low: 'bg-green-500/15 text-green-400',
}

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  warning: AlertTriangle,
  info: Info,
  success: CheckCircle,
  default: Lightbulb,
}

export function InsightsPanel({
  insights,
  maxItems = 10,
  variant = 'compact',
  showHeader = true,
  onMarkRead,
  onExpand,
}: InsightsPanelProps) {
  const { t } = useTranslation()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [readIds, setReadIds] = useState<Set<string>>(new Set())

  if (insights.length === 0) {
    return (
      <div>
        {showHeader && (
          <div className={ZS.sectionHeader}>
            <Lightbulb className="h-3.5 w-3.5 text-muted-foreground" />
            <span className={ZS.body + ' font-medium text-muted-foreground'}>
              {t('zenskill.insights.title', 'Insights')} (0)
            </span>
          </div>
        )}
        <div className={ZS.emptyState + ' pl-5'}>暂无洞察</div>
      </div>
    )
  }

  const handleExpand = (insight: Insight) => {
    const id = insight.id || insight.title
    if (expandedId === id) {
      setExpandedId(null)
    } else {
      setExpandedId(id)
      if (!readIds.has(id) && onMarkRead) {
        onMarkRead(id)
        setReadIds(prev => new Set(prev).add(id))
      }
    }
  }

  return (
    <div>
      {showHeader && (
        <div className={ZS.sectionHeader}>
          <Lightbulb className="h-3.5 w-3.5 text-muted-foreground" />
          <span className={ZS.body + ' font-medium text-muted-foreground'}>
            {t('zenskill.insights.title', 'Insights')} ({insights.length})
          </span>
        </div>
      )}
      <div className="space-y-1">
        {insights.slice(0, maxItems).map((insight, index) => {
          const id = insight.id || insight.title
          const isExpanded = expandedId === id
          const isRead = readIds.has(id)
          const Icon = TYPE_ICONS[insight.type] || TYPE_ICONS.default

          return (
            <div key={index} className="text-xs rounded px-2 py-1.5 hover:bg-muted/50 group">
              <div
                className="flex items-start gap-2 cursor-pointer"
                onClick={() => handleExpand(insight)}
              >
                {/* 展开/收起图标 */}
                <span className="shrink-0 mt-0.5">
                  {isExpanded ? (
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-3 w-3 text-muted-foreground" />
                  )}
                </span>

                {/* 洞察类型图标 */}
                <span className={`shrink-0 mt-0.5 ${LEVEL_COLORS[insight.level] || LEVEL_COLORS.low}`}>
                  <Icon className="h-3 w-3" />
                </span>

                {/* 标题 */}
                <span className={`flex-1 ${isRead ? 'text-muted-foreground/60' : 'text-foreground'}`}>
                  {insight.title}
                </span>

                {/* 级别标签 */}
                <span className={`text-[9px] px-1 py-0.5 rounded shrink-0 ${LEVEL_COLORS[insight.level] || LEVEL_COLORS.low}`}>
                  {insight.level}
                </span>
              </div>

              {/* 展开的详情 */}
              {isExpanded && (
                <div className="mt-2 ml-5 pl-2 border-l border-border/30">
                  <div className="text-[11px] text-muted-foreground/80 whitespace-pre-wrap">
                    {insight.content}
                  </div>
                  {insight.timestamp && (
                    <div className="text-[9px] text-muted-foreground/60 mt-1">
                      {insight.timestamp}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
        {insights.length > maxItems && (
          <div className={ZS.body + ' text-muted-foreground pl-5'}>
            +{insights.length - maxItems} more
          </div>
        )}
      </div>
    </div>
  )
}
