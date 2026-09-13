/**
 * ZenSkill model catalog (extracted from models.ts MODEL_REGISTRY).
 *
 * Single source of truth for shipped model definitions in this distribution.
 * models.ts re-exports this as MODEL_REGISTRY.
 *
 * The catalog mirrors the engine's real model list: IDs use the
 * `provider/model` form the ZenSkill agent-engine resolves
 * (see zenskill/runtime/agent/providers resolve_model()) and match
 * packages/server-core/src/model-fetchers/zenskill.ts one-to-one.
 */

import type { ModelDefinition } from './models.ts';

export const ZENSKILL_MODEL_REGISTRY: ModelDefinition[] = [
  // ----------------------------------------
  // DeepSeek Models (via ZenSkill agent-engine)
  // ----------------------------------------
  {
    id: 'deepseek/deepseek-v4-flash',
    name: 'DeepSeek V4 Flash',
    shortName: 'V4 Flash',
    description: 'Fast reasoning model via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
    supportsThinking: true,
  },
  {
    id: 'deepseek/deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    shortName: 'V4 Pro',
    description: 'Pro reasoning model via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
    supportsThinking: true,
  },
  {
    id: 'deepseek/deepseek-chat',
    name: 'DeepSeek Chat',
    shortName: 'Chat',
    description: 'General chat model via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'deepseek/deepseek-reasoner',
    name: 'DeepSeek Reasoner',
    shortName: 'Reasoner',
    description: 'Deep reasoning model via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
    supportsThinking: true,
  },
];
