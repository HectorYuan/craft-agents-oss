import { registerPiModelResolver } from '../../src/config/llm-connections.ts'

// P1b: the pi-ai SDK is removed — migration tests register a static catalog
// covering the model IDs the storage-migration assertions depend on
// (anthropic + openrouter families). The SDK catalog no longer drifts
// (models.dev uplifts are gone with the SDK), so a static table is stable.
const STATIC_CATALOGS: Record<string, Array<{ id: string; name: string; shortName: string; description: string; provider: 'zenskill'; contextWindow: number }>> = {
  anthropic: [
    { id: 'pi/claude-opus-4-8', name: 'Claude Opus 4.8', shortName: 'Opus 4.8', description: 'anthropic model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
    { id: 'pi/claude-opus-4-7', name: 'Claude Opus 4.7', shortName: 'Opus 4.7', description: 'anthropic model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
    { id: 'pi/claude-opus-4-6', name: 'Claude Opus 4.6', shortName: 'Opus 4.6', description: 'anthropic model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
    { id: 'pi/claude-sonnet-4-6', name: 'Claude Sonnet 4.6', shortName: 'Sonnet 4.6', description: 'anthropic model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
    { id: 'pi/claude-haiku-4-5', name: 'Claude Haiku 4.5', shortName: 'Haiku 4.5', description: 'anthropic model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
  ],
  openrouter: [
    { id: 'pi/openrouter/auto', name: 'OpenRouter Auto', shortName: 'Auto', description: 'openrouter model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
    { id: 'pi/openrouter/claude-sonnet-4.6', name: 'Claude Sonnet 4.6 (OpenRouter)', shortName: 'Sonnet 4.6 OR', description: 'openrouter model via Craft Agents Backend', provider: 'zenskill', contextWindow: 200000 },
  ],
}

registerPiModelResolver((piAuthProvider?: string) =>
  piAuthProvider
    ? STATIC_CATALOGS[piAuthProvider] ?? []
    : Object.values(STATIC_CATALOGS).flat(),
)
