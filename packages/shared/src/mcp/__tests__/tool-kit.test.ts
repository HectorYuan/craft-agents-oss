/**
 * tool-kit tests — in-process MCP server construction without claude-agent-sdk.
 * Mirrors the PoC: McpServer + InMemoryTransport + Client full-loop.
 */
import { describe, it, expect } from 'bun:test'
import { z } from 'zod'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js'
import { defineTool, createInProcessMcpServer } from '../tool-kit.ts'

async function connect(config: { type: string; instance: any }) {
  const [clientT, serverT] = InMemoryTransport.createLinkedPair()
  await config.instance.connect(serverT)
  const client = new Client({ name: 'test', version: '1.0.0' })
  await client.connect(clientT)
  return client
}

describe('createInProcessMcpServer', () => {
  // 每测试独立构造：McpServer 实例有连接状态，不可跨测试复用
  const makeConfig = () => createInProcessMcpServer('api_test', '1.0.0', [
    defineTool({
      name: 'api_request',
      description: 'test tool',
      inputSchema: {
        path: z.string().describe('endpoint'),
        method: z.enum(['GET', 'POST']).describe('method'),
      },
      handler: async args => ({ ok: true, args }),
    }),
    defineTool({
      name: 'shaped_tool',
      description: 'returns KitToolResult directly',
      inputSchema: {},
      handler: async () => ({
        content: [{ type: 'text' as const, text: 'pre-shaped' }],
      }),
    }),
  ])

  it('returns sdk-type config with McpServer instance', () => {
    const config = makeConfig()
    expect(config.type).toBe('sdk')
    expect(config.instance).toBeDefined()
  })

  it('exposes tools over InMemoryTransport with zod-validated args', async () => {
    const client = await connect(makeConfig())
    const { tools } = await client.listTools()
    const names = tools.map(t => t.name).sort()
    expect(names).toEqual(['api_request', 'shaped_tool'])

    const r = await client.callTool({
      name: 'api_request',
      arguments: { path: '/x', method: 'GET' },
    })
    const parsed = JSON.parse((r.content as any)[0].text)
    expect(parsed.ok).toBe(true)
    expect(parsed.args).toEqual({ path: '/x', method: 'GET' })
  })

  it('auto-wraps plain object handler results as text content', async () => {
    const client = await connect(makeConfig())
    const r = await client.callTool({ name: 'shaped_tool', arguments: {} })
    expect((r.content as any)[0].text).toBe('pre-shaped')
  })

  it('rejects invalid arguments (zod validation reaches the client)', async () => {
    const client = await connect(makeConfig())
    const r = await client.callTool({
      name: 'api_request',
      arguments: { method: 'NOT_A_METHOD' },
    })
    expect(r.isError).toBe(true)
  })
})
