/**
 * Centralized path configuration for ZenSkill.
 *
 * Resolution order:
 * 1. ZENSKILL_CONFIG_DIR env (new, preferred) — used as-is, no migration.
 * 2. CRAFT_CONFIG_DIR env (legacy, kept for compatibility with existing dev
 *    tooling and multi-instance setups) — used as-is, no migration.
 * 3. Default: ~/.zenskill
 *
 * ONE-TIME MIGRATION (default resolution only):
 *
 *   TIMING CONTRACT — this migration runs at *module load time*, i.e. before
 *   any consumer of CONFIG_DIR is evaluated. Because every component derives
 *   its paths from CONFIG_DIR (see the C1 rebrand gate: no component may
 *   hardcode ~/.craft-agent), the migration is guaranteed to complete before
 *   any file/directory handle inside the config dir is opened (logger files,
 *   window state, sessions, sources, credentials, ...).
 *
 *   Trigger conditions (all must hold):
 *   - ZENSKILL_DATA_MIGRATE !== '0' (opt-out kill switch)
 *   - ~/.zenskill does not exist yet
 *   - legacy ~/.craft-agent exists
 *
 *   Steps: copy (recursive) → verify file counts match → rename the legacy
 *   directory to ~/.craft-agent.migrated-bak. The legacy directory is NEVER
 *   deleted. On any failure (copy, verification, rename — including the
 *   Windows case where a handle held by another process makes the rename
 *   fail), the partially-copied ~/.zenskill is removed and the legacy
 *   directory keeps being used (graceful downgrade). Check
 *   getConfigMigrationNotice() for a human-readable outcome.
 *
 * Multi-instance development still works by pointing CRAFT_CONFIG_DIR (or
 * ZENSKILL_CONFIG_DIR) at ~/.zenskill-1, ~/.zenskill-2, ... via the
 * detect-instance.sh script.
 */

import { homedir } from 'os';
import { join } from 'path';
import { cpSync, existsSync, readdirSync, renameSync, rmSync } from 'fs';
import { debug } from '../utils/debug.ts';

// 子目录 'desktop'：~/.zenskill 顶层被 ZenSkill CLI 占用（config.json 同 schema），
// 桌面端数据隔离在 ~/.zenskill/desktop（偏差 D3，方案 v1.5）
const DEFAULT_DIR_NAME = '.zenskill/desktop';
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
 * Copy legacy → new, verify, then rename legacy to *.migrated-bak.
 * Returns true when the new directory should be used; on any failure the
 * partially-copied new directory is removed and the legacy dir is kept.
 */
function migrateLegacyConfigDir(newDir: string, legacyDir: string): boolean {
  try {
    debug(`[paths] migrating config dir ${legacyDir} -> ${newDir}`);
    cpSync(legacyDir, newDir, { recursive: true });

    const legacyCount = countEntriesRecursive(legacyDir);
    const newCount = countEntriesRecursive(newDir);
    if (newCount !== legacyCount) {
      throw new Error(`copy verification failed (${legacyCount} entries -> ${newCount})`);
    }

    renameSync(legacyDir, `${legacyDir}${MIGRATED_BAK_SUFFIX}`);
    migrationNotice = `Migrated config data from ${legacyDir} to ${newDir} (backup at ${legacyDir}${MIGRATED_BAK_SUFFIX})`;
    debug(`[paths] ${migrationNotice}`);
    return true;
  } catch (error) {
    // Roll back the copy; the legacy directory is never touched.
    try {
      rmSync(newDir, { recursive: true, force: true });
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

  const newDir = join(homedir(), DEFAULT_DIR_NAME);

  // Kill switch: keep resolving to the new directory but never migrate data.
  if (process.env.ZENSKILL_DATA_MIGRATE === '0') return newDir;

  const legacyDir = getLegacyConfigDir();
  if (existsSync(newDir) || !existsSync(legacyDir)) return newDir;

  return migrateLegacyConfigDir(newDir, legacyDir) ? newDir : legacyDir;
}

export const CONFIG_DIR = resolveConfigDir();
