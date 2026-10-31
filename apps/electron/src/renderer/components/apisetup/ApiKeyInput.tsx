/**
 * ApiKeyInput - Reusable API key entry form control
 *
 * Renders a password input for the API key, a preset selector for Base URL,
 * and an optional Model override field.
 *
 * Does NOT include layout wrappers or action buttons — the parent
 * controls placement via the form ID ("api-key-form") for submit binding.
 *
 * Used in: Onboarding CredentialsStep, Settings API dialog
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Command as CommandPrimitive } from "cmdk"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  StyledDropdownMenuContent,
  StyledDropdownMenuItem,
} from "@/components/ui/styled-dropdown"
import { cn } from "@/lib/utils"
import { Check, ChevronDown, Eye, EyeOff, Loader2 } from "lucide-react"
import { pickTierDefaults, resolveTierModels, type PiModelInfo } from "./tier-models"
import {
  mergeEnginePresets,
  resolveCustomEndpointPayload,
  resolveEndpointProtocol,
  resolvePiAuthProviderForSubmit,
  resolvePresetStateForBaseUrlChange,
  type PresetKey,
} from "./submit-helpers"

import type { CustomEndpointApi, CustomEndpointConfig } from '@config/llm-connections'
import { PROVIDER_PRESETS } from '@config/provider-presets'
import type { LlmCatalogResult, RegionMismatchDiagnosis } from '@craft-agent/shared/protocol'

const DEFAULT_ENDPOINT_PROVIDERS = new Set(['anthropic', 'openai', 'pi', 'google'])

export type ApiKeyStatus = 'idle' | 'validating' | 'success' | 'error'

export type { CustomEndpointApi }

export interface ApiKeySubmitData {
  apiKey: string
  baseUrl?: string
  connectionDefaultModel?: string
  models?: string[]
  piAuthProvider?: string
  modelSelectionMode?: 'automaticallySyncedFromProvider' | 'userDefined3Tier'
  /** Custom endpoint protocol — set when user configures an arbitrary API endpoint */
  customEndpoint?: CustomEndpointConfig
  /** IAM credentials for Pi+Bedrock (piAuthProvider='amazon-bedrock') setup */
  iamCredentials?: {
    accessKeyId: string
    secretAccessKey: string
    sessionToken?: string
  }
  /** AWS region for Pi+Bedrock */
  awsRegion?: string
  /** Bedrock authentication method — determines auth type for Pi+Bedrock connections */
  bedrockAuthMethod?: 'iam_credentials' | 'environment'
}

export interface ApiKeyInputProps {
  /** Current validation status */
  status: ApiKeyStatus
  /** Error message to display when status is 'error' */
  errorMessage?: string
  /** Called when the form is submitted with the key and optional endpoint config */
  onSubmit: (data: ApiKeySubmitData) => void
  /** Form ID for external submit button binding (default: "api-key-form") */
  formId?: string
  /** Disable the input (e.g. during validation) */
  disabled?: boolean
  /** Provider type determines which presets and placeholders to show */
  providerType?: 'anthropic' | 'openai' | 'pi' | 'google' | 'pi_api_key'
  /** Pre-fill values when editing an existing connection */
  initialValues?: {
    apiKey?: string
    baseUrl?: string
    connectionDefaultModel?: string
    activePreset?: string
    models?: string[]
    /** Pre-fill the protocol toggle for custom endpoints */
    customApi?: CustomEndpointApi
  }
}

interface Preset {
  key: PresetKey
  label: string
  url: string
  placeholder?: string
  /** Requires the Pi SDK for authentication (e.g. OpenAI-compatible-only endpoint) — hidden in Anthropic API Key mode. */
  piOnly?: boolean
}

