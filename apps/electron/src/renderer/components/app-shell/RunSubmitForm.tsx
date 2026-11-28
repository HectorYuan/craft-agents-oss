/**
 * RunSubmitEntry — 会话内派发入口（D4）。
 *
 * 落点：composer 区的 run 状态 chip 旁边（`ChatInputZone`），不新开页面——
 * 派发语义就是「在目标会话里开一轮」，入口天然带 sessionId，审计回链不断。
 *
 * 自门控：`run:submit` 通道不可用（服务端统一能力 flag 关）→ 整块不渲染。
 * 交互校验只做空白标题与数值范围；capId 白名单、budget 语义、会话可见性
 * 一律由服务端判定，失败时就地提示且不收起 popover（不吞错）。
 */

import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { Play } from 'lucide-react'
import { RPC_CHANNELS } from '@craft-agent/shared/protocol'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  RUN_SUBMIT_CAP_IDS,
  canSubmitRunSubmitForm,
  parseRunSubmitInput,
  type RunSubmitFormValues,
} from './runSubmitModel'

const EMPTY_FORM: RunSubmitFormValues = {
  title: '',
  description: '',
  capId: RUN_SUBMIT_CAP_IDS[0],
  maxSteps: '',
  timeoutSec: '',
}

function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (err && typeof err === 'object' && 'message' in err) {
    const msg = (err as { message?: unknown }).message
    if (typeof msg === 'string' && msg) return msg
  }
  return ''
}

interface RunSubmitEntryProps {
  sessionId: string
}

export function RunSubmitEntry({ sessionId }: RunSubmitEntryProps) {
  const { t } = useTranslation()
  const available = window.electronAPI.isChannelAvailable(RPC_CHANNELS.run.SUBMIT)
  const [open, setOpen] = React.useState(false)
  const [values, setValues] = React.useState<RunSubmitFormValues>(EMPTY_FORM)
  const [submitting, setSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [lastRunId, setLastRunId] = React.useState<string | null>(null)

  if (!available) return null

  const canSubmit = canSubmitRunSubmitForm(values) && !submitting

  const patch = (next: Partial<RunSubmitFormValues>) =>
    setValues((prev) => ({ ...prev, ...next }))

  const handleSubmit = async (event?: React.FormEvent) => {
    event?.preventDefault()
    if (!canSubmit) return
    const parsed = parseRunSubmitInput(values, sessionId)
    if (!parsed.ok) {
      setError(t(parsed.error))
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const result = await window.electronAPI.runSubmit(parsed.request)
      setLastRunId(result.runId)
      setOpen(false)
      setValues((prev) => ({ ...prev, title: '', description: '', maxSteps: '', timeoutSec: '' }))
    } catch (err) {
      // 服务端拒绝（capId/会话/预算）时保留输入与 popover，原文提示不吞错。
      const msg = errorMessage(err)
      setError(msg || t('chat.runSubmitFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Popover open={open} onOpenChange={(next) => { setOpen(next); if (!next) setError(null) }}>
        <PopoverTrigger asChild>
          <button
            data-testid="run-submit-open"
            type="button"
            title={t('chat.runSubmitOpen')}
            aria-label={t('chat.runSubmitOpen')}
            className={cn(
              'flex items-center gap-1 rounded-[8px] px-2 h-[26px] text-[11px] font-medium',
              'bg-white/70 dark:bg-white/10 hover:bg-white dark:hover:bg-white/15',
              'text-foreground/70 hover:text-foreground transition-colors select-none',
            )}
          >
            <Play className="h-3 w-3" />
            {t('chat.runSubmitOpen')}
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" side="top" className="w-80">
          <form data-testid="run-submit-form" onSubmit={handleSubmit} className="flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-[11px]">
              <span className="opacity-70">{t('chat.runSubmitTitle')}</span>
              <Input
                data-testid="run-submit-title"
                value={values.title}
                maxLength={200}
                placeholder={t('chat.runSubmitTitlePlaceholder')}
                onChange={(e) => patch({ title: e.target.value })}
                autoFocus
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px]">
              <span className="opacity-70">{t('chat.runSubmitDescription')}</span>
              <textarea
                data-testid="run-submit-description"
                value={values.description}
                maxLength={2000}
                rows={2}
                className="w-full rounded-md border border-foreground/15 bg-transparent px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30"
                onChange={(e) => patch({ description: e.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1 text-[11px]">
              <span className="opacity-70">{t('chat.runSubmitCap')}</span>
              <select
                data-testid="run-submit-cap"
                value={values.capId}
                className="h-8 rounded-md border border-foreground/15 bg-transparent px-2 text-sm"
                onChange={(e) => patch({ capId: e.target.value })}
              >
                {RUN_SUBMIT_CAP_IDS.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="opacity-70">{t('chat.runSubmitMaxSteps')}</span>
                <Input
                  data-testid="run-submit-max-steps"
                  inputMode="numeric"
                  value={values.maxSteps}
                  onChange={(e) => patch({ maxSteps: e.target.value })}
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="opacity-70">{t('chat.runSubmitTimeout')}</span>
                <Input
                  data-testid="run-submit-timeout"
                  inputMode="numeric"
                  value={values.timeoutSec}
                  onChange={(e) => patch({ timeoutSec: e.target.value })}
                />
              </label>
            </div>
            {error && (
              <div data-testid="run-submit-error" className="text-[11px] text-destructive break-words">
                {error}
              </div>
            )}
            <div className="flex justify-end">
              <Button
                data-testid="run-submit-submit"
                type="submit"
                size="sm"
                disabled={!canSubmit}
              >
                {submitting ? t('chat.runSubmitSubmitting') : t('chat.runSubmitSubmit')}
              </Button>
            </div>
          </form>
        </PopoverContent>
      </Popover>
      {lastRunId && (
        <span
          data-testid="run-submit-runid"
          title={lastRunId}
          className="text-[11px] tabular-nums opacity-60 select-none truncate max-w-[120px]"
        >
          run {lastRunId}
        </span>
      )}
    </div>
  )
}
