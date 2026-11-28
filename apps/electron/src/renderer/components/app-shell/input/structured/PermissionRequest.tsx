import React from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, Check, X, RefreshCw, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { PermissionRequest as PermissionRequestType } from '../../../../../shared/types'
import type { PermissionResponse } from './types'

/**
 * 否决载荷构造（纯函数，便于单测）。
 * 理由为空白 ⇒ 返回 null（界面不应允许提交；后端仍有 reason_missing 兜底）。
 * 超长理由按契约 500 上限截断（与后端 normalize_reason 同口径）。
 */
export function buildDenyResponse(reason: string): PermissionResponse | null {
  const text = (reason || '').trim()
  if (!text) return null
  return { type: 'permission', allowed: false, alwaysAllow: false, reason: text.slice(0, 500) }
}

interface PermissionRequestProps {
  request: PermissionRequestType
  onResponse: (response: PermissionResponse) => void
  /** When true, removes container styling (shadow, rounded) - used when wrapped by InputContainer */
  unstyled?: boolean
}

/**
 * PermissionRequest - Self-contained structured input for permission approval
 *
 * Shows:
 * - Shield icon + "Permission Required" header
 * - Tool name badge + bridge run chip (runId / subtaskId / depth, when present)
 * - Description of what the tool wants to do
 * - Command preview (scrollable)
 * - Countdown to auto-deny when the bridge supplied timeoutMs
 * - Action buttons: Allow / Always Allow / Deny
 * - Deny reveals a required reason field; the reason is sent with the reply so
 *   the backend can write it into ~/.zenskill/audit/approval-audit.jsonl
 *   (specs/swarm_integration_contract_v1.yaml → approval.reason_rules)
 */
