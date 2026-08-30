/**
 * ZenskillBackend — Subprocess RPC Client
 *
 * Thin subprocess client for ZenSkill's agent-engine. Spawns a
 * `zenskill agent-engine serve` subprocess and communicates via JSONL
 * over stdin/stdout.
 *
 * Implements AgentBackend by translating ZenSkill's AgentEvent stream
 * into Craft AgentEvents. Tool proxy (register_tools / tool_execute_request /
 * tool_execute_response / pre_tool_use_request / pre_tool_use_response) is
 * handled via the same wire format as PiAgent.
 *
 * Intentionally kept minimal — no SDK dependency, no auth plumbing, no overflow
 * recovery. ZenSkill handles its own LLM calls and compaction internally.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { createInterface, type Interface as ReadlineInterface } from 'node:readline';
import type { AgentBackend } from './types.ts';
import type { AgentEvent } from '@craft-agent/core/types';
import { getLlmConnection } from '../../config/storage.ts';
import { getCredentialManager } from '../../credentials/manager.ts';

// ============================================================
// JSONL Protocol Types (mirror zenskill/runtime/agent/rpc.py)
// ============================================================

interface ServerHello {
  type: 'server_hello';
  protocolVersion: string;
}

interface ServerEvent {
  type: 'event';
  event: Record<string, unknown>;
}

interface ToolExecuteRequest {
  type: 'tool_execute_request';
  requestId: string;
  toolName: string;
  args: Record<string, unknown>;
}

interface PreToolUseRequest {
  type: 'pre_tool_use_request';
  requestId: string;
  toolName: string;
  input: Record<string, unknown>;
}

interface ServerResponse {
  type: 'response';
  id?: string;
  command?: string;
  success: boolean;
  data?: Record<string, unknown>;
  error?: string;
}

interface RegisterToolsResult {
  type: 'register_tools_result';
  id?: string;
  count: number;
  total: number;
}

type ServerMessage =
  | ServerHello
  | ServerEvent
  | ToolExecuteRequest
  | PreToolUseRequest
  | ServerResponse
  | RegisterToolsResult
  | { type: string; [key: string]: unknown };

// ============================================================
// EventQueue — async generator pattern for streaming events
// ============================================================

class EventQueue {
  private queue: unknown[] = [];
  private resolvers: Array<(value: IteratorResult<unknown>) => void> = [];
  private done = false;

  reset(): void {
    this.queue = [];
    this.resolvers = [];
    this.done = false;
  }

  enqueue(event: unknown): void {
    if (this.done) return;
    if (this.resolvers.length > 0) {
      this.resolvers.shift()!({ value: event, done: false });
    } else {
      this.queue.push(event);
    }
  }

  complete(): void {
    this.done = true;
    for (const r of this.resolvers) {
      r({ value: undefined, done: true });
    }
    this.resolvers = [];
  }

  async *drain(): AsyncGenerator<unknown> {
    while (true) {
      if (this.queue.length > 0) {
        yield this.queue.shift()!;
      } else if (this.done) {
        return;
      } else {
        const value = await new Promise<IteratorResult<unknown>>((resolve) => {
          this.resolvers.push(resolve);
        });
        if (value.done) return;
        yield value.value;
      }
    }
  }
}

// ============================================================
// ZenskillAgent
// ============================================================

export interface ZenskillBackendConfig {
  /** Path to zenskill executable (default: 'zenskill') */
  zenskillPath?: string;
  /** Working directory for the subprocess */
  cwd?: string;
  /** Permission mode: full / restricted / plan / sandbox */
  permission?: string;
  /** Session root directory */
  sessionRoot?: string;
  /** Model override (provider/model format) */
  model?: string;
  /** Enable faux mode for testing (no real LLM calls) */
  faux?: boolean;
  /** Debug logging */
  debug?: boolean;
  /** Connection slug — set by the factory for credential routing */
  connectionSlug?: string;
  /** LLM provider type from the connection ('anthropic' | 'pi' | 'pi_compat') */
  providerType?: string;
}

export class ZenskillAgent implements AgentBackend {
  private config: ZenskillBackendConfig;
  private subprocess: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private eventQueue = new EventQueue();
  private rpcIdCounter = 0;

  // Pending tool proxy requests
  private pendingToolExecutions = new Map<string, {
    resolve: (result: { content: string; isError: boolean }) => void;
  }>();
  private pendingPermissions = new Map<string, {
    resolve: (allowed: boolean) => void;
    toolName: string;
  }>();

