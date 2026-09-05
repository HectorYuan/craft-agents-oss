/**
 * Shared data shapes for the ZenSkill GTD panels.
 * Extracted from ZenSkillDataPanel so both the embedded panel (compact
 * variant) and the GtdWorkspace full page (full variant) render from the
 * same definitions.
 */

export interface GtdItem {
  id: string
  text?: string
  raw_text?: string
  status?: string
  created_at?: string
}

export interface GtdAction {
  id: string
  title: string
  priority?: string
  status?: string
  due_date?: string
  project_id?: string
  energy_required?: number
  /** Origin marker from the backend ("agent" | "user") — rendered as a source chip in full variant */
  created_by?: string
}

export interface GtdCalendarEvent {
  date: string
  time: string
  title: string
}

/** calendar_month / calendar_list event — id fields are contract-pending, read defensively */
export interface GtdCalendarEventWithId extends Partial<GtdCalendarEvent> {
  event_id?: string
  id?: string
  time_str?: string
  period?: string
}

/** calendar_month shape (contract pending — all reads use optional chaining) */
export interface GtdCalendarMonthData {
  year?: number
  month?: number
  days?: Record<string, number>
  events?: GtdCalendarEventWithId[]
}

/** calendar_suggest slot — backend contract: {date, time, period}; time_str kept for pre-fix payloads */
export interface GtdCalendarSuggestion {
  date?: string
  time?: string
  time_str?: string
  period?: string
  score?: number
  reason?: string
}

export interface GtdProject {
  id: string
  name: string
  status?: string
  progress?: number
}

export const PRIORITY_COLOR: Record<string, string> = {
  P0: 'bg-red-500/15 text-red-400',
  P1: 'bg-orange-500/15 text-orange-400',
  P2: 'bg-yellow-500/15 text-yellow-400',
  P3: 'bg-muted text-muted-foreground',
}

/** energy_required chip color, tiered by numeric value (low / mid / high) */
export function energyChipClass(value: number): string {
  if (value <= 3) return 'bg-green-500/10 text-green-400'
  if (value <= 6) return 'bg-yellow-500/10 text-yellow-400'
  return 'bg-red-500/10 text-red-400'
}

/** Parse "YYYY-MM-DD..." as a local date (new Date(iso) would parse as UTC) */
export function parseIsoDate(s?: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s ?? '')
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}

/** Canonical key of the Monday-based week containing d */
export function weekKey(d: Date): string {
  const monday = new Date(d)
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return `${monday.getFullYear()}-${monday.getMonth()}-${monday.getDate()}`
}
