/**
 * GtdWorkspace — ZenSkill top-level GTD workspace page (L2).
 *
 * Full-page counterpart of the ZenSkillDataPanel GTD tab: Inbox capture
 * flow / Actions / Calendar / Projects, switched by in-page tabs. Data is
 * fetched through the useMcpTool L3 hook (JSON extraction + zenskill:changed
 * auto-refresh); write tools are called directly and rely on the
 * zenskill:changed broadcast to refresh, never manual refetches.
 */
import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Zap, Inbox, Circle, CalendarDays, FolderKanban } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { InboxPanel } from '../panels/InboxPanel'
import { ActionsPanel, type ActionStatusFilter } from '../panels/ActionsPanel'
import { CalendarPanel, type CalendarScope } from '../panels/CalendarPanel'
import { ProjectsPanel } from '../panels/ProjectsPanel'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

type GtdTab = 'inbox' | 'actions' | 'calendar' | 'projects'

interface InboxData { count?: number; items?: { id: string; text?: string; raw_text?: string; status?: string }[] }
interface ActionData { count?: number; items?: { id: string; title: string; priority?: string; status?: string; due_date?: string }[] }
interface CalendarData { count?: number; events?: { date: string; time: string; title: string }[] }
interface ProjectData { count?: number; items?: { id: string; name: string; status?: string; progress?: number }[] }

interface GtdWorkspaceProps {
  workspaceId?: string
}

function TabSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1.5 pt-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted/60 animate-pulse"
          style={{ width: `${72 - i * 12}%` }}
        />
      ))}
    </div>
  )
}

export function GtdWorkspace({ workspaceId }: GtdWorkspaceProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<GtdTab>('inbox')
  const [actionStatus, setActionStatus] = useState<ActionStatusFilter>('pending')
  const [calendarScope, setCalendarScope] = useState<CalendarScope>('today')
  const [busyId, setBusyId] = useState<string | null>(null)

  const sourceSlug = ZENSKILL_SOURCE_SLUG
  const inbox = useMcpTool<InboxData>(workspaceId, sourceSlug, 'gtd_inbox_list', { limit: 50 })
  const actions = useMcpTool<ActionData>(workspaceId, sourceSlug, 'action_list', { status: actionStatus, limit: 50 })
  const calendar = useMcpTool<CalendarData>(workspaceId, sourceSlug, 'calendar_list', { scope: calendarScope })
  const projects = useMcpTool<ProjectData>(workspaceId, sourceSlug, 'project_list', { status: 'active' })

  const runTool = useCallback(async (tool: string, args: Record<string, unknown>) => {
    if (!workspaceId) return
    setBusyId(String(args.action_id ?? args.item_id ?? args.project_id ?? tool))
    try {
      // Refresh is driven by the zenskill:changed broadcast (subscribed in
      // useMcpTool) — no manual refetch here, mirroring DataPanel behavior.
      await window.electronAPI.callMcpTool(workspaceId, sourceSlug, tool, args)
    } finally {
      setBusyId(null)
    }
  }, [workspaceId, sourceSlug])

  const capture = useCallback((text: string) => {
    void runTool('gtd_capture', { text })
  }, [runTool])

  const addAction = useCallback(({ title, priority, dueDate }: { title: string; priority: string; dueDate: string }) => {
    const args: Record<string, unknown> = { title, priority }
    if (dueDate) args.due_date = dueDate
    void runTool('action_add', args)
  }, [runTool])

  const error = inbox.error ?? actions.error ?? calendar.error ?? projects.error

  const tabs: { key: GtdTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { key: 'inbox', label: t('zenskill.gtd.tab.inbox'), icon: Inbox },
    { key: 'actions', label: t('zenskill.gtd.tab.actions'), icon: Circle },
    { key: 'calendar', label: t('zenskill.gtd.tab.calendar'), icon: CalendarDays },
    { key: 'projects', label: t('zenskill.gtd.tab.projects'), icon: FolderKanban },
  ]

  const busy = inbox.loading || actions.loading || calendar.loading || projects.loading

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/30 shrink-0">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-accent" />
          <div>
            <div className="text-sm font-medium">{t('zenskill.gtd.title')}</div>
            <div className="text-[11px] text-muted-foreground">{t('zenskill.gtd.subtitle')}</div>
          </div>
        </div>
        {busy && (
          <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden" title={t('zenskill.gtd.loading')}>
            <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
          </div>
        )}
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-destructive bg-destructive/5 rounded p-2">{error}</div>
      )}

      {/* Tab bar */}
      <div className="px-5 pt-2 border-b border-border/30 flex gap-1 shrink-0">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              activeTab === key
                ? 'border-accent text-accent'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {activeTab === 'inbox' && (
            inbox.loading && !inbox.data ? <TabSkeleton rows={4} /> : (
              <InboxPanel
                variant="full"
                items={inbox.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                onClarify={(itemId) => runTool('inbox_clarify', { item_id: itemId })}
                onArchive={(itemId) => runTool('inbox_archive', { item_id: itemId })}
                onCaptureSubmit={capture}
                captureDisabled={!workspaceId || busyId === 'gtd_capture'}
                capturePlaceholder={t('zenskill.gtd.capture.placeholder')}
              />
            )
          )}

          {activeTab === 'actions' && (
            actions.loading && !actions.data ? <TabSkeleton rows={4} /> : (
              <ActionsPanel
                variant="full"
                actions={actions.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                status={actionStatus}
                onStatusChange={setActionStatus}
                onAdd={addAction}
                addDisabled={!workspaceId || busyId === 'action_add'}
                onDone={(actionId) => runTool('action_done', { action_id: actionId })}
                onMarkNext={(actionId) => runTool('action_mark_next', { action_id: actionId })}
                onDelete={(actionId) => runTool('action_delete', { action_id: actionId })}
                statusLabels={{
                  pending: t('zenskill.gtd.actions.status.pending'),
                  next: t('zenskill.gtd.actions.status.next'),
                  done: t('zenskill.gtd.actions.status.done'),
                }}
              />
            )
          )}

          {activeTab === 'calendar' && (
            calendar.loading && !calendar.data ? <TabSkeleton rows={3} /> : (
              <CalendarPanel
                variant="full"
                events={calendar.data?.events ?? []}
                count={calendar.data?.count}
                scope={calendarScope}
                onScopeChange={setCalendarScope}
                scopeLabels={{
                  today: t('zenskill.gtd.calendar.scope.today'),
                  week: t('zenskill.gtd.calendar.scope.week'),
                }}
              />
            )
          )}

          {activeTab === 'projects' && (
            projects.loading && !projects.data ? <TabSkeleton rows={3} /> : (
              <ProjectsPanel
                variant="full"
                projects={projects.data?.items ?? []}
                busyId={busyId}
                maxItems={100}
                onDone={(projectId) => runTool('project_done', { project_id: projectId })}
              />
            )
          )}
        </div>
      </div>
    </div>
  )
}