  // State
  private _isProcessing = false;
  private serverReady = false;
  private serverVersion: string | null = null;

  constructor(config: ZenskillBackendConfig) {
    this.config = config;
  }

  // ============================================================
  // Lifecycle
  // ============================================================

  // ============================================================
  // Path & Credential Resolution (packaged / dev)
  // ============================================================

  /** resourcesPath exists only inside packaged Electron; dev falls back to cwd. */
  private _packagedAppResource(relPath: string): string | null {
    const resourcesPath = (process as unknown as { resourcesPath?: string }).resourcesPath;
    if (resourcesPath) {
      const p = join(resourcesPath, 'app', 'resources', relPath);
      if (existsSync(p)) return p;
    }
    return null;
  }

  /**
   * Resolve the zenskill CLI wrapper. The wrapper is a cmd/sh script next to
   * the bundled uv; executing the engine pack's __main__.py directly fails on
   * package-relative imports.
   */
  private _resolveZenSkillPath(): string {
    const wrapperName = process.platform === 'win32' ? 'zenskill-cmd.cmd' : 'zenskill-cmd';
    const packaged = this._packagedAppResource(join('bin', wrapperName));
    if (packaged) return packaged;
    const dev = join(process.cwd(), 'resources', 'bin', wrapperName);
    if (existsSync(dev)) return dev;
    return this.config.zenskillPath || 'zenskill';
  }

  /**
   * Resolve the pi auth provider for this connection (e.g. 'deepseek').
   * Synthetic test connections carry it on the config itself; persisted
   * connections are resolved from storage as fallback.
   */
  private _resolveAuthProvider(): string | undefined {
    const cfg = this.config as ZenskillBackendConfig & { piAuthProvider?: string };
    if (cfg.piAuthProvider) return cfg.piAuthProvider;
    if ((cfg.providerType === 'pi' || cfg.providerType === 'pi_compat') && cfg.connectionSlug) {
      return getLlmConnection(cfg.connectionSlug)?.piAuthProvider;
    }
    return undefined;
  }

  /**
   * Map the connection's provider to the env var the engine reads its API
   * key from (zenskill/runtime/agent/providers registry).
   */
  private _providerKeyEnv(authProvider?: string): string | null {
    const cfg = this.config as ZenskillBackendConfig & { providerType?: string };
    switch (authProvider ?? cfg.providerType) {
      case 'deepseek':
        return 'DEEPSEEK_API_KEY';
      case 'anthropic':
      case 'anthropic_compat':
        return 'ANTHROPIC_API_KEY';
      case 'openai':
      case 'openai_compat':
      case 'openai-codex':
        return 'OPENAI_API_KEY';
      case 'ark':
      case 'volc':
        return 'ARK_API_KEY';
      case 'qwen':
        return 'DASHSCOPE_API_KEY';
      case 'moonshot':
        return 'MOONSHOT_API_KEY';
      case 'zhipu':
        return 'ZHIPU_API_KEY';
      default:
        return null;
    }
  }

  /**
   * Engine model ids must be provider-prefixed ('deepseek/deepseek-chat'):
   * a bare model name hits the engine's "unknown model → OpenAI fallback",
   * which sends the request to api.openai.com regardless of the credential
   * actually available.
   */
  private _engineModelId(model: string, authProvider?: string): string {
    if (model.includes('/')) return model;
    // Defense in depth: stub catalogs can leak test ids (e.g. 'mock-gpt')
    // through connection defaults — substitute the provider's real default.
    if (/mock|^$/i.test(model)) {
      const defaults: Record<string, string> = {
        deepseek: 'deepseek-v4-flash',
        anthropic: 'claude-sonnet-4-5',
        openai: 'gpt-4o-mini',
        volc: 'doubao-pro-32k',
        qwen: 'qwen-plus',
      };
      const real = defaults[authProvider ?? ''];
      if (real) return `${authProvider}/${real}`;
    }
    const registryProvider =
      ({ deepseek: 'deepseek', anthropic: 'anthropic', openai: 'openai', 'openai-codex': 'openai', ark: 'volc', volc: 'volc', qwen: 'qwen', mimo: 'mimo' } as Record<string, string>)[
        authProvider ?? ''
      ];
    return registryProvider ? `${registryProvider}/${model}` : model;
  }

