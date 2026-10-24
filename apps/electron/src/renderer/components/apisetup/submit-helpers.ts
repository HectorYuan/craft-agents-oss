import type { CustomEndpointApi, CustomEndpointConfig } from '@config/llm-connections'
import { PROVIDER_PRESETS } from '@config/provider-presets'

export type PresetKey = string

/**
 * 预设的最小形状（GUI 侧 Preset 与之结构兼容）。
 */
export interface EnginePresetView {
  key: PresetKey
  label: string
  url: string
  placeholder?: string
  /** 只在 Pi SDK 路径可用（Anthropic/Claude 路径隐藏） */
  piOnly?: boolean
}

/**
 * 引擎真相源下发的预设（2026-10-24 P3 / P6）。
 *
 * 真相源 = 父仓 specs/providers.yaml，生成物 = packages/shared/src/config/provider-presets.ts
 * （由 scripts/sync_provider_registry.py 生成，勿手改）。
 *
 * 为什么不再在 GUI 里硬编码端点副本：minimax 的端点语义（国际站 / 国内站 /
 * Anthropic 兼容变体）历史上就在 GUI 与引擎之间漂移过 —— GUI 只有 openai 兼容的
 * 两个预设，引擎却已注册 anthropic 变体 ⇒ 用户选不到（2026-10-24 P6 的由来）。
 *
 * 合并规则：
 *   ① 同名条目以**真相源**为准（label / url / placeholder / piOnly）；
 *   ② 真相源新增、GUI 侧还没有的条目**追加**在引擎区块末尾（不打断 GUI 专有
 *      预设的相对顺序）；
 *   ③ 纯 GUI 专有的预设（groq / mistral / xai / cerebras / zai / huggingface /
 *      openrouter / vercel / manifest / bedrock / azure / kimi-coding / custom）
 *      保持本地定义 —— 它们不在引擎注册表里。
 */
const ENGINE_PRESET_BY_KEY = new Map(PROVIDER_PRESETS.map(p => [p.key, p]))

export function mergeEnginePresets(local: EnginePresetView[]): EnginePresetView[] {
  const merged: EnginePresetView[] = []
  const seen = new Set<string>()
  let lastEngineIndex = -1
  for (const p of local) {
    const g = ENGINE_PRESET_BY_KEY.get(p.key)
    if (g) {
      merged.push({
        key: g.key,
        label: g.label,
        url: g.baseUrl,
        placeholder: g.placeholder,
        piOnly: g.piOnly,
      })
      seen.add(g.key)
      lastEngineIndex = merged.length - 1
    } else {
      merged.push(p)
    }
  }
  const extra = PROVIDER_PRESETS.filter(p => !seen.has(p.key)).map(p => ({
    key: p.key,
    label: p.label,
    url: p.baseUrl,
    placeholder: p.placeholder,
    piOnly: p.piOnly,
  }))
  merged.splice(lastEngineIndex + 1, 0, ...extra)
  return merged
}

/**
 * Preset keys that are regional variants of a canonical Pi auth provider.
 * The Pi SDK recognizes both 'minimax' and 'minimax-cn' as separate providers
 * with distinct base URLs (api.minimax.io vs api.minimaxi.com), so only
 * 'minimax-global' needs aliasing — 'minimax-cn' maps 1:1 to the Pi SDK provider.
 */
const PI_AUTH_PROVIDER_ALIASES: Record<string, string> = {
  'minimax-global': 'minimax',
}

export function resolvePiAuthProviderForSubmit(
  activePreset: PresetKey,
  lastNonCustomPreset: PresetKey | null
): string | undefined {
  if (activePreset === 'custom') {
    // Pi SDK needs a provider hint for auth header formatting even when
    // the URL is user-provided — default to anthropic as the safest baseline.
    const resolved = lastNonCustomPreset && lastNonCustomPreset !== 'custom'
      ? lastNonCustomPreset
      : 'anthropic'
    return PI_AUTH_PROVIDER_ALIASES[resolved] ?? resolved
  }

  return PI_AUTH_PROVIDER_ALIASES[activePreset] ?? activePreset
}

export function resolvePresetStateForBaseUrlChange(params: {
  matchedPreset: PresetKey
  activePreset: PresetKey
  activePresetHasEmptyUrl: boolean
  lastNonCustomPreset: PresetKey | null
}): { activePreset: PresetKey; lastNonCustomPreset: PresetKey | null } {
  const { matchedPreset, activePreset, activePresetHasEmptyUrl, lastNonCustomPreset } = params

  if (matchedPreset !== 'custom') {
    return {
      activePreset: matchedPreset,
      lastNonCustomPreset: matchedPreset,
    }
  }

  if (activePresetHasEmptyUrl) {
    return {
      activePreset,
      lastNonCustomPreset,
    }
  }

  return {
    activePreset: 'custom',
    lastNonCustomPreset,
  }
}

/**
 * Resolve the customEndpoint + piAuthProvider payload at submit time.
 *
 * Three submit branches:
 *  - branded openai-compat preset (e.g. Manifest)  → pinned to openai-completions
 *  - generic custom preset with a base URL         → honors the protocol toggle
 *  - everything else                               → no customEndpoint, passthrough piAuth
 */
export function resolveCustomEndpointPayload(params: {
  activePreset: PresetKey
  baseUrl: string
  customApi: CustomEndpointApi
  brandedOpenAiCompatPresets: ReadonlySet<string>
  fallbackPiAuthProvider: string | undefined
}): {
  customEndpoint: CustomEndpointConfig | undefined
  piAuthProvider: string | undefined
} {
  const { activePreset, baseUrl, customApi, brandedOpenAiCompatPresets, fallbackPiAuthProvider } = params

  const isBrandedOpenAiCompat = brandedOpenAiCompatPresets.has(activePreset) && !!baseUrl
  const isCustomEndpoint = (activePreset === 'custom' && !!baseUrl) || isBrandedOpenAiCompat
  const effectiveApi: CustomEndpointApi = isBrandedOpenAiCompat ? 'openai-completions' : customApi

  return {
    customEndpoint: isCustomEndpoint ? { api: effectiveApi } : undefined,
    piAuthProvider: isCustomEndpoint
      ? (effectiveApi === 'anthropic-messages' ? 'anthropic' : 'openai')
      : fallbackPiAuthProvider,
  }
}
