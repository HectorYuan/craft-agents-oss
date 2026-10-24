import { afterEach, describe, expect, it } from 'bun:test'
import { diagnoseRegionMismatch } from '../llm-connections'

/**
 * 区域不符诊断（P4，2026-10-24）。
 *
 * 事实：MiniMax 的 key 不可跨区 ⇒ 境内 key 打国际站 = 401 `invalid api key (2049)`，
 * 与「key 填错」完全同形。诊断办法 = **用同一个 key 去试同厂商的另一个区域端点**：
 * 那边能列出型号 ⇒ key 属于那边 ⇒ 明确告诉用户该用哪个端点。
 *
 * 这里用桩 fetch 验证三件事：
 *   ① 兄弟端点通 ⇒ 给出确证结论（含该用哪个 provider / 端点 / 名称）；
 *   ② 兄弟端点也不通 ⇒ **不给结论**（不猜，照旧显示原始 401）；
 *   ③ 端点不在真相源 / 没有同族兄弟 ⇒ 不给结论。
 */

const realFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = realFetch
})

function stubFetch(routes: Record<string, { status: number; body: string }>) {
  const calls: string[] = []
  globalThis.fetch = (async (input: Parameters<typeof fetch>[0]) => {
    const url = String(input)
    calls.push(url)
    const hit = Object.entries(routes).find(([prefix]) => url.startsWith(prefix))
    const status = hit ? hit[1].status : 404
    const body = hit ? hit[1].body : 'not found'
    return new Response(body, { status })
  }) as typeof fetch
  return calls
}

describe('diagnoseRegionMismatch', () => {
  it('兄弟区域端点能列出型号 ⇒ 给出确证结论与该用的端点', async () => {
    const calls = stubFetch({
      'https://api.minimaxi.com': { status: 401, body: '{"error":{"message":"invalid api key (2049)"}}' },
      'https://api.minimax.io': { status: 200, body: '{"data":[{"id":"MiniMax-M3"}]}' },
    })

    const diagnosis = await diagnoseRegionMismatch('https://api.minimaxi.com/v1', 'sk-test-key')

    expect(diagnosis).toBeDefined()
    expect(diagnosis?.endpointRegion).toBe('cn')
    expect(diagnosis?.keyRegion).toBe('global')
    expect(diagnosis?.suggestedProvider).toBe('minimax')
    expect(diagnosis?.suggestedBaseUrl).toBe('https://api.minimax.io/v1')
    expect(diagnosis?.message).toContain('国际站')
    expect(diagnosis?.message).toContain('国内站')
    // 确实去试了兄弟端点（只试一次、只试对的那个）
    expect(calls.length).toBe(1)
    expect(calls[0].startsWith('https://api.minimax.io')).toBe(true)
  })

  it('兄弟端点也不通 ⇒ 不给结论（不猜）', async () => {
    stubFetch({
      'https://api.minimaxi.com': { status: 401, body: 'invalid api key (2049)' },
      'https://api.minimax.io': { status: 401, body: 'invalid api key (2049)' },
    })

    const diagnosis = await diagnoseRegionMismatch('https://api.minimaxi.com/v1', 'sk-bad-key')
    expect(diagnosis).toBeUndefined()
  })

  it('端点不在真相源 ⇒ 不给结论', async () => {
    stubFetch({})
    const diagnosis = await diagnoseRegionMismatch('https://unknown.example.com/v1', 'sk-test-key')
    expect(diagnosis).toBeUndefined()
  })

  it('没有同族兄弟端点的 provider（如 anthropic）⇒ 不给结论', async () => {
    const calls = stubFetch({})
    const diagnosis = await diagnoseRegionMismatch('https://api.anthropic.com', 'sk-test-key')
    expect(diagnosis).toBeUndefined()
    expect(calls.length).toBe(0)
  })

  it('Anthropic 兼容端点 ⇒ 兄弟端点也应是 Anthropic 兼容（同协议优先）', async () => {
    const calls = stubFetch({
      'https://api.minimax.cn/anthropic': { status: 401, body: 'invalid api key (2049)' },
      'https://api.minimax.io/anthropic': { status: 200, body: '{"data":[{"id":"MiniMax-M3"}]}' },
    })

    const diagnosis = await diagnoseRegionMismatch('https://api.minimax.cn/anthropic', 'sk-test-key')
    expect(diagnosis?.suggestedProvider).toBe('minimax-anthropic')
    expect(diagnosis?.suggestedBaseUrl).toBe('https://api.minimax.io/anthropic')
    expect(calls[0]).toContain('/anthropic/v1/models')
  })
})
