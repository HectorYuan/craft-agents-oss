import { RPC_CHANNELS } from '@craft-agent/shared/protocol'
import { getWorkspaceByNameOrId } from '@craft-agent/shared/config'
import { loadWorkspaceSources } from '@craft-agent/shared/sources'
import { safeJsonParse } from '@craft-agent/shared/utils/files'
import { getCredentialManager } from '@craft-agent/shared/credentials'
import type { RpcServer } from '@craft-agent/server-core/transport'
import type { HandlerDeps } from '../handler-deps'

export const HANDLED_CHANNELS = [
  RPC_CHANNELS.sources.GET,
  RPC_CHANNELS.sources.CREATE,
  RPC_CHANNELS.sources.DELETE,
  RPC_CHANNELS.sources.START_OAUTH,
  RPC_CHANNELS.sources.SAVE_CREDENTIALS,
  RPC_CHANNELS.sources.GET_PERMISSIONS,
  RPC_CHANNELS.workspace.GET_PERMISSIONS,
  RPC_CHANNELS.permissions.GET_DEFAULTS,
  RPC_CHANNELS.sources.GET_MCP_TOOLS,
] as const

export function registerSourcesHandlers(server: RpcServer, deps: HandlerDeps): void {
  const log = deps.platform.logger

  // Get all sources for a workspace
  server.handle(RPC_CHANNELS.sources.GET, async (_ctx, workspaceId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) {
      log.error(`SOURCES_GET: Workspace not found: ${workspaceId}`)
      return []
    }
    return loadWorkspaceSources(workspace.rootPath)
  })

  // Create a new source
  server.handle(RPC_CHANNELS.sources.CREATE, async (_ctx, workspaceId: string, config: Partial<import('@craft-agent/shared/sources').CreateSourceInput>) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { createSource } = await import('@craft-agent/shared/sources')
    return createSource(workspace.rootPath, {
      name: config.name || 'New Source',
      provider: config.provider || 'custom',
      type: config.type || 'mcp',
      enabled: config.enabled ?? true,
      mcp: config.mcp,
      api: config.api,
      local: config.local,
    })
  })

  // Delete a source
  server.handle(RPC_CHANNELS.sources.DELETE, async (_ctx, workspaceId: string, sourceSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { deleteSource } = await import('@craft-agent/shared/sources')
    deleteSource(workspace.rootPath, sourceSlug)

    // Clean up stale slug from workspace default sources
    const { loadWorkspaceConfig, saveWorkspaceConfig } = await import('@craft-agent/shared/workspaces')
    const config = loadWorkspaceConfig(workspace.rootPath)
    if (config?.defaults?.enabledSourceSlugs?.includes(sourceSlug)) {
      config.defaults.enabledSourceSlugs = config.defaults.enabledSourceSlugs.filter(s => s !== sourceSlug)
      saveWorkspaceConfig(workspace.rootPath, config)
    }
  })

  // Start OAuth flow for a source (DEPRECATED — use oauth:start + performOAuth client-side)
  // Kept for backward compatibility with old IPC preload; WS clients use performOAuth().
  server.handle(RPC_CHANNELS.sources.START_OAUTH, async () => {
    return {
      success: false,
      error: 'Deprecated: use the client-side performOAuth() flow (oauth:start + oauth:complete) instead',
    }
  })

  // Save credentials for a source (bearer token or API key)
  server.handle(RPC_CHANNELS.sources.SAVE_CREDENTIALS, async (_ctx, workspaceId: string, sourceSlug: string, credential: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { loadSource, getSourceCredentialManager } = await import('@craft-agent/shared/sources')

    const source = loadSource(workspace.rootPath, sourceSlug)
    if (!source) {
      throw new Error(`Source not found: ${sourceSlug}`)
    }

    // SourceCredentialManager handles credential type resolution
    const credManager = getSourceCredentialManager()
    await credManager.save(source, { value: credential })

    log.info(`Saved credentials for source: ${sourceSlug}`)
  })

  // Get permissions config for a source (raw format for UI display)
  server.handle(RPC_CHANNELS.sources.GET_PERMISSIONS, async (_ctx, workspaceId: string, sourceSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return null

    const { existsSync, readFileSync } = await import('fs')
    const { getSourcePermissionsPath } = await import('@craft-agent/shared/agent')
    const path = getSourcePermissionsPath(workspace.rootPath, sourceSlug)

    if (!existsSync(path)) return null

    try {
      const content = readFileSync(path, 'utf-8')
      return safeJsonParse(content)
    } catch (error) {
      log.error('Error reading permissions config:', error)
      return null
    }
  })

  // Get permissions config for a workspace (raw format for UI display)
  server.handle(RPC_CHANNELS.workspace.GET_PERMISSIONS, async (_ctx, workspaceId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return null

    const { existsSync, readFileSync } = await import('fs')
    const { getWorkspacePermissionsPath } = await import('@craft-agent/shared/agent')
    const path = getWorkspacePermissionsPath(workspace.rootPath)

    if (!existsSync(path)) return null

    try {
      const content = readFileSync(path, 'utf-8')
      return safeJsonParse(content)
    } catch (error) {
      log.error('Error reading workspace permissions config:', error)
      return null
    }
  })

  // Get default permissions from ~/.craft-agent/permissions/default.json
  server.handle(RPC_CHANNELS.permissions.GET_DEFAULTS, async () => {
    const { existsSync, readFileSync } = await import('fs')
    const { getAppPermissionsDir } = await import('@craft-agent/shared/agent')
    const { join } = await import('path')

    const defaultPath = join(getAppPermissionsDir(), 'default.json')
    if (!existsSync(defaultPath)) return { config: null, path: defaultPath }

    try {
      const content = readFileSync(defaultPath, 'utf-8')
      return { config: safeJsonParse(content), path: defaultPath }
    } catch (error) {
      log.error('Error reading default permissions config:', error)
      return { config: null, path: defaultPath }
    }
  })

  // Get MCP tools for a source with permission status
  server.handle(RPC_CHANNELS.sources.GET_MCP_TOOLS, async (_ctx, workspaceId: string, sourceSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return { success: false, error: 'Workspace not found' }

    try {
      const sources = await loadWorkspaceSources(workspace.rootPath)
      const source = sources.find(s => s.config.slug === sourceSlug)
      if (!source) return { success: false, error: 'Source not found' }
      if (source.config.type !== 'mcp') return { success: false, error: 'Source is not an MCP server' }
      if (!source.config.mcp) return { success: false, error: 'MCP config not found' }

      if (source.config.connectionStatus === 'needs_auth') {
        return { success: false, error: 'Source requires authentication' }
      }
      if (source.config.connectionStatus === 'failed') {
        return { success: false, error: source.config.connectionError || 'Connection failed' }
      }
      if (source.config.connectionStatus === 'untested') {
        return { success: false, error: 'Source has not been tested yet' }
      }

      const { CraftMcpClient } = await import('@craft-agent/shared/mcp')
      let client: InstanceType<typeof CraftMcpClient>

      if (source.config.mcp.transport === 'stdio') {
        if (!source.config.mcp.command) {
          return { success: false, error: 'Stdio MCP source is missing required "command" field' }
        }
        log.info(`Fetching MCP tools via stdio: ${source.config.mcp.command}`)
        client = new CraftMcpClient({
          transport: 'stdio',
          command: source.config.mcp.command,
          args: source.config.mcp.args,
          env: source.config.mcp.env,
        })
      } else {
        if (!source.config.mcp.url) {
          return { success: false, error: 'MCP source URL is required for HTTP/SSE transport' }
        }

        let accessToken: string | undefined
        if (source.config.mcp.authType === 'oauth' || source.config.mcp.authType === 'bearer') {
          const credentialManager = getCredentialManager()
          const credentialId = source.config.mcp.authType === 'oauth'
            ? { type: 'source_oauth' as const, workspaceId: source.workspaceId, sourceId: sourceSlug }
            : { type: 'source_bearer' as const, workspaceId: source.workspaceId, sourceId: sourceSlug }
          const credential = await credentialManager.get(credentialId)
          accessToken = credential?.value
        }

        log.info(`Fetching MCP tools from ${source.config.mcp.url}`)
        client = new CraftMcpClient({
          transport: 'http',
          url: source.config.mcp.url,
          headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
        })
      }

      const tools = await client.listTools()
      await client.close()

      const { loadSourcePermissionsConfig, permissionsConfigCache } = await import('@craft-agent/shared/agent')
      const permissionsConfig = loadSourcePermissionsConfig(workspace.rootPath, sourceSlug)

      const mergedConfig = permissionsConfigCache.getMergedConfig({
        workspaceRootPath: workspace.rootPath,
        activeSourceSlugs: [sourceSlug],
      })

      const toolsWithPermission = tools.map(tool => {
        const allowed = mergedConfig.readOnlyMcpPatterns.some((pattern: RegExp) => pattern.test(tool.name))
        return {
          name: tool.name,
          description: tool.description,
          allowed,
        }
      })

      return { success: true, tools: toolsWithPermission }
    } catch (error) {
      log.error('Failed to get MCP tools:', error)
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch tools'
      if (errorMessage.includes('404')) {
        return { success: false, error: 'MCP server endpoint not found. The server may be offline or the URL may be incorrect.' }
      }
      if (errorMessage.includes('401') || errorMessage.includes('403')) {
        return { success: false, error: 'Authentication failed. Please re-authenticate with this source.' }
      }
      return { success: false, error: errorMessage }
    }
  })

  // ── callMcpTool: invoke a specific MCP tool by name ──
  // Connection cache: reuse CraftMcpClient across calls (keyed by source slug)
  const mcpClientCache = new Map<string, { client: any; lastUsed: number }>()
  // In-flight client creation per slug: concurrent callers on a cold cache
  // share one spawn instead of racing N subprocesses (which all fail).
  const mcpClientPending = new Map<string, Promise<any>>()
  const MCP_CACHE_TTL_MS = 5 * 60 * 1000 // 5 min idle timeout

  async function getMcpClient(sourceSlug: string, source: any) {
    const cached = mcpClientCache.get(sourceSlug)
    if (cached && Date.now() - cached.lastUsed < MCP_CACHE_TTL_MS) {
      cached.lastUsed = Date.now()
      return cached.client
    }

    const inFlight = mcpClientPending.get(sourceSlug)
    if (inFlight) return inFlight

    const creation = createMcpClient(sourceSlug, source)
    mcpClientPending.set(sourceSlug, creation)
    try {
      return await creation
    } finally {
      mcpClientPending.delete(sourceSlug)
    }
  }

  async function createMcpClient(sourceSlug: string, source: any) {
    // Close stale cached client if any
    const cached = mcpClientCache.get(sourceSlug)
    if (cached) {
      try { await cached.client.close() } catch { /* ignore */ }
      mcpClientCache.delete(sourceSlug)
    }

    const { CraftMcpClient } = await import('@craft-agent/shared/mcp')
    let client: InstanceType<typeof CraftMcpClient>

    if (source.config.mcp.transport === 'stdio') {
      if (!source.config.mcp.command) throw new Error('Missing command')
      client = new CraftMcpClient({
        transport: 'stdio',
        command: source.config.mcp.command,
        args: source.config.mcp.args,
        env: source.config.mcp.env,
      })
    } else {
      if (!source.config.mcp.url) throw new Error('Missing URL')
      let accessToken: string | undefined
      if (source.config.mcp.authType === 'oauth' || source.config.mcp.authType === 'bearer') {
        const credentialManager = getCredentialManager()
        const credentialId = source.config.mcp.authType === 'oauth'
          ? { type: 'source_oauth' as const, workspaceId: source.workspaceId, sourceId: sourceSlug }
          : { type: 'source_bearer' as const, workspaceId: source.workspaceId, sourceId: sourceSlug }
        const credential = await credentialManager.get(credentialId)
        accessToken = credential?.value
      }
      client = new CraftMcpClient({
        transport: 'http',
        url: source.config.mcp.url,
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
      })
    }

    mcpClientCache.set(sourceSlug, { client, lastUsed: Date.now() })
    return client
  }

  server.handle('callMcpTool', async (_ctx, workspaceId: string, sourceSlug: string, toolName: string, args: Record<string, unknown>) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return { success: false, error: 'Workspace not found' }

    try {
      const sources = await loadWorkspaceSources(workspace.rootPath)
      const source = sources.find(s => s.config.slug === sourceSlug)
      if (!source) return { success: false, error: 'Source not found' }
      if (source.config.type !== 'mcp' || !source.config.mcp) return { success: false, error: 'Not an MCP source' }
      if (source.config.connectionStatus === 'failed') return { success: false, error: 'Source connection failed' }

      const client = await getMcpClient(sourceSlug, source)
      let result
      try {
        result = await client.callTool(toolName, args)
      } catch (callErr) {
        const msg = callErr instanceof Error ? callErr.message : String(callErr)
        // Stale connection (subprocess died mid-session): rebuild once, retry.
        // bebe4fc only covers cold-start concurrency; this covers mid-life drops.
        if (!/Connection closed|Not connected|transport/i.test(msg)) throw callErr
        log.warn(`MCP tool ${toolName} failed (${msg.slice(0, 80)}) — rebuilding connection`)
        await mcpClientCache.get(sourceSlug)?.client.close().catch?.(() => {})
        mcpClientCache.delete(sourceSlug)
        const fresh = await getMcpClient(sourceSlug, source)
        result = await fresh.callTool(toolName, args)
      }

      // Broadcast change event for write tools.
      // Prefixes cover whole GTD families; READ_TOOLS excludes read tools that
      // sit under those prefixes (gtd_inbox_list/gtd_review/... would otherwise
      // be misclassified as writes, spamming broadcasts and automation rules).
      const WRITE_TOOL_PREFIXES = ['gtd_', 'inbox_', 'action_', 'project_', 'incubating_']
      const WRITE_TOOLS_EXACT = ['memory_remember', 'goal_set', 'habit_check', 'skill_install', 'skill_uninstall']
      const READ_TOOLS = ['gtd_inbox_list', 'gtd_review', 'action_list', 'project_list', 'incubating_list']
      const isWriteTool = (n: string) =>
        !READ_TOOLS.includes(n) &&
        (WRITE_TOOLS_EXACT.includes(n) || WRITE_TOOL_PREFIXES.some((p) => n.startsWith(p)))
      if (isWriteTool(toolName)) {
        // Achievement unlocks ride in the event payload so automation rules
        // and webhooks can react (action_done/habit_check return them).
        const payload: Record<string, unknown> = { type: toolName, sourceSlug }
        try {
          const text = (result as any)?.result?.content?.[0]?.text
          if (typeof text === 'string') {
            const parsed = JSON.parse(text)
            if (Array.isArray(parsed?.new_achievements) && parsed.new_achievements.length > 0) {
              payload.newAchievements = parsed.new_achievements
            }
          }
        } catch { /* payload enrichment is best-effort */ }
        try {
          server.push('zenskill:changed', { to: 'workspace', workspaceId }, payload)
        } catch { /* broadcast is best-effort */ }
        // Feed the automation event bus so rules can react to ZenSkill data changes
        try {
          await deps.sessionManager.emitZenSkillChanged(workspaceId, payload)
        } catch { /* automation emit is best-effort */ }
      }

      return { success: true, result }
    } catch (error) {
      log.error(`Failed to call MCP tool ${toolName}:`, error)
      return { success: false, error: error instanceof Error ? error.message : 'Tool call failed' }
    }
  })
}