// Anthropic provider presets - for Claude Code backend
// Also used by Pi API key flow (same providers, routed via Pi SDK)
const ANTHROPIC_PRESETS: Preset[] = mergeEnginePresets([
  { key: 'anthropic', label: 'Anthropic', url: 'https://api.anthropic.com', placeholder: 'sk-ant-...' },
  { key: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1', placeholder: 'sk-...' },
  { key: 'openai-eu', label: 'OpenAI EU', url: 'https://eu.api.openai.com/v1', placeholder: 'sk-...' },
  { key: 'openai-us', label: 'OpenAI US', url: 'https://us.api.openai.com/v1', placeholder: 'sk-...' },
  { key: 'google', label: 'Google AI Studio', url: 'https://generativelanguage.googleapis.com/v1beta', placeholder: 'AIza...' },
  { key: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1', placeholder: 'sk-or-...' },
  { key: 'azure-openai-responses', label: 'Azure OpenAI', url: '', placeholder: 'Paste your key here...' },
  { key: 'amazon-bedrock', label: 'Amazon Bedrock', url: 'https://bedrock-runtime.us-east-1.amazonaws.com', placeholder: 'AKIA...' },
  { key: 'groq', label: 'Groq', url: 'https://api.groq.com/openai/v1', placeholder: 'gsk_...' },
  { key: 'mistral', label: 'Mistral', url: 'https://api.mistral.ai/v1', placeholder: 'Paste your key here...' },
  { key: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com', placeholder: 'sk-...' },
  // 国产厂商补齐（2026-10-22）：qwen / volc / mimo / glm 官方端点此前**完全缺失**
  // （GUI 里选不到），引擎侧早已支持（_REGISTRY 15 provider）。
  // 端点与 specs/providers.yaml 真相源一致；preset key = 引擎 provider 名。
  { key: 'qwen', label: '通义千问 (Qwen)', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', placeholder: 'sk-...' },
  { key: 'volc', label: '火山引擎 (豆包)', url: 'https://ark.cn-beijing.volces.com/api/v3', placeholder: 'sk-...' },
  { key: 'mimo', label: 'MiMo (小米)', url: 'https://api.xiaomimimo.com/v1', placeholder: 'sk-...' },
  { key: 'glm', label: '智谱 GLM（官方）', url: 'https://open.bigmodel.cn/api/paas/v4', placeholder: 'sk-...' },
  { key: 'xai', label: 'xAI (Grok)', url: 'https://api.x.ai/v1', placeholder: 'xai-...' },
  { key: 'cerebras', label: 'Cerebras', url: 'https://api.cerebras.ai/v1', placeholder: 'csk-...' },
  { key: 'zai', label: 'z.ai (GLM)', url: 'https://api.z.ai/api/coding/paas/v4', placeholder: 'Paste your key here...' },
  { key: 'huggingface', label: 'Hugging Face', url: 'https://router.huggingface.co/v1', placeholder: 'hf_...' },
  // MiniMax 端点必须用 OpenAI 兼容 base（/v1），不是 Anthropic 兼容 base（/anthropic）。
  // 引擎侧 minimax/minimax-cn 注册为 openai-completions 协议，会在 base 后拼
  // "/chat/completions"——若 base 带 /anthropic，最终打到
  // https://api.minimax.io/anthropic/chat/completions，该路由不存在 → 探活 404
  // （GUI 显示 "API endpoint not found. Check the URL."）。
  // Anthropic 兼容 base（/anthropic → /v1/messages）只在引擎按 anthropic-messages
  // 协议解析时可用；引擎注册表把这两个 provider 锁在 openai-completions 上。
  // 端点语义：api.minimax.io = 国际站，api.minimaxi.com = 国内站（key 不可跨区）。
  { key: 'minimax-global', label: 'Minimax Global', url: 'https://api.minimax.io/v1', placeholder: 'Paste your key here...', piOnly: true },
  { key: 'minimax-cn', label: 'Minimax CN', url: 'https://api.minimaxi.com/v1', placeholder: 'Paste your key here...', piOnly: true },
  { key: 'kimi-coding', label: 'Kimi (Coding)', url: 'https://api.kimi.com/coding', placeholder: 'sk-kimi-...' },
  { key: 'moonshotai', label: 'Moonshot AI', url: 'https://api.moonshot.ai/v1', placeholder: 'sk-...', piOnly: true },
  { key: 'moonshotai-cn', label: 'Moonshot AI (CN)', url: 'https://api.moonshot.cn/v1', placeholder: 'sk-...', piOnly: true },
  { key: 'vercel-ai-gateway', label: 'Vercel AI Gateway', url: 'https://ai-gateway.vercel.sh', placeholder: 'Paste your key here...' },
  { key: 'manifest', label: 'Manifest', url: 'https://app.manifest.build/v1', placeholder: 'mnfst_...' },
  { key: 'custom', label: 'Custom', url: '', placeholder: 'Paste your key here...' },
])

/**
 * Presets without a Pi SDK provider entry that nonetheless expose a known
 * OpenAI-compatible protocol. They behave like 'custom' on submit (customEndpoint
 * gets pinned to openai-completions) but stay branded in the dropdown.
 */
const OPENAI_COMPAT_CUSTOM_URL_PRESETS: ReadonlySet<string> = new Set(['manifest'])

// OpenAI provider presets - for Codex backend
// Only direct OpenAI is supported; 3PP providers (OpenRouter, Vercel, Ollama) should be
// configured via the Anthropic/Claude connection which routes through the Claude Agent SDK.
const OPENAI_PRESETS: Preset[] = [
  { key: 'openai', label: 'OpenAI', url: '' },
]

// Pi provider presets - unified API for 20+ LLM providers
const PI_PRESETS: Preset[] = [
  { key: 'pi', label: 'ZenSkill Backend (Direct)', url: '' },
  { key: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api' },
  { key: 'custom', label: 'Custom', url: '' },
]

// Google AI Studio preset - single endpoint, no custom URL needed
const GOOGLE_PRESETS: Preset[] = [
  { key: 'google', label: 'Google AI Studio', url: '' },
]

const COMPAT_ANTHROPIC_DEFAULTS = 'claude-opus-4-8, claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5'
const COMPAT_OPENAI_DEFAULTS = 'openai/gpt-5.2-codex, openai/gpt-5.1-codex-mini'
// MiniMax 型号表（2026-10-22 用真实 key 拉线上 GET /v1/models 实测校正）：
// 线上共 9 个型号 —— M3 / M3.1-Flash / M2.7 / M2.7-highspeed / M2.5 /
// M2.5-highspeed / M2.1 / M2.1-highspeed / M2。
// 此处只列**当代主力**（不含已被代际取代的 M2 / M2.1 系列）。
// 旧表只有 'MiniMax-M2.5, MiniMax-M2.5-highspeed' ⇒ GUI 从不提供 M3 / M3.1-Flash，
// 用户只能手写型号名（线上并不存在 "MiniMax-M3.0"）⇒ 探活必失败。
const COMPAT_MINIMAX_DEFAULTS = 'MiniMax-M3, MiniMax-M3.1-Flash, MiniMax-M2.7, MiniMax-M2.7-highspeed, MiniMax-M2.5, MiniMax-M2.5-highspeed'
const COMPAT_KIMI_DEFAULTS = 'k3, kimi-for-coding, kimi-for-coding-highspeed'
// DeepSeek preset suggestion — bare ID the ZenSkill engine resolves via its
// PREDEFINED_MODELS catalog (users can still edit it).
const DEEPSEEK_DEFAULT_MODEL = 'deepseek-v4-flash'

function getPresetsForProvider(providerType: 'anthropic' | 'openai' | 'pi' | 'google' | 'pi_api_key'): Preset[] {
  if (providerType === 'pi_api_key') return ANTHROPIC_PRESETS
  if (providerType === 'google') return GOOGLE_PRESETS
  if (providerType === 'pi') return PI_PRESETS
  if (providerType === 'openai') return OPENAI_PRESETS
  // Anthropic mode: exclude presets that only work via Pi SDK
  return ANTHROPIC_PRESETS.filter(p => !p.piOnly)
}

function getPresetForUrl(url: string, presets: Preset[]): PresetKey {
  const match = presets.find(p => p.key !== 'custom' && p.url === url)
  return match?.key ?? 'custom'
}

function parseModelList(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

// ============================================================
// Pi model tier selection (for providers with many models)
// ============================================================

export function ApiKeyInput({
  status,
  errorMessage,
  onSubmit,
  formId = "api-key-form",
  disabled,
  providerType = 'anthropic',
  initialValues,
}: ApiKeyInputProps) {
  // Get presets based on provider type
  const presets = getPresetsForProvider(providerType)
  const defaultPreset = presets[0]

  // Compute initial preset: explicit (Pi piAuthProvider), derived from URL, or default
  const initialPreset = initialValues?.activePreset
    ?? (initialValues?.baseUrl ? getPresetForUrl(initialValues.baseUrl, presets) : defaultPreset.key)

  const { t } = useTranslation()
  const [apiKey, setApiKey] = useState(initialValues?.apiKey ?? '')
  const [showValue, setShowValue] = useState(false)
  const [baseUrl, setBaseUrl] = useState(initialValues?.baseUrl ?? defaultPreset.url)
  const [activePreset, setActivePreset] = useState<PresetKey>(initialPreset)
  const [lastNonCustomPreset, setLastNonCustomPreset] = useState<PresetKey | null>(
    initialPreset !== 'custom' ? initialPreset : defaultPreset.key
  )
  const [connectionDefaultModel, setConnectionDefaultModel] = useState(initialValues?.connectionDefaultModel ?? '')
  const [customApi, setCustomApi] = useState<CustomEndpointApi>(initialValues?.customApi ?? 'openai-completions')
  const [modelError, setModelError] = useState<string | null>(null)
  /**
   * 区域不符诊断（2026-10-24 P4）：厂商的 401 与「key 填错」同形 ⇒ 引擎侧用
   * 同一个 key 试过同厂商的另一个区域端点、确证 key 属于那边之后才给这份结论。
   * 有它 ⇒ 提交被阻断，并给出「该用哪个端点」的一键切换。
   */
  const [regionMismatch, setRegionMismatch] = useState<RegionMismatchDiagnosis | null>(null)
  /**
   * 引擎型号目录快照（2026-10-24 P3）：预设映射 + 型号目录新鲜度。
   * 拉不到不阻断（回退到静态真相源 + 直连厂商拉线上目录）。
   */
  const [engineCatalog, setEngineCatalog] = useState<LlmCatalogResult | null>(null)

  // Bedrock auth state
  const [bedrockAuthMethod, setBedrockAuthMethod] = useState<'iam_credentials' | 'environment'>('iam_credentials')
  const [awsAccessKeyId, setAwsAccessKeyId] = useState('')
  const [awsSecretAccessKey, setAwsSecretAccessKey] = useState('')
  const [awsSessionToken, setAwsSessionToken] = useState('')
  const [awsRegion, setAwsRegion] = useState('us-east-1')

  // Pi model tier state (for providers with many models like OpenRouter, Vercel)
  const [piModels, setPiModels] = useState<PiModelInfo[]>([])
  const [piModelsLoading, setPiModelsLoading] = useState(false)
  const [bestModel, setBestModel] = useState('')
  const [defaultModel, setDefaultModel] = useState('')
  const [cheapModel, setCheapModel] = useState('')
  const [openTier, setOpenTier] = useState<string | null>(null)
  // 厂商**线上**型号清单（2026-10-22）：pi SDK 内置目录会过期
  // （minimax 只到 MiniMax-M2.5 ⇒ 用户手写 "MiniMax-M3.0"，线上并不存在）。
  const [onlineModels, setOnlineModels] = useState<string[]>([])
  const [fetchingOnlineModels, setFetchingOnlineModels] = useState(false)
  const [tierFilter, setTierFilter] = useState('')
  const [tierDropdownPosition, setTierDropdownPosition] = useState<{ top: number; left: number; width: number } | null>(null)
  const tierFilterInputRef = useRef<HTMLInputElement>(null)
  const hydratedTierProviderRef = useRef<string | null>(null)

  const isDisabled = disabled || status === 'validating'

  const isPiApiKeyFlow = providerType === 'pi_api_key'
  const isBedrock = activePreset === 'amazon-bedrock'
  const isDefaultProviderPreset = DEFAULT_ENDPOINT_PROVIDERS.has(activePreset)

  // Provider-specific placeholders from the active preset
  const activePresetObj = presets.find(p => p.key === activePreset)
  const apiKeyPlaceholder = activePresetObj?.placeholder
    ?? (providerType === 'google' ? 'AIza...'
    : providerType === 'pi' ? 'pi-...'
    : providerType === 'openai' ? 'sk-...'
    : 'Paste your key here...')

  // Fetch Pi SDK models when a provider is selected in pi_api_key flow.
  // Returns all models sorted by cost (expensive-first) for the searchable tier dropdowns.
  const initialValuesModels = initialValues?.models
  const loadPiModels = useCallback(async (provider: string) => {
    if (!isPiApiKeyFlow || !provider || provider === 'custom' || DEFAULT_ENDPOINT_PROVIDERS.has(provider) || OPENAI_COMPAT_CUSTOM_URL_PRESETS.has(provider)) {
      setPiModels([])
      return
    }
    setPiModelsLoading(true)
    try {
      const result = await window.electronAPI.getPiProviderModels(provider)
      setPiModels(result.models)

      if (hydratedTierProviderRef.current !== provider) {
        const tiers = resolveTierModels(result.models, provider === initialPreset ? initialValuesModels : undefined)
        setBestModel(tiers.best)
        setDefaultModel(tiers.default_)
        setCheapModel(tiers.cheap)
        hydratedTierProviderRef.current = provider
      }
    } catch (err) {
      console.error('[ApiKeyInput] Failed to load models for', provider, err)
      setPiModels([])
    } finally {
      setPiModelsLoading(false)
    }
  }, [isPiApiKeyFlow, initialPreset, initialValuesModels])

  useEffect(() => {
    loadPiModels(activePreset)
  }, [activePreset, loadPiModels])

  // 引擎型号目录快照（P3）：预设映射（provider → GUI 预设 key）与新鲜度。
  // 拉失败**不阻断**——静态真相源（生成物）已在编译期进包，直连厂商拉线上目录
  // 也仍然可用（fetchOnlineModels）。
  useEffect(() => {
    let cancelled = false
    window.electronAPI
      .fetchLlmCatalog({})
      .then(res => {
        if (!cancelled && res?.success) setEngineCatalog(res)
      })
      .catch(() => {
        /* 引擎目录不可用 → 回退静态真相源 + 直连厂商 */
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Whether to show 3 tier dropdowns instead of text input
  const hasPiModels = isPiApiKeyFlow && piModels.length > 0 && !isDefaultProviderPreset && activePreset !== 'custom' && !isBedrock

  // 端点协议：决定拉哪个型号清单 URL（openai → {base}/models；anthropic → {base}/v1/models）
  // ★ 协议以**预设自带的 api**（provider 契约下发的真相源）为准；只有 custom 预设
  //   才由 mode 开关决定。★ 否则「openai 预设 + Anthropic mode」会把 x-api-key
  //   发给 openai 兼容端点 ⇒ 厂商 401 且文案误判为「key 无效 / 区域不符」。
  const endpointProtocol: 'openai-completions' | 'anthropic-messages' =
    resolveEndpointProtocol({ presetKey: activePreset, modeApi: customApi })

  /**
   * 拉取厂商线上型号清单（真实 HTTP）。
   * 失败**不阻断**配置——目录拉不到时仍可手填型号；成功时用于：
   *   ① 校验用户填的型号是否线上真实存在（填表即预检）
   *   ② 用线上目录补齐 pi SDK 的过期目录（让 M3 / M3.1-Flash 直接可选）
   */
  const fetchOnlineModels = useCallback(async (): Promise<string[]> => {
    const base = baseUrl.trim()
    const key = apiKey.trim()
    if (!base) {
      setModelError('请先选择预设或填写端点地址')
      return []
    }
    if (!key) {
      setModelError('请先填写 API Key（拉取线上型号需要它）')
      return []
    }
    setFetchingOnlineModels(true)
    try {
      const result = await window.electronAPI.fetchLlmModels({
        apiKey: key,
        baseUrl: base,
        protocol: endpointProtocol,
      })
      if (!result.success) {
        setOnlineModels([])
        // 区域不符（P4）：厂商 401 与「key 填错」同形 ⇒ 引擎侧用同一个 key 试过
        // 同厂商的另一个区域端点，确证 key 属于那边之后才给这份结论。
        // 有确证 ⇒ 给出「该用哪个端点」；没有 ⇒ 照旧显示原始错误（不猜）。
        if (result.regionMismatch) {
          setRegionMismatch(result.regionMismatch)
          setModelError(result.regionMismatch.message)
          return []
        }
        setRegionMismatch(null)
        setModelError(result.error || '拉取线上型号失败')
        return []
      }
      setRegionMismatch(null)
      const models = result.models ?? []
      setOnlineModels(models)
      return models
    } catch (err) {
      console.error('[ApiKeyInput] Failed to fetch online models', err)
      setOnlineModels([])
      setModelError('拉取线上型号失败')
      return []
    } finally {
      setFetchingOnlineModels(false)
    }
  }, [apiKey, baseUrl, providerType, endpointProtocol])

  /**
   * 一键切到诊断给出的端点（P4）：区域不符时省去用户自己去找端点。
   * 预设 key 从引擎目录快照里按 provider 反查（provider 名与 GUI 预设 key
   * 不总是同名，例如 provider `minimax` ↔ 预设 `minimax-global`）；
   * 快照不可用时回退到编译期进包的静态真相源。
   */
  const applySuggestedEndpoint = useCallback(() => {
    if (!regionMismatch) return
    const preset =
      engineCatalog?.presets?.find(p => p.provider === regionMismatch.suggestedProvider) ??
      PROVIDER_PRESETS.find(p => p.provider === regionMismatch.suggestedProvider)
    if (preset) {
      setActivePreset(preset.key)
      setLastNonCustomPreset(preset.key)
      setBaseUrl(preset.baseUrl)
    } else {
      setBaseUrl(regionMismatch.suggestedBaseUrl)
    }
    setModelError(null)
    setRegionMismatch(null)
  }, [regionMismatch, engineCatalog])

  /** 校验填写的型号是否在厂商线上目录中（目录未知时不阻断） */  const validateModelsAgainstOnline = useCallback((models: string[]): boolean => {
    if (models.length === 0) return true
    const typed = parseModelList(connectionDefaultModel)
    if (typed.length === 0) return true
    // Anthropic 兼容路由会把未知型号静默归一化（实测 M3.0 → 200 且实际跑 M3.1-Flash）
    // ⇒ 只有 openai 兼容协议才把「不在目录」当错误。
    if (endpointProtocol === 'anthropic-messages') return true
    const missing = typed.filter((m) => !models.includes(m))
    if (missing.length > 0) {
      setModelError(
        `型号 ${missing.join(', ')} 不在厂商线上目录中。可用：${models.slice(0, 8).join(', ')}${models.length > 8 ? ' …' : ''}`
      )
      return false
    }
    setModelError(null)
    return true
  }, [connectionDefaultModel, endpointProtocol])

  /** tier 下拉列表 = 线上目录优先（补齐 pi SDK 的过期目录）+ pi SDK 目录 */
  const tierModelOptions = useMemo<PiModelInfo[]>(() => {
    if (onlineModels.length === 0) return piModels
    const onlineItems: PiModelInfo[] = onlineModels.map((id) => ({
      id: id.startsWith('pi/') ? id : `pi/${id}`,
      name: id,
      costInput: 0,
      costOutput: 0,
      contextWindow: 0,
      reasoning: false,
    }))
    const known = new Set(onlineItems.map((m) => m.id))
    return [...onlineItems, ...piModels.filter((m) => !known.has(m.id))]
  }, [onlineModels, piModels])

  const handlePresetSelect = (preset: Preset) => {
    setActivePreset(preset.key)
    // 选预设 ⇒ 协议跟随预设（mode 开关同步），否则保存下来的连接会带着错配的协议
    setCustomApi(resolveEndpointProtocol({ presetKey: preset.key, modeApi: customApi }))
    if (preset.key !== 'custom') {
      setLastNonCustomPreset(preset.key)
    }
    if (preset.key === 'custom') {
      setBaseUrl('')
    } else {
      setBaseUrl(preset.url)
    }
    setModelError(null)
    // Pre-fill recommended model for Ollama; clear for all others
    // (Default provider presets hide the field entirely, others default to provider model IDs when empty)
    if (preset.key === 'ollama') {
      setConnectionDefaultModel('qwen3-coder')
    } else if (preset.key === 'openrouter' || preset.key === 'vercel-ai-gateway') {
      setConnectionDefaultModel(providerType === 'openai' ? COMPAT_OPENAI_DEFAULTS : COMPAT_ANTHROPIC_DEFAULTS)
    } else if (preset.key === 'minimax-global' || preset.key === 'minimax-cn') {
      setConnectionDefaultModel(COMPAT_MINIMAX_DEFAULTS)
    } else if (preset.key === 'kimi-coding') {
      setConnectionDefaultModel(COMPAT_KIMI_DEFAULTS)
    } else if (preset.key === 'manifest') {
      setConnectionDefaultModel('auto')
    } else if (preset.key === 'deepseek') {
      setConnectionDefaultModel(DEEPSEEK_DEFAULT_MODEL)
    } else if (preset.key === 'custom' || OPENAI_COMPAT_CUSTOM_URL_PRESETS.has(preset.key)) {
      setConnectionDefaultModel(providerType === 'openai' ? COMPAT_OPENAI_DEFAULTS : COMPAT_ANTHROPIC_DEFAULTS)
    } else {
      setConnectionDefaultModel('')
    }
  }

  const handleBaseUrlChange = (value: string) => {
    setBaseUrl(value)
    const presetKey = getPresetForUrl(value, presets)
    const currentPresetObj = presets.find(p => p.key === activePreset)
    const nextPresetState = resolvePresetStateForBaseUrlChange({
      matchedPreset: presetKey,
      activePreset,
      activePresetHasEmptyUrl: currentPresetObj?.url === '',
      lastNonCustomPreset,
    })
    setActivePreset(nextPresetState.activePreset)
    setLastNonCustomPreset(nextPresetState.lastNonCustomPreset)
    setModelError(null)
    if (!connectionDefaultModel.trim()) {
      if (presetKey === 'ollama') {
        setConnectionDefaultModel('qwen3-coder')
      } else if (presetKey === 'manifest') {
        setConnectionDefaultModel('auto')
      } else if (presetKey === 'minimax-global' || presetKey === 'minimax-cn') {
        setConnectionDefaultModel(COMPAT_MINIMAX_DEFAULTS)
      } else if (presetKey === 'kimi-coding') {
        setConnectionDefaultModel(COMPAT_KIMI_DEFAULTS)
      } else if (presetKey === 'deepseek') {
        setConnectionDefaultModel(DEEPSEEK_DEFAULT_MODEL)
      } else if (presetKey === 'openrouter' || presetKey === 'vercel-ai-gateway' || presetKey === 'custom') {
        setConnectionDefaultModel(providerType === 'openai' ? COMPAT_OPENAI_DEFAULTS : COMPAT_ANTHROPIC_DEFAULTS)
      }
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    // 区域不符已确证 ⇒ 阻断提交（P4）：此时提交必然得到 401，
    // 而用户改对端点就能用 ⇒ 明确阻断 + 给一键切换，比放行再失败好。
    if (regionMismatch) {
      setModelError(regionMismatch.message)
      return
    }

    const effectivePiAuthProvider = isPiApiKeyFlow
      ? resolvePiAuthProviderForSubmit(activePreset, lastNonCustomPreset)
      : undefined

    // Pi API key flow with tier dropdowns — submit selected models
    if (hasPiModels) {
      if (!bestModel || !defaultModel || !cheapModel) {
        setModelError('Please select a model for each tier.')
        return
      }
      const models: string[] = [bestModel, defaultModel, cheapModel]
      // 填表即预检：已拉到线上目录时，型号不在目录就别提交（省掉一次必然失败的探活）
      if (onlineModels.length > 0) {
        const missing = models.filter((m) => !onlineModels.includes(m.replace(/^pi\//, '')))
        if (missing.length > 0 && endpointProtocol !== 'anthropic-messages') {
          setModelError(
            `型号 ${missing.join(', ')} 不在厂商线上目录中。可用：${onlineModels.slice(0, 8).join(', ')}${onlineModels.length > 8 ? ' …' : ''}`
          )
          return
        }
      }
      onSubmit({
        apiKey: apiKey.trim(),
        baseUrl: baseUrl.trim() || undefined,
        connectionDefaultModel: bestModel,
        models,
        piAuthProvider: effectivePiAuthProvider,
        modelSelectionMode: 'userDefined3Tier',
      })
      return
    }

    // Bedrock — routes through Pi SDK with piAuthProvider='amazon-bedrock'.
    // Submit with auth method and optional IAM credentials.
    if (isBedrock) {
      if (bedrockAuthMethod === 'iam_credentials' && !awsAccessKeyId.trim()) {
        setModelError('Access Key ID is required for IAM authentication.')
        return
      }
      if (bedrockAuthMethod === 'iam_credentials' && !awsSecretAccessKey.trim()) {
        setModelError('Secret Access Key is required for IAM authentication.')
        return
      }
      const parsedModels = parseModelList(connectionDefaultModel)

    // 填表即预检（与 pi 流程同一条规则）
    if (onlineModels.length > 0 && !validateModelsAgainstOnline(onlineModels)) {
      return
    }
      onSubmit({
        apiKey: '',
        piAuthProvider: effectivePiAuthProvider,
        bedrockAuthMethod,
        awsRegion: awsRegion.trim() || 'us-east-1',
        ...(bedrockAuthMethod === 'iam_credentials' ? {
          iamCredentials: {
            accessKeyId: awsAccessKeyId.trim(),
            secretAccessKey: awsSecretAccessKey.trim(),
            ...(awsSessionToken.trim() ? { sessionToken: awsSessionToken.trim() } : {}),
          },
        } : {}),
        connectionDefaultModel: parsedModels[0],
        models: parsedModels.length > 0 ? parsedModels : undefined,
      })
      return
    }

    const effectiveBaseUrl = baseUrl.trim()

    const parsedModels = parseModelList(connectionDefaultModel)

    const isUsingDefaultEndpoint = isDefaultProviderPreset || !effectiveBaseUrl
    const requiresModel = !isDefaultProviderPreset && !!effectiveBaseUrl
    if (requiresModel && parsedModels.length === 0) {
      setModelError('Default model is required for custom endpoints.')
      return
    }

    // Include custom endpoint protocol when user configured a custom base URL.
    // Branded openai-compat presets (e.g. Manifest) are pinned to openai-completions
    // and routed via the Pi SDK's openai adapter.
    const { customEndpoint, piAuthProvider: resolvedPiAuthProvider } = resolveCustomEndpointPayload({
      activePreset,
      baseUrl: effectiveBaseUrl,
      customApi,
      brandedOpenAiCompatPresets: OPENAI_COMPAT_CUSTOM_URL_PRESETS,
      fallbackPiAuthProvider: effectivePiAuthProvider,
    })

    onSubmit({
      apiKey: apiKey.trim(),
      baseUrl: isUsingDefaultEndpoint ? undefined : effectiveBaseUrl,
      connectionDefaultModel: parsedModels[0],
      models: parsedModels.length > 0 ? parsedModels : undefined,
      piAuthProvider: resolvedPiAuthProvider,
      modelSelectionMode: isPiApiKeyFlow
        ? (parsedModels.length > 0 ? 'userDefined3Tier' : 'automaticallySyncedFromProvider')
        : undefined,
      customEndpoint,
    })
  }

  const tierConfigs = [
    { label: 'Best', desc: 'most capable', value: bestModel, onChange: setBestModel },
    { label: 'Balanced', desc: 'good for everyday use', value: defaultModel, onChange: setDefaultModel },
    { label: 'Fast', desc: 'summarization & utility', value: cheapModel, onChange: setCheapModel },
  ]
  const activeTierConfig = openTier ? tierConfigs.find(t => t.label === openTier) : null

  return (
    <form id={formId} onSubmit={handleSubmit} className="space-y-6">
      {/* API Key — hidden for Bedrock (uses IAM/Environment auth) */}
      {!isBedrock && (<div className="space-y-2">
        <Label htmlFor="api-key">API Key</Label>
        <div className={cn(
          "relative rounded-md shadow-minimal transition-colors",
          "bg-foreground-2 focus-within:bg-background"
        )}>
          <Input
            id="api-key"
            type={showValue ? 'text' : 'password'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={apiKeyPlaceholder}
            className={cn(
              "pr-10 border-0 bg-transparent shadow-none",
              status === 'error' && "focus-visible:ring-destructive"
            )}
            disabled={isDisabled}
            autoFocus
          />
          <button
            type="button"
            onClick={() => setShowValue(!showValue)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            tabIndex={-1}
          >
            {showValue ? (
              <EyeOff className="size-4" />
            ) : (
              <Eye className="size-4" />
            )}
          </button>
        </div>
      </div>)}

      {/* Endpoint/Provider Preset Selector - hidden when only one preset (e.g. Codex/OpenAI direct) */}
      {presets.length > 1 && (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="base-url">Endpoint</Label>
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={isDisabled}
              className="flex h-6 items-center gap-1 rounded-[6px] bg-background shadow-minimal pl-2.5 pr-2 text-[12px] font-medium text-foreground/50 hover:bg-foreground/5 hover:text-foreground focus:outline-none"
            >
              {presets.find(p => p.key === activePreset)?.label}
              <ChevronDown className="size-2.5 opacity-50" />
            </DropdownMenuTrigger>
            <StyledDropdownMenuContent align="end" className="z-floating-menu">
              {presets.map((preset) => (
                <StyledDropdownMenuItem
                  key={preset.key}
                  onClick={() => handlePresetSelect(preset)}
                  className="justify-between"
                >
                  {preset.label}
                  <Check className={cn("size-3", activePreset === preset.key ? "opacity-100" : "opacity-0")} />
                </StyledDropdownMenuItem>
              ))}
            </StyledDropdownMenuContent>
          </DropdownMenu>
        </div>
        {/* Base URL input - hidden for default provider presets (Anthropic/OpenAI) and Bedrock */}
        {!isDefaultProviderPreset && !isBedrock && (
          <div className={cn(
            "rounded-md shadow-minimal transition-colors",
            "bg-foreground-2 focus-within:bg-background"
          )}>
            <Input
              id="base-url"
              type="text"
              value={baseUrl}
              onChange={(e) => handleBaseUrlChange(e.target.value)}
              placeholder="https://your-api-endpoint.com"
              className="border-0 bg-transparent shadow-none"
              disabled={isDisabled}
            />
          </div>
        )}
      </div>
      )}

      {/* Protocol Toggle — visible as soon as Custom preset is selected */}
      {activePreset === 'custom' && !isDefaultProviderPreset && (
        <div className="space-y-2">
          <Label>Protocol</Label>
          <div className={cn(
            "flex rounded-md shadow-minimal overflow-hidden",
            "bg-foreground-2",
            isDisabled && "opacity-50 pointer-events-none"
          )}>
            {([
              { value: 'openai-completions' as const, label: 'OpenAI Compatible' },
              { value: 'anthropic-messages' as const, label: 'Anthropic Compatible' },
            ]).map(({ value, label }) => (
              <button
                key={value}
                type="button"
                disabled={isDisabled}
                onClick={() => setCustomApi(value)}
                className={cn(
                  "flex-1 py-1.5 text-[12px] font-medium transition-colors",
                  customApi === value
                    ? "bg-background text-foreground shadow-minimal"
                    : "text-foreground/50 hover:text-foreground/70"
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-foreground/30">
            Most third-party APIs (Ollama, vLLM, DashScope) use OpenAI Compatible.
          </p>
        </div>
      )}

      {/* Bedrock Auth Section */}
      {isBedrock && (
        <>
          {/* Auth Method Toggle */}
          <div className="space-y-2">
            <Label>Authentication</Label>
            <div className={cn(
              "flex rounded-md shadow-minimal overflow-hidden",
              "bg-foreground-2",
              isDisabled && "opacity-50 pointer-events-none"
            )}>
              {([
                { value: 'iam_credentials' as const, label: 'IAM Credentials' },
                { value: 'environment' as const, label: 'Environment (AWS CLI)' },
              ]).map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  disabled={isDisabled}
                  onClick={() => setBedrockAuthMethod(value)}
                  className={cn(
                    "flex-1 py-1.5 text-[12px] font-medium transition-colors",
                    bedrockAuthMethod === value
                      ? "bg-background text-foreground shadow-minimal"
                      : "text-foreground/50 hover:text-foreground/70"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* IAM Credential Fields */}
          {bedrockAuthMethod === 'iam_credentials' && (
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="aws-access-key-id" className="text-muted-foreground font-normal text-xs">
                  Access Key ID
                </Label>
                <div className={cn("rounded-md shadow-minimal transition-colors", "bg-foreground-2 focus-within:bg-background")}>
                  <Input
                    id="aws-access-key-id"
                    type="text"
                    value={awsAccessKeyId}
                    onChange={(e) => setAwsAccessKeyId(e.target.value)}
                    placeholder="AKIA..."
                    className="border-0 bg-transparent shadow-none"
                    disabled={isDisabled}
                    autoFocus
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="aws-secret-key" className="text-muted-foreground font-normal text-xs">
                  Secret Access Key
                </Label>
                <div className={cn("relative rounded-md shadow-minimal transition-colors", "bg-foreground-2 focus-within:bg-background")}>
                  <Input
                    id="aws-secret-key"
                    type={showValue ? 'text' : 'password'}
                    value={awsSecretAccessKey}
                    onChange={(e) => setAwsSecretAccessKey(e.target.value)}
                    placeholder={t("apiSetup.secretAccessKey")}
                    className="pr-10 border-0 bg-transparent shadow-none"
                    disabled={isDisabled}
                  />
                  <button
                    type="button"
                    onClick={() => setShowValue(!showValue)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    tabIndex={-1}
                  >
                    {showValue ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="aws-session-token" className="text-muted-foreground font-normal text-xs">
                  Session Token <span className="text-foreground/30">· optional</span>
                </Label>
                <div className={cn("rounded-md shadow-minimal transition-colors", "bg-foreground-2 focus-within:bg-background")}>
                  <Input
                    id="aws-session-token"
                    type="text"
                    value={awsSessionToken}
                    onChange={(e) => setAwsSessionToken(e.target.value)}
                    placeholder={t("apiSetup.temporaryCredentials")}
                    className="border-0 bg-transparent shadow-none"
                    disabled={isDisabled}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Environment info */}
          {bedrockAuthMethod === 'environment' && (
            <div className="rounded-md bg-foreground-2 p-3">
              <p className="text-xs text-foreground/50">
                Uses your existing AWS credential chain — <code className="text-foreground/70">~/.aws/credentials</code>, <code className="text-foreground/70">AWS_PROFILE</code>, IAM roles, SSO sessions, and environment variables.
              </p>
            </div>
          )}

          {/* AWS Region */}
          <div className="space-y-1.5">
            <Label htmlFor="aws-region" className="text-muted-foreground font-normal text-xs">
              AWS Region
            </Label>
            <div className={cn("rounded-md shadow-minimal transition-colors", "bg-foreground-2 focus-within:bg-background")}>
              <Input
                id="aws-region"
                type="text"
                value={awsRegion}
                onChange={(e) => setAwsRegion(e.target.value)}
                placeholder="us-east-1"
                className="border-0 bg-transparent shadow-none"
                disabled={isDisabled}
              />
            </div>
          </div>
        </>
      )}

      {/* Model Selection — 3 tier dropdowns for Pi providers, text input for custom/compat */}
      {/* 拉取厂商线上型号（2026-10-22）：pi SDK 内置目录会过期
          （minimax 只到 MiniMax-M2.5 ⇒ 用户手写 "MiniMax-M3.0"，线上并不存在） */}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs text-foreground/70"
          disabled={isDisabled || fetchingOnlineModels}
          onClick={async () => {
            const models = await fetchOnlineModels()
            if (models.length === 0) return
            const typed = parseModelList(connectionDefaultModel)
            if (typed.length === 0) {
              setConnectionDefaultModel(models[0])
              setModelError(null)
            } else {
              validateModelsAgainstOnline(models)
            }
          }}
        >
          {fetchingOnlineModels ? <Loader2 className="size-3 animate-spin" /> : null}
          拉取线上型号
        </Button>
        {onlineModels.length > 0 && (
          <span className="text-xs text-foreground/40">线上 {onlineModels.length} 个型号</span>
        )}
      </div>

      {hasPiModels ? (
        <div className="space-y-3">
          {piModelsLoading ? (
            <div className="flex items-center gap-2 py-3 text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              <span className="text-xs">{t("apiSetup.loadingModels")}</span>
            </div>
          ) : (
            <>
              {tierConfigs.map(({ label, desc, value }) => (
                <div key={label} className="space-y-1.5">
                  <Label className="text-muted-foreground font-normal text-xs">
                    {label}{' '}
                    <span className="text-foreground/30">· {desc}</span>
                  </Label>
                  <button
                    type="button"
                    disabled={isDisabled}
                    onClick={(e) => {
                      if (openTier === label) {
                        setOpenTier(null)
                        setTierFilter('')
                      } else {
                        const rect = e.currentTarget.getBoundingClientRect()
                        setTierDropdownPosition({ top: rect.bottom + 4, left: rect.left, width: rect.width })
                        setOpenTier(label)
                        setTierFilter('')
                        setTimeout(() => tierFilterInputRef.current?.focus(), 0)
                      }
                    }}
                    className={cn(
                      "flex h-9 w-full items-center justify-between rounded-md px-3 text-sm",
                      "bg-foreground-2 shadow-minimal transition-colors",
                      "hover:bg-background focus:outline-none focus:bg-background",
                      isDisabled && "opacity-50 pointer-events-none"
                    )}
                  >
                    <span className="truncate text-foreground">
                      {tierModelOptions.find(m => m.id === value)?.name ?? 'Select model...'}
                    </span>
                    <ChevronDown className="size-3 opacity-50 shrink-0" />
                  </button>
                </div>
              ))}
              {activeTierConfig && tierDropdownPosition && (
                <>
                  <div
                    className="fixed inset-0 z-floating-backdrop"
                    onClick={() => { setOpenTier(null); setTierFilter('') }}
                  />
                  <div
                    className="fixed z-floating-menu min-w-[200px] overflow-hidden rounded-[8px] bg-background text-foreground shadow-modal-small"
                    style={{
                      top: tierDropdownPosition.top,
                      left: tierDropdownPosition.left,
                      width: tierDropdownPosition.width,
                    }}
                  >
                    <CommandPrimitive
                      className="min-w-[200px]"
                      shouldFilter={false}
                    >
                      <div className="border-b border-border/50 px-3 py-2">
                        <CommandPrimitive.Input
                          ref={tierFilterInputRef}
                          value={tierFilter}
                          onValueChange={setTierFilter}
                          placeholder={t("apiSetup.searchModels")}
                          autoFocus
                          className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground placeholder:select-none"
                        />
                      </div>
                      <CommandPrimitive.List className="max-h-[240px] overflow-y-auto p-1">
                        {tierModelOptions
                          .filter(m => m.name.toLowerCase().includes(tierFilter.toLowerCase()))
                          .map((model) => (
                            <CommandPrimitive.Item
                              key={model.id}
                              value={model.id}
                              onSelect={() => {
                                activeTierConfig.onChange(model.id)
                                setOpenTier(null)
                                setTierFilter('')
                              }}
                              className={cn(
                                "flex cursor-pointer select-none items-center justify-between gap-3 rounded-[6px] px-3 py-2 text-[13px]",
                                "outline-none data-[selected=true]:bg-foreground/5"
                              )}
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span className="truncate">{model.name}</span>
                                {model.reasoning && (
                                  <span className="text-[10px] text-foreground/30 shrink-0">reasoning</span>
                                )}
                              </div>
                              <Check className={cn("size-3 shrink-0", activeTierConfig.value === model.id ? "opacity-100" : "opacity-0")} />
                            </CommandPrimitive.Item>
                          ))}
                      </CommandPrimitive.List>
                    </CommandPrimitive>
                  </div>
                </>
              )}
              {modelError && (
                <p className="text-xs text-destructive">{modelError}</p>
              )}
            </>
          )}
        </div>
      ) : !isDefaultProviderPreset && (
        <div className="space-y-2">
          <Label htmlFor="connection-default-model" className="text-muted-foreground font-normal">
            Default Model{' '}
            <span className="text-foreground/30">
              · {!isBedrock && baseUrl.trim() ? 'required' : 'optional'}
            </span>
          </Label>
          <div className={cn(
            "rounded-md shadow-minimal transition-colors",
            "bg-foreground-2 focus-within:bg-background",
            modelError && "ring-1 ring-destructive/40"
          )}>
            <Input
              id="connection-default-model"
              type="text"
              value={connectionDefaultModel}
              onChange={(e) => {
                setConnectionDefaultModel(e.target.value)
                setModelError(null)
              }}
              placeholder={
                activePreset === 'deepseek'
                  ? 'e.g. deepseek-v4-flash, deepseek-v4-pro'
                  : 'e.g. claude-opus-4-8, claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5'
              }
              className="border-0 bg-transparent shadow-none"
              disabled={isDisabled}
            />
          </div>
          {modelError && (
            <p className="text-xs text-destructive">{modelError}</p>
          )}
          {regionMismatch && (
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto justify-start p-0 text-xs"
              onClick={applySuggestedEndpoint}
            >
              改用「{regionMismatch.suggestedLabel}」端点
            </Button>
          )}
          <p className="text-xs text-foreground/30">
            Comma-separated list. The first model is the default. The last is used for summarization.
          </p>
          {(activePreset === 'custom' || !activePreset) && (
            <p className="text-xs text-foreground/30">
              Required for custom endpoints. Use the provider-specific model ID.
            </p>
          )}
        </div>
      )}

      {/* Error message */}
      {status === 'error' && errorMessage && (
        <p className="text-sm text-destructive">{errorMessage}</p>
      )}
    </form>
  )
}
