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
 *
 * Day 1 interaction deepening:
 * - each suggestion gets an [×] dismiss button; dismissed triggers are kept
 *   in sessionStorage under `zenskill.progression.dismissed.{YYYY-MM-DD}`
 *   so they stay hidden for the rest of the day and clear naturally the
 *   next day (the date is part of the key);
 * - accepted suggestions (send clicked) are recorded under
 *   `zenskill.progression.accepted.{YYYY-MM-DD}` as a feedback trail.
 */
import { useCallback, useState } from 'react'
import { useAtomValue } from 'jotai'
import { useTranslation } from 'react-i18next'
import { ArrowRight, X } from 'lucide-react'
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

const DISMISS_PREFIX = 'zenskill.progression.dismissed.'
const ACCEPT_PREFIX = 'zenskill.progression.accepted.'

/** Local date (YYYY-MM-DD) — same convention as the ReviewBar/ActionsPanel */
function todayKey(): string {
  const d = new Date()
  const p = (n: number) => (n < 10 ? `0${n}` : String(n))
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** Read a per-day trigger list from sessionStorage (missing/corrupt → empty) */
function readDayTriggers(prefix: string): string[] {
  try {
    const raw = sessionStorage.getItem(prefix + todayKey())
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function appendDayTrigger(prefix: string, trigger: string): void {
  try {
    const current = readDayTriggers(prefix)
    if (!current.includes(trigger)) current.push(trigger)
    sessionStorage.setItem(prefix + todayKey(), JSON.stringify(current))
  } catch {
    // sessionStorage unavailable (quota/private mode) — dismiss is session-only UX
  }
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
  // Dismissed triggers for today — session-scoped, keyed by date so the next
  // day starts with a fresh (empty) set.
  const [dismissed, setDismissed] = useState<string[]>(() => readDayTriggers(DISMISS_PREFIX))

  const dismiss = useCallback((trigger: string) => {
    setDismissed((cur) => (cur.includes(trigger) ? cur : [...cur, trigger]))
    appendDayTrigger(DISMISS_PREFIX, trigger)
  }, [])

  const sendPrompt = useCallback(async (progression: TaskProgression, index: number) => {
    if (!workspaceId) return
    const prompt = typeof progression.prompt === 'string' ? progression.prompt.trim() : ''
    if (!prompt || sendingId !== null) return
    const id = typeof progression.trigger === 'string' && progression.trigger ? progression.trigger : `idx-${index}`

    // Feedback trail: this suggestion was accepted (Day 1 / governance prep)
    appendDayTrigger(ACCEPT_PREFIX, id)

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

  if (!workspaceId) return null
  const visible = progressions.filter((progression, index) => {
    const id = typeof progression?.trigger === 'string' && progression.trigger ? progression.trigger : `idx-${index}`
    return !dismissed.includes(id)
  })
  if (visible.length === 0) return null
  const hasHigh = visible.some((p) => p?.priority === 'high')

  return (
    <div
      role="list"
      aria-label={t('zenskill.progression.title')}
      className={`mx-5 mt-2 rounded-md border bg-muted/5 text-xs shrink-0 ${
        hasHigh ? 'border-red-400/30 progression-breathe' : 'border-border/30'
      }`}
    >
      {visible.map((progression, index) => {
        const isHigh = progression?.priority === 'high'
        const suggestion = typeof progression?.suggestion === 'string' ? progression.suggestion : ''
        const prompt = typeof progression?.prompt === 'string' ? progression.prompt.trim() : ''
        const id = typeof progression?.trigger === 'string' && progression.trigger ? progression.trigger : `idx-${index}`
        return (
          <div
            key={id}
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
            <button
              type="button"
              onClick={() => dismiss(id)}
              title={t('zenskill.progression.dismiss')}
              aria-label={t('zenskill.progression.dismiss')}
              className="inline-flex shrink-0 items-center rounded p-0.5 text-muted-foreground/60 transition-colors hover:bg-muted/60 hover:text-muted-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
