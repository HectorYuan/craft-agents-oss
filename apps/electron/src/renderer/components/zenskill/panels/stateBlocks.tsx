/**
 * stateBlocks.tsx — ZenSkill **通用五态**展示件（第十九批 D 段 D-1）
 *
 * ★ 为什么要抽出来
 * ---------------
 * 第十八批 D4 的「无权限态」原本是 `CultivationPage` 里的**私有**组件；
 * 第十九批 D 段要把三域（会话 / 项目 / 技能）接上同一个 ZenSkill 源
 * ⇒ 三域都要「加载 / 空 / 错 / 成功 / 无权限」五态
 * ⇒ **三份复制**就是「同一概念三个名字」的老问题 ⇒ 抽成共享层。
 *
 * ★ 通用五态文案只有**一份**（`zenskill.state.*`）
 *   —— 修炼域也改用它 ⇒ 真源（`stateCopy`）里不出现第二套同义说法。
 *
 * ★ 量纲纪律：这三个块**不承载任何量纲读数**
 *   （能量 = 点 / 注意力 = 分钟 …… 那是读数组件的事）。
 *
 * ★ 组件库占位字不得进产品：Empty / Info_Alert / SystemMessage 的
 *   默认文案是「空状态标题」「错误标题」等**占位字** ⇒ 实例必须覆写，
 *   覆写用的句子登记在主仓真相源 `copy_terminology.json` 的 `stateCopy` 段。
 */
import React from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { Spinner } from '@craft-agent/ui'

/** 加载态：Spinner（craft 既有形态；**禁止用 shimmer 条代替**） */
export function LoadingBlock({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2 py-3 text-foreground/30">
      <Spinner className="h-3.5 w-3.5" />
      <span className="text-xs">{label ?? t('zenskill.state.loading', '读取中')}</span>
    </div>
  )
}

/** 错误态：craft 详情页既有形态（max-w-sm + rounded-[8px] + border-destructive/20） */
export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation()
  return (
    <div className="max-w-sm rounded-[8px] border border-destructive/20 p-2 text-xs text-destructive">
      <div className="text-foreground">{t('zenskill.state.error.title', '这一块暂时读不到')}</div>
      <div className="mt-0.5 text-muted-foreground">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1.5 inline-flex items-center gap-1 rounded border border-border/30 px-2 py-1 text-[11.25px] hover:bg-muted/50"
        >
          <RefreshCw className="h-3 w-3" />
          {t('zenskill.state.error.retry', '重试')}
        </button>
      )}
    </div>
  )
}

/**
 * 无权限态（稿 `24:20` SystemMessage/system）：工作区**没有 ZenSkill 数据源**。
 *
 * ★ 这**不是故障** —— 重试无用 ⇒ 不能落进错误卡（会误报为故障 + 给出骗人的「重试」）。
 * ★ 判定见 `panels/errors.ts`（纯函数，可被测试导入）。
 */
export function NoDataSourceBlock({ hint }: { hint?: string }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-[5.625px] bg-foreground/10 px-[11.25px] py-[7.5px] text-[13.125px] text-muted-foreground">
      {t('zenskill.state.noAccess.title', '这个工作区没有 ZenSkill 数据源')}
      <div className="mt-0.5 text-[11.25px] text-muted-foreground/80">
        {hint ??
          t(
            'zenskill.state.noAccess.hint',
            '在这个工作区里添加 ZenSkill 数据源后，这里会显示成长与过程的读数',
          )}
      </div>
    </div>
  )
}
