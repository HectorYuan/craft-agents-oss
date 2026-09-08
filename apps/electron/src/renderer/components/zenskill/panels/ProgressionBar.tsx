/**
 * ProgressionBar — compact progression suggestions strip under the
 * GtdWorkspace ReviewBar (conversational GTD proposal, layer 3 / MVP-2a).
 *
 * Data is fetched by the parent via useMcpTool('task_progressions') and
 * passed in already filtered; the backend tool runs in parallel (frontend
 * codes against the contract with defensive reads). Each suggestion renders
 * as a one-line card: priority dot (high=red / medium=yellow / low=grey) +
 * suggestion text + a send button. While a high-priority suggestion exists
 * the whole strip breathes (subtle box-shadow pulse via .progression-breathe).
 *
 * Sending mirrors PageToChatBridge's session handling (MVP-1 precedent):
 * - an active session belonging to this workspace -> sendMessage directly
 *   on it, toast, then navigate to that session's chat view;
 * - otherwise -> action/new-session route with send=true, which creates a
 *   session, navigates to it and delayed-sends the prompt.
 * The strip is hidden entirely when there is nothing to show — including
 * tool errors (the backend tool may not exist yet).
 */
import { useCallback, useState } from 'react'
import { useAtomValue } from 'jotai'
import { useTranslation } from 'react-i18next'
import { ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { isSessionsNavigation, routes, useNavigation } from '@/contexts/NavigationContext'
import { sessionMetaMapAtom } from '@/atoms/sessions'
import type { TaskProgression } from './types'

interface ProgressionBarProps {
  /** Workspace the suggestions belong to; the strip is hidden without one */
  workspaceId?: string
  /** Valid suggestions (suggestion text present), already defensively extracted */
  progressions: TaskProgression[]
}

/** Priority dot color — unknown values collapse to low/grey */
function priorityDotClass(priority?: string): string {
  if (priority === 'high') return 'bg-red-400'
  if (priority === 'medium') return 'bg-yellow-500'
  return 'bg-muted-foreground/40'
}

export function ProgressionBar({ workspaceId, progressions }: ProgressionBarProps) {
  const { t } = useTranslation()
  const { navigate, navigationState } = useNavigation()
  const sessionMetaMap = useAtomValue(sessionMetaMapAtom)
  const [sendingId, setSendingId] = useState<string | null>(null)

  const sendPrompt = useCallback(async (progression: TaskProgression, index: number) => {
    if (!workspaceId) return
    const prompt = typeof progression.prompt === 'string' ? progression.prompt.trim() : ''
    if (!prompt || sendingId !== null) return
    const id = typeof progression.trigger === 'string' && progression.trigger ? progression.trigger : `idx-${index}`

    setSendingId(id)
    try {
      // a) An active session in this workspace -> send directly, then show it
      if (isSessionsNavigation(navigationState) && navigationState.details?.type === 'session') {
        const sessionId = navigationState.details.sessionId
        const meta = sessionMetaMap.get(sessionId)
        if (meta?.workspaceId === workspaceId) {
          await window.electronAPI.sendMessage(sessionId, prompt)
          toast.success(t('zenskill.progression.sent'))
          await navigate(routes.view.allSessions(sessionId))
          return
        }
      }

      // b) No matching active session -> create one, navigate to it and
      // delayed-send via the existing 'new-session' route handling
      await navigate(routes.action.newSession({ input: prompt, send: true }))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t('zenskill.toast.toolFailed'))
    } finally {
      setSendingId(null)
    }
  }, [workspaceId, sendingId, navigationState, sessionMetaMap, navigate, t])

  if (!workspaceId || progressions.length === 0) return null
  const hasHigh = progressions.some((p) => p?.priority === 'high')

  return (
    <div
      role="list"
      aria-label={t('zenskill.progression.title')}
      className={`mx-5 mt-2 rounded-md border bg-muted/5 text-xs shrink-0 ${
        hasHigh ? 'border-red-400/30 progression-breathe' : 'border-border/30'
      }`}
    >
      {progressions.map((progression, index) => {
        const isHigh = progression?.priority === 'high'
        const suggestion = typeof progression?.suggestion === 'string' ? progression.suggestion : ''
        const prompt = typeof progression?.prompt === 'string' ? progression.prompt.trim() : ''
        return (
          <div
            key={typeof progression?.trigger === 'string' && progression.trigger ? progression.trigger : `idx-${index}`}
            role="listitem"
            className="flex items-center gap-2 px-3 py-1.5 border-b border-border/20 last:border-b-0 min-w-0"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full shrink-0 ${priorityDotClass(progression?.priority)} ${isHigh ? 'animate-pulse' : ''}`}
            />
            <span className="truncate min-w-0 text-foreground/80" title={suggestion}>
              {suggestion}
            </span>
            <button
              type="button"
              onClick={() => void sendPrompt(progression, index)}
              disabled={!prompt || sendingId !== null}
              title={t('zenskill.progression.send')}
              className="ml-auto inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-accent transition-colors hover:bg-accent/10 disabled:opacity-40"
            >
              <ArrowRight className={`h-3 w-3 ${sendingId !== null ? 'animate-pulse' : ''}`} />
              {t('zenskill.progression.send')}
            </button>
          </div>
        )
      })}
    </div>
  )
}
