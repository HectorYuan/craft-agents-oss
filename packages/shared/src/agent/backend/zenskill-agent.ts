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
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { createInterface, type Interface as ReadlineInterface } from 'node:readline';
import { BaseAgent } from '../base-agent.ts';
import type { AgentEvent } from '@craft-agent/core/types';
import type { BackendConfig } from './types.ts';
import { AbortReason } from '../core/session-lifecycle.ts';
import type { LLMQueryRequest, LLMQueryResult } from '../llm-tool.ts';
import type { ThinkingLevel } from '../thinking-levels.ts';

// ============================================================
// JSONL Protocol Types (mirror zenskill/runtime/agent/rpc.py)
// ============================================================

interface ServerHello {
  type: 'server_hello';
  protocolVersion: string;
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
  | ToolExecuteRequest
  | PreToolUseRequest
  | ServerResponse
  | RegisterToolsResult
  | { type: string; [key: string]: unknown };

// ============================================================
// Typed Error (P0-3)
// ============================================================

interface AgentError {
  code: 'auth_error' | 'rate_limited' | 'service_error' | 'network_error' | 'unknown';
  title: string;
  message: string;
  retryable: boolean;
  retryAfterMs?: number;
}

function parseAgentError(raw: string): AgentError {
  const lower = raw.toLowerCase();
  if (lower.includes('api key') || lower.includes('unauthorized') || lower.includes('401') || lower.includes('invalid')) {
    return { code: 'auth_error', title: 'Authentication Error', message: raw, retryable: false };
  }
  if (lower.includes('rate limit') || lower.includes('429') || lower.includes('too many')) {
    return { code: 'rate_limited', title: 'Rate Limited', message: raw, retryable: true, retryAfterMs: 30000 };
  }
  if (lower.includes('500') || lower.includes('502') || lower.includes('503') || lower.includes('service')) {
    return { code: 'service_error', title: 'Service Error', message: raw, retryable: true, retryAfterMs: 5000 };
  }
  if (lower.includes('timeout') || lower.includes('econnrefused') || lower.includes('network')) {
    return { code: 'network_error', title: 'Network Error', message: raw, retryable: true, retryAfterMs: 3000 };
  }
  return { code: 'unknown', title: 'Error', message: raw, retryable: false };
}

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

export class ZenskillAgent extends BaseAgent {
  protected backendName = 'ZenSkill Agent Engine';
  protected _supportsBranching = true;

  // ZenSkill-specific state
  private subprocess: ChildProcess | null = null;
  private readline: ReadlineInterface | null = null;
  private rpcIdCounter = 0;
  private eventQueue = new EventQueue();

  // Error deduplication (P0-2)
  private lastError: string | null = null;
  private errorRepeatCount = 0;
  private static MAX_ERROR_REPEAT = 3;

  // State
  private _isProcessing = false;
  private serverReady = false;
  private serverVersion: string | null = null;
  private _faux = false;
  private _cachedSystemPrompt: string | null = null;

  constructor(config: BackendConfig) {
    super(config, 'deepseek/deepseek-v4-flash');
    this._faux = !!(config as any).faux || false;
    this._supportsBranching = true;
    this.startConfigWatcher();
  }

  // ============================================================
  // Lifecycle
  // ============================================================

  private async ensureSubprocess(): Promise<void> {
    if (this.subprocess && !this.subprocess.killed) return;
    await this.spawnSubprocess();
  }

