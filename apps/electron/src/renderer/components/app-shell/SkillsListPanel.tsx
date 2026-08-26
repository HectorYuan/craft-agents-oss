import * as React from 'react'
import { useTranslation } from "react-i18next"
import { Zap, Search, Download, Loader2, Check } from 'lucide-react'
import { toast } from 'sonner'
import { SkillAvatar } from '@/components/ui/skill-avatar'
import { EntityPanel } from '@/components/ui/entity-panel'
import { EntityListEmptyScreen } from '@/components/ui/entity-list-empty'
import { skillSelection } from '@/hooks/useEntitySelection'
import { SkillMenu } from './SkillMenu'
import { SendResourceToWorkspaceDialog } from './SendResourceToWorkspaceDialog'
import { EditPopover, getEditConfig } from '@/components/ui/EditPopover'
import { useActiveWorkspace, useAppShellContext } from '@/context/AppShellContext'
import { getFileManagerName } from '@/lib/platform'
import type { LoadedSkill } from '../../../shared/types'

export interface SkillsListPanelProps {
  skills: LoadedSkill[]
  onDeleteSkill: (skillSlug: string) => void
  onSkillClick: (skill: LoadedSkill) => void
  selectedSkillSlug?: string | null
  workspaceId?: string
  workspaceRootPath?: string
  className?: string
}