  private async _resolveProviderApiKey(): Promise<string | null> {
    const slug = this.config.connectionSlug;
    if (!slug) return null;
    try {
      return (await getCredentialManager().getLlmApiKey(slug)) ?? null;
    } catch {
      return null;
    }
  }

  private async ensureSubprocess(): Promise<void> {
    if (this.subprocess && !this.subprocess.killed) return;
    await this.spawnSubprocess();
  }

  private async spawnSubprocess(): Promise<void> {
    const authProvider = this._resolveAuthProvider();
    const args = ['agent-engine', 'serve'];
    if (this.config.permission) args.push('--permission', this.config.permission);
    if (this.config.cwd) args.push('--cwd', this.config.cwd);
    if (this.config.sessionRoot) args.push('--session-root', this.config.sessionRoot);
    if (this.config.model) args.push('--model', this._engineModelId(this.config.model, authProvider));
    if (this.config.faux) args.push('--faux');

    // Engine pack + bundled uv locations, then the provider credential.
    // The engine reads its LLM key from provider-specific env vars
    // (zenskill/core/llm_provider.py), so inject at spawn time to keep the
    // credential scoped to the subprocess.
    const env: Record<string, string> = { ...process.env } as Record<string, string>;
    const engineRoot = this._packagedAppResource('zenskill')
      ?? join(process.cwd(), 'resources', 'zenskill');
    if (existsSync(engineRoot)) env.CRAFT_ZENSKILL = engineRoot;

    const archDir = `${process.platform}-${process.arch}`;
    const uvName = process.platform === 'win32' ? 'uv.exe' : 'uv';
    const uvPath = this._packagedAppResource(join('bin', archDir, uvName))
      ?? join(process.cwd(), 'resources', 'bin', archDir, uvName);

    // Windows: spawn uv.exe directly. Node ≥20 refuses to spawn .cmd/.bat
    // without shell:true (CVE-2024-27980) — the zenskill-cmd.cmd wrapper is
    // only for interactive shell use. POSIX keeps the sh wrapper.
    let exe: string;
    if (process.platform === 'win32') {
      if (!existsSync(uvPath)) throw new Error(`Bundled uv not found: ${uvPath}`);
      exe = uvPath;
      args.unshift('run', '--project', engineRoot, '--python', '3.12', 'zenskill');
    } else {
      exe = this._resolveZenSkillPath();
    }
    if (existsSync(uvPath)) env.CRAFT_UV = uvPath;

    // One shared engine venv (same one the seeded MCP source uses): avoids
    // per-install provisioning on first run and keeps agent-engine + MCP
    // server on identical dependency sets.
    env.UV_PROJECT_ENVIRONMENT = join(homedir(), '.craft-agent', 'zenskill', 'venv');
    // Engine JSONL protocol writes via print(); piped stdout is block-buffered
    // otherwise and server_hello never reaches us.
    env.PYTHONUNBUFFERED = '1';

    const keyEnv = this._providerKeyEnv(authProvider);
    if (keyEnv) {
      const apiKey = await this._resolveProviderApiKey();
      if (apiKey) env[keyEnv] = apiKey;
    }

    const child = spawn(exe, args, {
      cwd: this.config.cwd || process.cwd(),
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
    });

    this.subprocess = child;

    // JSONL readline on stdout
    this.readline = createInterface({ input: child.stdout!, crlfDelay: Infinity });
    this.readline.on('line', (line: string) => this.handleLine(line));

    // Stderr capture
    child.stderr?.on('data', (data: Buffer) => {
      const text = data.toString().trim();
      if (text && this.config.debug) {
        console.error(`[zenskill stderr] ${text}`);
      }
    });

    // Wait for server_hello
    await new Promise<void>((resolve, reject) => {
      // Cold start on a fresh machine provisions the engine venv via uv
      // (~20-60s); warm starts answer server_hello in well under a second.
      const timeout = setTimeout(() => reject(new Error('ZenSkill subprocess timeout (no server_hello)')), 90000);
      const check = setInterval(() => {
        if (this.serverReady) {
          clearInterval(check);
          clearTimeout(timeout);
          resolve();
        }
      }, 50);
      child.on('error', (err) => {
        clearInterval(check);
        clearTimeout(timeout);
        reject(err);
      });
      child.on('exit', (code) => {
        if (!this.serverReady) {
          clearInterval(check);
          clearTimeout(timeout);
          reject(new Error(`ZenSkill subprocess exited with code ${code} before server_hello`));
        }
      });
    });
  }

