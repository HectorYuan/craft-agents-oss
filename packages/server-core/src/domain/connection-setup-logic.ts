/**
 * Connection Setup Logic
 *
 * Pure functions extracted from ipc.ts for testability.
 * No dependency on ipcMain, sessionManager, credential manager, or file I/O.
 */

import type { ModelDefinition } from '@craft-agent/shared/config/models'
import {
  type LlmConnection,
  type CustomEndpointApi,
  getDefaultModelsForConnection,
  getDefaultModelForConnection,
  defaultMidStreamBehavior,
} from '@craft-agent/shared/config'

// ============================================================
// Error Parsing
// ============================================================

/**
 * 探活失败的上下文（用于把「真实原因」还原出来）。
 *
 * 2026-10-22 用户报障：探活失败一律显示 "Invalid API key"，但实测 MiniMax 的
 * 失败有两类完全不同的原因，混成一句话 ⇒ 用户换 key / 改端点都无效：
 *   • HTTP 401  invalid api key (2049)          ← key 无效**或**端点区域不对
 *   • HTTP 400  unknown model 'minimax-m3.0'    ← 型号 id 线上不存在
 */
export interface ConnectionTestErrorContext {
  /** 本次探活实际使用的端点（用于把 host 写进错误信息） */
  baseUrl?: string
  /** 本次探活实际使用的型号（用于把型号写进错误信息） */
  model?: string
}

/** 取端点 host（用于告诉用户「打的是哪台」） */
function _endpointHost(baseUrl?: string): string | undefined {
  if (!baseUrl?.trim()) return undefined
  try {
    return new URL(baseUrl.trim()).host
  } catch {
    return undefined
  }
}

/** 取厂商错误体里最能说明问题的一句原文 */
function _serverDetail(msg: string): string | undefined {
  const quoted = msg.match(/"message"\s*:\s*"([^"]+)"/)
  if (quoted?.[1]) return quoted[1]
  const single = msg.match(/'([^']*(?:model|key)[^']*)'/i)
  if (single?.[1]) return single[1]
  return undefined
}

/** 取 HTTP 状态码 */
function _statusOf(msg: string): number | undefined {
  const m = msg.match(/\b(4\d\d|5\d\d)\b/)
  return m ? Number(m[1]) : undefined
}

/**
 * Parse an error message from a connection test into a user-friendly string.
 *
 * 保真原则（2026-10-22）：**不把不同原因压成同一句话**。
 * 错误信息里必须能看到 ① HTTP 状态 ② 实际端点 host ③ 厂商原文。
 */
export function parseTestConnectionError(msg: string, context?: ConnectionTestErrorContext): string {
  const lower = msg.toLowerCase()

  if (lower.includes('econnrefused') || lower.includes('enotfound') || lower.includes('fetch failed')) {
    return 'Cannot connect to API server. Check the URL and ensure the server is running.'
  }
  if (lower.includes('no api key found for')) {
    return 'Provider mismatch during setup. Select a provider preset in ZenSkill Backend API Key mode, or use Anthropic API Key mode for arbitrary compatible endpoints.'
  }
  // 型号错（400/404 + model）先于认证错判：厂商错误体里常常同时出现 model 字样，
  // 但根因是型号 id 不存在，换 key 毫无意义。
  if (
    (lower.includes('400') || lower.includes('404')) &&
    (lower.includes('model') || lower.includes('not have model'))
  ) {
    const parts: string[] = ['Model not found']
    if (context?.model) parts.push(`: ${context.model}`)
    const status = _statusOf(msg)
    if (status) parts.push(`(HTTP ${status})`)
    const host = _endpointHost(context?.baseUrl)
    if (host) parts.push(`· endpoint: ${host}`)
    const detail = _serverDetail(msg)
    if (detail) parts.push(`· server: ${detail}`)
    parts.push('· Refresh the model list from the provider instead of typing a model id by hand.')
    return parts.join(' ')
  }
  if (lower.includes('401') || lower.includes('unauthorized') || lower.includes('authentication')) {
    const parts: string[] = ['Invalid API key']
    const status = _statusOf(msg)
    if (status) parts.push(`(HTTP ${status})`)
    const host = _endpointHost(context?.baseUrl)
    if (host) {
      parts.push(`· endpoint: ${host}`)
      parts.push('· API keys are region-bound for many providers — check that this endpoint matches the key’s region.')
    }
    const detail = _serverDetail(msg)
    if (detail) parts.push(`· server: ${detail}`)
    return parts.join(' ')
  }
  if (lower.includes('404')) {
    return 'API endpoint not found. Check the URL.'
  }
  if (lower.includes('429') || lower.includes('rate limit')) {
    return 'Rate limit exceeded. Please try again.'
  }
  if (lower.includes('403')) {
    return 'API key does not have permission to access this resource'
  }

  return msg.slice(0, 300)
}