export function SkillsListPanel({
  skills,
  onDeleteSkill,
  onSkillClick,
  selectedSkillSlug,
  workspaceId,
  workspaceRootPath,
  className,
}: SkillsListPanelProps) {
  const { t } = useTranslation()
  const activeWorkspace = useActiveWorkspace()
  const canRevealLocally = !activeWorkspace?.remoteServer
  const { workspaces, activeWorkspaceId } = useAppShellContext()
  const hasOtherWorkspaces = workspaces.length > 1

  // Send to Workspace dialog state
  const [sendDialogOpen, setSendDialogOpen] = React.useState(false)
  const [sendResourceSlug, setSendResourceSlug] = React.useState<string | null>(null)
  const [sendResourceLabel, setSendResourceLabel] = React.useState('')

  // Marketplace search state
  const [marketQuery, setMarketQuery] = React.useState('')
  const [marketResults, setMarketResults] = React.useState<Array<{name: string; description: string; uri?: string; skill_id?: string; score?: number}>>([])
  const [marketLoading, setMarketLoading] = React.useState(false)
  const [installingUri, setInstallingUri] = React.useState<string | null>(null)
  const [installedUris, setInstalledUris] = React.useState<Set<string>>(new Set())
  const marketTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const searchMarketplace = React.useCallback((query: string) => {
    if (marketTimerRef.current) clearTimeout(marketTimerRef.current)
    if (!query.trim()) { setMarketResults([]); return }
    marketTimerRef.current = setTimeout(async () => {
      setMarketLoading(true)
      try {
        const res = await window.electronAPI.callMcpTool(workspaceId!, 'zenskill-4', 'skill_search', { query: query.trim(), top_k: 6 })
        const text = (res as any)?.result?.content?.[0]?.text
        if (text) {
          const data = JSON.parse(text)
          setMarketResults(data.results || [])
        }
      } catch { setMarketResults([]) }
      finally { setMarketLoading(false) }
    }, 400)
  }, [workspaceId])

  const installSkill = React.useCallback(async (uri: string, name: string) => {
    setInstallingUri(uri)
    try {
      const res = await window.electronAPI.callMcpTool(workspaceId!, 'zenskill-4', 'skill_install', { uri })
      const text = (res as any)?.result?.content?.[0]?.text
      const data = text ? JSON.parse(text) : {}
      if (data.ok) {
        setInstalledUris(prev => new Set(prev).add(uri))
        toast.success(`Installed: ${name}`)
      } else {
        toast.error(data.message || `Failed to install ${name}`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Install failed')
    } finally {
      setInstallingUri(null)
    }
  }, [workspaceId])

  return (
    <>
    {/* Marketplace search */}
    {workspaceId && (
      <div className="px-2 pt-2 pb-1 space-y-1.5">
        <div className="relative">
          <Search className="h-3 w-3 text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2" />
          <input
            value={marketQuery}
            onChange={(e) => { setMarketQuery(e.target.value); searchMarketplace(e.target.value) }}
            placeholder="Search ZenSkill marketplace..."
            className="w-full text-xs bg-muted/40 rounded pl-6 pr-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
          />
        </div>
        {marketLoading && (
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground pl-1">
            <Loader2 className="h-3 w-3 animate-spin" /> Searching...
          </div>
        )}
        {marketResults.length > 0 && (
          <div className="space-y-0.5 max-h-40 overflow-y-auto">
            {marketResults.map((r) => {
              const uri = r.uri || `clawhub://${r.skill_id || r.name}`
              return (
              <div key={r.uri || r.name} className="flex items-center gap-2 text-xs rounded px-2 py-1 hover:bg-muted/50 group">
                <div className="flex-1 min-w-0">
                  <div className="truncate font-medium">{r.name}</div>
                  <div className="truncate text-[10px] text-muted-foreground">{r.description}</div>
                </div>
                {installedUris.has(uri) ? (
                  <span className="text-[10px] text-green-500 shrink-0 flex items-center gap-0.5"><Check className="h-3 w-3" /> Installed</span>
                ) : (
                  <button
                    className="opacity-0 group-hover:opacity-100 shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
                    disabled={installingUri === uri}
                    onClick={() => installSkill(uri, r.name)}
                  >
                    {installingUri === uri ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                    Install
                  </button>
                )}
              </div>
              )
            })}
          </div>
        )}
      </div>
    )}

    <EntityPanel<LoadedSkill>
      items={skills}
      getId={(s) => s.slug}
      selection={skillSelection}
      selectedId={selectedSkillSlug}
      onItemClick={onSkillClick}
      className={className}
      containerProps={{ 'data-list-role': 'skills' }}
      emptyState={
        <EntityListEmptyScreen
          icon={<Zap />}
          title={t('skillsList.noSkillsConfigured')}
          description={t('skillsList.emptyDescription')}
          docKey="skills"
        >
          {workspaceRootPath && (
            <EditPopover
              align="center"
              trigger={
                <button className="inline-flex items-center h-7 px-3 text-xs font-medium rounded-[8px] bg-background shadow-minimal hover:bg-foreground/[0.03] transition-colors">
                  {t('skillsList.addSkill')}
                </button>
              }
              {...getEditConfig('add-skill', workspaceRootPath)}
            />
          )}
        </EntityListEmptyScreen>
      }
      mapItem={(skill) => ({
        icon: <SkillAvatar skill={skill} size="sm" workspaceId={workspaceId} />,
        title: skill.metadata.name,
        badges: (
          <span className="flex items-center gap-1.5 min-w-0">
            {skill.source === 'project' && (
              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-foreground/5 text-muted-foreground">
                {t('skillsList.projectBadge')}
              </span>
            )}
            <span className="truncate">{skill.metadata.description}</span>
          </span>
        ),
        menu: (
          <SkillMenu
            skillSlug={skill.slug}
            skillName={skill.metadata.name}
            onOpenInNewWindow={() => window.electronAPI.openUrl(`craftagents://skills/skill/${skill.slug}?window=focused`)}
            onShowInFinder={async () => {
              if (!canRevealLocally) return
              try {
                await window.electronAPI.showInFolder(skill.path)
              } catch (err) {
                const message = err instanceof Error ? err.message : String(err)
                toast.error(t('toast.failedToReveal', { fileManager: getFileManagerName() }), {
                  description: message,
                })
              }
            }}
            canShowInFinder={canRevealLocally}
            onDelete={skill.source === 'workspace' ? () => onDeleteSkill(skill.slug) : undefined}
            canDelete={skill.source === 'workspace'}
            deleteLabel={skill.source === 'workspace' ? t('skillsList.deleteSkill') : t('skillsList.managedByProject')}
            onSendToWorkspace={hasOtherWorkspaces && skill.source === 'workspace' ? () => {
              setSendResourceSlug(skill.slug)
              setSendResourceLabel(skill.metadata.name)
              setSendDialogOpen(true)
            } : undefined}
          />
        ),
      })}
    />

    {/* Send to Workspace dialog */}
    {sendResourceSlug && (
      <SendResourceToWorkspaceDialog
        open={sendDialogOpen}
        onOpenChange={setSendDialogOpen}
        resourceType="skill"
        resourceIds={[sendResourceSlug]}
        resourceLabel={sendResourceLabel}
        workspaces={workspaces}
        activeWorkspaceId={activeWorkspaceId}
      />
    )}
    </>
  )
}
