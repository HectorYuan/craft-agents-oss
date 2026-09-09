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
 *
 * Day 2 ritual mode: when the top visible progression is a time-based
 * ritual (morning_ritual / shutdown_ritual / weekly_review /
 * silence_wakeup — backend contract, read defensively) the whole strip
 * renders as a single ceremony card instead of the compact rows: icon +
 * i18n title heading, the suggestion line, and a confirm/dismiss button
 * pair. Confirm sends progression.prompt through the same session logic
 * as PageToChatBridge (above); the secondary button dismisses for the
 * rest of the day via the shared sessionStorage trail. The card carries
 * an accent left border with a faint gradient to stand apart from the
 * plain suggestions.
 */
import { useCallback, useState } from 'react'
import { useAtomValue } from 'jotai'
import { useTranslation } from 'react-i18next'
import { ArrowRight, Bell, CalendarCheck, Moon, Sunrise, X, type LucideIcon } from 'lucide-react'
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

/** Time-based ritual triggers (Day 2 backend contract) — exact matches only */
const RITUAL_TRIGGERS = ['morning_ritual', 'shutdown_ritual', 'weekly_review', 'silence_wakeup'] as const
type RitualTrigger = (typeof RITUAL_TRIGGERS)[number]

/** Per-ritual icon + i18n keys (title heading and confirm/dismiss labels) */
interface RitualStyle {
  icon: LucideIcon
  titleKey: string
  confirmKey: string
  dismissKey: string
}

const RITUAL_STYLES: Record<RitualTrigger, RitualStyle> = {
  morning_ritual: {
    icon: Sunrise,
    titleKey: 'zenskill.progression.morningTitle',
    confirmKey: 'zenskill.progression.morningConfirm',
    dismissKey: 'zenskill.progression.morningDismiss',
  },
  shutdown_ritual: {
    icon: Moon,
    titleKey: 'zenskill.progression.shutdownTitle',
    confirmKey: 'zenskill.progression.shutdownConfirm',
    dismissKey: 'zenskill.progression.shutdownDismiss',
  },
  weekly_review: {
    icon: CalendarCheck,
    titleKey: 'zenskill.progression.weeklyTitle',
    confirmKey: 'zenskill.progression.weeklyConfirm',
    dismissKey: 'zenskill.progression.weeklyDismiss',
  },
  silence_wakeup: {
    icon: Bell,
    titleKey: 'zenskill.progression.silenceTitle',
    confirmKey: 'zenskill.progression.silenceConfirm',
    dismissKey: 'zenskill.progression.silenceDismiss',
  },
}

/** Exact-match guard for the top-1 trigger (contract-pending, defensive) */
function ritualTriggerOf(trigger: unknown): RitualTrigger | null {
  return (RITUAL_TRIGGERS as readonly string[]).includes(trigger as string)
    ? (trigger as RitualTrigger)
    : null
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

  // Day 2 ritual mode: the top *visible* suggestion decides the strip's
  // mode. When it is a time-based ritual the whole strip renders as one
  // ceremony card; dismissing the ritual falls back to the plain rows.
  const top = visible[0]
  const ritual = top ? ritualTriggerOf(top.trigger) : null
  if (ritual && top) {
    const style = RITUAL_STYLES[ritual]
    const RitualIcon = style.icon
    const suggestion = typeof top.suggestion === 'string' ? top.suggestion : ''
    const prompt = typeof top.prompt === 'string' ? top.prompt.trim() : ''
    const busy = sendingId !== null
    return (
      <div
        role="group"
        aria-label={t(style.titleKey)}
        className={`mx-5 mt-2 shrink-0 rounded-md border border-accent/30 border-l-2 border-l-accent bg-gradient-to-r from-accent/10 via-accent/5 to-transparent px-4 py-3 ${
          top.priority === 'high' ? 'progression-breathe' : ''
        }`}
      >
        <div className="flex items-center gap-1.5">
          <RitualIcon className={`h-4 w-4 shrink-0 text-accent ${busy ? 'animate-pulse' : ''}`} />
          <span className="truncate text-xs font-semibold text-foreground">{t(style.titleKey)}</span>
        </div>
        {suggestion && (
          <p className="mt-1.5 truncate text-xs text-foreground/75" title={suggestion}>
            {suggestion}
          </p>
        )}
        <div className="mt-2.5 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void sendPrompt(top, 0)}
            disabled={!prompt || busy}
            className="inline-flex shrink-0 items-center gap-1 rounded bg-accent px-2.5 py-1 text-[11px] font-medium text-white transition-colors hover:bg-accent/90 disabled:opacity-40"
          >
            <RitualIcon className="h-3 w-3" />
            {t(style.confirmKey)}
          </button>
          <button
            type="button"
            onClick={() => dismiss(ritual)}
            disabled={busy}
            className="inline-flex shrink-0 items-center rounded px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground disabled:opacity-40"
          >
            {t(style.dismissKey)}
          </button>
        </div>
      </div>
    )
  }

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
