/**
 * Tests for the ZenSkill seed self-heal (R6).
 *
 * A source config migrated from an older install can point mcp.command at a
 * uv binary that no longer exists, and UV_PROJECT_ENVIRONMENT at the legacy
 * .craft-agent dir. applyZenskillSelfHeal() rewrites those in place.
 */
import { describe, it, expect } from 'bun:test';
import { mkdtempSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { applyZenskillSelfHeal, ZENSKILL_SOURCE_SLUG } from '../zenskill-seed.ts';
import type { FolderSourceConfig } from '../types.ts';

function makeConfig(overrides: Partial<FolderSourceConfig> = {}): FolderSourceConfig {
  return {
    id: 'src-1',
    name: 'ZenSkill',
    slug: ZENSKILL_SOURCE_SLUG,
    enabled: true,
    provider: 'zenskill',
    type: 'mcp',
    mcp: {
      transport: 'stdio',
      command: '/old/install/uv.exe',
      args: ['run', '--project', '/old/install/resources/zenskill', '--python', '3.12', 'zenskill', 'mcp', 'serve'],
      env: {
        UV_PROJECT_ENVIRONMENT: '/home/user/.craft-agent/zenskill/venv',
      },
    },
    isAuthenticated: true,
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  };
}

const NEW_PATHS = {
  uvPath: '/new/install/bin/uv.exe',
  engineDir: '/new/install/resources/zenskill',
  venvDir: '/home/user/.zenskill/desktop/zenskill/venv',
};

describe('applyZenskillSelfHeal', () => {
  it('rewrites command/args and legacy UV_PROJECT_ENVIRONMENT for a stale command', () => {
    const config = makeConfig();
    expect(applyZenskillSelfHeal(config, NEW_PATHS)).toBe(true);
    expect(config.mcp?.command).toBe(NEW_PATHS.uvPath);
    expect(config.mcp?.args).toEqual([
      'run', '--project', NEW_PATHS.engineDir, '--python', '3.12', 'zenskill', 'mcp', 'serve',
    ]);
    expect(config.mcp?.env?.UV_PROJECT_ENVIRONMENT).toBe(NEW_PATHS.venvDir);
  });

  it('treats a command that exists on disk as healthy and does not touch it', () => {
    // A real file so existsSync() returns true.
    const liveUv = join(mkdtempSync(join(tmpdir(), 'zenskill-seed-')), 'uv.exe');
    writeFileSync(liveUv, '');
    const config = makeConfig({
      mcp: { transport: 'stdio', command: liveUv },
    });
    expect(applyZenskillSelfHeal(config, NEW_PATHS)).toBe(false);
    expect(config.mcp?.command).toBe(liveUv);
  });

  it('backsfills a missing UV_PROJECT_ENVIRONMENT', () => {
    const config = makeConfig({
      mcp: { transport: 'stdio', command: '/missing/uv' },
    });
    expect(applyZenskillSelfHeal(config, NEW_PATHS)).toBe(true);
    expect(config.mcp?.env?.UV_PROJECT_ENVIRONMENT).toBe(NEW_PATHS.venvDir);
  });

  it('leaves a modern UV_PROJECT_ENVIRONMENT untouched', () => {
    const config = makeConfig();
    config.mcp!.env!.UV_PROJECT_ENVIRONMENT = '/custom/venv-path';
    expect(applyZenskillSelfHeal(config, NEW_PATHS)).toBe(true);
    expect(config.mcp?.env?.UV_PROJECT_ENVIRONMENT).toBe('/custom/venv-path');
  });

  it('returns false for non-stdio or command-less configs', () => {
    expect(applyZenskillSelfHeal(makeConfig({
      type: 'mcp',
      mcp: { transport: 'http', url: 'http://localhost' },
    }), NEW_PATHS)).toBe(false);
    expect(applyZenskillSelfHeal(makeConfig({
      mcp: { transport: 'stdio' },
    }), NEW_PATHS)).toBe(false);
    expect(applyZenskillSelfHeal(makeConfig({ mcp: undefined }), NEW_PATHS)).toBe(false);
  });

  it('keeps the seeded slug at zenskill-4', () => {
    expect(ZENSKILL_SOURCE_SLUG).toBe('zenskill-4');
  });
});
