/**
 * EnergyBar — 能量条可视化组件
 *
 * 从 ZenSkillDataPanel Today tab 提取。根据 pct 值显示不同颜色。
 */
import React from 'react'

export interface EnergyBarProps {
  level: string
  pct: number
  current?: number
  max?: number
}

function energyColor(pct: number): string {
  if (pct > 0.7) return 'bg-green-500/70'
  if (pct > 0.3) return 'bg-yellow-500/70'
  if (pct > 0.1) return 'bg-orange-500/70'
  return 'bg-red-500/70'
}

export function EnergyBar({ level, pct, current, max }: EnergyBarProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded bg-muted/60 overflow-hidden">
        <div
          className={`h-full rounded transition-all ${energyColor(pct)}`}
          style={{ width: `${Math.round(pct * 100)}%` }}
        />
      </div>
      <span className="text-[10px] text-muted-foreground w-8 text-right shrink-0">
        {Math.round(pct * 100)}%
      </span>
    </div>
  )
}

/** energyChipClass — 根据 energy_required 值返回芯片颜色类 */
export function energyChipClass(value: number): string {
  if (value <= 3) return 'bg-green-500/10 text-green-400'
  if (value <= 6) return 'bg-yellow-500/10 text-yellow-400'
  return 'bg-red-500/10 text-red-400'
}