/**
 * Setup test input validation. Pi custom-endpoint routing removed —
 * all providers are served by the zenskill engine.
 */
export function validateSetupTestInput(_params: {
  provider: 'anthropic' | 'zenskill'
  baseUrl?: string
}): { valid: true } | { valid: false; error: string } {
  return { valid: true }
}

/**
 * Returns true when a URL points to local loopback.
 * Used to permit keyless setup tests for local model runtimes (e.g. Ollama).
 */
export function isLoopbackBaseUrl(baseUrl?: string): boolean {
  if (!baseUrl?.trim()) return false
  try {
    const hostname = new URL(baseUrl.trim()).hostname
    const normalizedHostname = hostname.startsWith('[') && hostname.endsWith(']')
      ? hostname.slice(1, -1)
      : hostname
    return normalizedHostname === 'localhost' || normalizedHostname === '127.0.0.1' || normalizedHostname === '::1'
  } catch {
    return false
  }
}

/**
 * Setup tests require API keys for non-local endpoints, but local loopback
 * endpoints may be keyless.
 */
export function setupTestRequiresApiKey(baseUrl?: string): boolean {
  return !isLoopbackBaseUrl(baseUrl)
}

/**
 * Decide how a custom OpenAI/Anthropic-compatible endpoint should be persisted.
 *
 * - Loopback URL with no credential → keyless local model (Ollama, LM Studio).
 * - Loopback URL *with* a credential → real local OpenAI-compat server (vLLM, LiteLLM, etc.);
 *   must be treated like a remote custom endpoint so `piAuthProvider` is set, otherwise
 *   `getPiAuth()` returns null at runtime and chat requests fail with 401 (#636).
 * - Remote URL → always keyed with provider hint for the correct icon.
 *
 * Pure: caller spreads the result into the connection updates patch.
 */
export function resolveCustomEndpointSetup(input: {
  baseUrl: string | undefined
  credential: string | undefined
  customEndpointApi: CustomEndpointApi
}): {
  authType: Extract<LlmConnection['authType'], 'none' | 'api_key_with_endpoint'>
  name?: 'Local Model'
  piAuthProvider?: 'openai' | 'anthropic'
} {
  const isKeylessLoopback = isLoopbackBaseUrl(input.baseUrl) && !input.credential
  if (isKeylessLoopback) {
    return { authType: 'none', name: 'Local Model' }
  }
  return {
    authType: 'api_key_with_endpoint',
    piAuthProvider: input.customEndpointApi === 'anthropic-messages' ? 'anthropic' : 'openai',
  }
}

// ============================================================
// Built-in Connection Templates
// ============================================================

/**
 * Built-in connection templates for the onboarding flow.
 * Each template defines the default configuration for a known connection slug.
 */
export const BUILT_IN_CONNECTION_TEMPLATES: Record<string, {
  name: string | ((hasCustomEndpoint: boolean) => string)
  providerType: LlmConnection['providerType'] | ((hasCustomEndpoint: boolean) => LlmConnection['providerType'])
  authType: LlmConnection['authType'] | ((hasCustomEndpoint: boolean) => LlmConnection['authType'])
  piAuthProvider?: string
}> = {
  'anthropic-api': {
    name: (h) => h ? 'Custom Anthropic-Compatible' : 'Anthropic (API Key)',
    providerType: (h) => h ? 'pi_compat' : 'anthropic',
    authType: (h) => h ? 'api_key_with_endpoint' : 'api_key',
  },
  'claude-max': {
    name: 'Claude Max',
    providerType: 'anthropic',
    authType: 'oauth',
  },
  'chatgpt-plus': {
    name: 'ChatGPT Plus',
    providerType: 'pi',
    authType: 'oauth',
    piAuthProvider: 'openai-codex',
  },
  'github-copilot': {
    name: 'GitHub Copilot',
    providerType: 'pi',
    authType: 'oauth',
    piAuthProvider: 'github-copilot',
  },
  'pi-api-key': {
    name: 'ZenSkill Backend (API Key)',
    providerType: 'pi',
    authType: 'api_key',
    // piAuthProvider set dynamically from setup.piAuthProvider
  },
}

