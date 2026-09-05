/**
 * HabitList — 习惯列表
 *
 * 从 ZenSkillDataPanel Skills tab 提取。显示多个习惯的 streak/完成率/热力图/打卡按钮。
 */
import React from 'react'
import { Flame, Check } from 'lucide-react'
import { ZS } from './tokens'
import { HabitHeatmap } from './HabitHeatmap'

export interface Habit {
  id: string
  name?: string
  title?: string
  completion_rate?: number
  streak?: number
  target?: number
  best_streak?: number
  risk?: string
  completed?: Record<string, boolean>
}

export interface HabitListProps {
  habits: Habit[]
  maxItems?: number
  onCheckIn?: (habitId: string) => void
}

export function HabitList({ habits, maxItems = 4, onCheckIn }: HabitListProps) {
  if (habits.length === 0) {
    return <div className={ZS.emptyState}>暂无习惯</div>
  }

  return (
    <div>
      <div className={ZS.sectionHeader}>
        <Flame className="h-3.5 w-3.5 text-muted-foreground" />
        <span className={ZS.body + ' font-medium text-muted-foreground'}>
          Habits ({habits.length})
        </span>
      </div>
      <div className="space-y-1.5">
        {habits.slice(0, maxItems).map((h) => (
          <div key={h.id} className={ZS.hoverRow}>
            <div className="flex items-center justify-between gap-2">
              <span className="truncate">{h.title || h.name || h.id}</span>
              <div className="flex items-center gap-2 shrink-0">
                {(h.streak ?? 0) > 0 && (
                  <span className="text-[10px] text-orange-500">🔥{h.streak}</span>
                )}
                <span className="text-[10px] text-muted-foreground">
                  {Math.round((h.completion_rate ?? 0) * 100)}%
                </span>
                {onCheckIn && (
                  <button
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400"
                    title="Check in"
                    onClick={() => onCheckIn(h.id)}
                  >
                    <Check className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
            {h.completed && <HabitHeatmap completed={h.completed} />}
          </div>
        ))}
      </div>
    </div>
  )
}
