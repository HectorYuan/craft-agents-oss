/**
 * ZenSkill model catalog (extracted from models.ts MODEL_REGISTRY).
 *
 * Single source of truth for shipped model definitions in this distribution.
 * models.ts re-exports this as MODEL_REGISTRY.
 */

import type { ModelDefinition } from './models.ts';

export const ZENSKILL_MODEL_REGISTRY: ModelDefinition[] = [
  // ----------------------------------------
  // Anthropic Claude Models
  // ----------------------------------------
  {
    id: 'claude-opus-4-8',
    name: 'Opus 4.8',
    shortName: 'Opus',
    description: 'Most capable for complex work',
    descriptionKey: 'model.opusDesc',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'claude-opus-4-7',
    name: 'Opus 4.7',
    shortName: 'Opus',
    description: 'Previous Opus generation',
    descriptionKey: 'model.opusDesc',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  // TODO(opus-4.6-sunset): remove this entry when Opus 4.6 is deprecated by
  // Anthropic. Also drop the related 4.6 pieces in llm-connections.ts
  // PI_PREFERRED_DEFAULTS and the restoreOpus46ToAnthropicConnections
  // migration in storage.ts (grep for TODO(opus-4.6-sunset) to find them all).
  {
    id: 'claude-opus-4-6',
    name: 'Opus 4.6',
    // shortName intentionally collides with 4.8/4.7. Those are listed first,
    // so findModelIdByShortName('Opus') keeps returning 4.8 — zero behavior
    // change for callers that reference "Opus" abstractly.
    shortName: 'Opus',
    description: 'Previous Opus release',
    descriptionKey: 'model.opusDesc',
    provider: 'zenskill',
    contextWindow: 200_000,
  },
  {
    id: 'claude-sonnet-5',
    name: 'Sonnet 5',
    shortName: 'Sonnet',
    description: 'Best combination of speed and intelligence',
    descriptionKey: 'model.sonnetDesc',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'claude-sonnet-4-6',
    name: 'Sonnet 4.6',
    shortName: 'Sonnet',
    description: 'Previous Sonnet generation',
    descriptionKey: 'model.sonnetDesc',
    provider: 'zenskill',
    contextWindow: 200_000,
  },
  {
    id: 'claude-haiku-4-5-20251001',
    name: 'Haiku 4.5',
    shortName: 'Haiku',
    description: 'Fastest for quick answers',
    descriptionKey: 'model.haikuDesc',
    provider: 'zenskill',
    contextWindow: 200_000,
  },
  {
    id: 'claude-fable-5-1',
    name: 'Fable 5.1',
    shortName: 'Fable',
    description: 'Next-generation model for complex work',
    descriptionKey: 'model.fableDesc',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
  {
    id: 'claude-fable-5',
    name: 'Fable 5',
    // shortName intentionally collides with 5.1, which is listed first, so
    // findModelIdByShortName('Fable') resolves to the newest Fable.
    shortName: 'Fable',
    description: 'Previous Fable generation',
    descriptionKey: 'model.fableDesc',
    provider: 'zenskill',
    contextWindow: 1_000_000,
  },
];
