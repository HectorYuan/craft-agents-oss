/**
 * Zenskill Model Fetcher
 *
 * ZenSkill manages its own model list internally.
 * This fetcher returns the default models without remote API calls.
 *
 * 型号目录来自**真相源生成物**（主仓 `specs/providers.yaml` →
 * `scripts/sync_provider_registry.py` → shared/config/models-zenskill.generated.ts），
 * **不再手写第二份清单**。
 *
 * B15（2026-10-25）：此前本文件与 `shared/config/models-zenskill.ts` 各手写
 * 一份 4 条 deepseek 清单 ⇒ ① 目录里只有 deepseek，mimo / qwen / volc / glm /
 * minimax / moonshot 等厂商的型号在 GUI 里**根本不存在**；② 不在表里的型号
 * 会被 `agent/backend/zenskill-agent.ts` 静默替换成 DEFAULT_MODEL
 * ⇒ **用户选的国产型号直接被顶掉**。现在两个消费点共用同一份生成物。
 */

import type { ModelFetcher, ModelFetchResult, LlmConnection, ModelFetcherCredentials } from '@craft-agent/shared/config'
import { MODEL_REGISTRY } from '@craft-agent/shared/config'

export class ZenskillModelFetcher implements ModelFetcher {
  readonly refreshIntervalMs = 0 // No periodic refresh — models are static

  async fetchModels(_connection: LlmConnection, _credentials: ModelFetcherCredentials): Promise<ModelFetchResult> {
    return { models: MODEL_REGISTRY }
  }
}
