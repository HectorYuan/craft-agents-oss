/**
 * HabitHeatmap — 单个习惯的打卡热力图
 *
 * 从 ZenSkillDataPanel Skills tab 提取。CSS Grid 7xN 热力图。
 * 绿色=完成，灰色=未完成。
 */
import React from 'react'

export interface HabitHeatmapProps {
  completed: Record<string, boolean>
  days?: number
}

export function HabitHeatmap({ completed, days = 7 }: HabitHeatmapProps) {
  const entries = Object.entries(completed).slice(-days)

  if (entries.length === 0) {
    return <span className="text-[9px] text-muted-foreground/60">—</span>
  }

  return (
    <div className="flex items-center gap-0.5">
      {entries.map(([day, ok]) => (
        <span
          key={day}
          title={day}
          className={`h-2.5 w-2.5 rounded-[3px] ${ok ? 'bg-green-500/70' : 'bg-muted/60'}`}
        />
      ))}
      <span className="text-[9px] text-muted-foreground/60 ml-1">{days}d</span>
    </div>
  )
}
