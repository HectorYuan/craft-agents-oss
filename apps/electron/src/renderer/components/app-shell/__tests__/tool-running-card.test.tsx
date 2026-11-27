/**
 * ToolRunningCard 单测（P0-B）：running 态工具卡的执行反馈。
 *
 * 覆盖：
 * - 工具名 + 入参首行回显（>80 字符截断）+「等待工具返回」状态文案 + 已运行时长；
 * - 未带入参如实显示「参数未回传」，不编造片段；
 * - RunningTimer 控制器：启动即首 tick、按周期递增、stop 即 clearInterval，停止后不再 tick。
 *
 * 完成态卡片（GenericToolResultCard）既有基线语义不在本文件覆盖。
 */
import React from 'react'
import { describe, test, expect, beforeEach, afterEach } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import i18next from 'i18next'
import { initReactI18next, I18nextProvider } from 'react-i18next'
import { ToolRunningCard, RunningTimer, extractRunningEcho } from '../ToolRunningCard'

const i18n = i18next.createInstance()
await new Promise<void>((resolve) => {
  i18n.use(initReactI18next).init(
    {
      lng: 'zh',
      resources: {
        zh: {
          translation: {
            'common.waitingForToolReturn': '等待工具返回',
            'common.paramsNotPassed': '参数未回传',
          },
        },
      },
      interpolation: { escapeValue: false },
    },
    () => resolve(),
  )
})
expect(i18n.isInitialized).toBe(true)

function render(props: React.ComponentProps<typeof ToolRunningCard>) {
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <ToolRunningCard {...props} />
    </I18nextProvider>,
  )
}

describe('ToolRunningCard 静态渲染', () => {
  test('显示工具名、入参回显、等待文案与已运行时长', () => {
    const html = render({ toolName: 'read', toolInput: { path: 'a_write.txt' } })
    expect(html).toContain('read')
    expect(html).toContain('a_write.txt')
    expect(html).toContain('等待工具返回')
    // 时长徽标（首 tick 为 0 毫秒量级）
    expect(html).toMatch(/\d+(?:\.\d+)?s/)
  })

  test('入参回显超过 80 字符截断', () => {
    const longPath = '/repo/src/' + 'x'.repeat(100)
    const echo = extractRunningEcho({ path: longPath })
    expect(echo.length).toBeLessThanOrEqual(80)
    const html = render({ toolName: 'bash', toolInput: { command: longPath } })
    expect(html).not.toContain('x'.repeat(81))
  })

  test('未带入参：显示参数未回传，不编造回显', () => {
    const html = render({ toolName: 'list_dir', toolInput: undefined })
    expect(html).toContain('参数未回传')
  })

  test('入参仅含非字符串值：显示参数未回传', () => {
    expect(extractRunningEcho({ count: 3, flag: true })).toBe('')
    const html = render({ toolName: 'bash', toolInput: { count: 3, flag: true } })
    expect(html).toContain('参数未回传')
  })

  test('命令类入参优先于其它字符串字段', () => {
    expect(extractRunningEcho({ command: 'git status', note: 'hello' })).toBe('git status')
  })
})

describe('RunningTimer 生命周期', () => {
  let intervals: Map<number, () => void>
  let originalSetInterval: typeof setInterval
  let originalClearInterval: typeof clearInterval

  beforeEach(() => {
    intervals = new Map()
    originalSetInterval = globalThis.setInterval
    originalClearInterval = globalThis.clearInterval
    let fakeId = 0
    globalThis.setInterval = ((cb: () => void, ms?: number) => {
      const id = ++fakeId
      intervals.set(id, cb)
      return id as unknown as ReturnType<typeof setInterval>
    }) as typeof setInterval
    globalThis.clearInterval = ((id: ReturnType<typeof setInterval>) => {
      intervals.delete(id as unknown as number)
    }) as typeof clearInterval
  })

  afterEach(() => {
    globalThis.setInterval = originalSetInterval
    globalThis.clearInterval = originalClearInterval
  })

  test('启动即首 tick，按周期触发递增，stop 清除 interval 且不再触发', async () => {
    const ticks: number[] = []
    const timer = new RunningTimer(ms => ticks.push(ms), 10)
    timer.start()
    expect(ticks.length).toBe(1)
    expect(intervals.size).toBe(1)

    const [id, cb] = [...intervals.entries()][0]
    cb() // 第 2 个 tick
    cb() // 第 3 个 tick
    expect(ticks.length).toBe(3)
    expect(ticks[2] >= ticks[1]).toBe(true)

    timer.stop()
    expect(intervals.has(id)).toBe(false)
    expect(intervals.size).toBe(0)
    // 停止后 interval 已摘除：即使旧回调被外部触发，控制器也不再持有可触发的句柄。
    expect(() => timer.stop()).not.toThrow()
  })

  test('重复 stop 不抛错', () => {
    const timer = new RunningTimer(() => {}, 10)
    timer.start()
    timer.stop()
    expect(() => timer.stop()).not.toThrow()
  })

  test('startTime 作为基线：elapsed 从该基线起算，跨 tick 递增', () => {
    const now = 100_000
    const baseline = now - 2_000
    let clockNow = now
    const ticks: number[] = []
    const timer = new RunningTimer(ms => ticks.push(ms), 10, () => clockNow)
    timer.start(baseline)
    expect(ticks[0]).toBe(2_000)
    const [, cb] = [...intervals.entries()][0]
    clockNow = now + 600
    cb()
    expect(ticks[1]).toBe(2_600)
    timer.stop()
  })
})
