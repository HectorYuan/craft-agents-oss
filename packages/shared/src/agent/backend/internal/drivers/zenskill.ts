import type { ProviderDriver } from '../driver-types.ts';

/**
 * ZenSkill engine driver.
 *
 * The engine is a self-contained subprocess (zenskill-cmd wrapper → bundled
 * uv → `zenskill agent-engine serve`): no host-runtime staging, no
 * driver-level model fetching (models come from the LLM connection), and no
 * driver-level connection test — the generic mini-completion test through
 * ZenskillAgent exercises the real engine end to end.
 */
export const zenskillDriver: ProviderDriver = {
  provider: 'zenskill',
  buildRuntime() {
    return {};
  },
};
