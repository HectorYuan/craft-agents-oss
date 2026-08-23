/**
 * Zenskill Model Fetcher
 *
 * ZenSkill manages its own model list internally.
 * This fetcher returns the default models without remote API calls.
 */

import type { ModelFetcher, ModelFetchResult, LlmConnection, ModelFetcherCredentials } from '@craft-agent/shared/config'

export class ZenskillModelFetcher implements ModelFetcher {
  readonly refreshIntervalMs = 0 // No periodic refresh — models are static

  async fetchModels(_connection: LlmConnection, _credentials: ModelFetcherCredentials): Promise<ModelFetchResult> {
    return {
      models: [
        {
          id: 'deepseek/deepseek-v4-flash',
          name: 'DeepSeek V4 Flash',
          shortName: 'V4 Flash',
          description: 'Fast reasoning model via ZenSkill agent-engine',
          provider: 'zenskill' as any,
          contextWindow: 1000000,
          supportsThinking: true,
        },
        {
          id: 'deepseek/deepseek-v4-pro',
          name: 'DeepSeek V4 Pro',
          shortName: 'V4 Pro',
          description: 'Pro reasoning model via ZenSkill agent-engine',
          provider: 'zenskill' as any,
          contextWindow: 1000000,
          supportsThinking: true,
        },
        {
          id: 'deepseek/deepseek-chat',
          name: 'DeepSeek Chat',
          shortName: 'Chat',
          description: 'General chat model via ZenSkill agent-engine',
          provider: 'zenskill' as any,
          contextWindow: 1000000,
        },
        {
          id: 'deepseek/deepseek-reasoner',
          name: 'DeepSeek Reasoner',
          shortName: 'Reasoner',
          description: 'Deep reasoning model via ZenSkill agent-engine',
          provider: 'zenskill' as any,
          contextWindow: 1000000,
          supportsThinking: true,
        },
      ],
    }
  }
}
