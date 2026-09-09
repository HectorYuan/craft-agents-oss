/**
 * ProjectsPanel — GTD project list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab (name + status only). full variant
 * (GtdWorkspace): adds a progress bar, a hover project_done action, an
 * expandable chevron per row revealing the project's open actions —
 * fetched lazily through the useMcpTool L3 hook (action_list
 * {project_id}) only while the row is expanded, refreshed by the
 * zenskill:changed broadcast like every other read — a "new project"
 * inline form (name + optional outcome) calling project_add, and a
 * project_update inline edit (name/outcome/notes) in the expanded
 * detail area. compact JSX is unchanged.
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, ChevronRight, CircleDashed, FolderKanban, Pencil, Plus, X } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { PRIORITY_COLOR, type GtdProject } from './types'

export interface ProjectsPanelProps {
  projects: GtdProject[]
  busyId?: string | null
  maxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onDone?: (projectId: string) => void
  /** full variant: project_add form submit */
  onAddProject?: (input: { name: string; outcome?: string }) => void
  addProjectDisabled?: boolean
  /** full variant: project_update inline edit submit */
  onEditProject?: (input: { projectId: string; name: string; outcome?: string; notes?: string }) => void
  editProjectDisabled?: boolean
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
  onAddProject,
  addProjectDisabled,
  onEditProject,
  editProjectDisabled,
  workspaceId,
  sourceSlug,
}: ProjectsPanelProps) {
  const isFull = variant === 'full'
  const { t } = useTranslation()
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const canExpand = isFull && !!workspaceId && !!sourceSlug

  // full variant: project_add inline form
  const [formOpen, setFormOpen] = useState(false)
  const [formName, setFormName] = useState('')
  const [formOutcome, setFormOutcome] = useState('')

  // full variant: project_update inline edit (expanded detail area)
  const [editing, setEditing] = useState<{ id: string; name: string; outcome: string; notes: string } | null>(null)

  const submitAddProject = () => {
    const name = formName.trim()
    if (!name || addProjectDisabled) return
    onAddProject?.({ name, outcome: formOutcome.trim() || undefined })
    setFormName('')
    setFormOutcome('')
    setFormOpen(false)
  }

  const startEdit = (p: GtdProject) => {
    setEditing({ id: p.id, name: p.name, outcome: p.outcome ?? '', notes: p.notes ?? '' })
  }
  const saveEdit = () => {
    if (!editing) return
    const name = editing.name.trim()
    if (!name || editProjectDisabled) { setEditing(null); return }
    // outcome/notes are sent only when non-empty — defensive against
    // pre-fix project_update backends that would reject unknown args
    onEditProject?.({
      projectId: editing.id,
      name,
      outcome: editing.outcome.trim() || undefined,
      notes: editing.notes.trim() || undefined,
    })
    setEditing(null)
  }

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
          {isFull && onAddProject && (
            <button
              onClick={() => setFormOpen((v) => !v)}
              disabled={addProjectDisabled}
              className="ml-auto flex items-center gap-1 px-2 py-0.5 text-[11px] rounded text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
              title={t('zenskill.gtd.projects.addTitle')}
            >
              <Plus className="h-3 w-3" />
              {t('zenskill.gtd.projects.add')}
            </button>
          )}
        </div>
      )}
      {isFull && formOpen && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <input
            value={formName}
            autoFocus
            onChange={(e) => setFormName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) submitAddProject()
              if (e.key === 'Escape') setFormOpen(false)
            }}
            placeholder={t('zenskill.gtd.projects.formName')}
            disabled={addProjectDisabled}
            className="flex-1 min-w-0 text-xs bg-muted/40 rounded px-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
          />
          <input
            value={formOutcome}
            onChange={(e) => setFormOutcome(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) submitAddProject()
              if (e.key === 'Escape') setFormOpen(false)
            }}
            placeholder={t('zenskill.gtd.projects.formOutcome')}
            disabled={addProjectDisabled}
            className="w-40 shrink-0 text-xs bg-muted/40 rounded px-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground disabled:opacity-50"
          />
          <button
            onClick={submitAddProject}
            disabled={addProjectDisabled || !formName.trim()}
            className="p-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40 shrink-0"
            title={t('zenskill.gtd.projects.addTitle')}
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setFormOpen(false)}
            className="p-1.5 rounded text-muted-foreground hover:bg-muted/60 shrink-0"
            title={t('zenskill.gtd.projects.cancel')}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {projects.length === 0 ? (
        isFull ? (
          <div className="flex flex-col items-center gap-1 py-3 text-muted-foreground/60">
            <FolderKanban className="h-4 w-4" />
            <span className="text-[11px] italic">{t('zenskill.gtd.projects.empty')}</span>
            {onAddProject && (
              <button
                onClick={() => setFormOpen(true)}
                disabled={addProjectDisabled}
                className="text-[11px] text-accent hover:underline disabled:opacity-40"
              >
                {t('zenskill.gtd.projects.createFirst')}
              </button>
            )}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground italic pl-5">{t('zenskill.gtd.projects.empty', 'No active projects')}</div>
        )
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
                      title={t('zenskill.gtd.projects.done', 'Done')}
                      disabled={busyId === p.id}
                      onClick={() => onDone?.(p.id)}
                    >
                      <Check className="h-3 w-3" />
                    </button>
                  )}
                </div>
                {expanded && canExpand && (
                  <div className="pl-6 pb-1">
                    {editing && editing.id === p.id ? (
                      <div className="space-y-1 mb-1">
                        <input
                          value={editing.name}
                          autoFocus
                          onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return
                            if (e.key === 'Enter') saveEdit()
                            if (e.key === 'Escape') setEditing(null)
                          }}
                          aria-label={t('zenskill.gtd.projects.formName')}
                          placeholder={t('zenskill.gtd.projects.formName')}
                          className="w-full text-xs bg-muted/40 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-accent/40"
                        />
                        <input
                          value={editing.outcome}
                          onChange={(e) => setEditing({ ...editing, outcome: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return
                            if (e.key === 'Enter') saveEdit()
                            if (e.key === 'Escape') setEditing(null)
                          }}
                          aria-label={t('zenskill.gtd.projects.formOutcome')}
                          placeholder={t('zenskill.gtd.projects.formOutcome')}
                          className="w-full text-xs bg-muted/40 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground"
                        />
                        <input
                          value={editing.notes}
                          onChange={(e) => setEditing({ ...editing, notes: e.target.value })}
                          onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return
                            if (e.key === 'Enter') saveEdit()
                            if (e.key === 'Escape') setEditing(null)
                          }}
                          aria-label={t('zenskill.gtd.projects.formNotes')}
                          placeholder={t('zenskill.gtd.projects.formNotes')}
                          className="w-full text-xs bg-muted/40 rounded px-2 py-1 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground"
                        />
                        <div className="flex items-center gap-1">
                          <button
                            onClick={saveEdit}
                            disabled={editProjectDisabled || busyId === editing.id || !editing.name.trim()}
                            className="p-1 rounded hover:bg-green-500/20 text-green-400 disabled:opacity-40"
                            title={t('zenskill.gtd.actions.editSave')}
                          >
                            <Check className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => setEditing(null)}
                            className="p-1 rounded hover:bg-muted/60 text-muted-foreground"
                            title={t('zenskill.gtd.actions.editCancel')}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ) : (
                      onEditProject && (
                        <button
                          onClick={() => startEdit(p)}
                          disabled={editProjectDisabled}
                          className="mb-1 flex items-center gap-1 px-1.5 py-0.5 text-[10px] rounded text-muted-foreground hover:bg-accent/10 hover:text-accent transition-colors disabled:opacity-40"
                          title={t('zenskill.gtd.projects.edit')}
                        >
                          <Pencil className="h-3 w-3" />
                          {t('zenskill.gtd.projects.edit')}
                        </button>
                      )
                    )}
                    <ProjectActions projectId={p.id} workspaceId={workspaceId!} sourceSlug={sourceSlug!} />
                  </div>
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
