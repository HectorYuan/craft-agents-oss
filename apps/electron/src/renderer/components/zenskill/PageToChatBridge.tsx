/**
 * PageToChatBridge — shared "continue in chat" button for ZenSkill pages.
 *
 * Bridges a full-page view back into the conversational layer: the Sparkles
 * button builds a context-aware prompt from the page's current data (the
 * useMcpTool caches passed in as contextData) and hands it to the chat
 * session layer. The prompt travels as the message body — the user sees
 * exactly what is sent; nothing is injected into the system prompt.
 *
 * Session handling mirrors the deep-link new-session precedent in
 * NavigationContext (MVP-1 architecture review):
 * - an active session belonging to this workspace -> sendMessage directly
 *   on it, then navigate to the chat view;
 * - otherwise -> action/new-session route with send=true, which creates a
 *   session, navigates to it and delayed-sends the prompt (the existing
 *   NavigationContext 'new-session' handling does create/navigate/send).
 */
import { useCallback, useState } from 'react'
import { useAtomValue } from 'jotai'
import { useTranslation } from 'react-i18next'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { isSessionsNavigation, routes, useNavigation } from '@/contexts/NavigationContext'
import { sessionMetaMapAtom } from '@/atoms/sessions'

interface PageToChatBridgeProps {
  /** Page display name ("GTD Workspace") — surfaced in the sent-toast */
  pageName: string
  /** Page-specific prompt builder — receives the page's current context data */
  buildPrompt: (context: any) => string
  /** Page data snapshot (useMcpTool caches) fed to buildPrompt */
  contextData: any
  /** Workspace the page's data belongs to; the bridge is disabled without it */
  workspaceId?: string
  className?: string
}

export function PageToChatBridge({ pageName, buildPrompt, contextData, workspaceId, className }: PageToChatBridgeProps) {
  const { t } = useTranslation()
  const { navigate, navigationState } = useNavigation()
  const sessionMetaMap = useAtomValue(sessionMetaMapAtom)
  const [sending, setSending] = useState(false)

  const handleClick = useCallback(async () => {
    if (!workspaceId || sending) return
    const prompt = buildPrompt(contextData)
    if (!prompt) return

    setSending(true)
    try {
      // a) An active session in this workspace -> send directly, then show it
      if (isSessionsNavigation(navigationState) && navigationState.details?.type === 'session') {
        const sessionId = navigationState.details.sessionId
        const meta = sessionMetaMap.get(sessionId)
        if (meta?.workspaceId === workspaceId) {
          await window.electronAPI.sendMessage(sessionId, prompt)
          toast.success(t('zenskill.bridge.sent', { page: pageName }))
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
      setSending(false)
    }
  }, [workspaceId, sending, buildPrompt, contextData, navigationState, sessionMetaMap, navigate, t, pageName])

  return (
    <button
      type="button"
      onClick={() => void handleClick()}
      disabled={!workspaceId || sending}
      title={t('zenskill.bridge.continueInChat')}
      aria-label={t('zenskill.bridge.continueInChat')}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-accent disabled:opacity-40 ${className ?? ''}`}
    >
      <Sparkles className={`h-3.5 w-3.5 ${sending ? 'animate-pulse text-accent' : ''}`} />
    </button>
  )
}
