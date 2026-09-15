export type RecentDirScenario = 'none' | 'few' | 'many'

const RECENT_DIR_SCENARIO_DATA: Record<RecentDirScenario, string[]> = {
  none: [],
  few: [
    '/Users/demo/projects/zenskill',
    '/Users/demo/projects/zenskill/apps/electron',
    '/Users/demo/projects/zenskill/packages/shared',
  ],
  many: [
    '/Users/demo/projects/zenskill',
    '/Users/demo/projects/zenskill/apps/electron',
    '/Users/demo/projects/zenskill/apps/viewer',
    '/Users/demo/projects/zenskill/apps/cli',
    '/Users/demo/projects/zenskill/packages/shared',
    '/Users/demo/projects/zenskill/packages/server-core',
    '/Users/demo/projects/zenskill/packages/pi-agent-server',
    '/Users/demo/projects/zenskill/packages/ui',
    '/Users/demo/projects/zenskill/scripts',
  ],
}

/** Return a copy of the fixture list for the selected scenario. */
export function getRecentDirsForScenario(scenario: RecentDirScenario): string[] {
  return [...RECENT_DIR_SCENARIO_DATA[scenario]]
}
