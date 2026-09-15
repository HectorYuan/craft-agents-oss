// One-time userData migration for the Craft Agents → ZenSkill rebrand (P1.3).
//
// The app previously ran under the name "Craft Agents", so Electron's userData
// directory lived at `%APPDATA%\Craft Agents`. After the rebrand, `app.setName`
// makes Electron resolve userData to `%APPDATA%\ZenSkill`, which would look
// like a fresh install. This module migrates the old data exactly once:
//
//   copy → verify (recursive file counts match) → rename the legacy directory
//   to `Craft Agents.migrated-bak` (never delete — rollback is a plain rename).
//
// On any failure the freshly copied directory is removed and the legacy
// directory is left untouched, so the app keeps running against the old data.
//
// Runs at the earliest point in main/index.ts, right after `app.setName()`,
// before components that open handles into the data directory.
//
// Set `ZENSKILL_DATA_MIGRATE=0` to skip migration entirely.

import { app } from 'electron'
import { cpSync, existsSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { APP_NAME } from '@craft-agent/shared/brand'
import { mainLog } from './logger'

const LEGACY_APP_DIR_NAME = 'Craft Agents'
const LEGACY_BACKUP_SUFFIX = '.migrated-bak'

/**
 * Post-migration fixup (R1): a migrated config.json can carry
 * `setupDeferred: true` from the legacy install even though the user never
 * finished onboarding (empty llmConnections). Without this, the rebranded app
 * would skip onboarding forever and start with no working LLM connection.
 * Clears the deferred flag only when no LLM connection was migrated.
 */
function clearStaleSetupDeferred(newPath: string): void {
  const configPath = join(newPath, 'config.json')
  if (!existsSync(configPath)) return
  try {
    const raw = readFileSync(configPath, 'utf8')
    const config = JSON.parse(raw) as Record<string, unknown>
    if (config?.setupDeferred !== true) return
    const connections = config?.llmConnections
    if (Array.isArray(connections) && connections.length > 0) return
    delete config.setupDeferred
    writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8')
    mainLog.info('[UserDataMigration] Cleared stale setupDeferred in migrated config.json')
  } catch (error) {
    // Formatting/parse issues must never fail the migration.
    mainLog.warn('[UserDataMigration] Failed to inspect config.json after migration', {
      error: String(error),
    })
  }
}

/** Recursively count files under `dir` (files only, directories excluded). */
function countFilesRecursive(dir: string): number {
  let count = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const entryPath = join(dir, entry.name)
    if (entry.isDirectory()) {
      count += countFilesRecursive(entryPath)
    } else if (entry.isFile()) {
      count += 1
    }
  }
  return count
}

/**
 * Migrate `%APPDATA%\Craft Agents` → `%APPDATA%\ZenSkill` (one-time, idempotent).
 *
 * Only runs when the ZenSkill directory does not exist yet and the legacy
 * directory does. Any failure removes the partial copy, keeps the legacy
 * directory as-is, and logs a warning — startup is never blocked.
 */
export function migrateLegacyUserData(): void {
  if (process.env.ZENSKILL_DATA_MIGRATE === '0') {
    mainLog.info('[UserDataMigration] Skipped (ZENSKILL_DATA_MIGRATE=0)')
    return
  }

  const appData = app.getPath('appData')
  const newPath = join(appData, APP_NAME)
  const legacyPath = join(appData, LEGACY_APP_DIR_NAME)

  if (existsSync(newPath)) return // already on ZenSkill data — nothing to do
  if (!existsSync(legacyPath)) return // fresh install — nothing to migrate

  const backupPath = `${legacyPath}${LEGACY_BACKUP_SUFFIX}`
  try {
    mainLog.info('[UserDataMigration] Migrating legacy userData', { from: legacyPath, to: newPath })
    cpSync(legacyPath, newPath, { recursive: true })

    const copied = countFilesRecursive(newPath)
    const legacy = countFilesRecursive(legacyPath)
    if (copied !== legacy) {
      throw new Error(`verification failed: ${copied} files copied vs ${legacy} in legacy directory`)
    }

    renameSync(legacyPath, backupPath)
    clearStaleSetupDeferred(newPath)
    mainLog.info('[UserDataMigration] Migration complete', { files: copied, backup: backupPath })
  } catch (error) {
    // Roll back: drop the partial copy, keep the legacy directory untouched.
    try {
      rmSync(newPath, { recursive: true, force: true })
    } catch (cleanupError) {
      mainLog.warn('[UserDataMigration] Failed to remove partial copy after failed migration', {
        path: newPath,
        error: String(cleanupError),
      })
    }
    mainLog.warn('[UserDataMigration] Migration failed — keeping legacy userData directory as-is', {
      legacyPath,
      error: String(error),
    })
  }
}
