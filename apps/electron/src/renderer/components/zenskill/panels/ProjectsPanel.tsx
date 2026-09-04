/**
 * ProjectsPanel — GTD project list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab (name + status only). full variant
 * (GtdWorkspace): adds a progress bar, a hover project_done action, and an
 * expandable chevron per row revealing the project's open actions —
 * fetched lazily through the useMcpTool L3 hook (action_list
 * {project_id}) only while the row is expanded, refreshed by the
 * zenskill:changed broadcast like every other read.
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronRight, CircleDashed } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { PRIORITY_COLOR, type GtdProject } from './types'

export interface ProjectsPanelProps {
  projects: GtdProject[]
  busyId?: string | null
  maxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onDone?: (projectId: string) => void
  /** full variant: enable expandable per-project action lists */
  workspaceId?: string
  sourceSlug?: string
}

interface ProjectActionListData {
  items?: { id: string; title: string; priority?: string; due_date?: string }[]
}

/** Open actions of one project — mounted only while its row is expanded */
function ProjectActions({ projectId, workspaceId, sourceSlug }: { projectId: string; workspaceId: string; sourceSlug: string }) {
  const { t } = useTranslation()
  const actions = useMcpTool<ProjectActionListData>(
    workspaceId,
    sourceSlug,
    'action_list',
    { status: 'pending', project_id: projectId, limit: 20 },
  )
  const items = actions.data?.items ?? []

  if (actions.loading && !actions.data) {
    return (
      <div className="pl-6 pb-1 space-y-1">
        <div className="h-3 w-3/4 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 w-1/2 rounded bg-muted/60 animate-pulse" />
      </div>
    )
  }
  if (actions.error && !actions.data) {
    return <div className="pl-6 pb-1 text-[11px] text-destructive/80 italic truncate" title={actions.error}>{actions.error}</div>
  }
  if (items.length === 0) {
    return (
      <div className="pl-6 pb-1 flex items-center gap-1 text-[11px] text-muted-foreground/60 italic">
        <CircleDashed className="h-3 w-3" />
        {t('zenskill.gtd.projects.actionsEmpty')}
      </div>
    )
  }
  return (
    <div className="pl-6 pb-1 space-y-0.5">
      {items.map((a) => (
        <div key={a.id} className="flex items-center gap-1.5 text-[11px] rounded px-1.5 py-0.5 hover:bg-muted/40">
          <span className={`text-[9px] px-1 py-px rounded shrink-0 ${PRIORITY_COLOR[a.priority || 'P2'] || PRIORITY_COLOR.P2}`}>
            {a.priority || 'P2'}
          </span>
          <span className="truncate flex-1" title={a.title}>{a.title}</span>
          {a.due_date && <span className="text-[10px] text-muted-foreground shrink-0">{a.due_date.slice(5)}</span>}
        </div>
      ))}
    </div>
  )
}

export function ProjectsPanel({
  projects,
  busyId,
  maxItems = 100,
  variant = 'compact',
  showHeader = true,
  onDone,
  workspaceId,
  sourceSlug,
}: ProjectsPanelProps) {
  const isFull = variant === 'full'
  const { t } = useTranslation()
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const canExpand = isFull && !!workspaceId && !!sourceSlug

  const toggleExpand = (id: string) => {
    setExpandedIds((cur) => {
      const next = new Set(cur)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

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
          {projects.slice(0, maxItems).map((p) => {
            const expanded = expandedIds.has(p.id)
            return (
              <div key={p.id}>
                <div className={`text-xs rounded px-2 py-0.5 flex items-center gap-1.5 group ${isFull ? 'hover:bg-muted/40' : ''}`}>
                  {canExpand ? (
                    <button
                      className="p-0.5 -ml-0.5 rounded hover:bg-muted/60 text-muted-foreground shrink-0"
                      title={t('zenskill.gtd.projects.toggle')}
                      aria-expanded={expanded}
                      onClick={() => toggleExpand(p.id)}
                    >
                      <ChevronRight className={`h-3 w-3 transition-transform ${expanded ? 'rotate-90' : ''}`} />
                    </button>
                  ) : null}
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
                {expanded && canExpand && (
                  <ProjectActions projectId={p.id} workspaceId={workspaceId!} sourceSlug={sourceSlug!} />
                )}
              </div>
            )
          })}
          {projects.length > maxItems && (
            <div className="text-xs text-muted-foreground pl-5">+{projects.length - maxItems} more</div>
          )}
        </div>
      )}
    </div>
  )
}
