/**
 * SessionToActionDialog — D4.2.1 · F06 lightweight collection bar for turning
 * a session into a GTD action.
 *
 * Reuses the existing Dialog / Input / Button idiom (no standalone page or
 * drawer). The parent owns the MCP call (`action_add` with the internal
 * `_source_session_id`); this dialog only collects title / priority / due
 * date and reports the input back.
 *
 * Title prefill: first user message (`preview`) first, session name second.
 */
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { useRegisterModal } from "@/context/ModalContext"
import { actionTitleFromSession } from "@/utils/project-session-meta"
import type { SessionMeta } from "@/atoms/sessions"

/** Matches the existing action_add form's priority order (P0–P3; backend normalizes legacy high/medium/low). */
const PRIORITIES = ['P0', 'P1', 'P2', 'P3'] as const

export interface SessionToActionInput {
  title: string
  priority: string
  dueDate: string
}

interface SessionToActionDialogProps {
  open: boolean
  /** Session being converted; `null` while the dialog is closed. */
  session: SessionMeta | null
  /** MCP call in flight — locks the form and buttons. */
  submitting: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (input: SessionToActionInput) => void
}

export function SessionToActionDialog({
  open,
  session,
  submitting,
  onOpenChange,
  onSubmit,
}: SessionToActionDialogProps) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState<string>('P2')
  const [dueDate, setDueDate] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Register with modal context so the X button / Cmd+W closes this dialog first.
  useRegisterModal(open, () => onOpenChange(false))

  // Reset the form and prefill the title whenever the dialog opens for a session.
  useEffect(() => {
    if (open) {
      setTitle(session ? actionTitleFromSession(session) : '')
      setPriority('P2')
      setDueDate('')
      const timer = setTimeout(() => inputRef.current?.focus(), 0)
      return () => clearTimeout(timer)
    }
  }, [open, session])

  const canSubmit = title.trim().length > 0 && !submitting

  const handleSubmit = () => {
    if (!canSubmit) return
    onSubmit({ title: title.trim(), priority, dueDate })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]" onOpenAutoFocus={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('session.action.toAction')}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-4">
          <Input
            ref={inputRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('session.action.titlePlaceholder')}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return
              if (e.key === 'Enter') handleSubmit()
            }}
          />
          <div className="flex items-center gap-1.5">
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              disabled={submitting}
              className="w-24 shrink-0 text-xs bg-muted/40 rounded px-1 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
              title="Priority"
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              disabled={submitting}
              className="flex-1 min-w-0 text-xs bg-muted/40 rounded px-1.5 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 text-muted-foreground disabled:opacity-50"
              title="Due date"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {t('session.action.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
