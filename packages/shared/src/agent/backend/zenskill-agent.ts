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

import { spawn, type ChildProcess, type SpawnOptions } from "node:child_process";
import { ZENSKILL_MODEL_REGISTRY } from '../../config/models-zenskill.ts';
import { DEFAULT_MODEL } from '../../config/models.ts';
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
// Helpers
// ============================================================

function safeParseJson(text: string): any {
  try {
    return JSON.parse(text)
  } catch {
    // Try extracting JSON from MCP content wrapper
    try {
      const inner = JSON.parse(text)
      const innerText = inner?.content?.[0]?.text
      if (typeof innerText === 'string') return JSON.parse(innerText)
    } catch { /* ignore */ }
    return null
  }
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

  // C1: 引擎侧会话续接 —— 模型上下文活在引擎子进程内存与其自身会话文件
  // (~/.zenskill/agent/sessions/{sid}.jsonl) 里，宿主 session.jsonl 只服务 UI。
  // engineSessionId 记录当前绑定的引擎会话（含崩溃重启前捕获值，供重启后重续）；
  // reportedEngineSessionId 对宿主落库回调去重。
  private engineSessionId: string | null = null;
  private reportedEngineSessionId: string | null = null;

  // G3: Crash-restart policy — idle crashes auto-restart with backoff;
  // in-flight crashes report instead (silently restarting would drop the
  // conversation context without the user noticing).
  private crashRestartCount = 0;
  private restartPending = false;
  private destroyed = false;
  private static MAX_CRASH_RESTARTS = 3;
  private static RESTART_BACKOFF_MS = [1000, 4000, 16000];

  constructor(config: BackendConfig) {
    // 模型优先级：GUI 连接/会话配置(config.model) > zenskill llm_config.json（spawn
    // 时不带 --model，由 Python resolve_model 兜底解析）。禁止硬编码具体模型名——
    // 发布后用户环境各异，硬编码会让 GUI 永远覆盖用户配置。
    super(config, '');
    this._faux = !!(config as any).faux || false;
    this._supportsBranching = true;
    this.startConfigWatcher();
  }

  // ============================================================
  // Path Resolution
  // ============================================================

  private _resolveZenSkillPath(): string {
    const isWin = process.platform === 'win32';
    const wrapperName = isWin ? 'zenskill-cmd.cmd' : 'zenskill-cmd';

    // 1. Packaged app: resources/bin/zenskill-cmd
    if ((process as any).resourcesPath) {
      const packaged = require('path').join(
        (process as any).resourcesPath, 'app', 'resources', 'bin', wrapperName,
      );
      if (require('fs').existsSync(packaged)) return packaged;
    }

    // 2. Dev runtime: walk up to project root
    if (process.env.CRAFT_DEV_RUNTIME) {
      const devPath = require('path').join(
        __dirname, '..', '..', '..', '..', '..', 'apps', 'electron', 'resources', 'bin', wrapperName,
      );
      if (require('fs').existsSync(devPath)) return devPath;
    }

    // 3. Fallback: PATH
    return 'zenskill';
  }

  // ============================================================
  // Lifecycle
  // ============================================================

  private async ensureSubprocess(): Promise<void> {
    if (this.subprocess && !this.subprocess.killed) {
      // Reuse path: re-send register_tools defensively (idempotent on the
      // subprocess side — dict assignment). Covers any case where the
      // subprocess lost its proxy registrations (internal session reset,
      // post-crash-restart edge) — otherwise MCP tools go invisible to the
      // model and every call returns Unknown tool.
      this.registerPoolTools();
      return;
    }
    await this.spawnSubprocess();
    this.crashRestartCount = 0; // fresh instance, fresh crash budget (G3)
  }

  private async spawnSubprocess(): Promise<void> {
    const zenskillPath = this._resolveZenSkillPath();
    const args = ['agent-engine', 'serve'];
    const permMode = (this.config as any).permissionMode || this.config.session?.permissionMode;
    const permMap: Record<string, string> = { 'allow-all': 'full', 'full': 'full', 'restricted': 'restricted', 'plan': 'plan', 'sandbox': 'sandbox' };
    const mappedPerm = permMap[permMode] || undefined;
    if (mappedPerm) args.push('--permission', mappedPerm);
    if (this.workingDirectory) args.push('--cwd', this.workingDirectory);
    if (this._model) {
      // GUI 连接的模型 ID 带 providerType 前缀（如 `pi/deepseek-v4-flash`）。
      // 引擎已不是 pi 后端：`pi/...` 会落进未知提供方静默空回合（实测：
      // 兜底 openai + api.openai.com，DeepSeek key 打 OpenAI 官方返回
      // 401 非 SSE 响应，被流解析器吞掉表现为挂起）；剥掉前缀让引擎按
      // PREDEFINED_MODELS/registry 正常路由。
      const engineModel = this._model.replace(/^pi\//i, '');
      // 旧会话可能持久化了引擎注册表之外的模型（如修复前的默认 claude-opus-4-8）：
      // 未知模型走未知提供方兜底必然失败，回退到注册表第一项（当前默认）。
      // 自定义网关连接（config.baseUrl）的模型 id 任意、不在静态目录也必须
      // 透传——否则用户配的网关模型被 DEFAULT_MODEL 顶掉（baseUrl 修复链闭合）
      const known = ZENSKILL_MODEL_REGISTRY.some((m) => m.id === engineModel);
      const isGateway = !!this.config.baseUrl;
      args.push('--model', isGateway || known ? engineModel : DEFAULT_MODEL);
    }
    if (this._faux) args.push('--faux');
    // C5: --debug 取证链 —— 宿主 debug 模式时引擎同步开 DEBUG 日志（stderr →
    // 上方 stderr 转发 → 控制台），prompt 组装/续接回放可在日志直接定位
    if (this.config.debugMode?.enabled) args.push('--debug');

    const env = { ...process.env };
    // Windows 中文环境：引擎子进程缺 PYTHONUTF8 时按系统代码页（GBK）读写
    // stdio，中文消息会变乱码并产生 lone surrogate 打挂 LLM 请求
    env['PYTHONUTF8'] = '1';
    env['PYTHONIOENCODING'] = 'utf-8';
    const apiKey = await this.resolveApiKey(this.config.connectionSlug);
    if (apiKey) {
      env['DEEPSEEK_API_KEY'] = apiKey;
      // 引擎 agent 循环的 OpenAI 兼容路径（pi/deepseek-*，runtime/agent/providers）
      // 读取 OPENAI_API_KEY 鉴权；DEEPSEEK_API_KEY 单独注入不会被 pi 的凭据
      // 解析命中。单连接（ZenSkill Backend）下两键同值即完成路由。
      env['OPENAI_API_KEY'] = apiKey;
    }
    // 连接级自定义网关透传（Desktop baseUrl 断点修复，对齐 Server Mode）：
    // 引擎 _apply_connection_env_overrides 消费；单引擎进程=单连接，env 即
    // 连接作用域。未设置时路径不变。
    if (this.config.baseUrl) {
      env['ZENSKILL_AGENT_BASE_URL'] = String(this.config.baseUrl);
    }
    if ((this.config as any).customEndpointApi) {
      env['ZENSKILL_AGENT_API'] = String((this.config as any).customEndpointApi);
    }

    // Set CRAFT_ZENSKILL for wrapper scripts
    if ((process as any).resourcesPath) {
      env['CRAFT_ZENSKILL'] = require('path').join(
        (process as any).resourcesPath, 'app', 'resources', 'zenskill',
      );
      env['CRAFT_UV'] = require('path').join(
        (process as any).resourcesPath, 'app', 'resources', 'bin',
        process.platform === 'win32' ? 'win32-x64' : `${process.platform}-${process.arch}`,
        process.platform === 'win32' ? 'uv.exe' : 'uv',
      );
    }

    // Windows: Node ≥20.12 refuses to spawn .cmd/.bat without shell:true
    // (CVE-2024-27980 mitigation) → packaged installs get `spawn EINVAL` because
    // _resolveZenSkillPath() resolves to zenskill-cmd.cmd. Bypass the wrapper by
    // invoking the bundled uv.exe directly with the wrapper's semantics:
    // cd %CRAFT_ZENSKILL% && uv run --project %CRAFT_ZENSKILL% --python 3.12 zenskill ...
    let command = zenskillPath;
    let spawnArgs = args;
    const expandTilde = (p: string): string =>
      p.startsWith('~') ? require('path').join(require('os').homedir(), p.slice(1)) : p;
    let cwd = this.workingDirectory ? expandTilde(this.workingDirectory) : process.cwd();
    if (process.platform === 'win32' && /\.cmd$/i.test(zenskillPath) && env['CRAFT_UV'] && env['CRAFT_ZENSKILL']) {
      command = env['CRAFT_UV'] as string;
      spawnArgs = [
        'run', '--project', env['CRAFT_ZENSKILL'] as string, '--python', '3.12',
        'zenskill', ...args,
      ];
      if (!env['UV_PROJECT_ENVIRONMENT']) {
        env['UV_PROJECT_ENVIRONMENT'] = require('path').join(
          env['USERPROFILE'] || require('os').homedir(), '.zenskill', 'electron-venv',
        );
      }
      if (!env['UV_PYTHON_INSTALL_DIR']) {
        env['UV_PYTHON_INSTALL_DIR'] = require('path').join(env['CRAFT_ZENSKILL'], 'python');
      }
      cwd = env['CRAFT_ZENSKILL'] as string;
    }

    const spawnOpts: SpawnOptions = {
      stdio: ['pipe', 'pipe', 'pipe'],
      env,
      windowsHide: true,
    };
    // Residual .cmd case (dev runtime without CRAFT_* env): shell escapes EINVAL.
    // Args are code-controlled, so shell:true is acceptable here.
    if (process.platform === 'win32' && /\.(cmd|bat)$/i.test(command)) {
      spawnOpts.shell = true;
    } else {
      spawnOpts.cwd = cwd;
    }

    const child = spawn(command, spawnArgs, spawnOpts);

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
      // uv 冷启动（首装 venv 同步）可超过 1 分钟，15s 会误判握手超时
      const timeout = setTimeout(() => reject(new Error('ZenSkill subprocess timeout (no server_hello; uv first-run may still be syncing deps — retry once)')), 90000);
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

    // Register MCP pool tools with subprocess (critical: without this the
    // model cannot see mcp__zenskill__* tools)
    this.registerPoolTools();

    // C1: 有已知引擎会话 id 时续接（应用重启 / 崩溃重启 / auth-retry 重建 agent
    // 后模型上下文不再从零开始）。必须在首条 prompt 前完成（引擎运行中拒切）。
    await this.resumeEngineSession();
  }

  // P0-1 + G3: Handle subprocess crash — distinguish idle vs in-flight
  private handleSubprocessCrash(errorMsg: string): void {
    const wasProcessing = this._isProcessing;
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

    if (this.destroyed) return;

    if (wasProcessing) {
      // In-flight crash: restarting silently would wipe the conversation
      // context without the user noticing — report and let the next user
      // action rebuild the subprocess via ensureSubprocess().
      this.eventQueue.enqueue({
        type: 'error',
        message: '子进程在会话处理中异常退出，本次对话上下文已丢失。重新发送消息将自动恢复。',
      });
      return;
    }

    // Idle crash: safe to auto-restart with backoff
    this.scheduleIdleRestart();
  }

  // G3: Idle-crash backoff restart (1s / 4s / 16s, then give up until
  // the next user action triggers ensureSubprocess())
  private scheduleIdleRestart(): void {
    if (this.restartPending) return; // exit+error handlers may both fire
    if (this.crashRestartCount >= ZenskillAgent.MAX_CRASH_RESTARTS) {
      this.eventQueue.enqueue({
        type: 'error',
        message: `ZenSkill 子进程连续崩溃 ${this.crashRestartCount} 次，已暂停自动重启。下次发送消息时将重试。`,
      });
      return;
    }
    const delay = ZenskillAgent.RESTART_BACKOFF_MS[this.crashRestartCount] ?? 16000;
    this.crashRestartCount++;
    this.restartPending = true;
    console.error(
      `[zenskill-agent] Idle crash — auto-restart ${this.crashRestartCount}/${ZenskillAgent.MAX_CRASH_RESTARTS} in ${delay}ms`,
    );
    setTimeout(async () => {
      this.restartPending = false;
      if (this.destroyed) return;
      try {
        await this.spawnSubprocess();
        this.crashRestartCount = 0;
        console.error('[zenskill-agent] Auto-restart OK');
      } catch (err) {
        console.error(`[zenskill-agent] Auto-restart failed: ${err instanceof Error ? err.message : err}`);
        this.scheduleIdleRestart();
      }
    }, delay);
  }

  // ============================================================
  // C1: Engine session resume —— 模型上下文跨子进程存活
  // ============================================================

  /**
   * spawn 后、首条 prompt 前，用已知引擎会话 id 执行 switch_session，让引擎
   * build_context 沿 entry 链全量重建历史（含 compaction 摘要）。
   * 目标 sid 优先取本轮子进程已捕获的 engineSessionId（崩溃重启场景，引擎
   * 文件未变可直接重挂），否则回落宿主 header 持久化的 sdkSessionId（应用
   * 重启 / agent 重建场景）。失败不阻断对话：引擎将懒创建空白会话，新 sid
   * 随 prompt 响应回传并落库自愈；显式 debug 留痕便于 --debug 取证。
   */
  private async resumeEngineSession(): Promise<void> {
    const targetSid = this.engineSessionId ?? this.config.session?.sdkSessionId;
    if (!targetSid) return;
    const id = `resume-${++this.rpcIdCounter}`;
    const switched = await new Promise<boolean>((resolve) => {
      const timeout = setTimeout(() => resolve(false), 15000);
      const handler = (line: string) => {
        try {
          const msg = JSON.parse(line);
          if (msg.type === 'response' && msg.command === 'switch_session' && msg.id === id) {
            clearTimeout(timeout);
            this.readline?.off('line', handler);
            resolve(!!msg.success);
          }
        } catch { /* ignore */ }
      };
      this.readline?.on('line', handler);
      this.send({ type: 'switch_session', id, sessionId: targetSid });
    });
    if (switched) {
      this.captureEngineSessionId(targetSid);
      this.debug(`engine session resumed: ${targetSid}`);
    } else {
      this.debug(
        `engine session resume FAILED for ${targetSid} — continuing with a fresh engine context ` +
        '(host session.jsonl stays UI-only for the model this turn)',
      );
      // C4: 失败显式化 —— 历史未能续接时用户必须知道本轮从空白上下文开始，
      // 禁止静默兜底（信息级事件，UI 以 info 行呈现，不与错误气泡混淆）
      this.eventQueue.enqueue({
        type: 'info',
        message: `历史会话未能续接（引擎会话 ${targetSid} 加载失败），本轮对话从空白上下文开始`,
      });
    }
  }

  /** 引擎回传的 sid → 经 onSdkSessionIdUpdate 通知宿主落库 header.sdkSessionId */
  private captureEngineSessionId(sid: string): void {
    this.engineSessionId = sid;
    if (this.reportedEngineSessionId === sid) return;
    this.reportedEngineSessionId = sid;
    if (sid === this.config.session?.sdkSessionId) return; // 与宿主持有值一致，无需回写
    try {
      this.config.onSdkSessionIdUpdate?.(sid);
    } catch { /* 落库失败不能阻断对话 */ }
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
    this.destroyed = true; // G3: stop any pending auto-restart
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

      case 'response': {
        // prompt / switch_session / ensure_session_ready 的响应都在 data 里回传
        // 引擎侧 sessionId —— 捕获并落库，供下次 spawn 时 switch_session 续接。
        const sid = msg.data?.sessionId;
        if (typeof sid === 'string' && sid) this.captureEngineSessionId(sid);
        break;
      }

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
        'growth_milestone', 'web_search', 'web_fetch',
        // G8: companion/daily review read-only tools (WP-A/B additions)
        'companion_summary', 'daily_review', 'incubating_list', 'skill_browse',
        'growth_dashboard', 'habit_analyze'];
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
      parts.push(`Model: ${this._model || 'provider default (resolved by zenskill engine)'}`);
      parts.push('');
      parts.push(guideContent);

      // Fresh context injection — fetch live GTD/memory data via MCP pool
      try {
        const mcpPool = (this.config as any).mcpPool;
        if (mcpPool?.callTool) {
          // Find the zenskill source slug from pool proxy tools
          const proxyDefs = mcpPool.getProxyToolDefs?.() || [];
          const zsProxy = proxyDefs.find((d: any) => d.name.startsWith('mcp__') && d.name.includes('__gtd_inbox_list'));
          if (zsProxy) {
            const sourceSlug = zsProxy.name.split('__')[1];

            // GTD inbox (fresh)
            const gtdResult = await mcpPool.callTool(`mcp__${sourceSlug}__gtd_inbox_list`, { limit: 8 });
            const gtdText = typeof gtdResult === 'string' ? gtdResult : JSON.stringify(gtdResult);
            const gtdParsed = safeParseJson(gtdText);
            const gtdItems = gtdParsed?.items || [];
            if (gtdItems.length > 0) {
              parts.push('');
              parts.push('## Fresh GTD Inbox (top items)');
              for (const item of gtdItems.slice(0, 5)) {
                parts.push(`- ${item.raw_text || item.text || ''}`);
              }
            }

            // Memory (fresh)
            const memResult = await mcpPool.callTool(`mcp__${sourceSlug}__memory_list`, { n: 5 });
            const memText = typeof memResult === 'string' ? memResult : JSON.stringify(memResult);
            const memParsed = safeParseJson(memText);
            const memItems = memParsed?.items || [];
            if (memItems.length > 0) {
              parts.push('');
              parts.push('## Fresh Memory (recent)');
              for (const item of memItems.slice(0, 3)) {
                parts.push(`- ${item.content || ''}`);
              }
            }

            // Growth data (fresh)
            const growthResult = await mcpPool.callTool(`mcp__${sourceSlug}__growth_milestone`, {});
            const growthText = typeof growthResult === 'string' ? growthResult : JSON.stringify(growthResult);
            const growthParsed = safeParseJson(growthText);
            if (growthParsed) {
              parts.push('');
              parts.push('## Fresh Growth Status');
              parts.push(`- Milestones: ${JSON.stringify(growthParsed).slice(0, 200)}`);
            }

            // Growth feedback instruction
            parts.push('');
            parts.push('## Growth Feedback Rule');
            parts.push('After completing a user task, ALWAYS call `growth_report` (or `growth_milestone` for level-up detection) via the mcp__zenskill__ tools, and report skill growth to the user in this format:');
            parts.push('📈 [skill] 成长：[old_level] → [new_level]（已使用 N 次，成功率 X%）');
          }
        }
      } catch {
        // Fresh context injection is best-effort
      }

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

      // C5: prompt 组装留痕 —— engineSid 为空说明引擎会话尚未建立/未续接；
      // 引擎侧对应日志为 `prompt assemble: sid=… replayed=…`（--debug）
      this.debug(`prompt assemble: engineSid=${this.engineSessionId ?? '∅'}`);

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
    // Errors are propagated (reject) instead of swallowed as null so callers
    // can surface the real failure — e.g. testBackendConnection shows the
    // provider error instead of a generic "no response" hint. Callers that
    // treat failure as "no result" (title generation, summarization) already
    // wrap this in try/catch.
    await this.ensureSubprocess();
    const id = `mc-${++this.rpcIdCounter}`;
    return await new Promise<string | null>((resolve, reject) => {
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
              const error = typeof msg.error === 'string' && msg.error.trim()
                ? msg.error.trim()
                : 'mini_completion failed (no error detail from engine)';
              reject(new Error(error));
            }
          }
        } catch { /* ignore */ }
      };
      this.readline?.on('line', handler);
      this.send({ type: 'mini_completion', id, prompt });
    });
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
