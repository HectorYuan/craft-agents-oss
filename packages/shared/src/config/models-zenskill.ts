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
 *
 * 2026-10-06 国产补全：mimo/qwen/volc/gemini/moonshot/minimax/glm/ollama
 */

import type { ModelDefinition } from './models.ts';

export const ZENSKILL_MODEL_REGISTRY: ModelDefinition[] = [
  // ----------------------------------------
  // Xiaomi MiMo Models (via ZenSkill agent-engine, OpenAI-compatible endpoint)
  // ----------------------------------------
  {
    id: 'mimo/mimo-v2.6-flash',
    name: 'MiMo V2.6 Flash',
    shortName: 'V2.6 Flash',
    description: 'Xiaomi MiMo flash reasoning model via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
    supportsThinking: true,
  },
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
  // ----------------------------------------
  // Qwen Models (via ZenSkill agent-engine, OpenAI-compatible)
  // ----------------------------------------
  {
    id: 'qwen/qwen3-max',
    name: 'Qwen3 Max',
    shortName: 'Qwen3 Max',
    description: 'Flagship Qwen3 via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 262144,
    supportsThinking: true,
  },
  {
    id: 'qwen/qwen-plus',
    name: 'Qwen Plus',
    shortName: 'Qwen Plus',
    description: 'Balanced Qwen via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 131072,
  },
  {
    id: 'qwen/qwen-turbo',
    name: 'Qwen Turbo',
    shortName: 'Qwen Turbo',
    description: 'Fast Qwen via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 131072,
  },
  {
    id: 'qwen/qwen-coder-plus',
    name: 'Qwen Coder Plus',
    shortName: 'Qwen Coder',
    description: 'Code-specialized Qwen via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 131072,
  },
  // ----------------------------------------
  // Volcengine Models (Doubao)
  // ----------------------------------------
  {
    id: 'volc/doubao-pro-32k',
    name: 'Doubao Pro 32k',
    shortName: 'Doubao Pro',
    description: 'Flagship Doubao via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 32000,
  },
  {
    id: 'volc/doubao-lite-32k',
    name: 'Doubao Lite 32k',
    shortName: 'Doubao Lite',
    description: 'Fast Doubao via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 32000,
  },
  {
    id: 'volc/doubao-1-5-pro-32k',
    name: 'Doubao 1.5 Pro',
    shortName: 'Doubao 1.5',
    description: 'Improved Doubao via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 32000,
  },
  // ----------------------------------------
  // Gemini Models (via OpenAI-compatible proxy)
  // ----------------------------------------
  {
    id: 'gemini/gemini-2.5-pro',
    name: 'Gemini 2.5 Pro',
    shortName: 'Gemini 2.5 Pro',
    description: 'Flagship Gemini via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
    supportsThinking: true,
  },
  {
    id: 'gemini/gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    shortName: 'Gemini 2.5 Flash',
    description: 'Fast Gemini via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'gemini/gemini-2.0-flash',
    name: 'Gemini 2.0 Flash',
    shortName: 'Gemini 2.0',
    description: 'Stable Gemini via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  // ----------------------------------------
  // Moonshot / Kimi Models
  // ----------------------------------------
  {
    id: 'moonshot/kimi-k2-0905-preview',
    name: 'Kimi K2 Preview',
    shortName: 'Kimi K2',
    description: 'Flagship Kimi via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 256000,
  },
  {
    id: 'moonshot/kimi-k2-0711-preview',
    name: 'Kimi K2 0711',
    shortName: 'Kimi K2 0711',
    description: 'Kimi K2 0711 snapshot via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 200000,
  },
  // ----------------------------------------
  // MiniMax Models (overseas + CN)
  // ----------------------------------------
  {
    id: 'minimax/MiniMax-Text-01',
    name: 'MiniMax Text 01',
    shortName: 'MiniMax Text',
    description: 'Flagship MiniMax via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'minimax/abab6.5s-chat',
    name: 'MiniMax ABAB 6.5s',
    shortName: 'ABAB 6.5s',
    description: 'MiniMax ABAB via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
  },
  {
    id: 'minimax-cn/MiniMax-Text-01',
    name: 'MiniMax Text 01 (CN)',
    shortName: 'MiniMax CN',
    description: 'Domestic MiniMax via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  // ----------------------------------------
  // Zhipu GLM Models
  // ----------------------------------------
  {
    id: 'glm/glm-4-plus',
    name: 'GLM-4 Plus',
    shortName: 'GLM-4 Plus',
    description: 'Flagship Zhipu GLM via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
    supportsThinking: true,
  },
  {
    id: 'glm/glm-4-air',
    name: 'GLM-4 Air',
    shortName: 'GLM-4 Air',
    description: 'Balanced GLM via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
  },
  {
    id: 'glm/glm-4-flash',
    name: 'GLM-4 Flash',
    shortName: 'GLM-4 Flash',
    description: 'Free GLM via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
  },
  {
    id: 'glm/glm-4v-plus',
    name: 'GLM-4V Plus (Vision)',
    shortName: 'GLM-4V',
    description: 'Vision-capable GLM via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
  },
  // ----------------------------------------
  // Ollama Models (local)
  // ----------------------------------------
  {
    id: 'ollama/llama3.2',
    name: 'Llama 3.2 (Local)',
    shortName: 'Llama 3.2',
    description: 'Local Ollama Llama via ZenSkill agent-engine',
    provider: 'zenskill',
    contextWindow: 128000,
  },
];