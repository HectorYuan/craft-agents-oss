/**
 * CompanionCard — 陪伴感卡片
 *
 * 从 ZenSkillDataPanel Today tab 提取。问候语 + 能量条 + 紧急事项 + 洞察 + 建议。
 */
import React from 'react'
import { Lightbulb } from 'lucide-react'
import { ZS } from './tokens'
import { EnergyBar } from './EnergyBar'

export interface CompanionSummary {
  mood: string
  energy: { level: string; pct: number; current: number; max: number }
  inbox_pending: number
  pending_actions: number
  due_today: number
  overdue: number
  top_insight?: { type: string; title: string; content: string } | null
}

export interface CompanionCardProps {
  companion: CompanionSummary
  suggestions?: string[]
  dailyReviewMsg?: string
  onNavigateToChat?: (msg: string) => void
}

export function CompanionCard({ companion, suggestions, dailyReviewMsg, onNavigateToChat }: CompanionCardProps) {
  return (
    <div className={ZS.card + ' space-y-1.5'}>
      <div className={ZS.body + ' text-muted-foreground'}>{companion.mood}</div>

      <EnergyBar {...companion.energy} />

      {(companion.overdue > 0 || companion.due_today > 0) && (
        <div className="flex gap-3 text-[10px]">
          {companion.overdue > 0 && (
            <span className="text-red-400">⚠ {companion.overdue} overdue</span>
          )}
          {companion.due_today > 0 && (
            <span className="text-yellow-400">📅 {companion.due_today} due today</span>
          )}
        </div>
      )}

      {companion.top_insight && (
        <button
          className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70 text-left w-full"
          onClick={() => onNavigateToChat?.(`帮我分析这个洞察: ${companion.top_insight!.title}`)}
        >
          <Lightbulb className="h-3 w-3 mt-px shrink-0 text-yellow-500/60" />
          <span>{companion.top_insight.title}</span>
        </button>
      )}

      {suggestions && suggestions.length > 0 && (
        <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70">
          <Lightbulb className="h-3 w-3 mt-px shrink-0 text-yellow-500/60" />
          <span>{suggestions[0]}</span>
        </div>
      )}

      {dailyReviewMsg && (
        <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground/70 border-t border-border/30 pt-1.5 mt-1.5">
          <span className="shrink-0">📊</span>
          <span className="truncate" title={dailyReviewMsg}>{dailyReviewMsg}</span>
        </div>
      )}
    </div>
  )
}
