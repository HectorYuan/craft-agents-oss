/**
 * Tests for Agent Factory
 *
 * Verifies:
 * - Provider detection from auth type
 * - Backend creation for different providers
 * - LLM connection type mapping
 * - Available providers list
 */
import { describe, it, expect, beforeEach } from 'bun:test';
import { join } from 'node:path';
import {
  detectProvider,
  createBackend,
  createAgent,
  fetchBackendModels,
  getAvailableProviders,
  initializeBackendHostRuntime,
  isProviderAvailable,
  connectionTypeToProvider,
  connectionAuthTypeToBackendAuthType,
  providerTypeToAgentProvider,
  resolveModelForProvider,
  resolveSetupTestConnectionHint,
  createBackendFromConnection,
  testBackendConnection,
  validateStoredBackendConnection,
} from '../factory.ts';
import type { BackendConfig } from '../types.ts';
import type { Workspace, LlmConnection } from '../../../config/storage.ts';
import type { SessionConfig as Session } from '../../../sessions/storage.ts';
import { ClaudeAgent } from '../../claude-agent.ts';
import { ZenskillAgent } from '../zenskill-agent.ts';
import { isValidProviderAuthCombination } from '../../../config/llm-connections.ts';

// Test helpers
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
    createdAt: Date.now(),
    lastUsedAt: Date.now(),
    permissionMode: 'ask',
  };
}

function createTestConfig(overrides: Partial<BackendConfig> = {}): BackendConfig {
  return {
    provider: 'anthropic',
    workspace: createTestWorkspace(),
    session: createTestSession(),
    isHeadless: true, // Prevent config watchers from starting
    ...overrides,
  };
}

describe('detectProvider', () => {
  describe('Anthropic authentication types', () => {
    it('should return anthropic for api_key', () => {
      expect(detectProvider('api_key')).toBe('anthropic');
    });

    it('should return anthropic for oauth_token', () => {
      expect(detectProvider('oauth_token')).toBe('anthropic');
    });
  });

  describe('Unknown authentication types', () => {
    it('should default to zenskill for unknown types', () => {
      expect(detectProvider('unknown')).toBe('zenskill');
      expect(detectProvider('')).toBe('zenskill');
    });
  });
});

describe('createBackend / createAgent', () => {
  describe('Anthropic provider', () => {
    it('should throw for anthropic provider (not shipped)', () => {
      expect(() => createBackend(createTestConfig({ provider: 'anthropic' }))).toThrow(/不支持 Claude 后端/);
    });
  });

  describe('Unknown provider', () => {
    it('should fall back to ZenskillAgent', () => {
      const agent = createBackend(createTestConfig({ provider: 'mystery' as any }));
      expect(agent).toBeInstanceOf(ZenskillAgent);
    });
  });

  describe('createAgent alias', () => {
    it('should be an alias for createBackend', () => {
      expect(createAgent).toBe(createBackend);
    });
  });
});

describe('getAvailableProviders', () => {
  it('should return the shipped providers', () => {
    const providers = getAvailableProviders();

    expect(providers).toEqual(['zenskill']);
  });
});

describe('isProviderAvailable', () => {
  it('should return false for anthropic (not shipped)', () => {
    expect(isProviderAvailable('anthropic')).toBe(false);
  });

  it('should return false for unknown provider', () => {
    expect(isProviderAvailable('unknown' as any)).toBe(false);
  });
});

describe('connectionTypeToProvider', () => {
  it('should map anthropic type to anthropic provider', () => {
    expect(connectionTypeToProvider('anthropic')).toBe('anthropic');
  });

  it('should map openai type to zenskill (pi routing removed)', () => {
    expect(connectionTypeToProvider('openai')).toBe('zenskill');
  });

  it('should map openai-compat type to zenskill (pi routing removed)', () => {
    expect(connectionTypeToProvider('openai-compat')).toBe('zenskill');
  });

  it('should default to zenskill for unknown types', () => {
    expect(connectionTypeToProvider('unknown' as any)).toBe('zenskill');
  });
});

describe('connectionAuthTypeToBackendAuthType (legacy)', () => {
  it('should map api_key to api_key', () => {
    expect(connectionAuthTypeToBackendAuthType('api_key')).toBe('api_key');
  });

  it('should pass through oauth', () => {
    expect(connectionAuthTypeToBackendAuthType('oauth')).toBe('oauth');
  });

  it('should map none to undefined', () => {
    expect(connectionAuthTypeToBackendAuthType('none')).toBeUndefined();
  });
});

describe('providerTypeToAgentProvider', () => {
  describe('Anthropic SDK providers', () => {
    it('should map anthropic to anthropic', () => {
      expect(providerTypeToAgentProvider('anthropic')).toBe('anthropic');
    });
  });


});

describe('phase4 backend abstraction APIs', () => {
  it('initializeBackendHostRuntime bootstraps without throwing in dev runtime', () => {
    expect(() => initializeBackendHostRuntime({
      hostRuntime: {
        appRootPath: process.cwd(),
        isPackaged: false,
      },
    })).not.toThrow();
  });

  // Skip: resolveClaudeCliPath finds the CLI via node_modules traversal even from dist/, so this
  // only fails in a truly isolated packaged environment, not in the dev monorepo.
  it.skip('initializeBackendHostRuntime throws for dist-style host root in dev', () => {
    expect(() => initializeBackendHostRuntime({
      hostRuntime: {
        appRootPath: join(process.cwd(), 'apps', 'electron', 'dist'),
        isPackaged: false,
      },
    })).toThrow('Claude Code SDK not found');
  });

  it('resolveSetupTestConnectionHint always routes to zenskill', () => {
    expect(resolveSetupTestConnectionHint({ provider: 'anthropic', baseUrl: 'https://api.example.com' }))
      .toEqual({ providerType: 'zenskill' });
    expect(resolveSetupTestConnectionHint({ provider: 'zenskill', baseUrl: '' }))
      .toEqual({ providerType: 'zenskill' });
  });

  it('validateStoredBackendConnection returns not found for unknown slug', async () => {
    const result = await validateStoredBackendConnection({
      slug: '__missing-connection__',
      hostRuntime: {
        appRootPath: process.cwd(),
        isPackaged: false,
      },
    });

    expect(result.success).toBe(false);
    expect(result.error).toBe('Connection not found');
  });

  it('testBackendConnection keeps required model argument and validates key presence', async () => {
    const result = await testBackendConnection({
      provider: 'anthropic',
      apiKey: '   ',
      model: 'claude-sonnet-4-6',
      hostRuntime: {
        appRootPath: process.cwd(),
        isPackaged: false,
      },
    });

    expect(result.success).toBe(false);
    expect(result.error).toBe('API key is required');
  });
});

describe('resolveModelForProvider', () => {
});

