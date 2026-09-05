/**
 * GrowthCard — 技能成长卡片
 *
 * 从 ZenSkillDataPanel Today tab 提取。技能列表 + 等级标签 + 五维条形图。
 * 过滤 composite 字段，只展示 5 个核心维度。
 */
import React from 'react'
import { TrendingUp } from 'lucide-react'
import { ZS } from './tokens'

const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']

export interface GrowthSkill {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

export interface GrowthCardProps {
  skills: GrowthSkill[]
  maxItems?: number
  onNavigateToChat?: (msg: string) => void
}

/** 过滤掉 composite，只保留 5 个核心维度 */
export function filterScores(scores: Record<string, number>): Record<string, number> {
  const filtered: Record<string, number> = {}
  for (const k of FIVE_DIMS) {
    if (k in scores) filtered[k] = scores[k]
  }
  return filtered
}

export function GrowthCard({ skills, maxItems = 3, onNavigateToChat }: GrowthCardProps) {
  if (skills.length === 0) {
    return <div className={ZS.emptyState}>暂无数据</div>
  }

  return (
    <div>
      <div className={ZS.sectionHeader}>
        <TrendingUp className="h-3.5 w-3.5 text-muted-foreground" />
        <span className={ZS.body + ' font-medium text-muted-foreground'}>
          Growth ({skills.length})
        </span>
      </div>
      <div className="space-y-1.5">
        {skills.slice(0, maxItems).map((g) => (
          <div
            key={g.skill_id}
            className={ZS.hoverRow}
            onClick={() => onNavigateToChat?.(`帮我了解 ${g.skill_id} 的成长情况`)}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{g.skill_id}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                {g.level && (
                  <span className="text-[9px] px-1 py-px rounded bg-accent/10 text-accent">
                    {g.level}
                  </span>
                )}
                {g.usage_count != null && (
                  <span className="text-[10px] text-muted-foreground">{g.usage_count}次</span>
                )}
                {g.success_rate != null && (
                  <span className="text-[10px] text-green-500/80">
                    {Math.round(g.success_rate * 100)}%
                  </span>
                )}
              </div>
            </div>
            {g.scores && (
              <div className="flex items-center gap-1 mt-1">
                {Object.entries(filterScores(g.scores)).map(([k, v]) => (
                  <div key={k} className="flex-1" title={`${k}: ${v}`}>
                    <div className="h-1 rounded bg-muted/60 overflow-hidden">
                      <div className="h-full bg-accent/70" style={{ width: `${v}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