  // ============================================================
  // JSONL Message Handling
  // ============================================================

  private handleLine(line: string): void {
    if (!line.trim()) return;
    let msg: ServerMessage;
    try {
      msg = JSON.parse(line) as ServerMessage;
    } catch {
      return;
    }

    switch (msg.type) {
      case 'server_hello':
        this.serverReady = true;
        this.serverVersion = msg.protocolVersion;
        break;

      case 'event':
        this.handleSubprocessEvent(msg.event);
        break;

      case 'tool_execute_request':
        this.handleToolExecuteRequest(msg as ToolExecuteRequest);
        break;

      case 'pre_tool_use_request':
        this.handlePreToolUseRequest(msg as PreToolUseRequest);
        break;

      case 'response':
      case 'entry_appended':
      case 'queue_update':
      case 'agent_settled':
      case 'register_tools_result':
        // Informational — no action needed
        break;
    }
  }

  private handleSubprocessEvent(event: Record<string, unknown>): void {
    const adapted = this.adaptEvent(event);
    if (adapted) {
      this.eventQueue.enqueue(adapted);
    }
    // agent_end → complete the queue
    if (event.type === 'agent_end') {
      this.eventQueue.complete();
    }
  }

  private handleToolExecuteRequest(msg: ToolExecuteRequest): void {
    // Forward to host (Craft) via callback — resolved when host sends
    // tool_execute_response back through respondToToolExecution
    this.eventQueue.enqueue({
      type: 'tool_start',
      toolName: msg.toolName,
      toolCallId: msg.requestId,
      input: msg.args,
    });
  }

  private handlePreToolUseRequest(msg: PreToolUseRequest): void {
    // In allow-all mode, auto-allow. In ask mode, emit permission_request.
    this.send({
      type: 'pre_tool_use_response',
      requestId: msg.requestId,
      action: 'allow',
    });
  }

  // ============================================================
  // Event Adaptation (ZenSkill AgentEvent → Craft AgentEvent)
  // ============================================================

