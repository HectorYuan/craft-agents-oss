/**
 * O1-2 流式轮默认展开 + O1-1 起始/耗时字段消费回退。
 *
 * O1-2 状态矩阵：
 * - running 工具活动存在 → 强制展开（活动行挂载、可见）；
 * - 全部活动终结 → 回落既有折叠/展开策略（历史完成轮默认折叠）；
 * - intermediate / status 的 running 不计入（与 deriveTurnPhase 的 tool_active 口径一致）。
 *
 * O1-1 回退：
 * - 起始时刻优先 startedAt，缺失回退 timestamp；
 * - 完成耗时优先 durationMs，缺失回退 elapsedSeconds×1000；
 * - 缺字段不得报错、不得显示 NaN（非法/负值一律返回 undefined）。
 */

import { describe, it, expect } from 'bun:test'
import {
  shouldForceExpandTurn,
  resolveActivityStartMs,
  resolveActivityDurationMs,
} from '../turn-utils'
import type { ActivityItem } from '../TurnCard'

function activity(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 'activity-1',
    type: 'tool',
    status: 'completed',
    toolName: 'read',
    timestamp: 1_000,
    ...overrides,
  }
}

describe('O1-2 shouldForceExpandTurn', () => {
  it('存在 running 工具活动 → 强制展开', () => {
    const turn = { activities: [activity({ status: 'running' })] }
    expect(shouldForceExpandTurn(turn)).toBe(true)
  })

  it('全部活动终结（completed / error）→ 不强制展开，回落既有策略', () => {
    const turn = {
      activities: [
        activity({ status: 'completed' }),
        activity({ id: 'a2', status: 'error', toolName: 'bash' }),
      ],
    }
    expect(shouldForceExpandTurn(turn)).toBe(false)
  })

  it('历史完成轮（活动全终结）→ 折叠，不强制展开', () => {
    const turn = {
      activities: [activity({ status: 'completed' }), activity({ id: 'a2', status: 'completed' })],
    }
    expect(shouldForceExpandTurn(turn)).toBe(false)
  })

  it('intermediate / status 的 running 不计入强制展开判据', () => {
    const turn = {
      activities: [
        activity({ type: 'intermediate', status: 'running', toolName: undefined }),
        activity({ type: 'status', status: 'running', toolName: undefined }),
      ],
    }
    expect(shouldForceExpandTurn(turn)).toBe(false)
  })

  it('无活动 → 不强制展开', () => {
    expect(shouldForceExpandTurn({ activities: [] })).toBe(false)
  })
})

describe('O1-1 resolveActivityStartMs', () => {
  it('优先 startedAt，缺失回退 timestamp', () => {
    expect(resolveActivityStartMs(activity({ startedAt: 5_000, timestamp: 1_000 }))).toBe(5_000)
    expect(resolveActivityStartMs(activity({ startedAt: undefined, timestamp: 1_000 }))).toBe(1_000)
  })

  it('两个字段都缺失 → undefined，不产生 NaN', () => {
    expect(resolveActivityStartMs(activity({ startedAt: undefined, timestamp: undefined }))).toBeUndefined()
  })
})

describe('O1-1 resolveActivityDurationMs', () => {
  it('优先 durationMs', () => {
    expect(resolveActivityDurationMs(activity({ durationMs: 2_500, elapsedSeconds: 9 }))).toBe(2_500)
  })

  it('缺 durationMs 回退 elapsedSeconds×1000', () => {
    expect(resolveActivityDurationMs(activity({ elapsedSeconds: 3 }))).toBe(3_000)
  })

  it('两字段都缺失 → undefined', () => {
    expect(resolveActivityDurationMs(activity({}))).toBeUndefined()
  })

  it('NaN / 负值一律返回 undefined，不显示非法耗时', () => {
    expect(resolveActivityDurationMs(activity({ durationMs: NaN }))).toBeUndefined()
    expect(resolveActivityDurationMs(activity({ durationMs: -100 }))).toBeUndefined()
    expect(resolveActivityDurationMs(activity({ elapsedSeconds: NaN }))).toBeUndefined()
    expect(resolveActivityDurationMs(activity({ elapsedSeconds: -2 }))).toBeUndefined()
  })
})
