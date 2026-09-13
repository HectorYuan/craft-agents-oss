/**
 * ZenSkill MCP Source Seeding
 *
 * A fresh install ships the ZenSkill engine pack under resources/zenskill but
 * no user-facing configuration: sources are workspace data living under
 * ~/.zenskill/workspaces/<id>/sources/. This module seeds a ready-to-use
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
import { randomUUID } from 'crypto';
import { CONFIG_DIR } from '../config/paths.ts';
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

有生命的技能系统：把技能生态、GTD、记忆与成长体系作为 MCP 工具接入 ZenSkill。

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
        UV_PROJECT_ENVIRONMENT: join(CONFIG_DIR, 'zenskill', 'venv'),
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
 *
 * Self-heal (R6): when the source config already exists but points
 * mcp.command at a file that no longer exists (e.g. a uv path from a
 * pre-migration install location), the command/args/env are rewritten with
 * the current install's paths instead of being skipped forever.
 */
export function seedZenskillSource(workspaceRootPath: string): void {
  try {
    if (existsSync(getZenskillSeedDismissMarker())) return;

    const config = loadSourceConfig(workspaceRootPath, ZENSKILL_SOURCE_SLUG);

    if (!config) {
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

      const fresh = buildZenskillConfig();
      if (!fresh) return;

      saveSourceConfig(workspaceRootPath, fresh);
      saveSourceGuide(workspaceRootPath, ZENSKILL_SOURCE_SLUG, { raw: ZENSKILL_GUIDE });
      debug(`[zenskill-seed] Seeded ${ZENSKILL_SOURCE_SLUG} into ${workspaceRootPath}`);
      return;
    }

    // Source exists — repair stale engine paths left over from an old
    // install location (no-op when the configured command still exists).
    const engineDir = resolveEngineDir();
    const uvPath = resolveUvPath();
    if (!engineDir || !uvPath) {
      debug('[zenskill-seed] Self-heal skipped: engine pack or bundled uv not found');
      return;
    }
    if (applyZenskillSelfHeal(config, {
      uvPath,
      engineDir,
      venvDir: join(CONFIG_DIR, 'zenskill', 'venv'),
    })) {
      saveSourceConfig(workspaceRootPath, config);
      debug(
        `[zenskill-seed] Self-healed stale engine paths for ${ZENSKILL_SOURCE_SLUG} in ${workspaceRootPath}`
      );
    }
  } catch (error) {
    // Never block startup over seeding.
    debug(
      '[zenskill-seed] Failed:',
      error instanceof Error ? error.message : String(error)
    );
  }
}

/**
 * Rewrite a ZenSkill source config whose `mcp.command` points at a missing
 * file: command/args are replaced with the current install's uv + engine
 * pack paths, and UV_PROJECT_ENVIRONMENT is re-derived from CONFIG_DIR when
 * it references the legacy `.craft-agent` directory.
 *
 * Pure (no fs/IO apart from the caller's existsSync inputs decision) and
 * exported for tests. Returns true when `config` was mutated.
 */
export function applyZenskillSelfHeal(
  config: FolderSourceConfig,
  paths: { uvPath: string; engineDir: string; venvDir: string }
): boolean {
  const mcp = config.mcp;
  if (!mcp || mcp.transport !== 'stdio' || !mcp.command) return false;
  if (existsSync(mcp.command)) return false; // command still valid — nothing to heal

  mcp.command = paths.uvPath;
  mcp.args = [
    'run',
    '--project',
    paths.engineDir,
    '--python',
    '3.12',
    'zenskill',
    'mcp',
    'serve',
  ];

  const env = { ...mcp.env };
  if (
    !env.UV_PROJECT_ENVIRONMENT ||
    env.UV_PROJECT_ENVIRONMENT.includes('.craft-agent')
  ) {
    env.UV_PROJECT_ENVIRONMENT = paths.venvDir;
  }
  mcp.env = env;
  return true;
}
