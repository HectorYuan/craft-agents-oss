/**
 * Centralized branding assets for ZenSkill
 * Used by OAuth callback pages
 */

export const CRAFT_LOGO = [
  '███████╗███████╗███╗   ██╗███████╗██╗  ██╗██╗██╗     ██╗     ██╗',
  '██╔════╝██╔════╝████╗  ██║██╔════╝██║  ██║██║██║     ██║     ██║',
  '███████╗█████╗  ██╔██╗ ██║███████╗███████║██║██║     ██║     ██║',
  '╚════██║██╔══╝  ██║╚██╗██║╚════██║██╔══██║██║██║     ██║     ╚═╝',
  '███████║███████╗██║ ╚████║███████║██║  ██║██║███████╗███████╗██╗',
  '╚══════╝╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝╚═╝╚══════╝╚══════╝╚═╝',
] as const;

/** Logo as a single string for HTML templates */
export const CRAFT_LOGO_HTML = CRAFT_LOGO.map((line) => line.trimEnd()).join('\n');

/** Session viewer base URL — upstream viewer does not exist for ZenSkill;
 *  point at the product repository instead so links land somewhere real. */
export const VIEWER_URL = 'https://github.com/HectorYuan/ZenSkill';
