import { describe, expect, it } from 'bun:test'
import {
  mergeEnginePresets,
  resolveCustomEndpointPayload,
  resolvePiAuthProviderForSubmit,
  resolvePresetStateForBaseUrlChange,
} from '../submit-helpers'
import { pickTierDefaults, resolveTierModels } from '../tier-models'

const MODELS = [
  { id: 'pi/zai-best', name: 'Best', costInput: 10, costOutput: 20, contextWindow: 200000, reasoning: true },
  { id: 'pi/zai-balanced', name: 'Balanced', costInput: 5, costOutput: 10, contextWindow: 200000, reasoning: true },
  { id: 'pi/zai-fast', name: 'Fast', costInput: 1, costOutput: 2, contextWindow: 128000, reasoning: false },
]

describe('ApiKeyInput tier hydration helpers', () => {
  it('resolveTierModels keeps saved tier selections when all are valid', () => {
    const saved = ['pi/zai-fast', 'pi/zai-balanced', 'pi/zai-best']
    const resolved = resolveTierModels(MODELS, saved)

    expect(resolved).toEqual({
      best: 'pi/zai-fast',
      default_: 'pi/zai-balanced',
      cheap: 'pi/zai-best',
    })
  })

  it('resolveTierModels preserves duplicate tiers when saved models are valid', () => {
    const saved = ['pi/zai-best', 'pi/zai-best', 'pi/zai-fast']
    const resolved = resolveTierModels(MODELS, saved)

    expect(resolved).toEqual({
      best: 'pi/zai-best',
      default_: 'pi/zai-best',
      cheap: 'pi/zai-fast',
    })
  })

  it('resolveTierModels falls back per-slot for invalid/missing saved values', () => {
    const resolved = resolveTierModels(MODELS, ['pi/zai-best', 'pi/not-real'])
    const defaults = pickTierDefaults(MODELS)

    expect(resolved).toEqual({
      best: 'pi/zai-best',
      default_: defaults.default_,
      cheap: defaults.cheap,
    })
  })
})

describe('resolvePiAuthProviderForSubmit', () => {
  it('preserves the last non-custom provider when custom endpoint mode is selected', () => {
    expect(resolvePiAuthProviderForSubmit('custom', 'openai')).toBe('openai')
  })

  it('defaults custom endpoint mode to anthropic routing when none was selected yet', () => {
    expect(resolvePiAuthProviderForSubmit('custom', null)).toBe('anthropic')
  })

  it('passes through non-custom presets unchanged', () => {
    expect(resolvePiAuthProviderForSubmit('google', 'anthropic')).toBe('google')
  })
})

describe('resolvePresetStateForBaseUrlChange', () => {
  it('updates the remembered provider when the typed URL matches a known preset', () => {
    expect(resolvePresetStateForBaseUrlChange({
      matchedPreset: 'openrouter',
      activePreset: 'custom',
      activePresetHasEmptyUrl: true,
      lastNonCustomPreset: 'anthropic',
    })).toEqual({
      activePreset: 'openrouter',
      lastNonCustomPreset: 'openrouter',
    })
  })

  it('preserves provider routing when editing a provider with an empty default URL', () => {
    expect(resolvePresetStateForBaseUrlChange({
      matchedPreset: 'custom',
      activePreset: 'azure-openai-responses',
      activePresetHasEmptyUrl: true,
      lastNonCustomPreset: 'azure-openai-responses',
    })).toEqual({
      activePreset: 'azure-openai-responses',
      lastNonCustomPreset: 'azure-openai-responses',
    })
  })

  it('falls back to custom while keeping the most recent matched provider', () => {
    expect(resolvePresetStateForBaseUrlChange({
      matchedPreset: 'custom',
      activePreset: 'openrouter',
      activePresetHasEmptyUrl: false,
      lastNonCustomPreset: 'openrouter',
    })).toEqual({
      activePreset: 'custom',
      lastNonCustomPreset: 'openrouter',
    })
  })
})

