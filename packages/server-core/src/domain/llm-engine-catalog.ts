/**
 * 引擎型号目录（真相源下发 + 引擎自己的覆盖层）—— 2026-10-24 P3 / P4
 *
 * 为什么这个模块存在（把「谁说了算」写清楚）：
 *
 *   - **预设清单与静态型号目录的真相源 = 父仓 `specs/providers.yaml`**，
 *     经 `scripts/sync_provider_registry.py` 生成到
 *     `packages/shared/src/config/providers-zenskill.ts` ⇒ GUI 不再硬编码
 *     端点副本（历史上 minimax 的端点语义漂移就是这么来的）。
 *   - **目录新鲜度的真相源 = 引擎自己**：`~/.zenskill/llm_catalog.json`
 *     （引擎的 llm_catalog 策略层写：首次配置必同步 / TTL / 拉取结果覆盖层）。
 *     GUI 只**读**它，不另造第二份缓存。
 *   - **线上最新目录**仍由「直连厂商 /models」拿（引擎没有 key 时也能拉），
 *     作为兜底：GUI 优先用引擎目录 + 真相源预设，拿不到再直连厂商。
 *
 * P4（区域不符诊断）：境内 key 打国际站（或反之）⇒ 厂商回 401
 * `invalid api key (2049)`，与「key 填错」长得一模一样 ⇒ 用户无从判断。
 * 诊断办法：**用同一个 key 去试同厂商的另一个区域端点** —— 那边通 ⇒ key 属于那边。
 * 判定所需的「端点 → 区域 / 厂商族」来自真相源（region / vendorFamily）。
 */

import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import {
  ZENSKILL_PROVIDER_PRESETS,
  ZENSKILL_PROVIDER_CATALOG,
} from '@craft-agent/shared/config/providers-zenskill'
import type { LlmCatalogProviderEntry, LlmCatalogResult } from '@craft-agent/shared/protocol'

/** 引擎覆盖层的 TTL（与 Python `llm_catalog.DEFAULT_TTL_SECONDS` 同步 = 24h） */
export const ENGINE_CATALOG_TTL_SECONDS = 24 * 60 * 60

/** 引擎目录覆盖层里单个 provider 的条目 */
export interface EngineOverlayEntry {
  models?: string[]
  base_url?: string
  api?: string
  /** 上次线上拉取时间（epoch 秒） */
  fetched_at?: number
}

/** 引擎目录覆盖层整体 */
export interface EngineCatalogOverlay {
  version?: number
  updated_at?: number
  providers?: Record<string, EngineOverlayEntry>
}

/** 覆盖层落盘位置（随 HOME；引擎写、GUI 读） */
export function engineCatalogOverlayPath(home: string = homedir()): string {
  return join(home, '.zenskill', 'llm_catalog.json')
}

/**
 * 读引擎目录覆盖层。
 *
 * 读不到 / 损坏 ⇒ 返回空覆盖层（**不抛**）：目录不可知不该把 GUI 带崩，
 * 上层据此回退到「直连厂商拉线上目录」。
 */
export function readEngineCatalogOverlay(home: string = homedir()): EngineCatalogOverlay {
  try {
    const raw = readFileSync(engineCatalogOverlayPath(home), 'utf-8')
    const data = JSON.parse(raw) as EngineCatalogOverlay
    if (!data || typeof data !== 'object') return { providers: {} }
    if (!data.providers || typeof data.providers !== 'object') data.providers = {}
    return data
  } catch {
    return { providers: {} }
  }
}

/**
 * 组装型号目录快照（GUI 消费的形态）。
 *
 * 口径：
 *   - `source='cache'`   ⇒ 引擎覆盖层里有**线上拉取**结果（models 取覆盖层）
 *   - `source='catalog'` ⇒ 只有静态目录（真相源生成物）
 *   - `stale` ⇒ 覆盖层缺失（从未同步）或年龄 > TTL（引擎同一条判据）
 */
export function buildLlmCatalogSnapshot(params?: {
  providers?: string[]
  overlay?: EngineCatalogOverlay
  now?: number
  home?: string
}): LlmCatalogResult {
  const now = params?.now ?? Date.now()
  const overlay = params?.overlay ?? readEngineCatalogOverlay(params?.home)
  const wanted = params?.providers?.length ? new Set(params.providers) : null

  const entries: LlmCatalogProviderEntry[] = []
  for (const entry of ZENSKILL_PROVIDER_CATALOG) {
    if (wanted && !wanted.has(entry.provider)) continue
    const overlayEntry = overlay.providers?.[entry.provider]
    const fetchedAtSec = typeof overlayEntry?.fetched_at === 'number' ? overlayEntry.fetched_at : undefined
    const hasRemote = Array.isArray(overlayEntry?.models) && overlayEntry.models.length > 0
    const ageSeconds = fetchedAtSec !== undefined ? Math.max(0, Math.floor(now / 1000 - fetchedAtSec)) : undefined
    const models = hasRemote
      ? (overlayEntry!.models as string[]).map(m => String(m))
      : entry.models.map(m => m.name)
    entries.push({
      provider: entry.provider,
      display: entry.display,
      source: hasRemote ? 'cache' : 'catalog',
      models,
      fetchedAt: fetchedAtSec !== undefined ? fetchedAtSec * 1000 : undefined,
      ageSeconds,
      // 从未同步过（无覆盖层）⇒ 按引擎口径「一定算过期」
      stale: ageSeconds === undefined ? true : ageSeconds > ENGINE_CATALOG_TTL_SECONDS,
      region: entry.region ?? '',
      vendorFamily: entry.vendorFamily ?? '',
    })
  }

  return {
    success: true,
    presets: ZENSKILL_PROVIDER_PRESETS.map(p => ({
      key: p.key,
      provider: p.provider,
      baseUrl: p.baseUrl,
      label: p.label,
      api: p.api,
      piOnly: p.piOnly,
      region: p.region ?? '',
      vendorFamily: p.vendorFamily ?? '',
    })),
    providers: entries,
  }
}

