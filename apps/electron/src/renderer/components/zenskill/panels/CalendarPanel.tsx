/**
 * CalendarPanel — GTD calendar events extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab (flat today list). full variant
 * (GtdWorkspace): a real month grid (calendar_month data with heat badges
 * and event chips), a selected-day detail sidebar (day events + due
 * actions + inline add form + calendar_delete with two-click confirm),
 * and calendar_suggest chips that prefill the add form. today/week stay
 * as quick scopes (week = current week row highlighted on the grid).
 *
 * calendar_month / calendar_suggest shapes are contract-pending (Python
 * side in sync) — every read goes through optional chaining.
 */
import React, { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { CalendarOff, ChevronLeft, ChevronRight, CircleDashed, Plus, Trash2, Wand2 } from 'lucide-react'
import type { Locale } from 'date-fns'
import { getDateLocale } from '@craft-agent/shared/i18n'
import type { GtdAction, GtdCalendarEvent, GtdCalendarEventWithId, GtdCalendarMonthData, GtdCalendarSuggestion } from './types'
import { parseIsoDate, weekKey } from './types'

export type CalendarScope = 'month' | 'today' | 'week'

export interface CalendarPanelProps {
  events: GtdCalendarEvent[]
  /** Event count for the header badge (defaults to events.length) */
  count?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  /** full variant: scope switch (controlled); 'month' shows the grid */
  scope?: CalendarScope
  onScopeChange?: (scope: CalendarScope) => void
  scopeLabels?: Partial<Record<CalendarScope, string>>
  /** full variant: calendar_month payload */
  monthData?: GtdCalendarMonthData | null
  /** Display cursor {year, month(1-12)}; falls back to today's month */
  monthYear?: { year: number; month: number }
  onPrevMonth?: () => void
  onNextMonth?: () => void
  /** full variant: selected day (YYYY-MM-DD) + detail data */
  selectedDate?: string
  onSelectDate?: (date: string) => void
  dayEvents?: GtdCalendarEventWithId[]
  dayActions?: GtdAction[]
  /** full variant: calendar_add */
  onAddEvent?: (input: { date: string; title: string; timeStr: string }) => void
  addEventDisabled?: boolean
  /** full variant: calendar_delete */
  onDeleteEvent?: (eventId: string) => void
  /** full variant: calendar_suggest */
  suggestions?: GtdCalendarSuggestion[]
  suggestActive?: boolean
  suggestLoading?: boolean
  onToggleSuggest?: () => void
  busyId?: string | null
}

const SCOPES: CalendarScope[] = ['month', 'today', 'week']

const HEAT_CLASS = ['bg-transparent', 'bg-accent/10', 'bg-accent/20', 'bg-accent/35'] as const
function heatClass(count: number): string {
  if (count >= 4) return HEAT_CLASS[3]
  if (count >= 2) return HEAT_CLASS[2]
  if (count >= 1) return HEAT_CLASS[1]
  return HEAT_CLASS[0]
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

function eventIdOf(e: GtdCalendarEventWithId): string | undefined {
  return e.event_id ?? e.id
}

function eventTimeOf(e: GtdCalendarEventWithId): string {
  return e.time ?? e.time_str ?? ''
}

/** Empty state with an inline lucide icon, following the panels' muted style */
function EmptyHint({ icon: Icon, text }: { icon: React.ComponentType<{ className?: string }>; text: string }) {
  return (
    <div className="flex flex-col items-center gap-1 py-3 text-muted-foreground/60">
      <Icon className="h-4 w-4" />
      <span className="text-[11px] italic">{text}</span>
    </div>
  )
}

export function CalendarPanel({
  events,
  count,
  variant = 'compact',
  showHeader = true,
  scope,
  onScopeChange,
  scopeLabels,
  monthData,
  monthYear,
  onPrevMonth,
  onNextMonth,
  selectedDate,
  onSelectDate,
  dayEvents,
  dayActions,
  onAddEvent,
  addEventDisabled,
  onDeleteEvent,
  suggestions,
  suggestActive,
  suggestLoading,
  onToggleSuggest,
  busyId,
}: CalendarPanelProps) {
  const isFull = variant === 'full'
  const { t, i18n } = useTranslation()
  const dateLocale: Locale = getDateLocale(i18n.language)
  const labelFor = (key: CalendarScope) => scopeLabels?.[key] ?? key

  // Add-form state (prefilled by suggestion chips)
  const [formTitle, setFormTitle] = useState('')
  const [formTime, setFormTime] = useState('')

  // Two-click delete confirm (same pattern as ActionsPanel)
  const [confirmEventId, setConfirmEventId] = useState<string | null>(null)
  const confirmRef = useRef<string | null>(null)
  confirmRef.current = confirmEventId
  const armDelete = (eventId: string) => {
    if (confirmRef.current === eventId) {
      setConfirmEventId(null)
      onDeleteEvent?.(eventId)
    } else {
      setConfirmEventId(eventId)
      setTimeout(() => setConfirmEventId((cur) => (cur === eventId ? null : cur)), 3000)
    }
  }

  const submitAdd = () => {
    const title = formTitle.trim()
    if (!title || !selectedDate || addEventDisabled) return
    onAddEvent?.({ date: selectedDate, title, timeStr: formTime.trim() })
    setFormTitle('')
    setFormTime('')
  }

  const now = new Date()
  const todayIso = `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`
  const todayKey = weekKey(now)

  const displayYear = monthYear?.year ?? now.getFullYear()
  const displayMonth = monthYear?.month ?? now.getMonth() + 1
  const monthEvents = monthData?.events ?? []

  const eventsOn = (dateStr: string): GtdCalendarEventWithId[] =>
    monthEvents.filter((e) => e?.date === dateStr)

  // Month grid: 7 columns, Monday-first, 5-6 rows of current-month days
  const daysInMonth = new Date(displayYear, displayMonth, 0).getDate()
  const firstOffset = (new Date(displayYear, displayMonth - 1, 1).getDay() + 6) % 7
  const cellCount = Math.ceil((firstOffset + daysInMonth) / 7) * 7
  const cells: (number | null)[] = []
  for (let i = 0; i < cellCount; i++) {
    const day = i - firstOffset + 1
    cells.push(day >= 1 && day <= daysInMonth ? day : null)
  }
  const weekdays = Array.from({ length: 7 }, (_, i) =>
    format(new Date(2024, 0, 1 + i), 'EEEEEE', { locale: dateLocale }),
  )

  const selectedDateObj = parseIsoDate(selectedDate)

  // --- compact variant: legacy flat today list, unchanged ---
  if (!isFull) {
    const headerCount = count ?? events.length
    return (
      <div>
        {showHeader && (
          <div className="flex items-center gap-1.5 mb-1.5">
            <span className="text-xs font-medium text-muted-foreground">Calendar ({headerCount})</span>
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

  // --- full variant ---
  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="text-xs font-medium text-muted-foreground">Calendar ({count ?? events.length})</span>
          <span className="ml-auto flex items-center gap-1">
            <button
              onClick={() => onToggleSuggest?.()}
              className={`flex items-center gap-1 px-2 py-0.5 text-[11px] rounded transition-colors ${
                suggestActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              }`}
              title={t('zenskill.gtd.calendar.suggest')}
            >
              <Wand2 className="h-3 w-3" />
              {t('zenskill.gtd.calendar.suggest')}
            </button>
            {SCOPES.map((key) => (
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
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-4 md:items-start">
        {/* Main column: today flat list (today scope) or month grid */}
        <div className="flex-1 min-w-0">
          {scope === 'today' ? (
            events.length === 0 ? (
              <EmptyHint icon={CalendarOff} text={t('zenskill.gtd.calendar.dayEmpty')} />
            ) : (
              <div className="space-y-0.5">
                {events.map((e, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs rounded px-2 py-0.5 hover:bg-muted/50">
                    {e.time && <span className="text-[10px] text-muted-foreground shrink-0">{e.time}</span>}
                    <span className="truncate">{e.title}</span>
                  </div>
                ))}
              </div>
            )
          ) : (
            <div>
              {/* Month navigation */}
              <div className="flex items-center gap-1 mb-1">
                <button
                  onClick={() => onPrevMonth?.()}
                  className="p-1 rounded text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  title={t('zenskill.gtd.calendar.prevMonth')}
                >
                  <ChevronLeft className="h-3 w-3" />
                </button>
                <span className="text-xs font-medium px-1">
                  {format(new Date(displayYear, displayMonth - 1, 1), 'LLLL yyyy', { locale: dateLocale })}
                </span>
                <button
                  onClick={() => onNextMonth?.()}
                  className="p-1 rounded text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                  title={t('zenskill.gtd.calendar.nextMonth')}
                >
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
              {/* Weekday header */}
              <div className="grid grid-cols-7 gap-0.5 mb-0.5">
                {weekdays.map((wd) => (
                  <div key={wd} className="text-center text-[9px] text-muted-foreground/70 uppercase">{wd}</div>
                ))}
              </div>
              {/* Day cells */}
              <div className="grid grid-cols-7 gap-0.5">
                {cells.map((day, i) => {
                  if (day === null) return <div key={`blank-${i}`} className="h-16 rounded border border-transparent" />
                  const dateStr = `${displayYear}-${pad2(displayMonth)}-${pad2(day)}`
                  const isToday = dateStr === todayIso
                  const isSelected = dateStr === selectedDate
                  const inWeek = scope === 'week' && weekKey(parseIsoDate(dateStr)!) === todayKey
                  const cellEvents = eventsOn(dateStr)
                  const cellCountNum = monthData?.days?.[dateStr] ?? cellEvents.length
                  return (
                    <button
                      key={dateStr}
                      onClick={() => onSelectDate?.(dateStr)}
                      className={`h-16 rounded border px-1 py-0.5 text-left transition-colors ${
                        isSelected
                          ? 'border-accent ring-1 ring-accent'
                          : inWeek
                            ? 'border-transparent bg-muted/40 hover:border-accent/50'
                            : 'border-border/30 hover:border-accent/50'
                      }`}
                    >
                      <div className={`h-full rounded-sm px-0.5 pt-0.5 ${heatClass(cellCountNum)}`}>
                        <div className="flex items-center justify-between">
                          {isToday ? (
                            <span className="inline-flex h-3.5 min-w-[14px] px-0.5 items-center justify-center rounded-full bg-accent text-[9px] font-semibold text-white">
                              {day}
                            </span>
                          ) : (
                            <span className="text-[10px] text-muted-foreground tabular-nums">{day}</span>
                          )}
                          {cellCountNum > 0 && (
                            <span className="text-[9px] text-accent/80 tabular-nums" title={`${cellCountNum}`}>
                              {cellCountNum}
                            </span>
                          )}
                        </div>
                        {cellEvents.slice(0, 2).map((e, j) => {
                          const time = eventTimeOf(e)
                          return (
                            <div key={j} className="truncate text-[9px] leading-[13px] rounded bg-background/70 px-0.5 text-foreground/80">
                              {time && <span className="text-accent/80 mr-0.5 tabular-nums">{time}</span>}
                              {e.title ?? ''}
                            </div>
                          )
                        })}
                        {cellEvents.length > 2 && (
                          <div className="text-[8px] leading-[11px] text-muted-foreground px-0.5">+{cellEvents.length - 2}</div>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Selected-day detail sidebar */}
        <div className="w-full md:w-72 shrink-0 space-y-2">
          {selectedDateObj && (
            <>
              <div className="text-xs font-medium border-b border-border/30 pb-1">
                {format(selectedDateObj, 'EEE, MMM d', { locale: dateLocale })}
                {selectedDate === todayIso && (
                  <span className="ml-1.5 text-[9px] px-1 py-px rounded bg-accent/15 text-accent align-middle">
                    {labelFor('today')}
                  </span>
                )}
              </div>

              {/* Suggested slots (calendar_suggest) — chips prefill the add form */}
              {suggestActive && (
                <div className="rounded border border-border/30 p-1.5">
                  <div className="text-[10px] font-medium text-muted-foreground mb-1 flex items-center gap-1">
                    <Wand2 className="h-3 w-3" />
                    {t('zenskill.gtd.calendar.suggestTitle')}
                  </div>
                  {suggestLoading && !suggestions?.length ? (
                    <div className="space-y-1">
                      <div className="h-4 w-3/4 rounded bg-muted/60 animate-pulse" />
                      <div className="h-4 w-2/3 rounded bg-muted/60 animate-pulse" />
                    </div>
                  ) : !suggestions?.length ? (
                    <div className="text-[10px] text-muted-foreground italic">{t('zenskill.gtd.calendar.suggestEmpty')}</div>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {suggestions.slice(0, 3).map((s, i) => {
                        const d = parseIsoDate(s.date)
                        return (
                          <button
                            key={i}
                            onClick={() => {
                              if (!s.date) return
                              onSelectDate?.(s.date)
                              setFormTime(s.time_str ?? '')
                            }}
                            className="px-1.5 py-0.5 text-[10px] rounded bg-accent/10 text-accent hover:bg-accent/20 transition-colors tabular-nums"
                          >
                            {d ? format(d, 'MM-dd', { locale: dateLocale }) : (s.date ?? '?')}
                            {s.time_str ? ` ${s.time_str}` : ''}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Inline add form (calendar_add) */}
              <div className="flex items-center gap-1.5">
                <input
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.nativeEvent.isComposing) submitAdd()
                  }}
                  placeholder={t('zenskill.gtd.calendar.addPlaceholder')}
                  disabled={addEventDisabled}
                  className="flex-1 min-w-0 text-xs bg-muted/40 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
                />
                <input
                  type="time"
                  value={formTime}
                  onChange={(e) => setFormTime(e.target.value)}
                  disabled={addEventDisabled}
                  aria-label={t('zenskill.gtd.calendar.timeLabel')}
                  className="text-xs bg-muted/40 rounded px-1 py-1 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground disabled:opacity-50"
                />
                <button
                  onClick={submitAdd}
                  disabled={addEventDisabled || !formTitle.trim()}
                  className="p-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40 shrink-0"
                  title={t('zenskill.gtd.calendar.addTitle')}
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Day events */}
              <div>
                <div className="text-[10px] font-medium text-muted-foreground mb-0.5">
                  {t('zenskill.gtd.calendar.dayEvents')} ({dayEvents?.length ?? 0})
                </div>
                {!dayEvents?.length ? (
                  <EmptyHint icon={CalendarOff} text={t('zenskill.gtd.calendar.dayEmpty')} />
                ) : (
                  <div className="space-y-0.5">
                    {dayEvents.map((e, i) => {
                      const eventId = eventIdOf(e)
                      const time = eventTimeOf(e)
                      return (
                        <div key={eventId ?? `event-${i}`} className="flex items-center gap-1.5 text-xs rounded px-2 py-0.5 hover:bg-muted/50 group">
                          {time && <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums">{time}</span>}
                          <span className="truncate flex-1">{e.title ?? ''}</span>
                          {eventId && onDeleteEvent && (
                            <button
                              className={`opacity-0 group-hover:opacity-100 p-0.5 rounded shrink-0 ${
                                confirmEventId === eventId
                                  ? 'bg-red-500/25 text-red-400'
                                  : 'hover:bg-red-500/20 text-muted-foreground hover:text-red-400'
                              }`}
                              title={confirmEventId === eventId ? t('zenskill.gtd.calendar.deleteConfirm') : t('zenskill.gtd.calendar.deleteEvent')}
                              disabled={busyId === eventId}
                              onClick={() => armDelete(eventId)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Due actions on the selected day */}
              <div>
                <div className="text-[10px] font-medium text-muted-foreground mb-0.5">
                  {t('zenskill.gtd.calendar.dayActions')} ({dayActions?.length ?? 0})
                </div>
                {!dayActions?.length ? (
                  <EmptyHint icon={CircleDashed} text={t('zenskill.gtd.calendar.dayActionsEmpty')} />
                ) : (
                  <div className="space-y-0.5">
                    {dayActions.map((a) => (
                      <div key={a.id} className="flex items-center gap-1.5 text-xs rounded px-2 py-0.5 hover:bg-muted/50">
                        <span className={`text-[9px] px-1 py-px rounded shrink-0 ${PRIORITY_BG(a.priority)}`}>
                          {a.priority || 'P2'}
                        </span>
                        <span className="truncate flex-1">{a.title}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** Priority chip background (local helper to keep the sidebar rows light) */
function PRIORITY_BG(priority?: string): string {
  switch (priority) {
    case 'P0': return 'bg-red-500/15 text-red-400'
    case 'P1': return 'bg-orange-500/15 text-orange-400'
    case 'P2': return 'bg-yellow-500/15 text-yellow-400'
    default: return 'bg-muted text-muted-foreground'
  }
}
