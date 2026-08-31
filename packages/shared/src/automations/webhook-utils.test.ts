/**
 * Tests for webhook utility functions (expandWebhookAction, etc.)
 */

import { describe, it, expect } from 'bun:test';
import { expandWebhookAction } from './webhook-utils.ts';
import type { WebhookAction } from './types.ts';

const env = {
  CRAFT_WH_SESSION_ID: 'sess-123',
  CRAFT_WH_EVENT: 'LabelAdd',
  API_TOKEN: 'tok-secret',
};

describe('expandWebhookAction', () => {
  it('expands URL templates', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com/hook/${CRAFT_WH_SESSION_ID}',
    };
    const result = expandWebhookAction(action, env);
    expect(result.url).toBe('https://api.example.com/hook/sess-123');
  });

  it('expands header values', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com',
      headers: { 'X-Event': '${CRAFT_WH_EVENT}', 'X-Static': 'unchanged' },
    };
    const result = expandWebhookAction(action, env);
    expect(result.headers).toEqual({ 'X-Event': 'LabelAdd', 'X-Static': 'unchanged' });
  });

  it('expands string body', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com',
      body: 'session=${CRAFT_WH_SESSION_ID}',
      bodyFormat: 'raw',
    };
    const result = expandWebhookAction(action, env);
    expect(result.body).toBe('session=sess-123');
  });

  it('expands object body (JSON)', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com',
      body: { id: '${CRAFT_WH_SESSION_ID}', event: '${CRAFT_WH_EVENT}' },
    };
    const result = expandWebhookAction(action, env);
    expect(result.body).toEqual({ id: 'sess-123', event: 'LabelAdd' });
  });

  it('expands basic auth credentials', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com',
      auth: { type: 'basic', username: '${CRAFT_WH_SESSION_ID}', password: '${API_TOKEN}' },
    };
    const result = expandWebhookAction(action, env);
    expect(result.auth).toEqual({ type: 'basic', username: 'sess-123', password: 'tok-secret' });
  });

  it('expands bearer auth token', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com',
      auth: { type: 'bearer', token: '${API_TOKEN}' },
    };
    const result = expandWebhookAction(action, env);
    expect(result.auth).toEqual({ type: 'bearer', token: 'tok-secret' });
  });

  it('passes through fields without templates unchanged', () => {
    const action: WebhookAction = {
      type: 'webhook',
      url: 'https://api.example.com/static',
      method: 'PUT',
      bodyFormat: 'json',
      captureResponse: true,
    };
    const result = expandWebhookAction(action, env);
    expect(result.url).toBe('https://api.example.com/static');
    expect(result.method).toBe('PUT');
    expect(result.bodyFormat).toBe('json');
    expect(result.captureResponse).toBe(true);
  });
});

describe('executeWebhookRequest default body', () => {
  const payloadEnv = {
    CRAFT_EVENT: 'ZenSkillChanged',
    CRAFT_EVENT_DATA: JSON.stringify({
      workspaceId: 'ws-1',
      timestamp: 123,
      data: { type: 'inbox_archive' },
    }),
    CRAFT_WORKSPACE_ID: 'ws-1',
  };

  it('sends full event payload as body when bodyFormat=json and body omitted', async () => {
    const { executeWebhookRequest: exec } = await import('./webhook-utils.ts');
    let captured: any = {};
    const origFetch = global.fetch;
    global.fetch = (async (_url: any, init?: any) => {
      captured = init;
      return new Response('ok', { status: 200 });
    }) as any;
    try {
      const action: WebhookAction = {
        type: 'webhook',
        url: 'https://api.example.com/hook',
        method: 'POST',
        bodyFormat: 'json',
      };
      const result = await exec(action, { env: payloadEnv });
      expect(result.success).toBe(true);
      const ct = captured?.headers?.['Content-Type'] ?? captured?.headers?.['content-type'];
      expect(ct).toBe('application/json');
      const parsed = JSON.parse(captured?.body!);
      expect(parsed.event).toBe('ZenSkillChanged');
      expect(parsed.data.type).toBe('inbox_archive');
    } finally {
      global.fetch = origFetch;
    }
  });

  it('sends no body when bodyFormat is not json (backward compat)', async () => {
    const { executeWebhookRequest: exec } = await import('./webhook-utils.ts');
    let capturedBody: string | undefined;
    const origFetch = global.fetch;
    global.fetch = (async (_url: any, init?: any) => {
      capturedBody = init?.body;
      return new Response('ok', { status: 200 });
    }) as any;
    try {
      const action: WebhookAction = { type: 'webhook', url: 'https://api.example.com', method: 'POST' };
      await exec(action, { env: payloadEnv });
      expect(capturedBody).toBeUndefined();
    } finally {
      global.fetch = origFetch;
    }
  });

  it('explicit body still wins over default payload', async () => {
    const { executeWebhookRequest: exec } = await import('./webhook-utils.ts');
    let capturedBody: string | undefined;
    const origFetch = global.fetch;
    global.fetch = (async (_url: any, init?: any) => {
      capturedBody = init?.body;
      return new Response('ok', { status: 200 });
    }) as any;
    try {
      const action: WebhookAction = {
        type: 'webhook',
        url: 'https://api.example.com',
        method: 'POST',
        bodyFormat: 'json',
        body: { custom: true },
      };
      await exec(action, { env: payloadEnv });
      expect(JSON.parse(capturedBody!)).toEqual({ custom: true });
    } finally {
      global.fetch = origFetch;
    }
  });
});
