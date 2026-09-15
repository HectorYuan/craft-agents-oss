/**
 * Centralized path configuration for ZenSkill.
 *
 * Resolution order:
 * 1. ZENSKILL_CONFIG_DIR env (new, preferred) — used as-is, no migration.
 * 2. CRAFT_CONFIG_DIR env (legacy, kept for compatibility with existing dev
 *    tooling and multi-instance setups) — used as-is, no migration.
 * 3. Default: ~/.zenskill — shared by the desktop app AND the ZenSkill CLI
 *    (single data model, single source of truth; decision D8).
 *
 * ONE-TIME MIGRATIONS (default resolution only):
 *
 *   TIMING CONTRACT — migrations run at *module load time*, i.e. before any
 *   consumer of CONFIG_DIR is evaluated. Because every component derives its
 *   paths from CONFIG_DIR (C1 rebrand gate: no component may hardcode a data
 *   dir), migrations are guaranteed to complete before any file/directory
 *   handle inside the config dir is opened (logger files, window state,
 *   sessions, sources, credentials, ...).
 *
 *   Stage A (D8 desktop merge): if the pre-merge desktop subtree
 *   ~/.zenskill/desktop exists, it is folded into ~/.zenskill:
 *   copy (recursive, overwrite-merge) → verify every top-level entry landed →
 *   rename the desktop dir to desktop.migrated-bak. The desktop config.json
 *   becomes canonical; a pre-existing CLI-side config.json is preserved as
 *   config.json.cli-bak. On any failure the root is left as-is and the
 *   desktop directory keeps being used (graceful downgrade).
 *
 *   Stage B (legacy import): for machines that never ran the desktop app —
 *   when ~/.zenskill has no config.json yet and legacy ~/.craft-agent exists,
 *   the legacy directory is copied in (config.json legacy wins), verified,
 *   and renamed to ~/.craft-agent.migrated-bak. Same failure semantics.
 *
 *   All stages honor ZENSKILL_DATA_MIGRATE === '0' (kill switch: the
 *   pre-D8 desktop layout is kept if present, else the root dir is used
 *   without touching any data).
 *
 * Multi-instance development still works by pointing ZENSKILL_CONFIG_DIR (or
 * CRAFT_CONFIG_DIR) at ~/.zenskill-1, ~/.zenskill-2, ... via the
 * detect-instance.sh script.
 */

import { homedir } from 'os';
import { join } from 'path';
import { copyFileSync, cpSync, existsSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'fs';
import { debug } from '../utils/debug.ts';

const ROOT_DIR_NAME = '.zenskill';
// v1.5 遗留：D8 之前的桌面端子目录（存在即触发 Stage A 合并）
const PRE_MERGE_DESKTOP_DIR_NAME = '.zenskill/desktop';
const LEGACY_DIR_NAME = '.craft-agent';
const MIGRATED_BAK_SUFFIX = '.migrated-bak';

/** The legacy Craft Agent config directory (~/.craft-agent). */
export function getLegacyConfigDir(): string {
  return join(homedir(), LEGACY_DIR_NAME);
}

/** Human-readable notice describing what the one-time migration did (or null). */
let migrationNotice: string | null = null;

export function getConfigMigrationNotice(): string | null {
  return migrationNotice;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Post-resolution fixups (idempotent, cheap — one config.json read):
 * 1. R1: a migrated config.json can carry `setupDeferred: true` from an
 *    install where the user never finished onboarding (empty llmConnections).
 *    Clear it so onboarding actually runs.
 * 2. Rewrite workspace rootPath entries still pointing at historical
 *    locations (`~/.zenskill/desktop/...`, `~/.craft-agent/...`) to the
 *    unified `~/.zenskill` root.
 */
function postResolutionFixups(dir: string): void {
  const configPath = join(dir, 'config.json');
  if (!existsSync(configPath)) return;
  try {
    const config = JSON.parse(readFileSync(configPath, 'utf8')) as Record<string, unknown>;

    if (config?.setupDeferred === true) {
      const connections = config?.llmConnections;
      if (!(Array.isArray(connections) && connections.length > 0)) {
        delete config.setupDeferred;
        debug(`[paths] cleared stale setupDeferred in ${configPath}`);
      }
    }

    const prefixes = [`~/${PRE_MERGE_DESKTOP_DIR_NAME}`, `~/${LEGACY_DIR_NAME}`];
    const workspaces = config?.workspaces as Array<{ rootPath?: string }> | undefined;
    let changed = false;
    for (const ws of workspaces ?? []) {
      if (typeof ws.rootPath !== 'string') continue;
      // 分隔符无关匹配（Windows 混合分隔符的历史 rootPath 也要命中）
      const norm = ws.rootPath.replace(/\\/g, '/');
      for (const prefix of prefixes) {
        if (norm.startsWith(prefix)) {
          ws.rootPath = `~/${ROOT_DIR_NAME}` + norm.slice(prefix.length);
          changed = true;
          break;
        }
      }
    }
    if (changed) {
      writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
      debug(`[paths] rewrote workspace rootPaths into ${dir}`);
    }
  } catch (error) {
    debug(`[paths] failed post-resolution fixups on ${configPath}: ${describeError(error)}`);
  }
}

/** Recursively count files/directories (symlinks counted, never followed). */
function countEntriesRecursive(dir: string): number {
  let count = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      count += 1;
      continue;
    }
    count += countEntriesRecursive(join(dir, entry.name));
  }
  return count;
}

