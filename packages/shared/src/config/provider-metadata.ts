/**
 * Provider metadata for user-facing error messages and recovery actions.
 * Maps provider identifiers to their status pages and dashboards.
 */

export interface ProviderMetadata {
  /** Display name (e.g., "Anthropic", "OpenAI") */
  name: string
  /** Provider status page URL */
  statusPageUrl?: string
  /** Provider dashboard/billing URL */
  dashboardUrl?: string
}

/**
 * Metadata for known providers.
 * Keys are piAuthProvider values + 'anthropic' for direct API connections.
 */
const PROVIDER_METADATA: Record<string, ProviderMetadata> = {
  anthropic: {
    name: 'Anthropic',
    statusPageUrl: 'https://status.anthropic.com',
    dashboardUrl: 'https://console.anthropic.com',
  },
  openai: {
    name: 'OpenAI',
    statusPageUrl: 'https://status.openai.com',
    dashboardUrl: 'https://platform.openai.com',
  },
  google: {
    name: 'Google AI Studio',
    statusPageUrl: 'https://status.cloud.google.com',
    dashboardUrl: 'https://aistudio.google.com',
  },
  'amazon-bedrock': {
    name: 'Amazon Bedrock',
    statusPageUrl: 'https://health.aws.amazon.com',
    dashboardUrl: 'https://console.aws.amazon.com/bedrock',
  },
  'google-vertex': {
    name: 'Google Vertex AI',
    statusPageUrl: 'https://status.cloud.google.com',
    dashboardUrl: 'https://console.cloud.google.com/vertex-ai',
  },
  'github-copilot': {
    name: 'GitHub Copilot',
    statusPageUrl: 'https://www.githubstatus.com',
    dashboardUrl: 'https://github.com/settings/copilot',
  },
  openrouter: {
    name: 'OpenRouter',
    dashboardUrl: 'https://openrouter.ai/settings',
  },
  groq: {
    name: 'Groq',
    statusPageUrl: 'https://status.groq.com',
    dashboardUrl: 'https://console.groq.com',
  },
  mistral: {
    name: 'Mistral',
    dashboardUrl: 'https://console.mistral.ai',
  },
  deepseek: {
    name: 'DeepSeek',
    dashboardUrl: 'https://platform.deepseek.com',
  },
  // ─── 2026-10-06 国产补全 ───
  mimo: {
    name: 'Mimo',
    dashboardUrl: 'https://api.xiaomimimo.com/dashboard',
  },
  qwen: {
    name: '通义千问',
    dashboardUrl: 'https://dashscope.console.aliyun.com',
  },
  volc: {
    name: '火山方舟（豆包）',
    statusPageUrl: 'https://status.volcengine.com',
    dashboardUrl: 'https://console.volcengine.com/ark',
  },
  'moonshot-cn': {
    name: 'Kimi (Moonshot)',
    dashboardUrl: 'https://platform.moonshot.cn',
  },
  'moonshotai-cn': {
    name: 'Kimi (Moonshot CN)',
    dashboardUrl: 'https://platform.moonshot.cn',
  },
  minimax: {
    name: 'MiniMax',
    statusPageUrl: 'https://status.minimaxi.com',
    dashboardUrl: 'https://api.minimaxi.com/user-center/basic-information',
  },
  'minimax-cn': {
    name: 'MiniMax CN',
    dashboardUrl: 'https://api.minimax.cn/user-center/basic-information',
  },
  glm: {
    name: '智谱 GLM',
    dashboardUrl: 'https://open.bigmodel.cn/console',
  },
  xai: {
    name: 'xAI',
    dashboardUrl: 'https://console.x.ai',
  },
}

/**
 * Look up provider metadata by provider type and optional piAuthProvider.
 *
 * For direct Anthropic connections: getProviderMetadata('anthropic')
 * For Pi connections: getProviderMetadata('pi', 'openai') or getProviderMetadata('pi', 'amazon-bedrock')
 */
export function getProviderMetadata(
  providerType: string,
  piAuthProvider?: string,
): ProviderMetadata | undefined {
  if (providerType === 'anthropic') {
    return PROVIDER_METADATA.anthropic
  }
  if (piAuthProvider) {
    return PROVIDER_METADATA[piAuthProvider]
  }
  return undefined
}

/**
 * Get just the display name for a provider, with a fallback.
 */
export function getProviderDisplayName(
  providerType: string,
  piAuthProvider?: string,
): string {
  return getProviderMetadata(providerType, piAuthProvider)?.name ?? 'AI provider'
}
