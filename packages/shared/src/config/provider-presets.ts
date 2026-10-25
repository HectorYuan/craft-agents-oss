/* eslint-disable */
/**
 * ⚠️ 本文件由 scripts/sync_provider_registry.py 自动生成
 *    （真相源：specs/providers.yaml）——**不要手改**。
 *    改动请改 specs/providers.yaml 后重新生成。
 */

/** 引擎支持的端点协议 */
export type ProviderApi = 'openai-completions' | 'anthropic-messages'

/** GUI 建连向导的预设（真相源 gui_presets 段） */
export interface ProviderPreset {
  /** 预设 key（GUI 侧标识） */
  key: string
  /** 引擎 provider 名（唯一真相源） */
  provider: string
  /** 端点基址 */
  baseUrl: string
  /** 展示名 */
  label: string
  /** 端点协议 */
  api: ProviderApi
  /** 输入框占位符 */
  placeholder: string
  /** 只在 Pi SDK 路径可用（Anthropic/Claude 路径隐藏） */
  piOnly: boolean
  /** 区域：cn / global（空串＝不适用） */
  region: string
  /** 厂商族（minimax / moonshot / …），用于「同族跨区域端点」诊断 */
  vendorFamily: string
}

/** 静态型号目录（真相源 catalog 段） */
export interface ProviderModel {
  name: string
  display: string
  tier: string
  capabilities: string[]
  contextWindow: number
}

/** 单个 provider 的目录条目 */
export interface ProviderCatalogEntry {
  provider: string
  display: string
  baseUrl: string
  api: ProviderApi
  apiKeyEnv: string
  docsUrl: string
  tags: string[]
  region: string
  vendorFamily: string
  models: ProviderModel[]
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    key: 'deepseek',
    provider: 'deepseek',
    baseUrl: 'https://api.deepseek.com/v1',
    label: 'DeepSeek',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'qwen',
    provider: 'qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    label: '通义千问 (Qwen)',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'volc',
    provider: 'volc',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    label: '火山引擎 (豆包)',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'mimo',
    provider: 'mimo',
    baseUrl: 'https://api.xiaomimimo.com/v1',
    label: 'MiMo (小米)',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'glm',
    provider: 'glm',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    label: '智谱 GLM',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'moonshotai',
    provider: 'moonshot-global',
    baseUrl: 'https://api.moonshot.ai/v1',
    label: 'Moonshot AI',
    api: 'openai-completions',
    placeholder: 'Paste your key here...',
    piOnly: true,
    region: 'global',
    vendorFamily: 'moonshot',
  },
  {
    key: 'moonshotai-cn',
    provider: 'moonshot',
    baseUrl: 'https://api.moonshot.cn/v1',
    label: 'Moonshot AI (CN)',
    api: 'openai-completions',
    placeholder: 'Paste your key here...',
    piOnly: true,
    region: 'cn',
    vendorFamily: 'moonshot',
  },
  {
    key: 'minimax-global',
    provider: 'minimax',
    baseUrl: 'https://api.minimax.io/v1',
    label: 'Minimax Global',
    api: 'openai-completions',
    placeholder: 'Paste your key here...',
    piOnly: true,
    region: 'global',
    vendorFamily: 'minimax',
  },
  {
    key: 'minimax-cn',
    provider: 'minimax-cn',
    baseUrl: 'https://api.minimaxi.com/v1',
    label: 'Minimax CN',
    api: 'openai-completions',
    placeholder: 'Paste your key here...',
    piOnly: true,
    region: 'cn',
    vendorFamily: 'minimax',
  },
  {
    key: 'minimax-anthropic',
    provider: 'minimax-anthropic',
    baseUrl: 'https://api.minimax.io/anthropic',
    label: 'Minimax (Anthropic 兼容)',
    api: 'anthropic-messages',
    placeholder: 'Paste your key here...',
    piOnly: false,
    region: 'global',
    vendorFamily: 'minimax',
  },
  {
    key: 'minimax-cn-anthropic',
    provider: 'minimax-cn-anthropic',
    baseUrl: 'https://api.minimax.cn/anthropic',
    label: 'Minimax CN (Anthropic 兼容)',
    api: 'anthropic-messages',
    placeholder: 'Paste your key here...',
    piOnly: false,
    region: 'cn',
    vendorFamily: 'minimax',
  },
  {
    key: 'anthropic',
    provider: 'anthropic',
    baseUrl: 'https://api.anthropic.com',
    label: 'Anthropic',
    api: 'anthropic-messages',
    placeholder: 'sk-ant-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'openai',
    provider: 'openai',
    baseUrl: 'https://api.openai.com/v1',
    label: 'OpenAI',
    api: 'openai-completions',
    placeholder: 'sk-...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'google',
    provider: 'gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    label: 'Google AI Studio',
    api: 'openai-completions',
    placeholder: 'AIza...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
  {
    key: 'ollama',
    provider: 'ollama',
    baseUrl: 'http://localhost:11434/v1',
    label: 'Ollama (本地)',
    api: 'openai-completions',
    placeholder: 'Paste your key here...',
    piOnly: false,
    region: '',
    vendorFamily: '',
  },
]

