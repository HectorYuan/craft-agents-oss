/**
 * ClarifyModal — small (non-fullscreen) modal for the two-step
 * inbox_clarify interaction.
 *
 * Step 1: the InboxPanel Wand2 button (full variant) opens this modal with
 * the raw inbox item. Step 2: the user picks one of the four clarify
 * categories and confirms; the parent then calls
 * inbox_clarify { item_id, result_type, target_id? }.
 *
 * For result_type=action the user may link an existing pending action —
 * it is passed as target_id so the backend links instead of creating a
 * duplicate downstream object. Esc / overlay click close the modal.
 */
import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Wand2, X } from 'lucide-react'
import type { GtdAction, GtdItem } from './types'

const RESULT_TYPES = ['action', 'project', 'calendar', 'reference'] as const
export type ClarifyResultType = (typeof RESULT_TYPES)[number]

export interface ClarifyModalProps {
  /** Inbox item being clarified; null closes the modal */
  item: GtdItem | null
  /** Existing pending actions offered as clarify targets (result_type=action) */
  pendingActions?: GtdAction[]
  /** Disables confirm while the clarify tool call is in flight */
  busy?: boolean
  onConfirm: (itemId: string, resultType: ClarifyResultType, targetId?: string) => void
  onClose: () => void
}

export function ClarifyModal({ item, pendingActions, busy, onConfirm, onClose }: ClarifyModalProps) {
  const { t } = useTranslation()
  const [resultType, setResultType] = useState<ClarifyResultType>('action')
  const [targetId, setTargetId] = useState('')

  // Fresh selection every time a different item is opened
  useEffect(() => {
    if (item) {
      setResultType('action')
      setTargetId('')
    }
  }, [item])

  // Esc closes
  useEffect(() => {
    if (!item) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [item, onClose])

  if (!item) return null

  const itemText = item.text || item.raw_text || ''
  const confirm = () => {
    if (busy || !itemText) return
    onConfirm(item.id, resultType, targetId || undefined)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-[min(360px,calc(100vw-32px))] rounded-md border border-border/40 bg-background shadow-lg p-3 text-xs">
        <div className="flex items-center gap-1.5 mb-2">
          <Wand2 className="h-3.5 w-3.5 text-accent" />
          <span className="font-medium flex-1">{t('zenskill.modal.clarify.title')}</span>
          <button
            className="p-0.5 rounded hover:bg-muted/60 text-muted-foreground"
            title={t('zenskill.modal.clarify.cancel')}
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="max-h-24 overflow-y-auto rounded bg-muted/40 px-2 py-1.5 text-muted-foreground break-words mb-2.5">
          {itemText}
        </div>

        <div className="grid grid-cols-2 gap-1 mb-2.5">
          {RESULT_TYPES.map((type) => (
            <button
              key={type}
              onClick={() => setResultType(type)}
              className={`px-2 py-1.5 rounded transition-colors ${
                resultType === type
                  ? 'bg-accent/15 text-accent'
                  : 'bg-muted/40 text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              }`}
            >
              {t(`zenskill.modal.clarify.type.${type}`)}
            </button>
          ))}
        </div>

        {resultType === 'action' && (pendingActions?.length ?? 0) > 0 && (
          <div className="mb-2.5">
            <div className="text-[10px] text-muted-foreground mb-1">{t('zenskill.modal.clarify.targetLabel')}</div>
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="w-full text-xs bg-muted/40 rounded px-1.5 py-1 outline-none focus:ring-1 focus:ring-accent/40"
            >
              <option value="">{t('zenskill.modal.clarify.targetNone')}</option>
              {pendingActions!.map((a) => (
                <option key={a.id} value={a.id}>{a.title}</option>
              ))}
            </select>
          </div>
        )}

        <div className="flex justify-end gap-1.5">
          <button
            onClick={onClose}
            className="px-2 py-1 rounded bg-muted/40 text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          >
            {t('zenskill.modal.clarify.cancel')}
          </button>
          <button
            onClick={confirm}
            disabled={busy || !itemText}
            className="px-2 py-1 rounded bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40"
          >
            {t('zenskill.modal.clarify.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
