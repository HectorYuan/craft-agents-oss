/**
 * LearningPathPage — 学习路径页面
 *
 * 用户输入目标技能，生成学习路径（按难度递增 + 已有技能前置）。
 * 数据源：learning_path MCP 工具。
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BookOpen, Search, ArrowRight, Clock, ChevronRight } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'
import { ErrorBoundary } from '../panels/ErrorBoundary'

// Must match ZENSKILL_SOURCE_SLUG in ../zenskill-registry. Imported values are
// avoided here because the registry imports every page (import cycle).
const ZENSKILL_SOURCE_SLUG = 'zenskill-4'

interface LearningStep {
  skill_id: string
  name: string
  difficulty: string
  estimated_interactions: number
  description?: string
}

interface LearningPathData {
  target?: string
  owned_skills?: string[]
  steps?: LearningStep[]
  estimated_total_interactions?: number
  message?: string
}

interface LearningPathPageProps {
  workspaceId?: string
  initialTab?: string
  onNavigateToChat?: (msg: string) => void
}

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: 'bg-green-500/15 text-green-400',
  intermediate: 'bg-yellow-500/15 text-yellow-400',
  advanced: 'bg-orange-500/15 text-orange-400',
  expert: 'bg-red-500/15 text-red-400',
}

export function LearningPathPage({ workspaceId, onNavigateToChat }: LearningPathPageProps) {
  const { t } = useTranslation()
  const [target, setTarget] = useState('')
  const [query, setQuery] = useState('')

  const path = useMcpTool<LearningPathData>(
    query ? workspaceId : undefined,
    ZENSKILL_SOURCE_SLUG,
    'learning_path',
    { target_skill: query, top_k: 8 },
  )

  const handleSubmit = () => {
    const trimmed = target.trim()
    if (trimmed) setQuery(trimmed)
  }

  const data = path.data
  const steps = data?.steps ?? []

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.learningPath.title', 'Learning Path')}</div>
              <div className={ZS.subtitle}>{t('zenskill.learningPath.subtitle', '生成学习路径')}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Search input */}
      <div className="px-5 pt-4 shrink-0">
        <div className="flex gap-2 max-w-2xl">
          <div className="relative flex-1">
            <Search className="h-3.5 w-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit() }}
              placeholder={t('zenskill.learningPath.placeholder', '输入目标技能...')}
              className="w-full text-xs bg-muted/40 rounded pl-7 pr-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={!target.trim() || path.loading}
            className="px-3 py-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 text-xs disabled:opacity-40"
          >
            {t('zenskill.learningPath.generate', '生成路径')}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* Loading */}
          {path.loading && (
            <div className="space-y-3">
              <div className={`${ZS.skeleton} w-48`} />
              <div className={`${ZS.skeleton} w-64`} />
              <div className={`${ZS.skeleton} w-56`} />
            </div>
          )}

          {/* Error */}
          {path.error && (
            <div className={ZS.errorBanner}>{path.error}</div>
          )}

          {/* Empty state */}
          {!path.loading && !path.error && !data && (
            <div className="text-center py-12 text-muted-foreground">
              <BookOpen className="h-8 w-8 mx-auto mb-3 opacity-40" />
              <div className="text-sm">{t('zenskill.learningPath.empty', '输入目标技能以生成学习路径')}</div>
            </div>
          )}

          {/* Results */}
          {data && (
            <>
              {/* Summary */}
              <div className={ZS.card}>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{data.message}</span>
                  {data.estimated_total_interactions && (
                    <span className="flex items-center gap-1 ml-auto">
                      <Clock className="h-3 w-3" />
                      ~{data.estimated_total_interactions} 次交互
                    </span>
                  )}
                </div>
                {data.owned_skills && data.owned_skills.length > 0 && (
                  <div className="text-[10px] text-muted-foreground/60 mt-1">
                    已有技能: {data.owned_skills.join(', ')}
                  </div>
                )}
              </div>

              {/* Steps */}
              {steps.length > 0 && (
                <ErrorBoundary componentName="LearningPathSteps">
                  <div className="space-y-2">
                    {steps.map((step, index) => (
                      <div
                        key={step.skill_id}
                        className={`${ZS.card} flex items-start gap-3`}
                      >
                        {/* Step number */}
                        <div className="shrink-0 w-6 h-6 rounded-full bg-accent/10 text-accent flex items-center justify-center text-[10px] font-medium">
                          {index + 1}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium truncate">{step.name}</span>
                            <span className={`text-[9px] px-1 py-0.5 rounded ${DIFFICULTY_COLORS[step.difficulty] || DIFFICULTY_COLORS.beginner}`}>
                              {step.difficulty}
                            </span>
                          </div>
                          {step.description && (
                            <div className="text-[10px] text-muted-foreground/70 mt-0.5 line-clamp-2">
                              {step.description}
                            </div>
                          )}
                          <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground/60">
                            <span>~{step.estimated_interactions} 次交互</span>
                          </div>
                        </div>

                        {/* Arrow to next */}
                        {index < steps.length - 1 && (
                          <ArrowRight className="h-3 w-3 text-muted-foreground/30 shrink-0 mt-2" />
                        )}
                      </div>
                    ))}
                  </div>
                </ErrorBoundary>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
