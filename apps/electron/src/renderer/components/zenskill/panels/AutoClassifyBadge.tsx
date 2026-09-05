/**
 * AutoClassifyBadge — AI 分类建议徽章（B09）
 *
 * 显示 inbox 条目的自动分类建议（action/project/reference/calendar），
 * 点击直接按建议澄清（无需打开 ClarifyModal）。颜色按类型编码。
 */
import React from 'react'
import { Wand2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type SuggestType = 'action' | 'project' | 'reference' | 'calendar'

const TYPE_COLORS: Record<SuggestType, string> = {
  action: 'bg-blue-500/15 text-blue-400',
  project: 'bg-purple-500/15 text-purple-400',
  reference: 'bg-yellow-500/15 text-yellow-400',
  calendar: 'bg-green-500/15 text-green-400',
}

export interface AutoClassifyBadgeProps {
  suggestedType: string
  /** 点击按建议一键澄清 */
  onClassify: (type: SuggestType) => void
  busy?: boolean
}

export function AutoClassifyBadge({ suggestedType, onClassify, busy }: AutoClassifyBadgeProps) {
  const { t } = useTranslation()
  const type = (['action', 'project', 'reference', 'calendar'] as const).includes(suggestedType as SuggestType)
    ? (suggestedType as SuggestType)
    : 'action'

  return (
    <button
      className={`opacity-0 group-hover:opacity-100 flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] shrink-0 transition-opacity ${TYPE_COLORS[type]} disabled:opacity-40`}
      title={t('zenskill.inbox.suggestBadge', 'AI 分类建议，点击采纳')}
      disabled={busy}
      onClick={(e) => {
        e.stopPropagation()
        onClassify(type)
      }}
    >
      <Wand2 className="h-2.5 w-2.5" />
      {t(`zenskill.modal.clarify.type.${type}`, type)}
    </button>
  )
}