export function PermissionRequest({ request, onResponse, unstyled = false }: PermissionRequestProps) {
  const { t } = useTranslation()

  const [denyOpen, setDenyOpen] = React.useState(false)
  const [reason, setReason] = React.useState('')
  const timeoutMs = request.timeoutMs
  const [remainingMs, setRemainingMs] = React.useState<number | undefined>(timeoutMs)

  React.useEffect(() => {
    if (timeoutMs == null) return
    const startedAt = Date.now()
    setRemainingMs(timeoutMs)
    const id = setInterval(() => {
      const left = timeoutMs - (Date.now() - startedAt)
      setRemainingMs(left > 0 ? left : 0)
      if (left <= 0) clearInterval(id)
    }, 1000)
    return () => clearInterval(id)
  }, [timeoutMs, request.requestId])

  const expired = remainingMs != null && remainingMs <= 0
  const secondsLeft = remainingMs != null ? Math.ceil(remainingMs / 1000) : undefined
  const trimmedReason = reason.trim()

  const handleAllow = () => {
    onResponse({ type: 'permission', allowed: true, alwaysAllow: false })
  }

  const handleAlwaysAllow = () => {
    onResponse({ type: 'permission', allowed: true, alwaysAllow: true })
  }

  const handleDenySubmit = () => {
    const payload = buildDenyResponse(reason)
    if (payload) onResponse(payload)
  }

  return (
    <div
      className={cn(
        'overflow-hidden h-full flex flex-col bg-info/5',
        unstyled
          ? 'border-0'
          : 'border border-info/30 rounded-[8px] shadow-middle'
      )}
      data-tutorial="permission-banner"
    >
      {/* Content - grows to fill available space and scrolls before actions disappear */}
      <div className="p-4 space-y-3 flex-1 min-h-0 flex flex-col overflow-y-auto">
        <div className="space-y-2 pb-1">
          <div className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-foreground">
            <ShieldAlert className="h-3.5 w-3.5 text-warning" />
            <span>{t('chat.permissionRequired')}</span>
            {request.runId && (
              <span
                className="ml-1 rounded-full border border-info/30 bg-info/10 px-2 py-0.5 font-mono text-[10px] font-normal text-info"
                data-testid="permission-run-chip"
                title={request.subtaskId ? `subtask ${request.subtaskId}` : undefined}
              >
                run {request.runId}
              </span>
            )}
            {secondsLeft != null && !expired && (
              <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-normal text-muted-foreground">
                <Clock className="h-3 w-3" />
                {t('chat.permissionTimeout', { seconds: secondsLeft })}
              </span>
            )}
          </div>
          <div className="text-xs leading-[18px] text-muted-foreground">
            <span className="font-medium text-foreground">Tool:</span> {request.toolName}
            <br />
            {request.description}
          </div>
        </div>

        {/* Command preview */}
        {request.command && (
          <div className="bg-foreground/5 rounded-md p-3 font-mono text-xs text-foreground/90 whitespace-pre-wrap break-all max-h-24 overflow-y-auto">
            {request.command}
          </div>
        )}

        {/* Deny reason (required). Only rendered after the user starts denying. */}
        {denyOpen && (
          <div className="space-y-1.5" data-testid="permission-deny-reason">
            <label
              htmlFor="permission-deny-reason-input"
              className="block text-[11px] font-medium text-foreground"
            >
              {t('chat.permissionReasonLabel')}
            </label>
            <textarea
              id="permission-deny-reason-input"
              data-testid="permission-deny-reason-input"
              className="w-full min-h-[56px] resize-y rounded-md border border-border bg-background px-2.5 py-2 text-xs leading-[18px] text-foreground outline-none focus-visible:ring-1 focus-visible:ring-info"
              placeholder={t('chat.permissionReasonPlaceholder')}
              value={reason}
              maxLength={500}
              autoFocus
              onChange={(e) => setReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleDenySubmit()
                }
              }}
            />
            <div className="text-[10px] text-muted-foreground">{trimmedReason.length}/500</div>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="shrink-0 flex flex-wrap items-center gap-2 px-3 py-2 border-t border-border/50">
        {!denyOpen ? (
          <>
            <Button
              size="sm"
              variant="default"
              className="h-7 gap-1.5"
              onClick={handleAllow}
              disabled={expired}
              data-tutorial="permission-allow-button"
            >
              <Check className="h-3.5 w-3.5" />
              {t('chat.permissionAllow')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1.5 border border-foreground/10 hover:bg-foreground/5 active:bg-foreground/10"
              onClick={handleAlwaysAllow}
              disabled={expired}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              {t('chat.permissionAlwaysAllow')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1.5 text-destructive hover:text-destructive border border-dashed border-destructive/50 hover:bg-destructive/10 hover:border-destructive/70 active:bg-destructive/20"
              onClick={() => setDenyOpen(true)}
              disabled={expired}
              data-testid="permission-deny-button"
            >
              <X className="h-3.5 w-3.5" />
              {t('chat.permissionDeny')}
            </Button>

            {/* Tip text */}
            <span className="min-w-0 flex-1 basis-full text-[10px] text-muted-foreground sm:basis-auto sm:text-right">
              {expired
                ? t('chat.permissionTimeout', { seconds: 0 })
                : '"Always Allow" remembers this command for the session'}
            </span>
          </>
        ) : (
          <>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1.5 text-destructive hover:text-destructive border border-dashed border-destructive/50 hover:bg-destructive/10 hover:border-destructive/70 active:bg-destructive/20"
              onClick={handleDenySubmit}
              disabled={!trimmedReason || expired}
              data-testid="permission-deny-submit"
            >
              <X className="h-3.5 w-3.5" />
              {t('chat.permissionDenySubmit')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7"
              onClick={() => {
                setDenyOpen(false)
                setReason('')
              }}
            >
              {t('common.cancel')}
            </Button>
            <span className="min-w-0 flex-1 basis-full text-[10px] text-muted-foreground">
              {t('chat.permissionReasonPlaceholder')}
            </span>
          </>
        )}
      </div>
    </div>
  )
}
