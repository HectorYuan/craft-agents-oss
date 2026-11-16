/**
 * ZenSkill MCP Source Seeding
 *
 * A fresh install ships the ZenSkill engine pack under resources/zenskill but
 * no user-facing configuration: sources are workspace data living under
 * ~/.zenskill/workspaces/<id>/sources/. This module seeds a ready-to-use
 * ZenSkill MCP source into workspaces that don't have one, so ZenSkill tools
 * (GTD inbox, memory, skills, growth) resolve out of the box.
 *
 * The slug MUST stay "zenskill": it is hardcoded in the renderer (the
 * "ZenSkill Data" panel keys off sourceSlug === 'zenskill') and in backend
 * system prompts (tool prefix mcp__zenskill__*).
 *
 * The engine pack runs through uv (`uv run --project <pack> zenskill mcp serve`)
 * — never by executing __main__.py directly, which fails on relative imports.
 * UV_PROJECT_ENVIRONMENT pins the venv to a per-user writable dir so packaged
 * installs under read-only locations don't try to create .venv inside the app.
 */

import {
  copyFileSync,
  existsSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from 'fs';
import { join } from 'path';
import { randomUUID } from 'crypto';
import { CONFIG_DIR } from '../config/paths.ts';
import type { FolderSourceConfig } from './types.ts';
import {
  getZenskillSeedDismissMarker,
  loadSourceConfig,
  loadSourceGuide,
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

export const ZENSKILL_SOURCE_SLUG = 'zenskill';

/** Interpreter inside the per-user venv, when that venv has been created. */
function resolveVenvPython(venvDir: string): string | null {
  const isWin = process.platform === 'win32';
  const p = join(venvDir, isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python');
  return existsSync(p) ? p : null;
}

interface ZenskillLaunchSpec {
  command: string;
  args: string[];
  env: Record<string, string>;
}

/**
 * Stdio launch spec for the engine pack.
 *
 * The pack ships inside a signed app bundle where `zenskill/` is read-only
 * (`dr-xr-xr-x` on macOS). `uv run --project <pack>` writes scratch files
 * (`.tmpXXXX`) into the project dir, fails there with
 * `Permission denied (os error 13)`, and exits immediately — the MCP handshake
 * then surfaces as `-32000 Connection closed`. Once the venv exists we launch
 * the interpreter directly: `-m zenskill` resolves through the editable install
 * (no cwd requirement) and only reads the pack, never writes into it.
 * uv stays the bootstrap path for installs that have no venv yet.
 */
function buildLaunchSpec(args: {
  engineDir: string;
  venvDir: string;
  configDir?: string;
  uvPath: string | null;
}): ZenskillLaunchSpec | null {
  const venvPy = resolveVenvPython(args.venvDir);
  if (venvPy) {
    const env: Record<string, string> = {};
    if (args.configDir) env.ZENSKILL_CONFIG_DIR = args.configDir;
    return { command: venvPy, args: ['-m', 'zenskill', 'mcp', 'serve'], env };
  }
  if (!args.uvPath) return null;
  const env: Record<string, string> = {
    // Keep uv's virtualenv out of a potentially read-only install dir.
    UV_PROJECT_ENVIRONMENT: args.venvDir,
  };
  if (args.configDir) env.ZENSKILL_CONFIG_DIR = args.configDir;
  return {
    command: args.uvPath,
    args: [
      'run',
      '--project',
      args.engineDir,
      '--python',
      '3.12',
      'zenskill',
      'mcp',
      'serve',
    ],
    env,
  };
}

/** guide.md shown next to the source in the UI and referenced by api-tools. */
const ZENSKILL_GUIDE = `# ZenSkill

有生命的技能系统：把技能生态、GTD、记忆与成长体系作为 MCP 工具接入 ZenSkill。

工具前缀为 \`mcp__zenskill__*\`，例如 \`mcp__zenskill__skill_search\`。

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
  if (!engineDir) {
    debug('[zenskill-seed] Engine pack not found, skipping seed');
    return null;
  }

  const venvDir = join(CONFIG_DIR, 'zenskill', 'venv');
  const spec = buildLaunchSpec({
    engineDir,
    venvDir,
    configDir: CONFIG_DIR,
    uvPath: resolveUvPath(),
  });
  if (!spec) {
    debug('[zenskill-seed] No venv interpreter and no bundled uv, skipping seed');
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
      command: spec.command,
      args: spec.args,
      // Point the engine's config/data dir at the desktop registry
      // (~/.zenskill) so the Python side resolves the same
      // workspaces/profiles as this app instead of the CLI's ~/.zenskill.
      env: spec.env,
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
/**
 * One-time legacy slug migration (issue: seed guard misjudged `zenskill-4`
 * as an existing source and skipped seeding).
 *
 * Renames the legacy source directory to the canonical slug and syncs the
 * `slug` field inside its config.json, keeping a `.bak` copy of the original
 * config. The directory rename is atomic within the same volume; on any
 * failure the original directory is left untouched (returns false) so the
 * caller's skip-path keeps the workspace working as before.
 */
function migrateLegacySourceSlug(sourcesDir: string, legacySlug: string): boolean {
  try {
    const from = join(sourcesDir, legacySlug);
    const to = join(sourcesDir, ZENSKILL_SOURCE_SLUG);
    if (existsSync(to)) return false; // 权威源已存在——不覆盖，交由外层跳过逻辑

    const cfgPath = join(from, 'config.json');
    // 原文备份 → 同步 slug 字段 → 目录改名（同盘原子操作）
    copyFileSync(cfgPath, `${cfgPath}.${legacySlug}.bak`);
    const cfg = JSON.parse(readFileSync(cfgPath, 'utf-8'));
    cfg.slug = ZENSKILL_SOURCE_SLUG;
    writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
    renameSync(from, to);
    return true;
  } catch (e) {
    debug(`[zenskill-seed] legacy slug migration failed: ${String(e)}`);
    return false;
  }
}

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
        // Legacy slug migration (pre-unification installs carry `zenskill-4`):
        // the startsWith guard used to treat it as "already has a source" and
        // skip seeding, leaving ZenSkill pages with `Source not found`.
        // Migrate the legacy directory to the canonical slug instead.
        if (!existing.includes(ZENSKILL_SOURCE_SLUG)) {
          const legacy = existing.find((s) => /^zenskill(-\d+)?$/.test(s));
          if (legacy && migrateLegacySourceSlug(sourcesDir, legacy)) {
            debug(
              `[zenskill-seed] Migrated legacy source ${legacy} → ${ZENSKILL_SOURCE_SLUG}`
            );
            // 迁移即完成：修复迁移过来的旧安装路径（等价于下方 config-exists
            // 分支的 self-heal），然后返回——不得落到全新播种覆盖用户 config
            const migrated = loadSourceConfig(workspaceRootPath, ZENSKILL_SOURCE_SLUG);
            const engineDir = resolveEngineDir();
            const uvPath = resolveUvPath();
            if (migrated && engineDir) {
              if (
                applyZenskillSelfHeal(migrated, {
                  uvPath,
                  engineDir,
                  venvDir: join(CONFIG_DIR, 'zenskill', 'venv'),
                  configDir: CONFIG_DIR,
                })
              ) {
                saveSourceConfig(workspaceRootPath, migrated);
                debug(
                  `[zenskill-seed] Self-healed stale engine paths after legacy migration`
                );
              }
            }
            return;
          } else {
            debug(
              `[zenskill-seed] Workspace already has ZenSkill source(s): ${existing.join(', ')}（迁移未执行/失败，保持原状）`
            );
            return; // 迁移失败（含目录被占用）不阻塞启动
          }
        } else {
          debug(
            `[zenskill-seed] Workspace already has ZenSkill source(s): ${existing.join(', ')}`
          );
          return;
        }
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
    if (!engineDir) {
      debug('[zenskill-seed] Self-heal skipped: engine pack not found');
      return;
    }
    if (applyZenskillSelfHeal(config, {
      uvPath,
      engineDir,
      venvDir: join(CONFIG_DIR, 'zenskill', 'venv'),
      configDir: CONFIG_DIR,
    })) {
      saveSourceConfig(workspaceRootPath, config);
      debug(
        `[zenskill-seed] Self-healed stale engine paths for ${ZENSKILL_SOURCE_SLUG} in ${workspaceRootPath}`
      );
    }

    // Brand refresh (TC-09): sources seeded before the ZenSkill rebrand carry
    // a guide.md that describes the product as "…接入 Craft Agents 的智能体" —
    // the model reads that guide and repeats the claim in chat. Rewrite any
    // guide that still contains the legacy brand with the current copy.
    try {
      const guide = loadSourceGuide(workspaceRootPath, ZENSKILL_SOURCE_SLUG);
      if (guide?.raw && /craft agents/i.test(guide.raw)) {
        saveSourceGuide(workspaceRootPath, ZENSKILL_SOURCE_SLUG, { raw: ZENSKILL_GUIDE });
        debug(
          `[zenskill-seed] Refreshed legacy-brand guide for ${ZENSKILL_SOURCE_SLUG} in ${workspaceRootPath}`
        );
      }
    } catch {
      // Guide refresh is best-effort — never block startup over it.
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
 * Rewrite a ZenSkill source config whose launch spec is stale or broken:
 *
 * - a missing `mcp.command` is rebuilt from the current install's paths;
 * - a config that still launches through `uv run` is upgraded to the venv
 *   interpreter once that venv exists (uv cannot write its scratch files into
 *   the read-only bundled pack — see buildLaunchSpec);
 * - `UV_PROJECT_ENVIRONMENT` is re-derived from CONFIG_DIR when it references
 *   the legacy `.craft-agent` directory, and dropped once we launch the
 *   interpreter directly (uv is not involved any more);
 * - a missing `ZENSKILL_CONFIG_DIR` is backfilled so the engine reads the
 *   desktop registry.
 *
 * Pure (no fs/IO apart from existsSync probes) and exported for tests.
 * Returns true when `config` was mutated.
 */
export function applyZenskillSelfHeal(
  config: FolderSourceConfig,
  paths: {
    uvPath: string | null;
    engineDir: string;
    venvDir: string;
    configDir?: string;
  }
): boolean {
  const mcp = config.mcp;
  if (!mcp || mcp.transport !== 'stdio' || !mcp.command) return false;

  const venvPy = resolveVenvPython(paths.venvDir);
  const commandAlive = existsSync(mcp.command);
  const launchesViaUv =
    /(^|[\\/])uv(\.exe)?$/i.test(mcp.command) || (mcp.args ?? [])[0] === 'run';

  if (venvPy && (launchesViaUv || !commandAlive)) {
    // Upgrade (or repair) to the prebuilt interpreter — no writes to the pack.
    mcp.command = venvPy;
    mcp.args = ['-m', 'zenskill', 'mcp', 'serve'];
  } else if (!commandAlive) {
    // No venv yet: bootstrap through uv, which creates one on first run.
    if (!paths.uvPath) return false;
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
  } else {
    // Command still valid and nothing to upgrade — leave the config alone.
    return false;
  }

  const env: Record<string, string> = { ...(mcp.env ?? {}) };
  const launchesDirectly = venvPy !== null && mcp.command === venvPy;
  if (launchesDirectly) {
    delete env.UV_PROJECT_ENVIRONMENT;
  } else if (
    !env.UV_PROJECT_ENVIRONMENT ||
    env.UV_PROJECT_ENVIRONMENT.includes('.craft-agent')
  ) {
    env.UV_PROJECT_ENVIRONMENT = paths.venvDir;
  }
  if (paths.configDir && !env.ZENSKILL_CONFIG_DIR) {
    env.ZENSKILL_CONFIG_DIR = paths.configDir;
  }
  mcp.env = env;
  return true;
}