// ── 区域判定（P4）──────────────────────────────────────────────────

/** 取 base URL 的 host（小写） */
export function hostOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).hostname.toLowerCase()
  } catch {
    return ''
  }
}

/**
 * 可配置 provider 的端点视图。
 *
 * 来源 = 真相源的**目录段 + 预设段并集**：只有目录段的 provider 才有静态型号
 * 目录（mimo / gemini 就没有），但**每一个可配置的 provider 都要能按 host 反查**
 * ——否则「用户填的端点属于哪个 provider / 哪个区域」会查不到。
 */
export interface ProviderEndpoint {
  provider: string
  display: string
  baseUrl: string
  api: 'openai-completions' | 'anthropic-messages'
  region: string
  vendorFamily: string
}

export function providerEndpoints(): ProviderEndpoint[] {
  const fromCatalog: ProviderEndpoint[] = ZENSKILL_PROVIDER_CATALOG.map(e => ({
    provider: e.provider,
    display: e.display,
    baseUrl: e.baseUrl,
    api: e.api,
    region: e.region ?? '',
    vendorFamily: e.vendorFamily ?? '',
  }))
  const seen = new Set(fromCatalog.map(e => e.provider))
  const fromPresets: ProviderEndpoint[] = ZENSKILL_PROVIDER_PRESETS.filter(p => !seen.has(p.provider)).map(
    p => ({
      provider: p.provider,
      display: p.label,
      baseUrl: p.baseUrl,
      api: p.api,
      region: p.region ?? '',
      vendorFamily: p.vendorFamily ?? '',
    }),
  )
  return [...fromCatalog, ...fromPresets]
}

/** 取 base URL 的 path（去掉尾部斜杠；无 path ⇒ 空串） */
export function pathOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).pathname.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

/**
 * 按端点找真相源里的 provider。
 *
 * ⚠️ **不能只看 host**：MiniMax 国际站的两个端点同 host 不同 path ——
 * `https://api.minimax.io/v1`（openai 兼容）与 `https://api.minimax.io/anthropic`
 * （anthropic 兼容）⇒ 只按 host 匹配会把 anthropic 端点认成 openai 那个
 * ⇒ 区域诊断会指向错误的端点（2026-10-24 单测抓到）。
 *
 * 判据：host 命中后，若同 host 有多个端点 ⇒ 再按 path 精确匹配；
 * path 互不为前缀（如 /v1 vs /anthropic）⇒ 不猜，取同 host 第一个并由调用方
 * 用协议参数交叉验证。
 */
export function findCatalogEntryByBaseUrl(
  baseUrl: string,
  entries: ProviderEndpoint[] = providerEndpoints(),
): ProviderEndpoint | undefined {
  const host = hostOf(baseUrl)
  if (!host) return undefined
  const byHost = entries.filter(e => hostOf(e.baseUrl) === host)
  if (byHost.length === 0) return undefined
  if (byHost.length === 1) return byHost[0]
  const path = pathOf(baseUrl)
  const exact = byHost.find(e => pathOf(e.baseUrl) === path)
  if (exact) return exact
  const prefixed = byHost.find(e => {
    const ep = pathOf(e.baseUrl)
    return ep !== '' && (path.startsWith(ep) || ep.startsWith(path))
  })
  return prefixed ?? byHost[0]
}

/**
 * 找「同厂商族的另一个区域端点」。
 *
 * 只有同族（vendorFamily 相同）且**区域不同**的 provider 才是候选 ——
 * 跨厂商猜端点没有意义。
 *
 * 同族内**优先同协议**的候选：用户用的是 Anthropic 兼容端点时，
 * 换到同协议的兄弟端点最贴近原意（协议降级会让 Claude SDK 路径失效）。
 */
export function findSiblingRegionProvider(
  provider: string,
  entries: ProviderEndpoint[] = providerEndpoints(),
): ProviderEndpoint | undefined {
  const self = entries.find(e => e.provider === provider)
  if (!self || !self.vendorFamily || !self.region) return undefined
  const siblings = entries.filter(
    e => e.provider !== provider && e.vendorFamily === self.vendorFamily && e.region !== self.region,
  )
  return siblings.find(e => e.api === self.api) ?? siblings[0]
}

/**
 * 这个响应像不像「key 无效 / 区域不对」？
 *
 * MiniMax 实测：跨区 key → HTTP 401 + `invalid api key (2049)`。
 * 401 与 2049 都算；其他 4xx（如 400 unknown model）不算。
 */
export function isRegionMismatchResponse(status: number, body: string): boolean {
  if (status === 401) return true
  const text = (body || '').toLowerCase()
  return text.includes('invalid api key') || text.includes('(2049)')
}
