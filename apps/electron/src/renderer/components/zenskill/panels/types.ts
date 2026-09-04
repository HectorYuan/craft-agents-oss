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
}

export interface GtdCalendarEvent {
  date: string
  time: string
  title: string
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
