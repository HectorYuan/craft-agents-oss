/**
 * Live type definitions salvaged from the removed Claude SDK tool modules
 * (llm-tool.ts / spawn-session-tool.ts / browser-tools.ts) — P2 backend
 * removal. Types only: zero runtime imports, safe for any consumer.
 */

import type { SpawnSessionResult, SpawnSessionHelpResult } from './base-agent.ts';

// ── call_llm (queryFn callback) ──

export interface LLMQueryRequest {
  /** Full prompt including serialized file content */
  prompt: string;
  /** Optional system prompt */
  systemPrompt?: string;
  /** Model to use (validated against registry) */
  model?: string;
  /** Max output tokens */
  maxTokens?: number;
  /** Sampling temperature 0-1 */
  temperature?: number;
  /** Structured output JSON schema — backends handle natively when possible */
  outputSchema?: Record<string, unknown>;
}

/** Result from an agent-native queryFn callback. */
export interface LLMQueryResult {
  text: string;
  model?: string;
  inputTokens?: number;
  outputTokens?: number;
  /** Non-fatal warning attached to a partially-successful result (e.g. SDK stopped at max_turns). */
  warning?: string;
}

/** Unified timeout for secondary LLM calls (call_llm and mini-completion flows). */
export const LLM_QUERY_TIMEOUT_MS = 120000;

// ── spawn_session ──

export type SpawnSessionFn = (input: Record<string, unknown>) => Promise<SpawnSessionResult | SpawnSessionHelpResult>;

// ── browser panes ──

export interface BrowserScreenshotArgs {
  mode?: 'raw' | 'agent'
  refs?: string[]
  includeLastAction?: boolean
  includeMetadata?: boolean
  /** Annotate screenshot with @eN labels on all interactive elements */
  annotate?: boolean
  format?: 'png' | 'jpeg'
  jpegQuality?: number
}
export interface BrowserScreenshotResult {
  imageBuffer: Buffer
  imageFormat: 'png' | 'jpeg'
  metadata?: Record<string, unknown>
}
export interface BrowserConsoleArgs {
  level?: 'all' | 'log' | 'info' | 'warn' | 'error'
  limit?: number
}
export interface BrowserScreenshotRegionArgs {
  x?: number
  y?: number
  width?: number
  height?: number
  ref?: string
  selector?: string
  padding?: number
  format?: 'png' | 'jpeg'
  jpegQuality?: number
}
export interface BrowserWindowResizeArgs {
  width: number
  height: number
}
export interface BrowserNetworkArgs {
  limit?: number
  status?: 'all' | 'failed' | '2xx' | '3xx' | '4xx' | '5xx'
  method?: string
  resourceType?: string
}
export interface BrowserWaitArgs {
  kind: 'selector' | 'text' | 'url' | 'network-idle'
  value?: string
  timeoutMs?: number
  pollMs?: number
  idleMs?: number
}
export interface BrowserKeyArgs {
  key: string
  modifiers?: Array<'shift' | 'control' | 'alt' | 'meta'>
}
export interface BrowserDownloadsArgs {
  action?: 'list' | 'wait'
  limit?: number
  timeoutMs?: number
}
export interface BrowserLifecycleActionResult {
  action: 'closed' | 'hidden' | 'released' | 'noop'
  requestedInstanceId?: string
  resolvedInstanceId?: string
  affectedIds: string[]
  reason?: string
}


export interface BrowserPaneFns {
  openPanel: (options?: { background?: boolean }) => Promise<{ instanceId: string }>;
  navigate: (url: string) => Promise<{ url: string; title: string }>;
  snapshot: () => Promise<{ url: string; title: string; nodes: Array<{ ref: string; role: string; name: string; value?: string; description?: string; focused?: boolean; checked?: boolean; disabled?: boolean }> }>;
  click: (ref: string, options?: { waitFor?: 'none' | 'navigation' | 'network-idle'; timeoutMs?: number }) => Promise<void>;
  clickAt: (x: number, y: number) => Promise<void>;
  drag: (x1: number, y1: number, x2: number, y2: number) => Promise<void>;
  fill: (ref: string, value: string) => Promise<void>;
  type: (text: string) => Promise<void>;
  select: (ref: string, value: string) => Promise<void>;
  setClipboard: (text: string) => Promise<void>;
  getClipboard: () => Promise<string>;
  screenshot: (args?: BrowserScreenshotArgs) => Promise<BrowserScreenshotResult>;
  screenshotRegion: (args: BrowserScreenshotRegionArgs) => Promise<BrowserScreenshotResult>;
  getConsoleLogs: (args?: BrowserConsoleArgs) => Promise<Array<{ timestamp: number; level: 'log' | 'info' | 'warn' | 'error'; message: string }>>;
  windowResize: (args: BrowserWindowResizeArgs) => Promise<{ width: number; height: number }>;
  getNetworkLogs: (args?: BrowserNetworkArgs) => Promise<Array<{ timestamp: number; method: string; url: string; status: number; resourceType: string; ok: boolean }>>;
  waitFor: (args: BrowserWaitArgs) => Promise<{ ok: true; kind: string; elapsedMs: number; detail: string }>;
  sendKey: (args: BrowserKeyArgs) => Promise<void>;
  getDownloads: (args?: BrowserDownloadsArgs) => Promise<Array<{ id: string; timestamp: number; url: string; filename: string; state: string; bytesReceived: number; totalBytes: number; mimeType: string; savePath?: string }>>;
  upload: (ref: string, filePaths: string[]) => Promise<void>;
  scroll: (direction: 'up' | 'down' | 'left' | 'right', amount?: number) => Promise<void>;
  goBack: () => Promise<void>;
  goForward: () => Promise<void>;
  evaluate: (expression: string) => Promise<unknown>;
  focusWindow: (instanceId?: string) => Promise<{ instanceId: string; title: string; url: string }>;
  releaseControl: (instanceId?: string) => Promise<BrowserLifecycleActionResult>;
  closeWindow: (instanceId?: string) => Promise<BrowserLifecycleActionResult>;
  hideWindow: (instanceId?: string) => Promise<BrowserLifecycleActionResult>;
  listWindows: () => Promise<Array<{
    id: string;
    title: string;
    url: string;
    isVisible: boolean;
    ownerType: 'session' | 'manual';
    ownerSessionId: string | null;
    boundSessionId: string | null;
    agentControlActive?: boolean;
  }>>;
  detectChallenge: () => Promise<{ detected: boolean; provider: string; signals: string[] }>;
}
