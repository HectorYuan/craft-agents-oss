/**
 * ProjectsListPanel
 *
 * Workspace-scoped project list shown in the navigator slot when the Projects
 * sidebar item is active. Mirrors the lightweight skeleton of
 * SkillsListPanel / AutomationsListPanel — no multi-select / drag-drop in v1.
 */

import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { useAtomValue } from 'jotai'
import { formatDistanceToNowStrict, type Locale } from 'date-fns'
import { FolderKanban, MessageSquare, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { EntityRow } from '@/components/ui/entity-row'
import { EntityListEmptyScreen } from '@/components/ui/entity-list-empty'
import { useMenuComponents, ContextMenuProvider } from '@/components/ui/menu-context'
import {
  ContextMenu,
  ContextMenuTrigger,
  StyledContextMenuContent,
} from '@/components/ui/styled-context-menu'
import type { LoadedProject } from '@craft-agent/shared/projects/types'
import { sessionMetaMapAtom, type SessionMeta } from '@/atoms/sessions'
import { shortTimeLocale } from '@/utils/session'
import { maxActiveAt, sessionsForProject } from '@/utils/project-session-meta'

export interface ProjectsListPanelProps {
  projects: LoadedProject[]
  workspaceId: string
  onProjectClick: (slug: string) => void
  onAddProject?: () => void
  /** Jump to All Sessions filtered by this project's id. */
  onJumpToSessions?: (projectId: string) => void
  selectedProjectSlug?: string | null
  className?: string
}

export function ProjectsListPanel({
  projects,
  workspaceId,
  onProjectClick,
  onAddProject,
  onJumpToSessions,
  selectedProjectSlug,
  className,
}: ProjectsListPanelProps) {
  const { t } = useTranslation()
  const sessionMetaMap = useAtomValue(sessionMetaMapAtom)

  const handleDelete = React.useCallback(async (project: LoadedProject) => {
    // Deleting a project rm -rf's its folder + all assets, so confirm first — mirrors the
    // ProjectInfoPage delete (shares the same wording key) instead of deleting on a single click.
    if (!window.confirm(t('projectInfo.deleteConfirm', { name: project.config.name }))) return
    try {
      await window.electronAPI.deleteProject(workspaceId, project.config.slug)
      toast.success(t('projectsList.deleted', { name: project.config.name }))
    } catch (err) {
      console.error('[ProjectsListPanel] Failed to delete project:', err)
      toast.error(t('projectsList.deleteFailed'))
    }
  }, [workspaceId, t])

  if (projects.length === 0) {
    return (
      <div className={cn('flex flex-col flex-1 min-h-0', className)}>
        <EntityListEmptyScreen
          icon={<FolderKanban />}
          title={t('projectsList.empty')}
          description={t('projectsList.emptyDescription')}
        >
          {onAddProject && (
            <button
              type="button"
              onClick={onAddProject}
              className="inline-flex items-center gap-1 h-7 px-3 text-xs font-medium rounded-[8px] bg-background shadow-minimal hover:bg-foreground/[0.03] transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              {t('projectsList.addProject')}
            </button>
          )}
        </EntityListEmptyScreen>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col flex-1 min-h-0', className)}>
      <ScrollArea className="flex-1">
        <div className="pb-2" data-list-role="projects">
          <div className="pt-1">
            {projects.map((project, index) => (
              <ProjectRow
                key={project.config.slug}
                project={project}
                metaMap={sessionMetaMap}
                isSelected={selectedProjectSlug === project.config.slug}
                isFirst={index === 0}
                onClick={() => onProjectClick(project.config.slug)}
                onDelete={() => handleDelete(project)}
                onJumpToSessions={onJumpToSessions ? () => onJumpToSessions(project.config.id) : undefined}
              />
            ))}
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}

interface ProjectRowProps {
  project: LoadedProject
  metaMap: Map<string, SessionMeta>
  isSelected: boolean
  isFirst: boolean
  onClick: () => void
  onDelete: () => void
  onJumpToSessions?: () => void
}

function ProjectRow({ project, metaMap, isSelected, isFirst, onClick, onDelete, onJumpToSessions }: ProjectRowProps) {
  const { t } = useTranslation()
  const config = project.config
  const subtitle = config.description?.trim() || config.workingDirectory || ''

  // D421-F02: aggregate sessions bound to this project (archived excluded);
  // count is a real enumerable number, active time shows `—` when absent.
  const bound = sessionsForProject(metaMap, config.id)
  const sessionCount = bound.length
  const activeAt = maxActiveAt(bound)
  const activeLabel = activeAt !== undefined
    ? t('projectsList.lastActive', {
        time: formatDistanceToNowStrict(new Date(activeAt), {
          locale: shortTimeLocale as Locale,
          roundingMethod: 'floor',
        }),
      })
    : '—'

  return (
    <ContextMenu modal={true}>
      <ContextMenuTrigger asChild>
        <div>
          <EntityRow
            showSeparator={!isFirst}
            separatorClassName="pl-10 pr-4"
            isSelected={isSelected}
            onMouseDown={(e: React.MouseEvent) => {
              if (e.button === 0) onClick()
            }}
            icon={<FolderKanban className="h-3.5 w-3.5 text-foreground/60" />}
            title={config.name}
            subtitle={
              <div className="space-y-0.5">
                {subtitle && <div className="truncate">{subtitle}</div>}
                <div className="text-foreground/45">
                  {t('projectsList.sessionCount', { count: sessionCount })}
                  <span className="mx-1">·</span>
                  {activeLabel}
                </div>
              </div>
            }
          />
        </div>
      </ContextMenuTrigger>
      <StyledContextMenuContent>
        <ContextMenuProvider>
          <ProjectRowMenu onDelete={onDelete} onJumpToSessions={onJumpToSessions} />
        </ContextMenuProvider>
      </StyledContextMenuContent>
    </ContextMenu>
  )
}

function ProjectRowMenu({ onDelete, onJumpToSessions }: { onDelete: () => void; onJumpToSessions?: () => void }) {
  const { t } = useTranslation()
  const { MenuItem, Separator } = useMenuComponents()
  return (
    <>
      {onJumpToSessions && (
        <>
          <MenuItem onClick={onJumpToSessions}>
            <MessageSquare className="h-3.5 w-3.5" />
            <span className="flex-1">{t('projectsList.jumpToSessions')}</span>
          </MenuItem>
          <Separator />
        </>
      )}
      <MenuItem onClick={onDelete} variant="destructive">
        <Trash2 className="h-3.5 w-3.5" />
        <span className="flex-1">{t('projectsList.delete')}</span>
      </MenuItem>
    </>
  )
}
