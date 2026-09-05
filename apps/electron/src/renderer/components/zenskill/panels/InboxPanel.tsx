/**
 * InboxPanel — GTD inbox list extracted from ZenSkillDataPanel.
 *
 * compact variant (default): byte-for-byte the JSX previously inlined in
 * ZenSkillDataPanel's GTD tab. full variant (GtdWorkspace): adds a
 * gtd_capture quick-input on top and renders more rows.
 *
 * The panel is a controlled presentation component: data and write
 * callbacks come from the parent; refresh is driven by the parent's
 * zenskill:changed subscription.
 */
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Inbox, ChevronRight, Archive, Wand2, Plus, Sparkles } from 'lucide-react'
import type { GtdItem } from './types'
import { AutoClassifyBadge, type SuggestType } from './AutoClassifyBadge'

export interface InboxPanelProps {
  items: GtdItem[]
  busyId?: string | null
  /** Rows to render before the "+N more" overflow line (default 5) */
  maxItems?: number
  variant?: 'compact' | 'full'
  showHeader?: boolean
  onItemClick?: (text: string) => void
  /** compact variant: one-shot clarify (auto-classify, no confirmation) */
  onClarify?: (itemId: string) => void
  /** full variant: opens the ClarifyModal two-step flow for this item */
  onClarifyRequest?: (item: GtdItem) => void
  onArchive?: (itemId: string) => void
  /** B09: item_id → suggested_type（来自 inbox_suggest）；有值时条目旁显示建议徽章 */
  suggestions?: Record<string, string>
  /** B10: 批量整理 — 按建议一键澄清全部条目（full variant header 按钮区） */
  onBatchClassify?: () => void
  batchClassifyDisabled?: boolean
  /** full variant: gtd_capture quick input (controlled when onCaptureValueChange is provided) */
  captureValue?: string
  onCaptureValueChange?: (value: string) => void
  onCaptureSubmit?: (text: string) => void
  captureDisabled?: boolean
  capturePlaceholder?: string
}

export function InboxPanel({
  items,
  busyId,
  maxItems = 5,
  variant = 'compact',
  showHeader = true,
  onItemClick,
  onClarify,
  onClarifyRequest,
  onArchive,
  suggestions,
  onBatchClassify,
  batchClassifyDisabled,
  captureValue,
  onCaptureValueChange,
  onCaptureSubmit,
  captureDisabled,
  capturePlaceholder,
}: InboxPanelProps) {
  const isFull = variant === 'full'
  const { t } = useTranslation()
  const [internalCapture, setInternalCapture] = useState('')
  const captureControlled = onCaptureValueChange !== undefined
  const captureText = captureControlled ? (captureValue ?? '') : internalCapture
  const setCaptureText = (value: string) => {
    if (captureControlled) onCaptureValueChange(value)
    else setInternalCapture(value)
  }

  const submitCapture = () => {
    const text = captureText.trim()
    if (!text || captureDisabled) return
    onCaptureSubmit?.(text)
    if (!captureControlled) setInternalCapture('')
  }

  return (
    <div>
      {showHeader && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <Inbox className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            GTD Inbox ({items.length})
          </span>
        </div>
      )}
      {isFull && (
        <div className="flex items-center gap-1.5 mb-1.5">
          <input
            value={captureText}
            onChange={(e) => setCaptureText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) submitCapture()
            }}
            placeholder={capturePlaceholder ?? 'Capture a thought... (Enter)'}
            disabled={captureDisabled}
            className="flex-1 text-xs bg-muted/40 rounded px-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50"
          />
          <button
            onClick={submitCapture}
            disabled={captureDisabled || !captureText.trim()}
            className="p-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"
            title="Capture (gtd_capture)"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          {onBatchClassify && items.length > 0 && (
            <button
              onClick={onBatchClassify}
              disabled={batchClassifyDisabled}
              className="flex items-center gap-1 px-2 py-1.5 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-xs disabled:opacity-40 shrink-0"
              title={t('zenskill.inbox.batchClassify', '按 AI 建议一键整理全部条目')}
            >
              <Sparkles className="h-3 w-3" />
              {t('zenskill.inbox.batchClassify', '批量整理')}
            </button>
          )}
        </div>
      )}
      {items.length === 0 ? (
        <div className="text-xs text-muted-foreground italic pl-5">No pending items</div>
      ) : (
        <div className="space-y-1">
          {items.slice(0, maxItems).map((item) => {
            const suggested = suggestions?.[item.id]
            return (
            <div
              key={item.id}
              className="flex items-center gap-1 text-xs rounded px-2 py-1 hover:bg-muted/50 group"
            >
              <button
                className="flex items-center gap-2 flex-1 truncate text-left"
                onClick={() => onItemClick?.(item.text || item.raw_text || '')}
                title="Click to discuss in chat"
              >
                <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                <span className="truncate flex-1">{item.text || item.raw_text}</span>
              </button>
              {suggested && (
                <AutoClassifyBadge
                  suggestedType={suggested}
                  busy={busyId === item.id}
                  onClassify={(type) => (onClarifyRequest ? onClarifyRequest(item) : onClarify?.(item.id))}
                />
              )}
              <button
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                title={onClarifyRequest ? t('zenskill.modal.clarify.open') : 'Clarify (auto-classify)'}
                disabled={busyId === item.id}
                onClick={() => (onClarifyRequest ? onClarifyRequest(item) : onClarify?.(item.id))}
              >
                <Wand2 className="h-3 w-3" />
              </button>
              <button
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent/20 text-muted-foreground hover:text-accent shrink-0"
                title="Archive"
                disabled={busyId === item.id}
                onClick={() => onArchive?.(item.id)}
              >
                <Archive className="h-3 w-3" />
              </button>
            </div>
            )
          })}
          {items.length > maxItems && (
            <div className="text-xs text-muted-foreground pl-5">+{items.length - maxItems} more</div>
          )}
        </div>
      )}
    </div>
  )
}
