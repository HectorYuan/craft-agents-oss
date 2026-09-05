/**
 * AchievementGrid — 成就徽章网格
 *
 * 从 ZenSkillDataPanel Memory tab 提取。已解锁彩色 + 未解锁灰色 + 进度条。
 */
import React from 'react'
import { Trophy } from 'lucide-react'
import { ZS } from './tokens'

export interface Achievement {
  id: string
  name?: string
  title?: string
  icon?: string
  tier?: string
  description?: string
  unlocked?: boolean
  progress?: number
  detail?: string
}

export interface AchievementGridProps {
  unlocked: Achievement[]
  locked: Achievement[]
  completionRate: number
  onNavigateToChat?: (msg: string) => void
}

export function AchievementGrid({ unlocked, locked, completionRate, onNavigateToChat }: AchievementGridProps) {
  if (unlocked.length === 0 && locked.length === 0) {
    return <div className={ZS.emptyState}>暂无成就</div>
  }

  return (
    <div>
      <div className={ZS.sectionHeader}>
        <Trophy className="h-3.5 w-3.5 text-muted-foreground" />
        <span className={ZS.body + ' font-medium text-muted-foreground'}>
          Achievements ({unlocked.length}/{unlocked.length + locked.length})
        </span>
        {completionRate > 0 && (
          <span className={ZS.micro + ' text-muted-foreground/60 ml-auto'}>
            {Math.round(completionRate * 100)}%
          </span>
        )}
      </div>

      {/* 已解锁徽章 */}
      {unlocked.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-1">
          {unlocked.map((a) => (
            <span
              key={a.id}
              className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent inline-flex items-center gap-1"
              title={`${a.description ?? ''}\n${a.detail ?? ''}`}
            >
              <span>{a.icon || '🏅'}</span>
              {a.title || a.name}
            </span>
          ))}
        </div>
      )}

      {/* 未解锁徽章 + 进度条（最接近解锁的排前面） */}
      {locked.length > 0 && locked.some((a) => (a.progress ?? 0) > 0) && (
        <div className="space-y-1 mt-1.5">
          {locked
            .filter((a) => (a.progress ?? 0) > 0)
            .slice(0, 3)
            .map((a) => (
              <div key={a.id} className="flex items-center gap-1.5 text-[10px]" title={a.description}>
                <span className="text-muted-foreground/40">{a.icon || '🔒'}</span>
                <span className="text-muted-foreground/70 truncate flex-1">{a.title || a.name}</span>
                <div className="w-10 h-1 rounded bg-muted/60 overflow-hidden shrink-0">
                  <div
                    className="h-full bg-accent/40"
                    style={{ width: `${Math.round((a.progress ?? 0) * 100)}%` }}
                  />
                </div>
                <span className="text-muted-foreground/50 w-7 text-right shrink-0">
                  {Math.round((a.progress ?? 0) * 100)}%
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