/**
 * Stage A (D8): fold the pre-merge desktop subtree into ~/.zenskill.
 * Copy is an overwrite-merge (existing CLI-side dirs gain the desktop's
 * entries; the desktop config.json becomes canonical). Returns true when the
 * root dir should be used; on failure the desktop dir is kept (data never
 * leaves it) and the caller falls back.
 */
function mergeDesktopDirIntoRoot(rootDir: string, desktopDir: string): boolean {
  try {
    debug(`[paths] merging pre-D8 desktop dir ${desktopDir} -> ${rootDir}`);

    // Preserve the CLI-side config before the desktop config becomes canonical.
    const cliConfig = join(rootDir, 'config.json');
    if (existsSync(cliConfig)) {
      copyFileSync(cliConfig, join(rootDir, 'config.json.cli-bak'));
    }

    cpSync(desktopDir, rootDir, { recursive: true });

    // Verify: every top-level entry of the desktop dir landed in the root.
    for (const entry of readdirSync(desktopDir, { withFileTypes: true })) {
      if (!existsSync(join(rootDir, entry.name))) {
        throw new Error(`merge verification failed: missing ${entry.name}`);
      }
    }

    renameSync(desktopDir, `${desktopDir}${MIGRATED_BAK_SUFFIX}`);
    migrationNotice = `Merged pre-D8 desktop data (${desktopDir}) into ${rootDir} (backup at ${desktopDir}${MIGRATED_BAK_SUFFIX})`;
    debug(`[paths] ${migrationNotice}`);
    return true;
  } catch (error) {
    // The desktop dir is untouched (copy-merge only reads from it) — keep
    // using it. Best-effort: no partial state to clean since cpSync merges.
    migrationNotice = `Desktop merge into ${rootDir} failed; continuing with the pre-merge desktop directory: ${describeError(error)}`;
    debug(`[paths] ${migrationNotice}`);
    return false;
  }
}

/**
 * Stage B: copy legacy → root, verify, then rename legacy to *.migrated-bak.
 * Returns true when the root directory should be used; on any failure the
 * partially-copied entries are removed and the legacy dir is kept.
 */
function migrateLegacyConfigDir(rootDir: string, legacyDir: string): boolean {
  try {
    debug(`[paths] migrating config dir ${legacyDir} -> ${rootDir}`);
    cpSync(legacyDir, rootDir, { recursive: true });

    const legacyCount = countEntriesRecursive(legacyDir);
    const rootCount = countEntriesRecursive(rootDir);
    if (rootCount !== legacyCount) {
      throw new Error(`copy verification failed (${legacyCount} entries -> ${rootCount})`);
    }

    renameSync(legacyDir, `${legacyDir}${MIGRATED_BAK_SUFFIX}`);
    migrationNotice = `Migrated config data from ${legacyDir} to ${rootDir} (backup at ${legacyDir}${MIGRATED_BAK_SUFFIX})`;
    debug(`[paths] ${migrationNotice}`);
    return true;
  } catch (error) {
    // Roll back the copy; the legacy directory is never touched.
    try {
      rmSync(rootDir, { recursive: true, force: true });
    } catch {
      /* best-effort cleanup */
    }
    migrationNotice = `Config migration from ${legacyDir} failed; continuing with the legacy directory: ${describeError(error)}`;
    debug(`[paths] ${migrationNotice}`);
    return false;
  }
}

function resolveConfigDir(): string {
  // 1/2. Explicit overrides take effect directly and never trigger migration.
  const zenEnv = process.env.ZENSKILL_CONFIG_DIR;
  if (zenEnv) return zenEnv;
  const craftEnv = process.env.CRAFT_CONFIG_DIR;
  if (craftEnv) return craftEnv;

  const rootDir = join(homedir(), ROOT_DIR_NAME);
  const preMergeDesktopDir = join(rootDir, 'desktop');
  const legacyDir = getLegacyConfigDir();

  let resolved: string;
  if (process.env.ZENSKILL_DATA_MIGRATE === '0') {
    // Kill switch: keep the pre-D8 layout if present, else the root dir.
    resolved = existsSync(preMergeDesktopDir) ? preMergeDesktopDir : rootDir;
  } else if (existsSync(preMergeDesktopDir)) {
    // Stage A: fold the desktop subtree into the root (desktop config wins).
    resolved = mergeDesktopDirIntoRoot(rootDir, preMergeDesktopDir) ? rootDir : preMergeDesktopDir;
  } else if (!existsSync(join(rootDir, 'config.json')) && existsSync(legacyDir)) {
    // Stage B: import legacy data on machines that never ran the desktop app.
    resolved = migrateLegacyConfigDir(rootDir, legacyDir) ? rootDir : legacyDir;
  } else {
    resolved = rootDir;
  }

  postResolutionFixups(resolved);
  return resolved;
}

export const CONFIG_DIR = resolveConfigDir();
