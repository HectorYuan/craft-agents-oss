/**
 * project-session-meta 纯函数单测（D4.2.1 · F02 / F03 / F04 / F05）
 *
 * 守的口径：
 *  - 只有 `projectId` 精确匹配项目 `config.id` 且非归档的会话才计入该项目；
 *  - 最近活跃取 `lastMessageAt`（回退 `updatedAt`）最大值，缺时间戳跳过、不当 0；
 *  - 未绑定 / 空白 / 指向已删除项目的会话解析为「无项目」；
 *  - F04 指标卡：缺键显 `—`，真实 0 显 0；Token 取 totalTokens 回退 input+output，不展成本。
 */
import { describe, expect, it } from 'bun:test'
import type { SessionMeta } from '../../atoms/sessions'
import {
  formatMessageCount,
  formatModel,
  formatTokenTotal,
  maxActiveAt,
  METRIC_PLACEHOLDER,
  recentProjectSessions,
  resolveSessionProject,
  sessionActiveAt,
  sessionsForProject,
  tokenTotal,
} from '../project-session-meta'

function meta(partial: Partial<SessionMeta> & { updatedAt?: number }): SessionMeta {
  return { id: partial.id ?? 's-' + Math.random(), workspaceId: 'ws-1', ...partial } as SessionMeta
}

describe('sessionsForProject', () => {
  it('只收集 projectId 精确匹配且未归档的会话', () => {
    const map = new Map<string, SessionMeta>([
      ['a', meta({ id: 'a', projectId: 'proj-alpha', lastMessageAt: 100 })],
      ['b', meta({ id: 'b', projectId: 'proj-alpha', isArchived: true, lastMessageAt: 200 })],
      ['c', meta({ id: 'c', projectId: 'proj-beta', lastMessageAt: 300 })],
      ['d', meta({ id: 'd', lastMessageAt: 400 })],
    ])

    const bound = sessionsForProject(map, 'proj-alpha')

    expect(bound.map((m) => m.id)).toEqual(['a'])
  })

  it('空项目 id / null / undefined 时返回空数组', () => {
    const map = new Map<string, SessionMeta>([['a', meta({ id: 'a', projectId: 'proj-alpha' })]])
    expect(sessionsForProject(map, '')).toEqual([])
    expect(sessionsForProject(map, null)).toEqual([])
    expect(sessionsForProject(map, undefined)).toEqual([])
  })
})

describe('maxActiveAt', () => {
  it('取 lastMessageAt 最大值', () => {
    const metas = [
      meta({ id: 'a', lastMessageAt: 100 }),
      meta({ id: 'b', lastMessageAt: 300 }),
      meta({ id: 'c', lastMessageAt: 200 }),
    ]
    expect(maxActiveAt(metas)).toBe(300)
  })

  it('缺 lastMessageAt 时回退 updatedAt', () => {
    const metas = [meta({ id: 'a', lastMessageAt: 100 }), meta({ id: 'b', updatedAt: 250 })]
    expect(maxActiveAt(metas)).toBe(250)
  })

  it('无时间戳的会话被跳过，空集合返回 undefined（不当 0）', () => {
    expect(maxActiveAt([])).toBeUndefined()
    expect(maxActiveAt([meta({ id: 'a' }), meta({ id: 'b' })])).toBeUndefined()
  })
})

describe('sessionActiveAt', () => {
  it('优先 lastMessageAt，其次 updatedAt，都缺时 undefined', () => {
    expect(sessionActiveAt(meta({ id: 'a', lastMessageAt: 100, updatedAt: 50 }))).toBe(100)
    expect(sessionActiveAt(meta({ id: 'b', updatedAt: 50 }))).toBe(50)
    expect(sessionActiveAt(meta({ id: 'c' }))).toBeUndefined()
  })
})

