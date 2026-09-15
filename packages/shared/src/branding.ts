/**
 * Centralized branding assets for ZenSkill
 * Used by OAuth callback pages
 */

export const ZENSKILL_LOGO = [
  '   ╭────────────────────────────────╮',
  '   │  ZenSkill  ·  Z-core           │',
  '   ╰────────────────────────────────╯',
  '      skill-driven personal OS',
] as const;

/** Logo as a single string for HTML templates */
export const ZENSKILL_LOGO_HTML = ZENSKILL_LOGO.map((line) => line.trimEnd()).join('\n');

/** Session viewer base URL */
export const VIEWER_URL = 'https://github.com/HectorYuan/ZenSkill#readme';