export const PROVIDER_CATALOG: ProviderCatalogEntry[] = [
  {
    provider: 'deepseek',
    display: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    api: 'openai-completions',
    apiKeyEnv: 'DEEPSEEK_API_KEY',
    docsUrl: 'https://platform.deepseek.com/api-keys',
    tags: ['cloud'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'deepseek-chat',
        display: 'DeepSeek V3',
        tier: 'standard',
        capabilities: ['chat', 'coding'],
        contextWindow: 64000,
      },
      {
        name: 'deepseek-reasoner',
        display: 'DeepSeek R1',
        tier: 'premium',
        capabilities: ['reasoning', 'coding'],
        contextWindow: 64000,
      },
      {
        name: 'deepseek-v4-pro',
        display: 'DeepSeek V4 Pro',
        tier: 'premium',
        capabilities: ['reasoning', 'coding', 'analysis'],
        contextWindow: 128000,
      },
      {
        name: 'deepseek-v4-flash',
        display: 'DeepSeek V4 Flash',
        tier: 'standard',
        capabilities: ['chat', 'coding', 'reasoning'],
        contextWindow: 1000000,
      },
    ],
  },
  {
    provider: 'anthropic',
    display: 'Anthropic (Claude)',
    baseUrl: 'https://api.anthropic.com',
    api: 'anthropic-messages',
    apiKeyEnv: 'ANTHROPIC_API_KEY',
    docsUrl: 'https://console.anthropic.com/',
    tags: ['cloud'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'claude-sonnet-4-20250514',
        display: 'Claude Sonnet 4',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'reasoning', 'vision'],
        contextWindow: 200000,
      },
      {
        name: 'claude-3-5-sonnet-20241022',
        display: 'Claude 3.5 Sonnet',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'vision'],
        contextWindow: 200000,
      },
      {
        name: 'claude-3-5-haiku-20241022',
        display: 'Claude 3.5 Haiku',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 200000,
      },
      {
        name: 'claude-opus-4-20250514',
        display: 'Claude Opus 4',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'reasoning'],
        contextWindow: 200000,
      },
    ],
  },
  {
    provider: 'openai',
    display: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    api: 'openai-completions',
    apiKeyEnv: 'OPENAI_API_KEY',
    docsUrl: 'https://platform.openai.com/api-keys',
    tags: ['cloud'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'gpt-4o',
        display: 'GPT-4o',
        tier: 'premium',
        capabilities: ['chat', 'vision', 'coding'],
        contextWindow: 128000,
      },
      {
        name: 'gpt-4o-mini',
        display: 'GPT-4o Mini',
        tier: 'standard',
        capabilities: ['chat', 'vision'],
        contextWindow: 128000,
      },
      {
        name: 'gpt-4-turbo',
        display: 'GPT-4 Turbo',
        tier: 'premium',
        capabilities: ['chat', 'coding'],
        contextWindow: 128000,
      },
      {
        name: 'gpt-3.5-turbo',
        display: 'GPT-3.5 Turbo',
        tier: 'standard',
        capabilities: ['chat'],
        contextWindow: 16385,
      },
    ],
  },
  {
    provider: 'volc',
    display: '火山引擎 (豆包)',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    api: 'openai-completions',
    apiKeyEnv: 'ARK_API_KEY',
    docsUrl: 'https://console.volcengine.com/ark',
    tags: ['cloud'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'doubao-pro-32k',
        display: '豆包 Pro 32K',
        tier: 'premium',
        capabilities: ['chat', 'coding'],
        contextWindow: 32000,
      },
      {
        name: 'doubao-pro-128k',
        display: '豆包 Pro 128K',
        tier: 'premium',
        capabilities: ['chat', 'coding'],
        contextWindow: 128000,
      },
      {
        name: 'doubao-lite-32k',
        display: '豆包 Lite 32K',
        tier: 'standard',
        capabilities: ['chat'],
        contextWindow: 32000,
      },
    ],
  },
  {
    provider: 'qwen',
    display: '通义千问 (Qwen)',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api: 'openai-completions',
    apiKeyEnv: 'DASHSCOPE_API_KEY',
    docsUrl: 'https://help.aliyun.com/zh/model-studio/',
    tags: ['cloud'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'qwen-plus',
        display: 'Qwen Plus',
        tier: 'standard',
        capabilities: ['chat', 'coding'],
        contextWindow: 131072,
      },
      {
        name: 'qwen-max',
        display: 'Qwen Max',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'reasoning'],
        contextWindow: 32000,
      },
      {
        name: 'qwen-turbo',
        display: 'Qwen Turbo',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 131072,
      },
    ],
  },
  {
    provider: 'ollama',
    display: 'Ollama (本地)',
    baseUrl: 'http://localhost:11434/v1',
    api: 'openai-completions',
    apiKeyEnv: '',
    docsUrl: 'https://ollama.com',
    tags: ['local'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'llama3.2',
        display: 'Llama 3.2',
        tier: 'free',
        capabilities: ['chat', 'local'],
        contextWindow: 128000,
      },
      {
        name: 'qwen2.5',
        display: 'Qwen 2.5',
        tier: 'free',
        capabilities: ['chat', 'local'],
        contextWindow: 32000,
      },
      {
        name: 'deepseek-r1',
        display: 'DeepSeek R1 (本地)',
        tier: 'free',
        capabilities: ['reasoning', 'local'],
        contextWindow: 128000,
      },
    ],
  },
  {
    provider: 'moonshot',
    display: 'Moonshot (Kimi)',
    baseUrl: 'https://api.moonshot.cn/v1',
    api: 'openai-completions',
    apiKeyEnv: 'MOONSHOT_API_KEY',
    docsUrl: 'https://platform.moonshot.cn',
    tags: ['cloud', 'domestic'],
    region: 'cn',
    vendorFamily: 'moonshot',
    models: [
      {
        name: 'kimi-k2-0905-preview',
        display: 'Kimi K2 Preview',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'long-context'],
        contextWindow: 256000,
      },
      {
        name: 'kimi-k2-0711-preview',
        display: 'Kimi K2 0711',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'long-context'],
        contextWindow: 200000,
      },
    ],
  },
  {
    provider: 'moonshot-global',
    display: 'Moonshot Global (Kimi)',
    baseUrl: 'https://api.moonshot.ai/v1',
    api: 'openai-completions',
    apiKeyEnv: 'MOONSHOT_API_KEY_GLOBAL',
    docsUrl: 'https://platform.moonshot.ai',
    tags: ['cloud', 'overseas'],
    region: 'global',
    vendorFamily: 'moonshot',
    models: [
      {
        name: 'kimi-k2-0905-preview',
        display: 'Kimi K2 Preview (Global)',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'long-context'],
        contextWindow: 256000,
      },
    ],
  },
  {
    provider: 'minimax',
    display: 'MiniMax',
    baseUrl: 'https://api.minimax.io/v1',
    api: 'openai-completions',
    apiKeyEnv: 'MINIMAX_API_KEY',
    docsUrl: 'https://platform.minimax.io/user-center/basic-information',
    tags: ['cloud', 'overseas'],
    region: 'global',
    vendorFamily: 'minimax',
    models: [
      {
        name: 'MiniMax-M3',
        display: 'MiniMax M3',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'vision', 'coding', 'long-context', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M3.1-Flash',
        display: 'MiniMax M3.1 Flash',
        tier: 'standard',
        capabilities: ['chat', 'reasoning', 'coding', 'long-context', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7',
        display: 'MiniMax M2.7',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7-highspeed',
        display: 'MiniMax M2.7 Highspeed',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5',
        display: 'MiniMax M2.5',
        tier: 'premium',
        capabilities: ['chat', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5-highspeed',
        display: 'MiniMax M2.5 Highspeed',
        tier: 'standard',
        capabilities: ['chat'],
        contextWindow: 1000000,
      },
    ],
  },
  {
    provider: 'minimax-cn',
    display: 'MiniMax (CN)',
    baseUrl: 'https://api.minimaxi.com/v1',
    api: 'openai-completions',
    apiKeyEnv: 'MINIMAX_API_KEY_CN',
    docsUrl: 'https://platform.minimaxi.com/user-center/basic-information',
    tags: ['cloud', 'domestic'],
    region: 'cn',
    vendorFamily: 'minimax',
    models: [
      {
        name: 'MiniMax-M3',
        display: 'MiniMax M3 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'vision', 'coding', 'long-context', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M3.1-Flash',
        display: 'MiniMax M3.1 Flash (CN)',
        tier: 'standard',
        capabilities: ['chat', 'reasoning', 'coding', 'long-context', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7',
        display: 'MiniMax M2.7 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7-highspeed',
        display: 'MiniMax M2.7 Highspeed (CN)',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5',
        display: 'MiniMax M2.5 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5-highspeed',
        display: 'MiniMax M2.5 Highspeed (CN)',
        tier: 'standard',
        capabilities: ['chat'],
        contextWindow: 1000000,
      },
    ],
  },
  {
    provider: 'minimax-anthropic',
    display: 'MiniMax (Anthropic 兼容)',
    baseUrl: 'https://api.minimax.io/anthropic',
    api: 'anthropic-messages',
    apiKeyEnv: 'MINIMAX_API_KEY',
    docsUrl: 'https://platform.minimax.io/docs/guides/text-generation',
    tags: ['cloud', 'overseas'],
    region: 'global',
    vendorFamily: 'minimax',
    models: [
      {
        name: 'MiniMax-M3',
        display: 'MiniMax M3',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'vision', 'coding', 'long-context', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M3.1-Flash',
        display: 'MiniMax M3.1 Flash',
        tier: 'standard',
        capabilities: ['chat', 'reasoning', 'coding', 'long-context', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7',
        display: 'MiniMax M2.7',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7-highspeed',
        display: 'MiniMax M2.7 Highspeed',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5',
        display: 'MiniMax M2.5',
        tier: 'premium',
        capabilities: ['chat', 'multimodal'],
        contextWindow: 1000000,
      },
    ],
  },
  {
    provider: 'minimax-cn-anthropic',
    display: 'MiniMax (CN, Anthropic 兼容)',
    baseUrl: 'https://api.minimax.cn/anthropic',
    api: 'anthropic-messages',
    apiKeyEnv: 'MINIMAX_API_KEY_CN',
    docsUrl: 'https://platform.minimaxi.com/docs/guides/text-generation',
    tags: ['cloud', 'domestic'],
    region: 'cn',
    vendorFamily: 'minimax',
    models: [
      {
        name: 'MiniMax-M3',
        display: 'MiniMax M3 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'vision', 'coding', 'long-context', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M3.1-Flash',
        display: 'MiniMax M3.1 Flash (CN)',
        tier: 'standard',
        capabilities: ['chat', 'reasoning', 'coding', 'long-context', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7',
        display: 'MiniMax M2.7 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'reasoning', 'multimodal'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.7-highspeed',
        display: 'MiniMax M2.7 Highspeed (CN)',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 1000000,
      },
      {
        name: 'MiniMax-M2.5',
        display: 'MiniMax M2.5 (CN)',
        tier: 'premium',
        capabilities: ['chat', 'multimodal'],
        contextWindow: 1000000,
      },
    ],
  },
  {
    provider: 'glm',
    display: '智谱 GLM',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    api: 'openai-completions',
    apiKeyEnv: 'GLM_API_KEY',
    docsUrl: 'https://open.bigmodel.cn/console',
    tags: ['cloud', 'domestic'],
    region: '',
    vendorFamily: '',
    models: [
      {
        name: 'glm-4-plus',
        display: 'GLM-4 Plus',
        tier: 'premium',
        capabilities: ['chat', 'coding', 'reasoning'],
        contextWindow: 128000,
      },
      {
        name: 'glm-4-air',
        display: 'GLM-4 Air',
        tier: 'standard',
        capabilities: ['chat', 'fast'],
        contextWindow: 128000,
      },
      {
        name: 'glm-4-flash',
        display: 'GLM-4 Flash',
        tier: 'free',
        capabilities: ['chat', 'fast'],
        contextWindow: 128000,
      },
      {
        name: 'glm-4v-plus',
        display: 'GLM-4V Plus (Vision)',
        tier: 'premium',
        capabilities: ['chat', 'vision'],
        contextWindow: 128000,
      },
    ],
  },
]
