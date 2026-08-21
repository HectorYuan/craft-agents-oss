/**
 * ZenSkill Provider Driver
 *
 * Minimal driver for the ZenSkill agent-engine backend.
 * ZenSkill manages its own LLM calls internally — no model fetching,
 * no credential validation, no runtime preparation needed here.
 */

import type { ProviderDriver } from '../driver-types.ts';
import type { BackendRuntimePayload } from '../driver-types.ts';

export const zenskillDriver: ProviderDriver = {
  provider: 'zenskill' as any,

  buildRuntime(): BackendRuntimePayload {
    // ZenSkill agent-engine handles everything internally
    // No special runtime paths needed
    return {};
  },
};
