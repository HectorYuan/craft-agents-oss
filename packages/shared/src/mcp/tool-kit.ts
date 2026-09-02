/**
 * tool-kit — in-process MCP server construction without @anthropic-ai/claude-agent-sdk.
 *
 * Replaces the SDK's `tool()` / `createSdkMcpServer()` thin wrappers with a
 * direct @modelcontextprotocol/sdk implementation:
 *
 *   defineTool({ name, description, inputSchema(zod raw shape), handler })
 *     → createInProcessMcpServer(name, version, tools)
 *       → { type: 'sdk', instance: McpServer }   // feeds mcpPool.sync
 *
 * The returned shape is structurally compatible with the SDK's
 * McpSdkServerConfigWithInstance: mcpPool.sync routes `config.instance`
 * into ApiSourcePoolClient over InMemoryTransport, so downstream
 * (pool → zenskill agent proxy → WebUI) is unchanged.
 */
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { z, type ZodRawShape } from 'zod'

/** Text-content result shape (MCP CallToolResult subset). */
export interface KitToolResult {
  content: Array<{ type: 'text'; text: string }>
  isError?: boolean
}

export interface KitTool<S extends ZodRawShape = ZodRawShape> {
  name: string
  description: string
  /** Zod raw shape (same input the SDK `tool()` wrapper accepted). */
  inputSchema: S
  /**
   * Business handler. May return a KitToolResult directly (already-shaped
   * content) or any serializable value (auto-wrapped as JSON text content).
   * args is typed `unknown` — narrow it inside the handler body.
   */
  handler: (args: unknown, extra: unknown) => Promise<KitToolResult | unknown>
  readOnly?: boolean
}

export function defineTool<S extends ZodRawShape>(t: KitTool<S>): KitTool<S> {
  return t
}

/** Shape returned to mcpPool consumers (ApiServerConfig-compatible). */
export interface InProcessMcpServerConfig {
  type: 'sdk'
  instance: McpServer
}

function normalizeResult(result: KitToolResult | unknown): KitToolResult {
  if (
    result &&
    typeof result === 'object' &&
    Array.isArray((result as KitToolResult).content)
  ) {
    const r = result as KitToolResult
    return {
      content: r.content.map(c => ({ type: 'text' as const, text: c.text })),
      ...(r.isError ? { isError: true } : {}),
    }
  }
  return {
    content: [{ type: 'text', text: JSON.stringify(result, null, 0) }],
  }
}

/**
 * Build an in-process MCP server from tool definitions.
 *
 * Uses @modelcontextprotocol/sdk's McpServer directly (its `.tool()` overload
 * natively accepts zod raw shapes — the same input the removed claude-agent-sdk
 * `tool()` wrapper took), so no SDK types or wrappers are involved.
 */
export function createInProcessMcpServer(
  name: string,
  version: string,
  tools: Array<KitTool>
): InProcessMcpServerConfig {
  const server = new McpServer({ name, version })
  for (const t of tools) {
    server.registerTool(
      t.name,
      {
        description: t.description,
        inputSchema: t.inputSchema,
        ...(t.readOnly ? { annotations: { readOnlyHint: true } } : {}),
      },
      (async (args: any, extra: unknown) =>
        normalizeResult(await t.handler(args, extra)) as any)
    )
  }
  return { type: 'sdk', instance: server }
}