describe('recentProjectSessions', () => {
  it('按活跃时间倒序并截断到 limit', () => {
    const metas = [
      meta({ id: 'a', lastMessageAt: 100 }),
      meta({ id: 'b', lastMessageAt: 400 }),
      meta({ id: 'c', lastMessageAt: 300 }),
      meta({ id: 'd', lastMessageAt: 200 }),
      meta({ id: 'e', lastMessageAt: 500 }),
    ]
    expect(recentProjectSessions(metas, 4).map((m) => m.id)).toEqual(['e', 'b', 'c', 'd'])
  })

  it('limit 为 0 时返回空数组', () => {
    expect(recentProjectSessions([meta({ id: 'a', lastMessageAt: 100 })], 0)).toEqual([])
  })
})

describe('resolveSessionProject', () => {
  const projects = [
    { id: 'proj-alpha', slug: 'alpha', name: 'Alpha', color: '#6366f1' },
    { id: 'proj-beta', slug: 'beta', name: 'Beta' },
  ]

  it('按 config.id 精确匹配项目', () => {
    const bound = resolveSessionProject(meta({ id: 'a', projectId: 'proj-alpha' }), projects)
    expect(bound?.name).toBe('Alpha')
  })

  it('未绑定 / 空白 projectId 解析为 undefined', () => {
    expect(resolveSessionProject(meta({ id: 'a' }), projects)).toBeUndefined()
    expect(resolveSessionProject(meta({ id: 'b', projectId: '   ' }), projects)).toBeUndefined()
  })

  it('指向已删除项目的失效绑定解析为 undefined（落无项目桶）', () => {
    expect(
      resolveSessionProject(meta({ id: 'c', projectId: 'proj-gone' }), projects),
    ).toBeUndefined()
  })

  it('项目列表为空时解析为 undefined', () => {
    expect(resolveSessionProject(meta({ id: 'd', projectId: 'proj-alpha' }), undefined)).toBeUndefined()
  })
})

describe('F04 指标卡：消息数 / Token / 模型', () => {
  it('占位符是 U+2014 破折号', () => {
    expect(METRIC_PLACEHOLDER).toBe('—')
  })

  it('消息数：缺键显占位符，真实 0 显 "0"，有值直取', () => {
    expect(formatMessageCount(meta({ id: 'a' }))).toBe(METRIC_PLACEHOLDER)
    expect(formatMessageCount(meta({ id: 'b', messageCount: 0 }))).toBe('0')
    expect(formatMessageCount(meta({ id: 'c', messageCount: 12 }))).toBe('12')
  })

  it('Token：优先 totalTokens，缺省回退 input+output；整块缺失 undefined', () => {
    expect(tokenTotal(meta({ id: 'a', tokenUsage: { inputTokens: 10, outputTokens: 5, totalTokens: 42, contextTokens: 2048, costUsd: 0.01 } }))).toBe(42)
    expect(tokenTotal(meta({ id: 'b', tokenUsage: { inputTokens: 10, outputTokens: 5, totalTokens: undefined as unknown as number, contextTokens: 2048, costUsd: 0 } }))).toBe(15)
    expect(tokenTotal(meta({ id: 'c' }))).toBeUndefined()
    expect(tokenTotal(meta({ id: 'd', tokenUsage: { inputTokens: undefined as unknown as number, outputTokens: undefined as unknown as number, totalTokens: undefined as unknown as number, contextTokens: 0, costUsd: 0 } }))).toBeUndefined()
  })

  it('Token 展示：千分位；整块缺失显占位符，不展成本', () => {
    expect(formatTokenTotal(meta({ id: 'a', tokenUsage: { inputTokens: 0, outputTokens: 0, totalTokens: 1234567, contextTokens: 2048, costUsd: 0.5 } }))).toBe('1,234,567')
    expect(formatTokenTotal(meta({ id: 'b' }))).toBe(METRIC_PLACEHOLDER)
  })

  it('模型：直取原始 id；缺键 / 空串 / 纯空白显占位符，不补默认名', () => {
    expect(formatModel(meta({ id: 'a' }))).toBe(METRIC_PLACEHOLDER)
    expect(formatModel(meta({ id: 'b', model: '' }))).toBe(METRIC_PLACEHOLDER)
    expect(formatModel(meta({ id: 'c', model: '   ' }))).toBe(METRIC_PLACEHOLDER)
    expect(formatModel(meta({ id: 'd', model: 'minimax-m2' }))).toBe('minimax-m2')
  })
})
