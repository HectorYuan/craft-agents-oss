import { describe, expect, it } from 'bun:test'
import {
  buildModelsUrl,
  parseModelsPayload,
  extractServerMessage,
  checkModelAgainstCatalog,
} from './llm-model-catalog'

// 端点形状：2026-10-22 对 MiniMax 实测（两条路由都返回同一批 9 个型号）
describe('buildModelsUrl', () => {
  it('builds openai-compatible models URL', () => {
    expect(buildModelsUrl('https://api.minimaxi.com/v1', 'openai-completions'))
      .toBe('https://api.minimaxi.com/v1/models')
  })

  it('builds anthropic-compatible models URL', () => {
    expect(buildModelsUrl('https://api.minimax.cn/anthropic', 'anthropic-messages'))
      .toBe('https://api.minimax.cn/anthropic/v1/models')
  })

  it('strips trailing slashes', () => {
    expect(buildModelsUrl('https://x/v1/', 'openai-completions')).toBe('https://x/v1/models')
  })

  it('returns empty for empty base', () => {
    expect(buildModelsUrl('', 'openai-completions')).toBe('')
    expect(buildModelsUrl('   ', 'openai-completions')).toBe('')
  })
})

describe('parseModelsPayload', () => {
  it('parses data[].id', () => {
    const raw = JSON.stringify({ data: [{ id: 'MiniMax-M3' }, { id: 'MiniMax-M3.1-Flash' }] })
    expect(parseModelsPayload(raw)).toEqual(['MiniMax-M3', 'MiniMax-M3.1-Flash'])
  })

  it('parses bare string arrays', () => {
    expect(parseModelsPayload(JSON.stringify({ data: ['a', 'b'] }))).toEqual(['a', 'b'])
  })

  it('falls back to name when id is missing', () => {
    expect(parseModelsPayload(JSON.stringify({ data: [{ name: 'x' }] }))).toEqual(['x'])
  })

  it('returns empty for malformed JSON', () => {
    expect(parseModelsPayload('<html>not json</html>')).toEqual([])
  })

  it('returns empty when data[] is absent', () => {
    expect(parseModelsPayload(JSON.stringify({ models: [] }))).toEqual([])
  })
})

describe('extractServerMessage', () => {
  it('extracts the vendor error message', () => {
    const raw = '{"type":"error","error":{"type":"authorized_error","message":"invalid api key (2049)"}}'
    expect(extractServerMessage(raw)).toBe('invalid api key (2049)')
  })

  it('extracts unknown-model text from single quotes', () => {
    const raw = "invalid params, unknown model 'minimax-m3.0' (2013)"
    expect(extractServerMessage(raw)).toBe("unknown model 'minimax-m3.0' (2013)")
  })

  it('returns undefined when nothing matches', () => {
    expect(extractServerMessage('plain failure')).toBeUndefined()
  })
})

describe('checkModelAgainstCatalog', () => {
  const catalog = ['MiniMax-M3', 'MiniMax-M3.1-Flash', 'MiniMax-M2.7']

  it('accepts a model present in the catalog', () => {
    expect(checkModelAgainstCatalog('MiniMax-M3', catalog).ok).toBe(true)
  })

  it('rejects a model absent from the catalog (openai-compatible)', () => {
    const result = checkModelAgainstCatalog('MiniMax-M3.0', catalog, 'openai-completions')
    expect(result.ok).toBe(false)
    expect(result.reason).toBe('not-listed')
  })

  it('does not block unknown models on anthropic-compatible endpoints', () => {
    // 实测：请求 MiniMax-M3.0 → 200，且实际返回 model=MiniMax-M3.1-Flash（静默归一化）
    const result = checkModelAgainstCatalog('MiniMax-M3.0', catalog, 'anthropic-messages')
    expect(result.ok).toBe(true)
  })

  it('does not block when the catalog is unknown', () => {
    expect(checkModelAgainstCatalog('anything', [], 'openai-completions').ok).toBe(true)
    expect(checkModelAgainstCatalog('anything', null, 'openai-completions').ok).toBe(true)
  })

  it('does not block an empty model', () => {
    expect(checkModelAgainstCatalog('', catalog).ok).toBe(true)
    expect(checkModelAgainstCatalog(undefined, catalog).ok).toBe(true)
  })
})