// ============================================================
// Pi Auth Provider Display Names
// ============================================================

const PI_AUTH_PROVIDER_DISPLAY_NAMES: Record<string, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  'openai-codex': 'OpenAI',
  google: 'Google AI Studio',
  openrouter: 'OpenRouter',
  'azure-openai-responses': 'Azure OpenAI',
  'amazon-bedrock': 'Amazon Bedrock',
  groq: 'Groq',
  mistral: 'Mistral',
  xai: 'xAI',
  cerebras: 'Cerebras',
  zai: 'z.ai',
  huggingface: 'Hugging Face',
  minimax: 'Minimax',
  'minimax-cn': 'Minimax CN',
  'kimi-coding': 'Kimi (Coding)',
  'vercel-ai-gateway': 'Vercel AI Gateway',
}

/** Get a human-readable display name for a Pi auth provider key */
export function piAuthProviderDisplayName(piAuthProvider: string): string | null {
  return PI_AUTH_PROVIDER_DISPLAY_NAMES[piAuthProvider] ?? null
}

// ============================================================
// Connection Creation
// ============================================================

/**
 * Create an LLM connection configuration from a connection slug.
 * Uses built-in templates for known slugs, throws for unknown slugs
 * (custom connections are created through the settings UI).
 */
export function createBuiltInConnection(slug: string, baseUrl?: string | null): LlmConnection {
  // Try exact match first, then strip numeric suffix for derived slugs (e.g. 'anthropic-api-2' → 'anthropic-api')
  const baseSlug = slug.replace(/-\d+$/, '')
  const template = BUILT_IN_CONNECTION_TEMPLATES[slug] ?? BUILT_IN_CONNECTION_TEMPLATES[baseSlug]
  if (!template) {
    throw new Error(`Unknown built-in connection slug: ${slug}. Custom connections should be created through settings.`)
  }

  const hasCustomEndpoint = !!baseUrl
  const providerType = typeof template.providerType === 'function'
    ? template.providerType(hasCustomEndpoint)
    : template.providerType
  const authType = typeof template.authType === 'function'
    ? template.authType(hasCustomEndpoint)
    : template.authType
  let name = typeof template.name === 'function'
    ? template.name(hasCustomEndpoint)
    : template.name

  // Append suffix number to name for derived connections (e.g. 'anthropic-api-2' → 'Anthropic (API Key) 2')
  const suffixMatch = slug.match(/-(\d+)$/)
  if (suffixMatch && !BUILT_IN_CONNECTION_TEMPLATES[slug]) {
    name = `${name} ${suffixMatch[1]}`
  }

  return {
    slug,
    name,
    providerType,
    authType,
    models: getDefaultModelsForConnection(providerType, template.piAuthProvider),
    defaultModel: getDefaultModelForConnection(providerType, template.piAuthProvider),
    modelSelectionMode: providerType === 'pi' ? 'automaticallySyncedFromProvider' : undefined,
    piAuthProvider: template.piAuthProvider,
    midStreamBehavior: defaultMidStreamBehavior(providerType),
    createdAt: Date.now(),
  }
}

// ============================================================
// Model Validation
// ============================================================

/**
 * Validate that the default model exists in the provided model list.
 * Handles both string and ModelDefinition model entries.
 *
 * This was extracted from inline logic in the setupLlmConnection IPC handler
 * to fix a bug where Array.includes() compared strings against ModelDefinition
 * objects, always returning false for Pi connections.
 */
export function validateModelList(
  models: Array<ModelDefinition | string>,
  defaultModel: string | undefined,
): { valid: boolean; error?: string; resolvedDefaultModel?: string } {
  if (!models || models.length === 0) {
    return { valid: true }
  }

  const modelIds = models.map(m => typeof m === 'string' ? m : m.id)

  if (defaultModel && !modelIds.includes(defaultModel)) {
    return {
      valid: false,
      error: `Default model "${defaultModel}" is not in the provided model list.`,
    }
  }

  if (!defaultModel) {
    const firstModel = models[0]
    const firstModelId = typeof firstModel === 'string' ? firstModel : firstModel!.id
    return {
      valid: true,
      resolvedDefaultModel: firstModelId,
    }
  }

  return { valid: true }
}
