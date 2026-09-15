/**
 * Tests for model detection utilities in config/models.ts
 */
import { describe, it, expect } from 'bun:test';
import {
  isClaudeModel,
  getModelShortName,
  getModelDisplayName,
  getModelContextWindow,
  getModelById,
  ANTHROPIC_MODELS,
  getModelIdByShortName,
  getDefaultSummarizationModel,
  DEFAULT_MODEL,
  normalizeDeprecatedModelId,
} from '../src/config/models.ts';

describe('isClaudeModel', () => {
  // Direct Anthropic model IDs
  it('detects direct Anthropic Claude model IDs', () => {
    expect(isClaudeModel('claude-sonnet-4-6')).toBe(true);
    expect(isClaudeModel('claude-opus-4-8')).toBe(true);
    expect(isClaudeModel('claude-haiku-4-5-20251001')).toBe(true);
    expect(isClaudeModel('claude-3-5-sonnet-20241022')).toBe(true);
  });

  // OpenRouter provider-prefixed Claude IDs
  it('detects OpenRouter-prefixed Claude model IDs', () => {
    expect(isClaudeModel('anthropic/claude-sonnet-4')).toBe(true);
    expect(isClaudeModel('anthropic/claude-opus-4-7')).toBe(true);
    expect(isClaudeModel('anthropic/claude-3.5-haiku')).toBe(true);
  });

  // Non-Claude models via OpenRouter
  it('rejects non-Claude OpenRouter models', () => {
    expect(isClaudeModel('openai/gpt-5')).toBe(false);
    expect(isClaudeModel('openai/gpt-4o')).toBe(false);
    expect(isClaudeModel('google/gemini-2.5-pro')).toBe(false);
    expect(isClaudeModel('meta-llama/llama-4-maverick')).toBe(false);
    expect(isClaudeModel('deepseek/deepseek-r1')).toBe(false);
    expect(isClaudeModel('mistralai/mistral-large')).toBe(false);
  });

  // Non-Claude models via Ollama (no provider prefix)
  it('rejects non-Claude Ollama models', () => {
    expect(isClaudeModel('llama3.2')).toBe(false);
    expect(isClaudeModel('deepseek-r1')).toBe(false);
    expect(isClaudeModel('qwen3-coder')).toBe(false);
    expect(isClaudeModel('mistral')).toBe(false);
    expect(isClaudeModel('gemma2')).toBe(false);
  });

  // Bedrock-native model IDs
  it('detects Bedrock-native Claude model IDs', () => {
    expect(isClaudeModel('anthropic.claude-opus-4-8')).toBe(true);
    expect(isClaudeModel('anthropic.claude-sonnet-4-6')).toBe(true);
    expect(isClaudeModel('anthropic.claude-haiku-4-5-20251001-v1:0')).toBe(true);
  });

  // Case insensitivity
  it('handles case variations', () => {
    expect(isClaudeModel('Claude-Sonnet-4-6')).toBe(true);
    expect(isClaudeModel('CLAUDE-OPUS-4-8')).toBe(true);
    expect(isClaudeModel('Anthropic/Claude-Sonnet-4')).toBe(true);
  });
});

describe('getModelShortName', () => {
  it('returns registry shortName for known models', () => {
    expect(getModelShortName('deepseek/deepseek-v4-flash')).toBe('V4 Flash');
    expect(getModelShortName('deepseek/deepseek-v4-pro')).toBe('V4 Pro');
  });

  it('strips provider prefix for slash-separated IDs', () => {
    expect(getModelShortName('openai/gpt-5.4')).toBe('gpt-5.4');
    expect(getModelShortName('anthropic/claude-sonnet-4')).toBe('claude-sonnet-4');
  });

  it('preserves version numbers for custom endpoint models', () => {
    expect(getModelShortName('gpt-5.4')).toBe('Gpt 5.4');
    expect(getModelShortName('gpt-5.2')).toBe('Gpt 5.2');
    expect(getModelShortName('glm-4.7')).toBe('Glm 4.7');
  });

  it('humanizes bare model names without versions', () => {
    expect(getModelShortName('mistral')).toBe('Mistral');
    expect(getModelShortName('gemma2')).toBe('Gemma2');
  });

  it('humanizes multi-part model names', () => {
    expect(getModelShortName('mistral-large')).toBe('Mistral large');
    expect(getModelShortName('deepseek-r1')).toBe('Deepseek r1');
  });

  it('strips date suffix for unknown claude models', () => {
    expect(getModelShortName('claude-sonnet-3-5-20241022')).toBe('Sonnet 3.5');
  });
});

describe('ZenSkill registry (DeepSeek catalog)', () => {
  it('mirrors the engine-real DeepSeek model list', () => {
    const ids = ANTHROPIC_MODELS.map(m => m.id);
    expect(ids).toContain('deepseek/deepseek-v4-flash');
    expect(ids).toContain('deepseek/deepseek-v4-pro');
    expect(ids).toContain('deepseek/deepseek-chat');
    expect(ids).toContain('deepseek/deepseek-reasoner');
  });

  it('defaults to DeepSeek V4 Flash', () => {
    expect(DEFAULT_MODEL).toBe('deepseek/deepseek-v4-flash');
  });

  it('resolves short names against the DeepSeek catalog', () => {
    expect(getModelIdByShortName('V4 Flash')).toBe('deepseek/deepseek-v4-flash');
    expect(getModelIdByShortName('V4 Pro')).toBe('deepseek/deepseek-v4-pro');
  });

  it('exposes DeepSeek V4 Flash metadata', () => {
    expect(getModelDisplayName('deepseek/deepseek-v4-flash')).toBe('DeepSeek V4 Flash');
    expect(getModelShortName('deepseek/deepseek-v4-flash')).toBe('V4 Flash');
    expect(getModelContextWindow('deepseek/deepseek-v4-flash')).toBe(1_000_000);
    expect(getModelById('deepseek/deepseek-v4-pro')?.id).toBe('deepseek/deepseek-v4-pro');
    expect(getModelById('claude-opus-4-8')).toBeUndefined();
  });

  it('falls back to DEFAULT_MODEL for summarization (no Haiku entry)', () => {
    expect(getDefaultSummarizationModel()).toBe(DEFAULT_MODEL);
  });

  it('still normalizes deprecated Anthropic IDs (pure mapping, registry-independent)', () => {
    expect(normalizeDeprecatedModelId('claude-opus-4-5-20251101')).toBe('claude-opus-4-8');
    expect(normalizeDeprecatedModelId('claude-opus-4-7')).toBe('claude-opus-4-7');
    expect(normalizeDeprecatedModelId('claude-opus-4-6')).toBe('claude-opus-4-6');
    expect(normalizeDeprecatedModelId('pi/claude-opus-4-6')).toBe('pi/claude-opus-4-6');
    expect(normalizeDeprecatedModelId('us.anthropic.claude-opus-4-6-v1')).toBe('us.anthropic.claude-opus-4-6-v1');
  });
});
