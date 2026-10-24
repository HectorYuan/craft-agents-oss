import { describe, expect, it } from 'bun:test'
import {
  buildLlmCatalogSnapshot,
  findCatalogEntryByBaseUrl,
  findSiblingRegionProvider,
  hostOf,
  isRegionMismatchResponse,
  readEngineCatalogOverlay,
  ENGINE_CATALOG_TTL_SECONDS,
  type EngineCatalogOverlay,
} from './llm-catalog'

// 真相源（specs/providers.yaml）经生成器产出的 presets/catalog —— 本模块的事实底座。
// 这里断言的是「引擎真相源 ⇒ GUI 拿到的目录」这条链，不复述 yaml 全文。

// 用例一律指向一个**不存在的**配置根目录 ⇒ 永不读用户真实 HOME 下的覆盖层，
// 用例结果只取决于本模块与真相源（不依赖本机状态）。
const NO_OVERLAY_DIR = '/nonexistent-config-dir-for-tests'

describe('buildLlmCatalogSnapshot —— 预设清单来自引擎真相源', () => {
  it('下发 minimax 的 Anthropic 兼容预设（2026-10-24 P6 的由来）', () => {
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR })
    const cn = snap.presets?.find(p => p.key === 'minimax-cn-anthropic')
    expect(cn).toBeDefined()
    expect(cn?.baseUrl).toBe('https://api.minimax.cn/anthropic')
    expect(cn?.api).toBe('anthropic-messages')
    expect(cn?.piOnly).toBe(false) // Anthropic 路径可用（不是 Pi 专属）
    expect(cn?.region).toBe('cn')
    expect(cn?.vendorFamily).toBe('minimax')

    const global = snap.presets?.find(p => p.key === 'minimax-anthropic')
    expect(global?.baseUrl).toBe('https://api.minimax.io/anthropic')
    expect(global?.region).toBe('global')
  })

  it('openai 兼容的两个 minimax 预设仍是 Pi 专属', () => {
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR })
    expect(snap.presets?.find(p => p.key === 'minimax-cn')?.piOnly).toBe(true)
    expect(snap.presets?.find(p => p.key === 'minimax-global')?.piOnly).toBe(true)
  })

  it('每个预设的 base_url 都指向其 provider 的注册表端点（不漂移）', () => {
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR })
    for (const preset of snap.presets ?? []) {
      const entry = findCatalogEntryByBaseUrl(preset.baseUrl)
      expect(entry?.provider).toBe(preset.provider)
    }
  })
})

describe('buildLlmCatalogSnapshot —— 新鲜度口径与引擎一致', () => {
  const now = 1_700_000_000_000

  it('没有覆盖层条目 ⇒ source=catalog 且 stale=true（从未同步过）', () => {
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR, overlay: { providers: {} }, now })
    const entry = snap.providers?.find(p => p.provider === 'minimax-cn')
    expect(entry?.source).toBe('catalog')
    expect(entry?.stale).toBe(true)
    expect(entry?.fetchedAt).toBeUndefined()
    expect(entry?.models.length).toBeGreaterThan(0) // 静态目录仍在
  })

  it('覆盖层有条目 ⇒ source=cache + 型号取覆盖层 + 年龄可算', () => {
    const overlay: EngineCatalogOverlay = {
      providers: {
        'minimax-cn': {
          models: ['MiniMax-M3', 'MiniMax-M3.1-Flash'],
          fetched_at: Math.floor(now / 1000) - 60,
        },
      },
    }
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR, overlay, now })
    const entry = snap.providers?.find(p => p.provider === 'minimax-cn')
    expect(entry?.source).toBe('cache')
    expect(entry?.models).toEqual(['MiniMax-M3', 'MiniMax-M3.1-Flash'])
    expect(entry?.ageSeconds).toBe(60)
    expect(entry?.stale).toBe(false)
    expect(entry?.fetchedAt).toBe((Math.floor(now / 1000) - 60) * 1000)
  })

  it('超过 TTL ⇒ stale=true（引擎同一条判据）', () => {
    const overlay: EngineCatalogOverlay = {
      providers: {
        'minimax-cn': { models: ['MiniMax-M3'], fetched_at: Math.floor(now / 1000) - ENGINE_CATALOG_TTL_SECONDS - 10 },
      },
    }
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR, overlay, now })
    expect(snap.providers?.find(p => p.provider === 'minimax-cn')?.stale).toBe(true)
  })

  it('providers 过滤只返回指定 provider', () => {
    const snap = buildLlmCatalogSnapshot({ configDir: NO_OVERLAY_DIR, providers: ['minimax-cn'], overlay: { providers: {} }, now })
    expect(snap.providers?.length).toBe(1)
    expect(snap.providers?.[0].provider).toBe('minimax-cn')
  })
})

describe('readEngineCatalogOverlay —— 读不到不当崩', () => {
  it('目录不存在 ⇒ 返回空覆盖层', () => {
    const overlay = readEngineCatalogOverlay(NO_OVERLAY_DIR)
    expect(overlay.providers).toEqual({})
  })
})

describe('区域判定（P4）', () => {
  it('按 host 找到端点所属 provider 与区域', () => {
    expect(findCatalogEntryByBaseUrl('https://api.minimax.cn/anthropic')?.provider).toBe('minimax-cn-anthropic')
    expect(findCatalogEntryByBaseUrl('https://api.minimaxi.com/v1')?.provider).toBe('minimax-cn')
    expect(findCatalogEntryByBaseUrl('https://api.minimax.io/v1')?.provider).toBe('minimax')
    expect(findCatalogEntryByBaseUrl('https://unknown.example.com/v1')).toBeUndefined()
  })

  it('同族兄弟端点：区域不同，且优先同协议', () => {
    const sibling = findSiblingRegionProvider('minimax-cn')
    expect(sibling).toBeDefined()
    expect(sibling?.region).not.toBe('cn')
    expect(sibling?.vendorFamily).toBe('minimax')
    expect(sibling?.api).toBe('openai-completions') // 与自身同协议

    const anthropicSibling = findSiblingRegionProvider('minimax-cn-anthropic')
    expect(anthropicSibling?.region).toBe('global')
    expect(anthropicSibling?.api).toBe('anthropic-messages') // 同协议优先
  })

  it('没有厂商族信息的 provider ⇒ 不猜兄弟端点', () => {
    expect(findSiblingRegionProvider('anthropic')).toBeUndefined()
  })

  it('401 / invalid api key (2049) 判为区域或 key 问题；400 unknown model 不判', () => {
    expect(isRegionMismatchResponse(401, '')).toBe(true)
    expect(isRegionMismatchResponse(400, '{"error":{"message":"invalid api key (2049)"}}')).toBe(true)
    expect(isRegionMismatchResponse(400, "unknown model 'minimax-m3.0' (2013)")).toBe(false)
    expect(isRegionMismatchResponse(404, 'not found')).toBe(false)
  })

  it('hostOf 对非法 URL 返回空串', () => {
    expect(hostOf('not a url')).toBe('')
    expect(hostOf('https://API.Minimax.CN/anthropic')).toBe('api.minimax.cn')
  })
})
