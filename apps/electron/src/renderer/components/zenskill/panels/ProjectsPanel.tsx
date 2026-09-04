/**
 * ProjectsPanel — GTD project list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab (name + status only). full variant
 * (GtdWorkspace): adds a progress bar and a hover project_done action.
 */
import React from 'react'
import { Check } from 'lucide-react'
import type { GtdProject } from './types'

export interface ProjectsPanelProps {
  projects: GtdProject[]
  busyId?: string | null
  maxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onDone?: (projectId: string) => void
}

export function ProjectsPanel({
  projects,
  busyId,
  maxItems = 100,
  variant = 'compact',
  showHeader = true,
  onDone,
}: ProjectsPanelProps) {
  const isFull = variant === 'full'

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <span className="text-xs font-medium text-muted-foreground">Projects ({projects.length})</span>
        </div>
      )}
      {projects.length === 0 ? (
        <div className="text-xs text-muted-foreground italic pl-5">No active projects</div>
      ) : (
        <div className="space-y-0.5">
          {projects.slice(0, maxItems).map((p) => (
            <div key={p.id} className="text-xs rounded px-2 py-0.5 flex items-center gap-1.5 group">
              <span className="truncate flex-1">{p.name}</span>
              {p.status && <span className="text-[9px] text-muted-foreground/60 shrink-0">{p.status}</span>}
              {isFull && typeof p.progress === 'number' && (
                <div className="w-12 h-1 rounded bg-muted/60 overflow-hidden shrink-0" title={`${Math.round(p.progress * 100)}%`}>
                  <div className="h-full bg-accent/60" style={{ width: `${Math.round(p.progress * 100)}%` }} />
                </div>
              )}
              {isFull && (
                <button
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-green-500/20 text-muted-foreground hover:text-green-400 shrink-0"
                  title="Done"
                  disabled={busyId === p.id}
                  onClick={() => onDone?.(p.id)}
                >
                  <Check className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
          {projects.length > maxItems && (
            <div className="text-xs text-muted-foreground pl-5">+{projects.length - maxItems} more</div>
          )}
        </div>
      )}
    </div>
  )
}
