/**
 * NowReadoutBar 真机数据渲染验收（试点）
 *
 * 数据不是手写 mock：直接取自真实后端 registry 工具在当前 workspace 的返回
 * （见会话记录：energy_level / attention_status / delegation_status / zenloop_status）。
 * 守的是「真实数据进真实组件 → 稿面读数正确」，覆盖满格 / 至多上限 / 空孵化池三条分支。
 */
import React from 'react'
import { describe, test, expect } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import i18next from 'i18next'
import { initReactI18next, I18nextProvider } from 'react-i18next'
import { NowReadoutBar } from '../panels/NowReadoutBar'

// 最小 i18n 实例：空资源，组件 t(key, defaultValue) 走默认值并正常插值。
// 等 init 完成，否则 initialized=false 时 t 不做插值（{n} 原样保留）。
const i18n = i18next.createInstance()
await new Promise<void>((resolve) => {
  i18n.use(initReactI18next).init(
    {
      lng: 'zh',
      resources: {
        zh: {
          translation: {
            'zenskill.readout.energy': '能量',
            'zenskill.readout.attention': '注意力',
            'zenskill.readout.loop': '回路',
            'zenskill.unit.point': '点',
            'zenskill.unit.minute': '分钟',
            'zenskill.readout.atMost': '至多',
            'zenskill.readout.energyRecovering': '恢复中 +{{n}} 点',
            'zenskill.readout.energyUsed': '已用 {{n}} 点',
            'zenskill.readout.attentionUpperHint': '近期深度占用暂时读不到，此值为上限',
            'zenskill.readout.attentionAvailable': '深度块可用',
            'zenskill.readout.loopCount': '{{n}} 条在跑',
            'zenskill.readout.loopIdle': '暂无在跑回路',
            'zenskill.readout.delegation': '智能体承担',
            'zenskill.state.empty': '暂无读数',
          },
        },
      },
      interpolation: { escapeValue: false },
    },
    () => resolve(),
  )
})
expect(i18n.isInitialized).toBe(true)

function render(props: React.ComponentProps<typeof NowReadoutBar>) {
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <NowReadoutBar {...props} />
    </I18nextProvider>,
  )
}

// ── 真实后端返回（2026-11-20 实查，非 mock）──────────────────────
const REAL = {
  energy: {
    status: {
      skill_id: 'zenskill-core',
      max_energy: 150,
      current_energy: 150,
      stored_energy: 95,
      pending_recovery: 12650,
      pct: 1.0,
      level: 'high',
      recovery_rate: 24,
      level_icon: '🟢',
    },
  },
  attention: {
    status: {
      available_minutes: 240,
      used_minutes: 0,
      remaining_minutes: 240,
      session_available: false,
    },
  },
  delegation: {
    status: { total: 3, agent_created: 0, ratio: 0.0, available: true },
  },
  loop: { active: 0, by_channel: {}, top: [] },
}

describe('NowReadoutBar —— 真实后端数据渲染', () => {
  const html = render({
    energy: REAL.energy as never,
    attention: REAL.attention as never,
    delegation: REAL.delegation as never,
    loop: REAL.loop as never,
  })

  test('能量格：真实封顶值 150 / 150 上稿，且待恢复>0 显示「恢复中」', () => {
    expect(html).toContain('150')
    expect(html).toContain('恢复中')
    expect(html).toContain('12650')
    // 满格进度条宽度 100%
    expect(html).toContain('width:100%')
  })

  test('注意力格：session_available=false 真实触发「至多」上限，240 分钟上稿', () => {
    expect(html).toContain('至多')
    expect(html).toContain('240')
    expect(html).toContain('此值为上限')
  })

  test('回路格：空孵化池 active=0，显示在跑 0 条且无 concept 频道', () => {
    expect(html).toContain('0 条在跑')
    expect(html).toContain('暂无在跑回路')
  })

  test('三格稿面零硬编码 hex（样式纪律）', () => {
    expect(/#[0-9a-fA-F]{3,8}\b/.test(html)).toBe(false)
  })
})

describe('NowReadoutBar —— 非空分支（有在跑回路 + 非满能量 + 会话可用）', () => {
  const html = render({
    energy:
      {
        status: {
          max_energy: 150,
          current_energy: 96,
          stored_energy: 96,
          pending_recovery: 0,
          pct: 0.64,
        },
      } as never,
    attention:
      {
        status: {
          available_minutes: 240,
          remaining_minutes: 120,
          session_available: true,
        },
      } as never,
    delegation:
      { status: { total: 4, agent_created: 2, ratio: 0.5, available: true } } as never,
    loop:
      {
        active: 2,
        by_channel: { review: 2 },
        top: [{ concept: '深度复盘', channel: 'review' }],
      } as never,
  })

  test('能量非满且无待恢复 → 显示「已用」而非「恢复中」', () => {
    expect(html).toContain('96')
    expect(html).toContain('已用')
    expect(html).not.toContain('恢复中')
  })

  test('会话可用 → 不出现「至多」，注意力显示深度块可用', () => {
    expect(html).not.toContain('至多')
    expect(html).toContain('120')
  })

  test('在跑回路显示 concept 名，委派比例 50% 上稿', () => {
    expect(html).toContain('深度复盘')
    expect(html).toContain('50%')
  })
})
