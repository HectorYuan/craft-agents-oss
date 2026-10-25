/**
 * ZenSkill model catalog — **由真相源生成**（B15，2026-10-25）。
 *
 * 数据来自主仓 `specs/providers.yaml`（provider 唯一真相源），由
 * `scripts/sync_provider_registry.py` 生成到 `models-zenskill.generated.ts`；
 * 本文件只做转接 —— **不要在这里手写型号**。
 *
 * 为什么不再手写（此前两份手写清单的问题）：
 *   ① 本文件与 `packages/server-core/src/model-fetchers/zenskill.ts` 各手写
 *      一份 4 条 deepseek 清单 ⇒ 目录里只有 deepseek，其余 14 个厂商
 *      （mimo / qwen / volc / glm / minimax / moonshot …）的型号在 GUI 里
 *      **根本不存在**（选型列表里没有国产型号）；
 *   ② 不在表里的型号会被 `agent/backend/zenskill-agent.ts` 静默替换成
 *      DEFAULT_MODEL ⇒ **用户选的国产型号直接被顶掉**。
 *
 * 型号 id 形如 `provider/model`，与引擎 resolve_model() 的解析形式一致。
 */

import type { ModelDefinition } from './models.ts';
import { ZENSKILL_MODEL_DEFINITIONS } from './models-zenskill.generated.ts';

export { ZENSKILL_MODEL_DEFINITIONS };

/**
 * GUI 侧型号目录。
 * zenskill 分发里所有厂商的型号都归 zenskill provider（ModelProvider = 'zenskill'），
 * 但 id 保留 `provider/model` 前缀 —— 引擎按该形式解析，且 region 变体
 * （minimax / minimax-cn）可据此区分，避免同名型号跨端点串路由。
 */
export const ZENSKILL_MODEL_REGISTRY: ModelDefinition[] = ZENSKILL_MODEL_DEFINITIONS;
