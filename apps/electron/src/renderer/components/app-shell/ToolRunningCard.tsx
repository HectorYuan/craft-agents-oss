/**
 * ToolRunningCard — running 态工具反馈卡片（P0-B）。
 *
 * 与 GenericToolResultCard 并列：活动 status === 'running' 时挂在活动行下方，
 * 展示工具名、入参首行回显、已运行时长（500ms tick）与等待文案；活动完成/失败/
 * 取消（status 转出 running）后卡片卸载，计时器经 cleanup clearInterval，不泄漏。
 * 完成态外观与既有结果卡基线不受影响。
 */
import React, { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Spinner } from '@craft-agent/ui'
import { cn } from '@/lib/utils'

/** 入参回显字符上限（首行）。 */
export const RUNNING_ECHO_LIMIT = 80

const ECHO_KEYS = [
  'path',
  'file_path',
  'filePath',
  'directory',
  'dir',
  'pattern',
  'url',
  'command',
  'cmd',
  'skill',
]

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

/** 抽取入参首行回显；无可用字符串返回 ''（调用方显示兜底文案，不编造）。 */
export function extractRunningEcho(toolInput?: Record<string, unknown>): string {
  if (!toolInput) return ''
  for (const key of ECHO_KEYS) {
    const hint = asString(toolInput[key])
    if (hint) return hint.slice(0, RUNNING_ECHO_LIMIT)
  }
  for (const value of Object.values(toolInput)) {
    const hint = asString(value)
    if (hint) return hint.slice(0, RUNNING_ECHO_LIMIT)
  }
  return ''
}

/** 已运行时长格式化：不足 1 分钟显示 0.0s，否则 m:ss。 */
export function formatElapsedRunning(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const rem = seconds % 60
  return `${minutes}:${rem.toString().padStart(2, '0')}`
}

/**
 * 计时器控制器：启动即首 tick，按 intervalMs 回调；stop 后 clearInterval
 * 且不再回调。组件卸载/状态切换经 useEffect 清理调用 stop，避免 interval 泄漏。
 */
export class RunningTimer {
  private id: ReturnType<typeof setInterval> | null = null

  constructor(
    private readonly onTick: (elapsedMs: number) => void,
    private readonly intervalMs = 500,
    private readonly clock: () => number = Date.now
  ) {}

  /**
   * @param baseline 活动时间戳基线（缺省取启动时刻）；clock 仅用于取当前时间，
   * 不得传入固定基线，否则 elapsed 恒为 0。
   */
  start(baseline?: number): void {
    const startedAt = baseline ?? this.clock()
    const tick = () => this.onTick(this.clock() - startedAt)
    tick()
    this.id = setInterval(tick, this.intervalMs)
  }

  stop(): void {
    if (this.id !== null) {
      clearInterval(this.id)
      this.id = null
    }
  }
}

interface ToolRunningCardProps {
  /** 工具名（展示在卡片头部） */
  toolName: string
  /** 工具入参（可选；缺失时如实显示兜底文案，不编造回显） */
  toolInput?: Record<string, unknown>
  /** 活动时间戳兜底（缺省时取挂载时刻） */
  startTime?: number
}

export function ToolRunningCard({ toolName, toolInput, startTime }: ToolRunningCardProps) {
  const { t } = useTranslation()
  const [elapsedMs, setElapsedMs] = useState(0)
  const timerRef = useRef<RunningTimer | null>(null)

  useEffect(() => {
    const timer = new RunningTimer(setElapsedMs, 500)
    timerRef.current = timer
    timer.start(startTime)
    return () => timer.stop()
  }, [startTime])

  const echo = extractRunningEcho(toolInput)

  return (
    <div
      data-testid="tool-running-card"
      className={cn(
        'mt-0.5 inline-flex max-w-full flex-col gap-0.5 rounded-md border border-border/60 bg-background px-2.5 py-1.5 text-left text-xs'
      )}
    >
      <span className="flex items-center gap-1.5 min-w-0">
        <Spinner className="text-[10px] shrink-0" />
        <span className="truncate font-medium text-foreground">{toolName}</span>
        <span className="ml-auto shrink-0 tabular-nums text-muted-foreground/70">
          {formatElapsedRunning(elapsedMs)}
        </span>
      </span>
      <div className="whitespace-pre-wrap break-all leading-[18px] text-muted-foreground">
        {echo || t('common.paramsNotPassed')}
      </div>
      <span className="text-[10px] text-muted-foreground/70">{t('common.waitingForToolReturn')}</span>
    </div>
  )
}
