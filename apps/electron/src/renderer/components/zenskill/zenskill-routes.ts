/**
 * ZenSkill route helpers — L1 route registry logic for the zenskill navigator.
 *
 * Pure data/logic module (no React imports) so shared/route-parser.ts can
 * delegate zenskill route parsing/building here without pulling in the
 * component tree.
 *
 * Route format (mirrors the pages navigator):
 *   zenskill            -> zenskill navigator, no page selected (registry default)
 *   zenskill/gtd        -> GTD workspace page
 *   zenskill/gtd?tab=x  -> GTD workspace page with initial tab (query is
 *                          stripped during parsing; tabs are in-page state)
 */
import type { ParsedCompoundRoute } from '../../../shared/route-parser'
import type { ZenSkillNavigationState } from '../../../shared/types'

export const ZENSKILL_ROUTE_PREFIX = 'zenskill'
export const ZENSKILL_PAGE_TYPE = 'zenskill-page'

/**
 * Parse a zenskill compound route from pre-split path segments.
 * segments[0] is guaranteed to be the 'zenskill' prefix by the caller.
 */
export function parseZenSkillCompoundRoute(segments: string[]): ParsedCompoundRoute {
  const page = segments[1]
  if (!page) {
    return { navigator: 'zenskill', details: null }
  }
  return { navigator: 'zenskill', details: { type: ZENSKILL_PAGE_TYPE, id: page } }
}

/** Build a zenskill route string from a parsed compound route. */
export function buildZenSkillRouteString(parsed: ParsedCompoundRoute): string {
  if (!parsed.details) return ZENSKILL_ROUTE_PREFIX
  return `${ZENSKILL_ROUTE_PREFIX}/${parsed.details.id}`
}

/** Convert a parsed compound route to the zenskill NavigationState member. */
export function zenskillCompoundToNavigationState(compound: ParsedCompoundRoute): ZenSkillNavigationState {
  return {
    navigator: 'zenskill',
    details: compound.details
      ? { type: ZENSKILL_PAGE_TYPE, pageSlug: compound.details.id }
      : null,
  }
}

/** Convert the zenskill NavigationState member back to a compound route. */
export function zenskillNavigationStateToCompoundRoute(state: ZenSkillNavigationState): ParsedCompoundRoute {
  return {
    navigator: 'zenskill',
    details: state.details
      ? { type: state.details.type, id: state.details.pageSlug }
      : null,
  }
}
