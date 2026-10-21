/**
 * 线上型号目录（Model Catalog）—— 纯函数部分
 *
 * 2026-10-22 用户报障：minimax「不支持最新 m3.0 / m3.1-flash」「没有有效的信息更新机制」。
 * 根因之一：GUI 的型号表是**静态硬编码**，用户只能手写型号 id；
 * 而线上并不存在 "MiniMax-M3.0"（未知型号 → HTTP 400 unknown model (2013)）。
 *
 * 本模块给出 GUI 侧「有效的信息更新机制」的纯逻辑：
 *   1. buildModelsUrl()   —— 按协议拼线上型号清单 URL
 *   2. parseModelsPayload() —— 解析 data[].id（兼容裸字符串数组）
 *   3. extractServerMessage() —— 从厂商错误体里取出人能看懂的一句原文
 *
 * 网络部分在 handler（llm-connections.ts）里，避免纯函数依赖 fetch。
 *
 * 端点与协议形状（2026-10-22 对 MiniMax 实测）：
 *   openai 兼容   base=https://api.minimaxi.com/v1        → GET {base}/models
 *   anthropic 兼容 base=https://api.minimax.cn/anthropic   → GET {base}/v1/models
 * 两条路由实测都返回同一批 9 个型号。
 */

/** 端点协议（与 CustomEndpointApi 同形） */
export type CatalogProtocol = 'openai-completions' | 'anthropic-messages'

/**
 * 拼线上型号清单 URL。
 *
 * openai 兼容：base 已含 /v1 → {base}/models
 * anthropic 兼容：base 形如 .../anthropic → {base}/v1/models
 */
export function buildModelsUrl(baseUrl: string, protocol: CatalogProtocol = 'openai-completions'): string {
  const base = (baseUrl || '').trim().replace(/\/+$/, '')
  if (!base) return ''
  if (protocol === 'anthropic-messages') return `${base}/v1/models`
  return `${base}/models`
}

/**
 * 解析型号清单响应体 → 型号 id 列表。
 * 兼容两种形状：{ data: [{ id }] } 与 { data: ["id"] }。
 * 返回空数组表示形状不对（调用方据此报错，不要静默当空目录）。
 */
export function parseModelsPayload(raw: string): string[] {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return []
  }
  const items = (data as { data?: unknown })?.data
  if (!Array.isArray(items)) return []
  const ids: string[] = []
  for (const item of items) {
    if (typeof item === 'string' && item) {
      ids.push(item)
    } else if (item && typeof item === 'object') {
      const id = (item as { id?: unknown; name?: unknown }).id ?? (item as { name?: unknown }).name
      if (typeof id === 'string' && id) ids.push(id)
    }
  }
  return ids
}

/**
 * 从厂商错误体里取出人能看懂的一句原文。
 * 例：{"error":{"message":"invalid api key (2049)"}} → "invalid api key (2049)"
 */
export function extractServerMessage(raw: string): string | undefined {
  const quoted = raw.match(/"message"\s*:\s*"([^"]+)"/)
  if (quoted?.[1]) return quoted[1]
  // "invalid params, unknown model 'minimax-m3.0' (2013)" —— 型号名在引号**外**
  const unknownModel = raw.match(/unknown model\s+'([^']+)'(\s*\(\d+\))?/i)
  if (unknownModel) return `unknown model '${unknownModel[1]}'${unknownModel[2] ?? ''}`
  // "invalid api key (2049)"
  const invalidKey = raw.match(/invalid api key\s*\((\d+)\)/i)
  if (invalidKey) return `invalid api key (${invalidKey[1]})`
  const single = raw.match(/'([^']*(?:model|key)[^']*)'/i)
  if (single?.[1]) return single[1]
  return undefined
}

/**
 * 校验型号是否在厂商线上目录中。
 *
 * 返回 { ok: true } 表示通过；
 * { ok: false, reason: 'not-listed' } 表示型号不在目录里；
 * { ok: true, unknown: true } 表示目录拉取失败/不可用 ⇒ **不做阻断**（不能因目录不可知就拦住配置）。
 *
 * 注意（2026-10-22 实测）：Anthropic 兼容路由对未知型号会**静默归一化**
 * （请求 MiniMax-M3.0 → 200 且实际返回 model=MiniMax-M3.1-Flash），
 * 所以 anthropic 协议下型号不在目录**不是错误**，只作提示。
 */
export function checkModelAgainstCatalog(
  model: string | undefined,
  catalog: string[] | undefined | null,
  protocol: CatalogProtocol = 'openai-completions',
): { ok: boolean; reason?: 'not-listed'; unknown?: boolean } {
  const id = (model || '').trim()
  if (!id) return { ok: true }
  if (!catalog || catalog.length === 0) return { ok: true, unknown: true }
  if (catalog.includes(id)) return { ok: true }
  // anthropic 兼容路由会自行归一化未知型号 ⇒ 不阻断
  if (protocol === 'anthropic-messages') return { ok: true }
  return { ok: false, reason: 'not-listed' }
}