describe('resolveCustomEndpointPayload', () => {
  const BRANDED = new Set(['manifest'])

  it('routes branded openai-compat presets through openai-completions regardless of toggle', () => {
    expect(resolveCustomEndpointPayload({
      activePreset: 'manifest',
      baseUrl: 'https://app.manifest.build/v1',
      customApi: 'anthropic-messages',
      brandedOpenAiCompatPresets: BRANDED,
      fallbackPiAuthProvider: undefined,
    })).toEqual({
      customEndpoint: { api: 'openai-completions' },
      piAuthProvider: 'openai',
    })
  })

  it('honors the protocol toggle for the generic custom preset', () => {
    expect(resolveCustomEndpointPayload({
      activePreset: 'custom',
      baseUrl: 'https://my-endpoint.example.com',
      customApi: 'anthropic-messages',
      brandedOpenAiCompatPresets: BRANDED,
      fallbackPiAuthProvider: undefined,
    })).toEqual({
      customEndpoint: { api: 'anthropic-messages' },
      piAuthProvider: 'anthropic',
    })
  })

  it('returns no customEndpoint for a standard preset, passing through the fallback piAuth', () => {
    expect(resolveCustomEndpointPayload({
      activePreset: 'openrouter',
      baseUrl: 'https://openrouter.ai/api/v1',
      customApi: 'openai-completions',
      brandedOpenAiCompatPresets: BRANDED,
      fallbackPiAuthProvider: 'openrouter',
    })).toEqual({
      customEndpoint: undefined,
      piAuthProvider: 'openrouter',
    })
  })

  it('treats branded preset with empty URL as non-custom (no customEndpoint)', () => {
    expect(resolveCustomEndpointPayload({
      activePreset: 'manifest',
      baseUrl: '',
      customApi: 'openai-completions',
      brandedOpenAiCompatPresets: BRANDED,
      fallbackPiAuthProvider: undefined,
    })).toEqual({
      customEndpoint: undefined,
      piAuthProvider: undefined,
    })
  })
})

// ── 引擎真相源优先的预设合并（2026-10-24 P3 / P6）────────────────────
//
// 背景：minimax 的端点语义（国际站 / 国内站 / Anthropic 兼容变体）历史上在
// GUI 与引擎之间漂移过 —— GUI 只硬编码了 openai 兼容的两个预设，引擎却已注册
// anthropic 变体 ⇒ 用户选不到。修法：GUI 的同名条目以真相源为准，真相源新增
// 的条目自动出现（生成物 = packages/shared/src/config/provider-presets.ts）。

describe('mergeEnginePresets —— 引擎真相源优先', () => {
  it('同名条目以真相源为准（端点 / 标签 / 占位符 / piOnly）', () => {
    const merged = mergeEnginePresets([
      { key: 'minimax-cn', label: '本地写死的旧标签', url: 'https://old.example.com/v1', placeholder: '旧占位', piOnly: false },
    ])
    const cn = merged.find(p => p.key === 'minimax-cn')
    expect(cn?.url).toBe('https://api.minimaxi.com/v1')
    expect(cn?.label).not.toBe('本地写死的旧标签')
    expect(cn?.piOnly).toBe(true) // openai 兼容 ⇒ Pi 专属（真相源口径）
  })

  it('真相源新增的预设自动出现：minimax 的两个 Anthropic 兼容变体（P6）', () => {
    const merged = mergeEnginePresets([{ key: 'anthropic', label: 'Anthropic', url: 'https://api.anthropic.com' }])
    const cn = merged.find(p => p.key === 'minimax-cn-anthropic')
    expect(cn).toBeDefined()
    expect(cn?.url).toBe('https://api.minimax.cn/anthropic')
    expect(cn?.piOnly).toBe(false) // Anthropic 路径可用
    const global = merged.find(p => p.key === 'minimax-anthropic')
    expect(global?.url).toBe('https://api.minimax.io/anthropic')
  })

  it('GUI 专有预设原样保留（不在引擎注册表里的那些）', () => {
    const local = [
      { key: 'groq', label: 'Groq', url: 'https://api.groq.com/openai/v1' },
      { key: 'custom', label: 'Custom', url: '' },
    ]
    const merged = mergeEnginePresets(local)
    expect(merged.find(p => p.key === 'groq')).toEqual(local[0])
    expect(merged.find(p => p.key === 'custom')).toEqual(local[1])
  })

  it('新增条目插在引擎区块末尾，不打乱 GUI 专有预设的相对顺序', () => {
    const merged = mergeEnginePresets([
      { key: 'anthropic', label: 'Anthropic', url: 'https://api.anthropic.com' },
      { key: 'groq', label: 'Groq', url: 'https://api.groq.com/openai/v1' },
      { key: 'manifest', label: 'Manifest', url: 'https://app.manifest.build/v1' },
    ])
    const keys = merged.map(p => p.key)
    expect(keys.indexOf('groq')).toBeLessThan(keys.indexOf('manifest'))
    // 引擎区块（anthropic 之后）里追加了真相源新增项
    expect(keys.indexOf('minimax-cn-anthropic')).toBeGreaterThan(keys.indexOf('anthropic'))
    expect(keys.indexOf('minimax-cn-anthropic')).toBeLessThan(keys.indexOf('groq'))
  })
})