  private async spawnSubprocess(): Promise<void> {
    const zenskillPath = 'zenskill';
    const args = ['agent-engine', 'serve'];
    const permMode = (this.config as any).permissionMode || this.config.session?.permissionMode;
    const permMap: Record<string, string> = { 'allow-all': 'full', 'full': 'full', 'restricted': 'restricted', 'plan': 'plan', 'sandbox': 'sandbox' };
    const mappedPerm = permMap[permMode] || undefined;
    if (mappedPerm) args.push('--permission', mappedPerm);
    if (this.workingDirectory) args.push('--cwd', this.workingDirectory);
    if (this._model) args.push('--model', this._model);
    if (this._faux) args.push('--faux');

    const env = { ...process.env };
    const apiKey = await this.resolveApiKey(this.config.connectionSlug);
    if (apiKey) {
      env['DEEPSEEK_API_KEY'] = apiKey;
    }

    const child = spawn(zenskillPath, args, {
      cwd: this.workingDirectory || process.cwd(),
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
    });

    this.subprocess = child;

    // JSONL readline on stdout
    this.readline = createInterface({ input: child.stdout!, crlfDelay: Infinity });
    this.readline.on('line', (line: string) => this.handleLine(line));

    // P0-1: Subprocess exit/crash handling
    child.on('exit', (code, signal) => {
      if (!this.serverReady) return; // Already handled in spawn timeout
      const reason = signal ? `killed by ${signal}` : `exit code ${code}`;
      console.error(`[zenskill-agent] Subprocess died: ${reason}`);
      this.handleSubprocessCrash(`Subprocess ${reason}`);
    });

    child.on('error', (err) => {
      console.error(`[zenskill-agent] Subprocess error: ${err.message}`);
      this.handleSubprocessCrash(err.message);
    });

    // Stderr capture (debug only)
    child.stderr?.on('data', (data: Buffer) => {
      const text = data.toString().trim();
      if (text && this.config.debugMode?.enabled) {
        console.error(`[zenskill stderr] ${text}`);
      }
    });

    // Wait for server_hello
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('ZenSkill subprocess timeout (no server_hello)')), 15000);
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