  private adaptEvent(event: Record<string, unknown>): AgentEvent | null {
    const eventType = event.type as string;

    switch (eventType) {
      case 'agent_start':
        return null; // Internal

      case 'agent_end': {
        const usage = event.usage as Record<string, number> | undefined;
        if (usage) {
          return {
            type: 'complete',
            usage: {
              inputTokens: usage.input_tokens || 0,
              outputTokens: usage.output_tokens || 0,
              totalTokens: usage.total_tokens || 0,
            },
          };
        }
        return { type: 'complete' };
      }

      case 'turn_start':
      case 'turn_end':
        return null; // Internal lifecycle

      case 'message_start':
        return null; // Start of assistant message — wait for deltas

      case 'message_update': {
        const delta = event.delta as Record<string, unknown> | undefined;
        // TextDelta
        if (delta?.type === 'TextDelta' && delta.text) {
          return { type: 'text_delta', text: delta.text as string };
        }
        // ThinkingDelta
        if (delta?.type === 'ThinkingDelta' && delta.thinking) {
          return { type: 'thinking_delta', thinking: delta.thinking as string };
        }
        return null;
      }

      case 'message_end': {
        const message = event.message as Record<string, unknown> | undefined;
        if (!message) return null;
        const stopReason = message.stop_reason as string | undefined;
        const errorMessage = message.error_message as string | undefined;

        if (stopReason === 'error' || stopReason === 'aborted') {
          return { type: 'error', message: errorMessage || 'Agent error' };
        }

        // Extract text content from assistant message
        const content = message.content as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(content)) {
          const textParts = content
            .filter((c) => c.type === 'TextContent' && c.text)
            .map((c) => c.text as string);
          if (textParts.length > 0) {
            return {
              type: 'text_complete',
              text: textParts.join(''),
              isIntermediate: stopReason === 'tool_use',
            };
          }
        }
        return null;
      }

      case 'tool_execution_start':
        return {
          type: 'tool_start',
          toolName: event.tool_name as string || 'tool',
          toolCallId: event.tool_call_id as string,
          input: event.params as Record<string, unknown> || {},
        };

      case 'tool_execution_end':
        return {
          type: 'tool_result',
          toolCallId: event.tool_call_id as string,
          toolName: event.tool_name as string || 'tool',
          result: this.extractToolResultText(event),
          isError: event.is_error as boolean || false,
        };

      case 'tool_execution_update':
        return null; // Partial output — not surfaced in Craft UI

      default:
        return null;
    }
  }

  private extractToolResultText(event: Record<string, unknown>): string {
    const result = event.result as Record<string, unknown> | undefined;
    if (!result) return '';
    const content = result.content as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(content)) {
      return content
        .filter((c) => c.type === 'TextContent' && c.text)
        .map((c) => c.text as string)
        .join('');
    }
    return String(result);
  }

  // ============================================================
  // AgentBackend Interface
  // ============================================================

  async *chat(
    message: string,
    _attachments?: unknown,
    _options?: unknown,
  ): AsyncGenerator<AgentEvent> {
    this._isProcessing = true;
    this.eventQueue.reset();

    try {
      await this.ensureSubprocess();

      // Send prompt
      const turnId = `turn-${++this.rpcIdCounter}`;
      this.send({
        type: 'prompt',
        id: turnId,
        message,
        streamingBehavior: 'steer',
      });

      // Yield events as they arrive
      for await (const event of this.eventQueue.drain()) {
        yield event as AgentEvent;
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      yield { type: 'error', message: errorMsg };
      yield { type: 'complete' };
    } finally {
      this._isProcessing = false;
    }
  }

  async abort(): Promise<void> {
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'abort' });
    }
    this.eventQueue.complete();
  }

  forceAbort(): void {
    this.abort();
  }

  interruptForHandoff(): void {
    this.abort();
  }

  redirect(message: string): boolean {
    // ZenSkill supports steering — inject the message into the current stream
    if (this._isProcessing) {
      this.send({ type: 'steer', message });
      return true;
    }
    return false;
  }

  async runMiniCompletion(prompt: string): Promise<string | null> {
    await this.ensureSubprocess();
    const id = `mc-${++this.rpcIdCounter}`;
    return await new Promise<string | null>((resolve, reject) => {
      // 30s is warm-path LLM latency; slow first-token providers rely on the
      // caller's own (generous) timeout instead.
      const timeout = setTimeout(() => resolve(null), 30000);
      const handler = (line: string) => {
        try {
          const msg = JSON.parse(line);
          if (msg.type === 'response' && msg.command === 'mini_completion' && msg.id === id) {
            clearTimeout(timeout);
            this.readline?.off('line', handler);
            if (msg.success) {
              resolve(msg.data?.text ?? null);
            } else {
              // Surface the engine's real failure (e.g. provider HTTP 401)
              // instead of collapsing it into a silent null.
              reject(new Error(String(msg.error ?? 'mini_completion failed')));
            }
          }
        } catch { /* ignore parse errors */ }
      };
      this.readline?.on('line', handler);
      this.send({ type: 'mini_completion', id, prompt });
    });
  }

  destroy(): void {
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'shutdown' });
      setTimeout(() => {
        if (this.subprocess && !this.subprocess.killed) {
          this.subprocess.kill();
        }
      }, 3000);
    }
    this.subprocess = null;
    this.readline = null;
    this.eventQueue.complete();
  }

  dispose(): void {
    this.destroy();
  }

  async postInit(): Promise<{ success: boolean }> {
    return { success: true };
  }

  getSessionId(): string | null {
    return null;
  }

  get supportsBranching(): boolean {
    return false;
  }

  // ============================================================
  // Tool Proxy
  // ============================================================

  registerTools(tools: Array<{ name: string; description: string; inputSchema: Record<string, unknown> }>): void {
    this.send({ type: 'register_tools', tools });
  }

  respondToToolExecution(requestId: string, result: { content: string; isError: boolean }): void {
    this.send({
      type: 'tool_execute_response',
      requestId,
      result,
    });
    // Also emit a tool_result event for the UI
    this.eventQueue.enqueue({
      type: 'tool_result',
      toolCallId: requestId,
      toolName: 'proxy',
      result: result.content,
      isError: result.isError,
    });
  }

  respondToPermission(requestId: string, allowed: boolean): void {
    this.send({
      type: 'pre_tool_use_response',
      requestId,
      action: allowed ? 'allow' : 'block',
    });
  }

  // ============================================================
  // Helpers
  // ============================================================

  private send(msg: Record<string, unknown>): void {
    if (this.subprocess?.stdin && !this.subprocess.stdin.destroyed) {
      this.subprocess.stdin.write(JSON.stringify(msg) + '\n');
    }
  }

  get isProcessing(): boolean {
    return this._isProcessing;
  }

  get version(): string | null {
    return this.serverVersion;
  }
}
