/**
 * ZenSkill MCP Source Seeding
 *
 * A fresh install ships the ZenSkill engine pack under resources/zenskill but
 * no user-facing configuration: sources are workspace data living under
 * ~/.craft-agent/workspaces/<id>/sources/. This module seeds a ready-to-use
 * ZenSkill MCP source into workspaces that don't have one, so ZenSkill tools
 * (GTD inbox, memory, skills, growth) resolve out of the box.
 *
 * The slug MUST stay "zenskill-4": it is hardcoded in the renderer (the
 * "ZenSkill Data" panel keys off sourceSlug === 'zenskill-4') and in backend
 * system prompts (tool prefix mcp__zenskill-4__*).
 *
 * The engine pack runs through uv (`uv run --project <pack> zenskill mcp serve`)
 * — never by executing __main__.py directly, which fails on relative imports.
 * UV_PROJECT_ENVIRONMENT pins the venv to a per-user writable dir so packaged
 * installs under read-only locations don't try to create .venv inside the app.
 */

import { existsSync, readdirSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import { randomUUID } from 'crypto';
import type { FolderSourceConfig } from './types.ts';
import {
  getZenskillSeedDismissMarker,
  loadSourceConfig,
  saveSourceConfig,
  saveSourceGuide,
} from './storage.ts';
import { getBundledAssetsDir } from '../utils/paths.ts';
import { debug } from '../utils/debug.ts';

/**
 * Packaged canonical layout: electron-builder ships the engine pack and uv
 * under <resourcesPath>/app/resources/ (win.files excludes the dist/resources
 * duplicate on Windows). getBundledAssetsDir only sees the dist copy, so try
 * resourcesPath first when running inside Electron.
 */
function packagedAppResource(subpath: string): string | null {
  const resourcesPath = (process as unknown as { resourcesPath?: string }).resourcesPath;
  if (!resourcesPath) return null;
  const p = join(resourcesPath, 'app', 'resources', subpath);
  return existsSync(p) ? p : null;
}

function resolveEngineDir(): string | null {
  return packagedAppResource('zenskill') ?? getBundledAssetsDir('zenskill') ?? null;
}

function resolveUvPath(): string | null {
  const archDir = `${process.platform}-${process.arch}`;
  const exeName = process.platform === 'win32' ? 'uv.exe' : 'uv';

  const packaged = packagedAppResource(join('bin', archDir, exeName));
  if (packaged) return packaged;

  const binDir = getBundledAssetsDir('bin');
  if (!binDir) return null;
  const uvPath = join(binDir, archDir, exeName);
  return existsSync(uvPath) ? uvPath : null;
}

export const ZENSKILL_SOURCE_SLUG = 'zenskill-4';

/** guide.md shown next to the source in the UI and referenced by api-tools. */
const ZENSKILL_GUIDE = `# ZenSkill

有生命的技能系统：把技能生态、GTD、记忆与成长体系作为 MCP 工具接入 Craft Agents。

工具前缀为 \`mcp__zenskill-4__*\`，例如 \`mcp__zenskill-4__skill_search\`。

## 能力概览

- **技能生态**：skill_search / skill_browse / skill_install / skill_context
- **GTD**：gtd_capture / gtd_inbox_list / action_add / action_done / project_list
- **记忆**：memory_remember / memory_list / memory_search
- **成长**：growth_report / growth_milestone / growth_dashboard / achievement_list
- **陪伴感**：energy_level / context_guide / companion_summary / proactive_insight

## 惯例

收到用户任务时优先调用 growth_report（或 growth_milestone 检测境界突破），
按 "📈 [skill] 成长：[old_level] → [new_level] (+N)" 格式向用户报告。
`;

function buildZenskillConfig(): FolderSourceConfig | null {
  const engineDir = resolveEngineDir();
  const uvPath = resolveUvPath();
  if (!engineDir || !uvPath) {
    debug('[zenskill-seed] Engine pack or bundled uv not found, skipping seed');
    return null;
  }

  return {
    id: randomUUID(),
    name: 'ZenSkill',
    slug: ZENSKILL_SOURCE_SLUG,
    enabled: true,
    provider: 'zenskill',
    type: 'mcp',
    icon: '🧘',
    tagline: 'GTD 收集、记忆、技能生态与成长报告',
    mcp: {
      transport: 'stdio',
      command: uvPath,
      args: [
        'run',
        '--project',
        engineDir,
        '--python',
        '3.12',
        'zenskill',
        'mcp',
        'serve',
      ],
      env: {
        // Keep uv's virtualenv out of a potentially read-only install dir.
        UV_PROJECT_ENVIRONMENT: join(homedir(), '.craft-agent', 'zenskill', 'venv'),
      },
    },
    isAuthenticated: true,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

/**
 * Seed the ZenSkill MCP source into a workspace if it has none.
 * Idempotent; safe to call for every workspace on every startup.
 */
export function seedZenskillSource(workspaceRootPath: string): void {
  try {
    if (existsSync(getZenskillSeedDismissMarker())) return;

    const sourcesDir = join(workspaceRootPath, 'sources');
    const existing = existsSync(sourcesDir)
      ? readdirSync(sourcesDir).filter((s) => s.startsWith('zenskill'))
      : [];
    if (existing.length > 0) {
      debug(
        `[zenskill-seed] Workspace already has ZenSkill source(s): ${existing.join(', ')}`
      );
      return;
    }

    if (loadSourceConfig(workspaceRootPath, ZENSKILL_SOURCE_SLUG)) return;

    const config = buildZenskillConfig();
    if (!config) return;

    saveSourceConfig(workspaceRootPath, config);
    saveSourceGuide(workspaceRootPath, ZENSKILL_SOURCE_SLUG, { raw: ZENSKILL_GUIDE });
    debug(`[zenskill-seed] Seeded ${ZENSKILL_SOURCE_SLUG} into ${workspaceRootPath}`);
  } catch (error) {
    // Never block startup over seeding.
    debug(
      '[zenskill-seed] Failed:',
      error instanceof Error ? error.message : String(error)
    );
  }
}
