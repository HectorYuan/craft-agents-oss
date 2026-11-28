/**
 * `run:submit` 派发表单的纯逻辑（D4）。
 *
 * 与渲染分离，便于单测：把「表单字符串」收敛成契约请求，或给出唯一一个
 * 失败键。前端只做体验级校验——空白标题、数值范围；capId 白名单、budget
 * 语义、会话可见性仍由服务端 `_run_submit` 判定（不复制 Python 逻辑）。
 */

import type { RunSubmitRequest } from '@craft-agent/shared/protocol'

/**
 * 可派发的 capId 列表。
 *
 * 真相源是 `specs/swarm_integration_contract_v1.yaml` 的
 * `capability_scope.declared_by`（只列声明了 `allow_tools` 的 cap）；
 * 这里只是渲染下拉的镜像，服务端才是权威校验。仓库侧有跨语言一致性
 * 用例（`tests/server/test_swarm_contract_consistency.py`）盯着这个常量。
 */
export const RUN_SUBMIT_CAP_IDS = ['zenswarm-runtime'] as const

export const RUN_SUBMIT_MAX_STEPS = { min: 1, max: 200 } as const
export const RUN_SUBMIT_TIMEOUT_SEC = { min: 1, max: 86400 } as const

/** 表单的原始字符串；数值字段的空串表示「不传」。 */
export interface RunSubmitFormValues {
  title: string
  description: string
  capId: string
  maxSteps: string
  timeoutSec: string
}

export type RunSubmitErrorKey =
  | 'chat.runSubmitInvalidTitle'
  | 'chat.runSubmitInvalidCap'
  | 'chat.runSubmitInvalidMaxSteps'
  | 'chat.runSubmitInvalidTimeout'

export type ParseRunSubmitResult =
  | { ok: true; request: RunSubmitRequest }
  | { ok: false; error: RunSubmitErrorKey }

/** 严格整数：仅接受 `^-?\d+$`；小数、科学计数法、空白一律判非法。 */
function parseRange(raw: string, min: number, max: number): { value?: number; invalid: boolean } {
  const trimmed = raw.trim()
  if (!trimmed) return { invalid: false, value: undefined }
  if (!/^\d+$/.test(trimmed)) return { invalid: true }
  const n = Number(trimmed)
  if (!Number.isSafeInteger(n) || n < min || n > max) return { invalid: true }
  return { value: n, invalid: false }
}

/**
 * 校验并构造 `run:submit` 请求。
 *
 * 空白标题、超范围数值各返回唯一键（UI 就地提示，popover 不收起）；
 * 数值字段留空则整个 `budget` 键省略，不发送 `{maxSteps: null}`。
 */
export function parseRunSubmitInput(
  values: RunSubmitFormValues,
  sessionId?: string,
): ParseRunSubmitResult {
  const title = values.title.trim()
  if (!title) return { ok: false, error: 'chat.runSubmitInvalidTitle' }

  const capId = values.capId
  if (!capId || !(RUN_SUBMIT_CAP_IDS as readonly string[]).includes(capId)) {
    return { ok: false, error: 'chat.runSubmitInvalidCap' }
  }

  const maxSteps = parseRange(values.maxSteps, RUN_SUBMIT_MAX_STEPS.min, RUN_SUBMIT_MAX_STEPS.max)
  if (maxSteps.invalid) return { ok: false, error: 'chat.runSubmitInvalidMaxSteps' }

  const timeout = parseRange(values.timeoutSec, RUN_SUBMIT_TIMEOUT_SEC.min, RUN_SUBMIT_TIMEOUT_SEC.max)
  if (timeout.invalid) return { ok: false, error: 'chat.runSubmitInvalidTimeout' }

  const description = values.description.trim()
  const taskContract: RunSubmitRequest['taskContract'] = { title }
  if (description) taskContract.description = description

  const budget: NonNullable<RunSubmitRequest['budget']> = {}
  if (maxSteps.value !== undefined) budget.maxSteps = maxSteps.value
  if (timeout.value !== undefined) budget.timeoutSec = timeout.value

  const request: RunSubmitRequest = { taskContract, capId }
  if (Object.keys(budget).length > 0) request.budget = budget
  if (sessionId) request.sessionId = sessionId

  return { ok: true, request }
}

/** 提交按钮是否可按（只认空白标题；范围错误在提交时就地提示）。 */
export function canSubmitRunSubmitForm(values: RunSubmitFormValues): boolean {
  return values.title.trim().length > 0
}
