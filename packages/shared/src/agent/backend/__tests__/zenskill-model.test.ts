/**
 * Tests for ZenskillAgent model resolution
 *
 * Verifies:
 * - No hardcoded model: empty config.model → empty _model (Python resolve_model fallback)
 * - config.model (from GUI connection/session) is adopted as-is
 */
import { describe, it, expect } from 'bun:test';
import { ZenskillAgent } from '../zenskill-agent.ts';
import type { BackendConfig } from '../types.ts';
import type { Workspace, LlmConnection } from '../../../config/storage.ts';
import type { SessionConfig as Session } from '../../../sessions/storage.ts';

function createTestWorkspace(): Workspace {
  return {
    id: 'test-workspace',
    name: 'Test Workspace',
    slug: 'workspace',
    rootPath: '/test/workspace',
    createdAt: Date.now(),
  };
}

function createTestSession(): Session {
  return {
    id: 'test-session',
    name: 'Test Session',
    workspaceRootPath: '/test/workspace',
  } as unknown as Session;
}

function createTestConfig(overrides: Partial<BackendConfig> = {}): BackendConfig {
  return {
    provider: 'zenskill',
    workspace: createTestWorkspace(),
    session: createTestSession(),
    isHeadless: true, // Prevent config watchers from starting
    ...overrides,
  };
}

describe('ZenskillAgent model resolution', () => {
  it('does not hardcode a model when config.model is absent', () => {
    const agent = new ZenskillAgent(createTestConfig());
    expect(agent.getModel()).toBe('');
  });

  it('adopts config.model from GUI connection/session when present', () => {
    const agent = new ZenskillAgent(
      createTestConfig({ model: 'deepseek/deepseek-v4-flash' }),
    );
    expect(agent.getModel()).toBe('deepseek/deepseek-v4-flash');
  });

  it('adopts any user-configured model name without provider assumptions', () => {
    const agent = new ZenskillAgent(
      createTestConfig({ model: 'deepseek/deepseek-reasoner' }),
    );
    expect(agent.getModel()).toBe('deepseek/deepseek-reasoner');
  });
});
