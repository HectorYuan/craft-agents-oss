/**
 * CalendarPanel — GTD calendar events extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab. full variant (GtdWorkspace): adds a
 * today/week scope switch (data fetching stays with the parent).
 */
import React from 'react'
import type { GtdCalendarEvent } from './types'

export type CalendarScope = 'today' | 'week'

export interface CalendarPanelProps {
  events: GtdCalendarEvent[]
  /** Event count for the header badge (defaults to events.length) */
  count?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  /** full variant: scope switch (controlled) */
  scope?: CalendarScope
  onScopeChange?: (scope: CalendarScope) => void
  scopeLabels?: Partial<Record<CalendarScope, string>>
}

export function CalendarPanel({
  events,
  count,
  variant = 'compact',
  showHeader = true,
  scope,
  onScopeChange,
  scopeLabels,
}: CalendarPanelProps) {
  const isFull = variant === 'full'
  const headerCount = count ?? events.length
  const labelFor = (key: CalendarScope) => scopeLabels?.[key] ?? key

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="text-xs font-medium text-muted-foreground">Calendar ({headerCount})</span>
          {isFull && (
            <span className="ml-2 flex items-center gap-0.5">
              {(['today', 'week'] as const).map((key) => (
                <button
                  key={key}
                  onClick={() => onScopeChange?.(key)}
                  className={`px-2 py-0.5 text-[11px] rounded transition-colors ${
                    scope === key
                      ? 'bg-accent/15 text-accent'
                      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                  }`}
                >
                  {labelFor(key)}
                </button>
              ))}
            </span>
          )}
        </div>
      )}
      {events.length === 0 ? (
        <div className="text-xs text-muted-foreground italic pl-5">No events today</div>
      ) : (
        <div className="space-y-0.5">
          {events.map((e, i) => (
            <div key={i} className="flex items-center gap-1.5 text-xs rounded px-2 py-0.5">
              {e.time && <span className="text-[10px] text-muted-foreground shrink-0">{e.time}</span>}
              <span className="truncate">{e.title}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