    // P1-9: Enable auto-compaction
    this.send({ type: 'set_auto_compaction', enabled: true });
  }

  // P0-1: Handle subprocess crash
  private handleSubprocessCrash(errorMsg: string): void {
    const parsed = parseAgentError(errorMsg);
    const deduped = this.deduplicateError(parsed.message);
    if (deduped) {
      this.eventQueue.enqueue({ type: 'error', message: deduped });
    }
    this.eventQueue.complete();
    this._isProcessing = false;
    this.subprocess = null;
    this.readline = null;
    this.serverReady = false;
  }

  // P0-2: Error deduplication
  private deduplicateError(message: string): string | null {
    if (message === this.lastError) {
      this.errorRepeatCount++;
      if (this.errorRepeatCount > ZenskillAgent.MAX_ERROR_REPEAT) {
        return null; // Suppress repeated errors
      }
      return `[${this.errorRepeatCount}/${ZenskillAgent.MAX_ERROR_REPEAT}] ${message}`;
    }
    this.lastError = message;
    this.errorRepeatCount = 1;
    return message;
  }

  // ============================================================
  // P0-4: Graceful Shutdown
  // ============================================================

  private async killSubprocessGracefully(): Promise<void> {
    if (!this.subprocess || this.subprocess.killed) return;

    // Try shutdown RPC first
    try {
      this.send({ type: 'shutdown' });
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          this.subprocess?.kill('SIGTERM');
          resolve();
        }, 2000);
        this.subprocess?.on('exit', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    } catch {
      // Fallback to SIGTERM
      this.subprocess.kill('SIGTERM');
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          this.subprocess?.kill('SIGKILL');
          resolve();
        }, 2000);
        this.subprocess?.on('exit', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
  }

  // ============================================================
  // P1-8: Config Watcher
  // ============================================================

  override destroy(): void {
    this.stopConfigWatcher();
    this.killSubprocessGracefully();
    this.eventQueue.complete();
    this._isProcessing = false;
  }

  override async clearHistory(): Promise<void> {
    await this.killSubprocessGracefully();
    this._cachedSystemPrompt = null;
    this.serverReady = false;
  }

  override setWorkspace(workspace: any): void {
    super.setWorkspace(workspace);
    this._cachedSystemPrompt = null;
    this.killSubprocessGracefully();
  }

  // ============================================================
  // JSONL Message Handling
  // ============================================================

  private handleLine(line: string): void {
    if (!line.trim()) return;
    let msg: Record<string, any>;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }

    const msgType = msg.type as string;

    if (msgType === 'event') {
      this.handleSubprocessEvent(msg.event);
      return;
    }

    if ([
      'agent_start', 'agent_end', 'turn_start', 'turn_end',
      'message_start', 'message_update', 'message_end',
      'tool_execution_start', 'tool_execution_end', 'tool_execution_update',
    ].includes(msgType)) {
      this.handleSubprocessEvent(msg);
      return;
    }

    switch (msgType) {
      case 'server_hello':
        this.serverReady = true;
        this.serverVersion = msg.protocolVersion;
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
        break;

      case 'compaction_end':
        this._cachedSystemPrompt = null;
        break;
    }
  }

  private handleSubprocessEvent(event: Record<string, unknown>): void {
    const adapted = this.adaptEvent(event);
    if (adapted) {
      this.eventQueue.enqueue(adapted);
    }
    if (event.type === 'agent_end') {
      this.eventQueue.complete();
    }
  }

  private async handleToolExecuteRequest(msg: ToolExecuteRequest): Promise<void> {
    this.eventQueue.enqueue({
      type: 'tool_start',
      toolName: msg.toolName,
      toolUseId: msg.requestId,
      input: msg.args,
    });

    const permCheck = this.checkToolPermission(msg.toolName, msg.args);
    if (permCheck.blocked) {
      this.send({
        type: 'tool_execute_response',
        requestId: msg.requestId,
        result: { content: permCheck.reason || 'Permission denied', isError: true },
      });
      return;
    }

    try {
      const result = await this.routeToolCall(msg.toolName, msg.args);
      this.send({
        type: 'tool_execute_response',
        requestId: msg.requestId,
        result,
      });
    } catch (error) {
      this.send({
        type: 'tool_execute_response',
        requestId: msg.requestId,
        result: {
          content: error instanceof Error ? error.message : String(error),
          isError: true,
        },
      });
    }
  }

  private handlePreToolUseRequest(msg: PreToolUseRequest): void {
    const permCheck = this.checkToolPermission(msg.toolName, msg.input);
    this.send({
      type: 'pre_tool_use_response',
      requestId: msg.requestId,
      action: permCheck.blocked ? 'block' : 'allow',
    });
  }

  // ============================================================
  // Tool Routing
  // ============================================================

  private async routeToolCall(
    toolName: string,
    args: Record<string, unknown>,
  ): Promise<{ content: string; isError: boolean }> {
    const mcpPool = (this.config as any).mcpPool;

    if (mcpPool?.isProxyTool?.(toolName)) {
      try {
        const result = await mcpPool.callTool(toolName, args);
        return { content: typeof result === 'string' ? result : JSON.stringify(result), isError: false };
      } catch (error) {
        return { content: error instanceof Error ? error.message : String(error), isError: true };
      }
    }

    return { content: `Unknown tool: ${toolName}`, isError: true };
  }

  private checkToolPermission(
    toolName: string,
    _args: Record<string, unknown>,
  ): { blocked: boolean; reason?: string } {
    const permMode = (this.config as any).permissionMode || this.config.session?.permissionMode;
    const mode = permMode === 'plan' ? 'plan' : permMode === 'restricted' ? 'restricted' : 'full';

    if (mode === 'full') return { blocked: false };

    if (mode === 'plan') {
      const readOnlyTools = ['read', 'grep', 'find', 'ls', 'skill_search', 'skill_trending',
        'skill_context', 'dashboard_summary', 'memory_list', 'memory_search',
        'gtd_inbox_list', 'gtd_review', 'action_list', 'project_list',
        'energy_level', 'habit_list', 'achievement_list', 'goal_progress',
        'proactive_insight', 'context_guide', 'learning_path', 'growth_report',
        'growth_milestone', 'web_search', 'web_fetch'];
      if (readOnlyTools.some(t => toolName.includes(t))) return { blocked: false };
      return { blocked: true, reason: `Tool '${toolName}' not allowed in plan mode` };
    }

    if (mode === 'restricted') {
      if (toolName.startsWith('mcp__')) return { blocked: false };
      return { blocked: true, reason: `Tool '${toolName}' not in sandbox whitelist` };
    }

    return { blocked: false };
  }

  // ============================================================
  // MCP Pool Tools Registration
  // ============================================================

  private registerPoolTools(): void {
    const mcpPool = (this.config as any).mcpPool;
    if (!mcpPool?.getProxyToolDefs) return;
    const proxyDefs = mcpPool.getProxyToolDefs();
    if (proxyDefs.length > 0) {
      this.send({ type: 'register_tools', tools: proxyDefs });
    }
  }

  // ============================================================
  // System Prompt Construction
  // ============================================================

  private async buildSystemPrompt(): Promise<string | null> {
    if (this._cachedSystemPrompt !== null) return this._cachedSystemPrompt;

    try {
      const { readFileSync, existsSync, readdirSync } = await import('node:fs');
      const { join } = await import('node:path');

      const workspaceRoot = this.workingDirectory || process.cwd();
      const sourcesDir = join(workspaceRoot, 'sources');
      let guideContent = '';

      if (existsSync(sourcesDir)) {
        const sourceDirs = readdirSync(sourcesDir, { withFileTypes: true })
          .filter(d => d.isDirectory())
          .map(d => d.name);

        for (const slug of sourceDirs) {
          const guidePath = join(sourcesDir, slug, 'guide.md');
          if (existsSync(guidePath)) {
            guideContent = readFileSync(guidePath, 'utf-8');
            break;
          }
        }
      }

      if (!guideContent) {
        this._cachedSystemPrompt = null;
        return null;
      }

      const parts: string[] = [];
      parts.push(`You are running in workspace: ${workspaceRoot}`);
      parts.push(`Model: ${this._model || 'deepseek/deepseek-v4-flash'}`);
      parts.push('');
      parts.push(guideContent);

      this._cachedSystemPrompt = parts.join('\n');
      return this._cachedSystemPrompt;
    } catch {
      this._cachedSystemPrompt = null;
      return null;
    }
  }

  // ============================================================
  // Event Adaptation (ZenSkill AgentEvent → Craft AgentEvent)
  // ============================================================

  adaptEvent(event: Record<string, any>): AgentEvent | null {
    const eventType = event.type as string;

    switch (eventType) {
      case 'agent_start':
      case 'turn_start':
      case 'turn_end':
      case 'message_start':
        return null;

      case 'agent_end': {
        const usage = event.usage as Record<string, number> | undefined;
        if (usage) {
          return {
            type: 'complete',
            usage: {
              inputTokens: usage.input_tokens || 0,
              outputTokens: usage.output_tokens || 0,
            },
          };
        }
        return { type: 'complete' };
      }

      case 'message_update': {
        const delta = event.delta as Record<string, unknown> | undefined;
        if (!delta) return null;
        const deltaKind = (delta.kind || delta.type) as string;
        const deltaText = delta.text as string;
        if ((deltaKind === 'text' || deltaKind === 'TextDelta') && deltaText) {
          return { type: 'text_delta', text: deltaText };
        }
        return null;
      }

      case 'message_end': {
        const nested = event.message as Record<string, unknown> | undefined;
        const stopReason = (nested?.stopReason ?? nested?.stop_reason ?? event.stopReason) as string | undefined;
        const errorMessage = (nested?.errorMessage ?? event.error_message) as string | undefined;

        if (stopReason === 'error' || stopReason === 'aborted') {
          const parsed = parseAgentError(errorMessage || 'Agent error');
          return { type: 'error', message: `[${parsed.code}] ${parsed.title}: ${parsed.message}` };
        }

        const textFromNested = nested?.text as string | undefined;
        const textFromTopLevel = event.text as string | undefined;
        const textContent = textFromNested ?? textFromTopLevel;
        const content = nested?.content as Array<Record<string, unknown>> | undefined;

        if (textContent && typeof textContent === 'string' && !Array.isArray(content)) {
          return {
            type: 'text_complete',
            text: textContent,
            isIntermediate: stopReason === 'tool_use',
          };
        }

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
          toolName: (event.tool_name as string) || 'tool',
          toolUseId: event.tool_call_id as string,
          input: (event.params as Record<string, unknown>) || {},
        };

      case 'tool_execution_end':
        return {
          type: 'tool_result',
          toolUseId: event.tool_call_id as string,
          toolName: (event.tool_name as string) || 'tool',
          result: this.extractToolResultText(event),
          isError: (event.is_error as boolean) || false,
        };

      case 'tool_execution_update':
        return null;

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

  protected async *chatImpl(
    message: string,
    attachments?: unknown,
    _options?: unknown,
  ): AsyncGenerator<AgentEvent> {
    this._isProcessing = true;
    this.eventQueue.reset();
    this.lastError = null;
    this.errorRepeatCount = 0;

    try {
      await this.ensureSubprocess();

      const turnId = `turn-${++this.rpcIdCounter}`;
      const systemPrompt = await this.buildSystemPrompt();

      // P1-5: Process attachments
      const promptMsg: Record<string, unknown> = {
        type: 'prompt',
        id: turnId,
        message,
        systemPrompt: systemPrompt || undefined,
        streamingBehavior: 'steer',
      };

      // Add attachments if present
      if (attachments && Array.isArray(attachments) && attachments.length > 0) {
        const attachmentParts: string[] = [];
        const images: Array<{ type: string; data: string; mimeType: string }> = [];

        for (const att of attachments as any[]) {
          if (att.mimeType?.startsWith('image/') && att.base64) {
            images.push({ type: 'image', data: att.base64, mimeType: att.mimeType });
          } else if (att.storedPath || att.path) {
            attachmentParts.push(`[Attached file: ${att.name}]\n[Stored at: ${att.storedPath || att.path}]`);
          }
        }

        if (attachmentParts.length > 0) {
          promptMsg.message = message + '\n\n' + attachmentParts.join('\n');
        }
        if (images.length > 0) {
          (promptMsg as any).images = images;
        }
      }

      this.send(promptMsg);

      for await (const event of this.eventQueue.drain()) {
        yield event as AgentEvent;
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      const parsed = parseAgentError(errorMsg);
      yield { type: 'error', message: `[${parsed.code}] ${parsed.title}: ${parsed.message}` };
      yield { type: 'complete' };
    } finally {
      this._isProcessing = false;
    }
  }

  override async abort(): Promise<void> {
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'abort' });
    }
    this.eventQueue.complete();
  }

  override forceAbort(_reason: AbortReason = AbortReason.UserStop): void {
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'abort' });
    }
    this.eventQueue.complete();
    this._isProcessing = false;
  }

  override isProcessing(): boolean {
    return this._isProcessing;
  }

  // ============================================================
  // P1-10: Model / Thinking Level
  // ============================================================

  override setModel(model: string): void {
    super.setModel(model);
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'set_model', model });
    }
    this._cachedSystemPrompt = null;
  }

  override setThinkingLevel(level: ThinkingLevel): void {
    super.setThinkingLevel(level);
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'set_thinking_level', level });
    }
  }

  // ============================================================
  // P0-4: Steer
  // ============================================================

  override respondToPermission(requestId: string, allowed: boolean, _alwaysAllow?: boolean): void {
    this.send({
      type: 'pre_tool_use_response',
      requestId,
      action: allowed ? 'allow' : 'block',
    });
  }

  override redirect(message: string): boolean {
    if (this.subprocess && !this.subprocess.killed) {
      this.send({ type: 'steer', message });
      return true;
    }
    return false;
  }

  // ============================================================
  // Mini Completion / Query
  // ============================================================

  override async runMiniCompletion(prompt: string): Promise<string | null> {
    try {
      await this.ensureSubprocess();
      const id = `mc-${++this.rpcIdCounter}`;
      return await new Promise<string | null>((resolve) => {
        const timeout = setTimeout(() => resolve(null), 30000);
        const handler = (line: string) => {
          try {
            const msg = JSON.parse(line);
            if (msg.type === 'response' && msg.command === 'mini_completion' && msg.id === id) {
              clearTimeout(timeout);
              this.readline?.off('line', handler);
              resolve(msg.success ? msg.data?.text ?? null : null);
            }
          } catch { /* ignore */ }
        };
        this.readline?.on('line', handler);
        this.send({ type: 'mini_completion', id, prompt });
      });
    } catch {
      return null;
    }
  }

  override async queryLlm(_request: LLMQueryRequest): Promise<LLMQueryResult> {
    const text = await this.runMiniCompletion(_request.prompt);
    return { text: text || '', model: this._model };
  }

  // ============================================================
  // Compaction
  // ============================================================

  async requestCompact(instruction?: string): Promise<{ compacted: boolean; tokensBefore: number | null; tokensAfter: number | null } | null> {
    try {
      await this.ensureSubprocess();
      const id = `compact-${++this.rpcIdCounter}`;
      return await new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 300000);
        const handler = (line: string) => {
          try {
            const msg = JSON.parse(line);
            if (msg.type === 'response' && msg.command === 'compact' && msg.id === id) {
              clearTimeout(timeout);
              this.readline?.off('line', handler);
              if (msg.success && msg.data) {
                this._cachedSystemPrompt = null;
                resolve({
                  compacted: msg.data.compacted ?? false,
                  tokensBefore: msg.data.tokensBefore ?? null,
                  tokensAfter: msg.data.tokensAfter ?? null,
                });
              } else {
                resolve(null);
              }
            }
          } catch { /* ignore */ }
        };
        this.readline?.on('line', handler);
        this.send({ type: 'compact', id, instruction });
      });
    } catch {
      return null;
    }
  }

  // ============================================================
  // API Key Resolution
  // ============================================================

  private async resolveApiKey(connectionSlug?: string): Promise<string | null> {
    try {
      const { getCredentialManager } = await import('../../credentials/manager.ts');
      const { getLlmConnection } = await import('../../config/storage.ts');
      const manager = getCredentialManager();

      if (connectionSlug) {
        const key = await manager.getLlmApiKey(connectionSlug);
        if (key) return key;

        const conn = getLlmConnection(connectionSlug);
        if (conn?.piAuthProvider) {
          const allConns = await this.getConnections();
          for (const c of allConns) {
            if (c.slug !== connectionSlug && c.piAuthProvider === conn.piAuthProvider && c.authType === 'api_key') {
              const key = await manager.getLlmApiKey(c.slug);
              if (key) return key;
            }
          }
        }

        const modelParts = this._model?.split('/');
        if (modelParts && modelParts.length >= 2) {
          const providerPrefix = modelParts[0];
          const allConns = await this.getConnections();
          for (const c of allConns) {
            if (c.slug !== connectionSlug && c.piAuthProvider === providerPrefix && c.authType === 'api_key') {
              const key = await manager.getLlmApiKey(c.slug);
              if (key) return key;
            }
          }
        }
      }

      return await manager.getApiKey();
    } catch {
      return null;
    }
  }

  private async getConnections(): Promise<Array<{ slug: string; piAuthProvider?: string; authType: string }>> {
    try {
      const { getLlmConnections } = await import('../../config/storage.ts');
      return getLlmConnections();
    } catch {
      return [];
    }
  }

  // ============================================================
  // Helpers
  // ============================================================

  private send(msg: Record<string, unknown>): void {
    if (this.subprocess?.stdin && !this.subprocess.stdin.destroyed) {
      this.subprocess.stdin.write(JSON.stringify(msg) + '\n');
    }
  }
}
