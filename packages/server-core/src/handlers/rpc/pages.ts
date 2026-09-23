import { RPC_CHANNELS } from '@craft-agent/shared/protocol'
import { getWorkspaceByNameOrId } from '@craft-agent/shared/config'
import { pushTyped, type RpcServer } from '@craft-agent/server-core/transport'
import type { HandlerDeps } from '../handler-deps'
import type { PageActionRequest } from '@craft-agent/shared/pages'
import type { PageActionBroker, PageActionExecutors } from '@craft-agent/shared/pages'
import type { CreatePageFromTemplateInput, PageTemplateInfo } from '@craft-agent/shared/pages'
import { atomicWriteFileSync, getBundledAssetsDir, readJsonFileSync, slugifyName } from '@craft-agent/shared/utils'
import { cpSync, existsSync, readFileSync, readdirSync } from 'node:fs'
import { basename, join } from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { assertPageSourceUsable } from '../../pages/source-gate'

export const HANDLED_CHANNELS = [
  RPC_CHANNELS.pages.GET,
  RPC_CHANNELS.pages.GET_ONE,
  RPC_CHANNELS.pages.CREATE,
  RPC_CHANNELS.pages.LIST_TEMPLATES,
  RPC_CHANNELS.pages.CREATE_FROM_TEMPLATE,
  RPC_CHANNELS.pages.UPDATE,
  RPC_CHANNELS.pages.DELETE,
  RPC_CHANNELS.pages.GET_CONTENT,
  RPC_CHANNELS.pages.SET_CONTENT,
  RPC_CHANNELS.pages.GET_DATA,
  RPC_CHANNELS.pages.LIST_GRANTS,
  RPC_CHANNELS.pages.ISSUE_GRANT,
  RPC_CHANNELS.pages.REVOKE_GRANT,
  RPC_CHANNELS.pages.CREATE_LEASE,
  RPC_CHANNELS.pages.RELEASE_LEASE,
  RPC_CHANNELS.pages.EXECUTE_ACTION,
  RPC_CHANNELS.pages.CANCEL_ACTION,
  RPC_CHANNELS.pages.GET_SHARE_CAPABILITIES,
  RPC_CHANNELS.pages.GET_SHARE_DATA_SCAN,
  RPC_CHANNELS.pages.PUBLISH,
  RPC_CHANNELS.pages.SET_PUBLICATION_PASSWORD,
  RPC_CHANNELS.pages.UNPUBLISH,
  RPC_CHANNELS.pages.GET_THUMBNAIL,
  RPC_CHANNELS.pages.REGENERATE_THUMBNAIL,
] as const

/** Cap on action response bodies returned to the renderer */
const ACTION_BODY_MAX_CHARS = 512 * 1024

// ------------------------------------------------------------------
// Template pool (zenskill/resources/pages) — the python package's
// resources dir, same target as the CLI's core.update_pages._pages_resource_dir:
// the CLI resolves it via importlib.resources("zenskill")/… or
// Path(update_pages.py).parent.parent/… — both are <python package root>/resources/pages.
// ------------------------------------------------------------------

/**
 * Locate the template pool on disk. Multi-candidate probe + explicit failure:
 *
 * 1. Packaged app: <resourcesPath>/app/resources/zenskill/zenskill/resources/pages —
 *    electron-builder embed, resolved like zenskill-seed's packagedAppResource.
 *    Only exists when running an installed build (dev's resourcesPath has no
 *    app/resources/zenskill), so packaged vs dev disambiguates naturally.
 * 2-3. Source checkout derived from cwd (server started inside the monorepo,
 *    cwd = vendor/craft-agents or vendor/craft-agents/apps/electron).
 * 4. Source checkout absolute path (this dev machine's checkout — carries the
 *    current `template: true` marks).
 * 5. Bundled assets copy (getBundledAssetsDir: <app>/resources/zenskill, dist
 *    copy, …) — build snapshot, LAST because a copied bundle can lag behind the
 *    source checkout (its page.json may predate the template demotion).
 *
 * Throws listing every tried candidate when none exists.
 */
function resolveTemplatePoolDir(): string {
  const poolSubpath = ['zenskill', 'resources', 'pages'] as const
  const candidates: string[] = []

  const resourcesPath = (process as unknown as { resourcesPath?: string }).resourcesPath
  if (resourcesPath) {
    // engineDir (pyproject root) is <resourcesPath>/app/resources/zenskill;
    // poolSubpath starts with the package-root dir nested inside it.
    candidates.push(join(resourcesPath, 'app', 'resources', 'zenskill', ...poolSubpath))
  }
  candidates.push(
    join(process.cwd(), '..', '..', ...poolSubpath),
    join(process.cwd(), '..', '..', '..', ...poolSubpath),
    join('/home/hector/DevSpace/ZenSkill', ...poolSubpath),
  )
  const bundled = getBundledAssetsDir('zenskill')
  if (bundled) candidates.push(join(bundled, ...poolSubpath))

  const hit = candidates.find(candidate => existsSync(candidate))
  if (hit) return hit
  throw new Error(`Page template pool not found. Tried: ${candidates.join(', ')}`)
}

/** Defensive page.json read (CLI _load_page_json: missing/corrupt → null). */
function loadTemplateConfig(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) return null
  try {
    const data = readJsonFileSync<unknown>(path)
    if (data && typeof data === 'object' && !Array.isArray(data)) {
      return data as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

/** Existing page directory names (slug-dedupe set; CLI _existing_slugs). */
function existingPageSlugs(workspaceRootPath: string): Set<string> {
  const pagesDir = join(workspaceRootPath, 'pages')
  if (!existsSync(pagesDir)) return new Set()
  return new Set(
    readdirSync(pagesDir, { withFileTypes: true })
      .filter(entry => entry.isDirectory())
      .map(entry => entry.name),
  )
}

export function registerPagesHandlers(server: RpcServer, deps: HandlerDeps): void {
  const log = deps.platform.logger

  // One broker per workspace: render leases and in-flight actions are
  // in-memory state scoped to the hosting process.
  const brokers = new Map<string, PageActionBroker>()

  // One MCP client pool per workspace, shared by all of its pages and
  // independent of session pools. Clients live until the process exits
  // (same lifetime as the brokers above).
  const mcpPools = new Map<string, import('@craft-agent/shared/mcp').McpClientPool>()

  async function broadcastChanged(workspaceId: string, workspaceRootPath: string): Promise<void> {
    const { loadWorkspacePages } = await import('@craft-agent/shared/pages')
    const pages = loadWorkspacePages(workspaceRootPath)
    pushTyped(server, RPC_CHANNELS.pages.CHANGED, { to: 'workspace', workspaceId }, workspaceId, pages)
  }

  /**
   * API executor for the action bridge. Resolves the source + credential
   * lazily per call (same seams sessions use), so tokens refresh correctly
   * and never leave the host process.
   */
  function buildApiExecutor(workspaceRootPath: string): NonNullable<PageActionExecutors['executeApi']> {
    // One refresh manager per workspace executor so failed-refresh cooldowns
    // survive across calls instead of resetting on every action.
    let refreshManager: import('@craft-agent/shared/sources').TokenRefreshManager | undefined
    return async (invocation, { signal }) => {
      const {
        loadSource,
        getSourceCredentialManager,
        getSourceServerBuilder,
        isApiOAuthProvider,
        hasRenewEndpoint,
        TokenRefreshManager,
        createTokenGetter,
        executeApiRequest,
      } = await import('@craft-agent/shared/sources')

      const source = loadSource(workspaceRootPath, invocation.sourceSlug)
      if (!source || source.config.type !== 'api') {
        throw new Error(`API source not found: ${invocation.sourceSlug}`)
      }
      // Fail fast with the stable source-auth-required error instead of
      // letting the request die on a 401 or a refresh timeout downstream.
      assertPageSourceUsable(source)

      const credManager = getSourceCredentialManager()
      const apiConfig = getSourceServerBuilder().buildApiConfig(source)

      // Credential resolution mirrors SessionManager.buildServersFromSources:
      // refreshable sources get a TokenRefreshManager-backed getter, plain
      // API sources read the vault per request, 'none' uses no credential.
      let credentialSource: import('@craft-agent/shared/sources').ApiCredentialSource
      if (isApiOAuthProvider(source.config.provider) || source.config.api?.authType === 'oauth' || hasRenewEndpoint(source)) {
        refreshManager ??= new TokenRefreshManager(credManager, { log: (msg: string) => log.info(msg) })
        credentialSource = createTokenGetter(refreshManager, source)
      } else if (source.config.api?.authType === 'none' || !source.config.api?.authType) {
        credentialSource = ''
      } else {
        credentialSource = async () => credManager.getApiCredential(source)
      }

      let outcome: Awaited<ReturnType<typeof executeApiRequest>>
      try {
        outcome = await executeApiRequest(
          apiConfig,
          credentialSource,
          { path: invocation.path, method: invocation.method, params: invocation.params },
          { signal },
        )
      } catch (err) {
        // A failed token refresh inside the request marks the source
        // needs_auth — reload and surface the stable auth error so this
        // very call already tells the page (and matches the banner).
        const fresh = loadSource(workspaceRootPath, invocation.sourceSlug)
        if (fresh) assertPageSourceUsable(fresh)
        throw err
      }

      // Shape the body for the renderer: parse JSON when it is JSON, cap size.
      let text = outcome.buffer.toString('utf-8')
      const truncated = text.length > ACTION_BODY_MAX_CHARS
      if (truncated) {
        text = `${text.slice(0, ACTION_BODY_MAX_CHARS)}…[truncated]`
      }
      let body: unknown = text
      if (!truncated && outcome.contentType?.toLowerCase().includes('json')) {
        try { body = JSON.parse(text) } catch { /* leave as text */ }
      }
      return { status: outcome.status, ok: outcome.ok, body }
    }
  }

  async function getBroker(workspaceId: string, workspaceRootPath: string): Promise<PageActionBroker> {
    const existing = brokers.get(workspaceRootPath)
    if (existing) return existing

    const { PageActionBroker } = await import('@craft-agent/shared/pages')
    const { loadWorkspaceSources } = await import('@craft-agent/shared/sources')

    let activeSourceSlugs: string[] = []
    try {
      activeSourceSlugs = loadWorkspaceSources(workspaceRootPath).map((source) => source.config.slug)
    } catch {
      // Policy annotation degrades gracefully without per-source permissions
    }

    const { McpClientPool } = await import('@craft-agent/shared/mcp')
    const { createPagesMcpExecutor } = await import('../../pages/mcp-executor')
    const { createPagesScriptExecutor } = await import('../../pages/script-executor-bridge')
    let mcpPool = mcpPools.get(workspaceRootPath)
    if (!mcpPool) {
      mcpPool = new McpClientPool({
        debug: (msg) => log.debug(`[pages] ${msg}`),
        workspaceRootPath,
      })
      mcpPools.set(workspaceRootPath, mcpPool)
    }

    const broker = new PageActionBroker({
      executors: {
        executeApi: buildApiExecutor(workspaceRootPath),
        executeMcp: createPagesMcpExecutor({ workspaceRootPath, pool: mcpPool, log }),
        executeScript: createPagesScriptExecutor({ workspaceRootPath, log }),
      },
      permissionsContext: { workspaceRootPath, activeSourceSlugs },
    })
    brokers.set(workspaceRootPath, broker)
    log.info(`Created page action broker for workspace ${workspaceId}`)
    return broker
  }

  // List all pages for a workspace
  server.handle(RPC_CHANNELS.pages.GET, async (_ctx, workspaceId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) {
      log.error(`PAGES_GET: Workspace not found: ${workspaceId}`)
      return []
    }
    const { loadWorkspacePages } = await import('@craft-agent/shared/pages')
    return loadWorkspacePages(workspace.rootPath)
  })

  // Get one page (by slug or id)
  server.handle(RPC_CHANNELS.pages.GET_ONE, async (_ctx, workspaceId: string, pageIdOrSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return null
    const { loadPage, loadPageById } = await import('@craft-agent/shared/pages')
    return loadPage(workspace.rootPath, pageIdOrSlug)
      ?? loadPageById(workspace.rootPath, pageIdOrSlug)
  })

  // Create a new page
  server.handle(RPC_CHANNELS.pages.CREATE, async (_ctx, workspaceId: string, input: import('@craft-agent/shared/pages').CreatePageInput) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { createPage } = await import('@craft-agent/shared/pages')
    const page = createPage(workspace.rootPath, {
      name: input.name?.trim() || 'New Page',
      description: input.description,
      kind: input.kind,
      projectId: input.projectId,
      content: input.content,
      refresh: input.refresh,
    })
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${page.slug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    // A page created with inline content gets a poster; empty pages wait for content.
    if (input.content !== undefined) {
      deps.sessionManager.enqueuePageThumbnail(workspaceId, workspace.rootPath, page.slug)
    }
    log.info(`Created page: ${page.slug}`)
    return page
  })

  // List the on-disk template pool (page packages demoted to templates).
  // Reads each pool member's page.json; `template` is true by definition —
  // a copied bundle's page.json may predate the demotion and lack the flag.
  server.handle(RPC_CHANNELS.pages.LIST_TEMPLATES, async (): Promise<PageTemplateInfo[]> => {
    const poolDir = resolveTemplatePoolDir()
    const entries: PageTemplateInfo[] = []
    const children = readdirSync(poolDir, { withFileTypes: true })
      .filter(child => child.isDirectory())
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    for (const child of children) {
      const cfg = loadTemplateConfig(join(poolDir, child.name, 'page.json'))
      if (!cfg) continue
      entries.push({
        slug: child.name,
        name: typeof cfg.name === 'string' && cfg.name ? cfg.name : child.name,
        description: typeof cfg.description === 'string' ? cfg.description : '',
        template: true,
      })
    }
    return entries
  })

  // Instantiate a template into {workspace}/pages/<new slug>/ — parity with the
  // python CLI `zenskill pages create --from-template` (zenskill/cli/pages.py):
  // whole-dir copy (minus bytecode/cache), new id/slug/name, template flag
  // dropped, refresh.script prefix rewritten to the instance dir (else cron
  // would run the TEMPLATE's script), page.json written last as the
  // completion marker. Slug collisions resolve via the existing dedupe
  // suffixes (-2, -3, …) — never an error; a missing/invalid template is.
  server.handle(RPC_CHANNELS.pages.CREATE_FROM_TEMPLATE, async (
    _ctx,
    input: CreatePageFromTemplateInput,
  ) => {
    const workspaceId = input?.workspaceId ?? ''
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)

    const templateSlug = String(input?.templateSlug ?? '')
    if (!templateSlug || /[/\\]/.test(templateSlug) || templateSlug === '.' || templateSlug === '..') {
      throw new Error(`Invalid template slug: ${templateSlug}`)
    }
    const poolDir = resolveTemplatePoolDir()
    const templateCfg = loadTemplateConfig(join(poolDir, templateSlug, 'page.json'))
    if (!templateCfg) {
      throw new Error(`Template not found or page.json invalid: ${templateSlug}`)
    }

    const { generatePageSlug, loadPageConfig } = await import('@craft-agent/shared/pages')
    const templateName = String(templateCfg.name || templateSlug)
    const givenName = String(input?.name ?? '').trim()

    let newName: string
    let newSlug: string
    if (givenName) {
      newName = givenName
      newSlug = generatePageSlug(workspace.rootPath, givenName)
    } else {
      // No name given: template name + sequence, the sequence doubles as the
      // slug dedupe so name and slug stay aligned (CLI behavior; slug falls
      // back to the bare sequence when the name slugsify to nothing).
      const existing = existingPageSlugs(workspace.rootPath)
      let seq = 1
      for (;;) {
        const candidateName = `${templateName} ${seq}`
        const candidateSlug = slugifyName(candidateName, String(seq))
        if (!existing.has(candidateSlug)) {
          newName = candidateName
          newSlug = candidateSlug
          break
        }
        seq++
      }
    }

    const targetDir = join(workspace.rootPath, 'pages', newSlug)
    if (existsSync(targetDir)) throw new Error(`Target page already exists: ${targetDir}`)

    // Whole-dir copy preserving index.html/scripts structure. Excludes match
    // the CLI: bytecode/cache dirs, and the template page.json — the instance
    // config is written last (completion marker), so a mid-copy failure never
    // leaves a half-written one.
    cpSync(join(poolDir, templateSlug), targetDir, {
      recursive: true,
      filter: src => {
        const name = basename(src)
        if (name === 'page.json' || name === '__pycache__') return false
        return !src.endsWith('.pyc') && !src.endsWith('.pyo')
      },
    })

    // Instance config (CLI _build_instance_config): fresh id/slug/name, drop
    // template, bump updatedAt, rewrite refresh.script's pages/<template slug>/
    // prefix to pages/<new slug>/, and re-digest the copied index.html.
    const cfg: Record<string, unknown> = { ...templateCfg }
    const oldSlug = String(cfg.slug || templateSlug)
    cfg.id = `page_${randomUUID().slice(0, 8)}`
    cfg.slug = newSlug
    cfg.name = newName
    delete cfg.template
    cfg.updatedAt = Date.now()

    const refresh = cfg.refresh
    if (refresh && typeof refresh === 'object') {
      const refreshRecord = refresh as Record<string, unknown>
      const oldPrefix = `pages/${oldSlug}/`
      if (typeof refreshRecord.script === 'string' && refreshRecord.script.startsWith(oldPrefix)) {
        refreshRecord.script = `pages/${newSlug}/` + refreshRecord.script.slice(oldPrefix.length)
      }
    }

    const indexHtmlPath = join(targetDir, 'index.html')
    if (existsSync(indexHtmlPath)) {
      // sha256 of the copied bytes (CLI: hashlib.sha256(read_bytes()))
      cfg.contentDigest = createHash('sha256').update(readFileSync(indexHtmlPath)).digest('hex')
    }

    // page.json last — the config watcher treats it as the completion marker.
    atomicWriteFileSync(join(targetDir, 'page.json'), JSON.stringify(cfg, null, 2) + '\n')

    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${newSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    const page = loadPageConfig(workspace.rootPath, newSlug)
    if (!page) throw new Error(`Created page config could not be re-read: ${newSlug}`)
    log.info(`Created page ${newSlug} from template ${templateSlug}`)
    return page
  })

  // Update page metadata/refresh spec (managed fields excluded). Slug stays stable.
  server.handle(RPC_CHANNELS.pages.UPDATE, async (
    _ctx,
    workspaceId: string,
    pageSlug: string,
    patch: import('@craft-agent/shared/pages').UpdatePagePatch,
  ) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { updatePage } = await import('@craft-agent/shared/pages')
    const updated = updatePage(workspace.rootPath, pageSlug, patch)
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    return updated
  })

  // Delete a page (content, data, and grants go with the folder). A published
  // page is unpublished first (best effort) so the public copy does not
  // silently outlive the local page — deletePageWithUnpublish is shared
  // verbatim with the delete_page session tool.
  server.handle(RPC_CHANNELS.pages.DELETE, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { deletePageWithUnpublish } = await import('@craft-agent/shared/pages')
    const { publicCopyMayRemain } = await deletePageWithUnpublish(workspace.rootPath, workspace.id, pageSlug, {
      log: (message: string) => log.warn(message),
    })
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    log.info(`Deleted page ${pageSlug}`)
    return { publicCopyMayRemain }
  })

  // Read page content (for editing/inspection — rendering should use CREATE_LEASE)
  server.handle(RPC_CHANNELS.pages.GET_CONTENT, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return { content: null }
    const { loadPageContent, loadPageConfig } = await import('@craft-agent/shared/pages')
    return {
      content: loadPageContent(workspace.rootPath, pageSlug),
      contentDigest: loadPageConfig(workspace.rootPath, pageSlug)?.contentDigest,
    }
  })

  // Write page content (updates contentDigest; existing grants go stale by design)
  server.handle(RPC_CHANNELS.pages.SET_CONTENT, async (_ctx, workspaceId: string, pageSlug: string, content: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { savePageContent } = await import('@craft-agent/shared/pages')
    const updated = savePageContent(workspace.rootPath, pageSlug, content)
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    deps.sessionManager.enqueuePageThumbnail(workspaceId, workspace.rootPath, pageSlug)
    return updated
  })

  // Read the page's data snapshot (cross-process contract written by refresh scripts)
  server.handle(RPC_CHANNELS.pages.GET_DATA, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return null
    const { readPageDataSnapshot } = await import('@craft-agent/shared/pages')
    return readPageDataSnapshot(workspace.rootPath, pageSlug)
  })

  // List persisted grants (validity — digest/expiry — is enforced at execution time)
  server.handle(RPC_CHANNELS.pages.LIST_GRANTS, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return []
    const { loadPageConfig } = await import('@craft-agent/shared/pages')
    return loadPageConfig(workspace.rootPath, pageSlug)?.grants ?? []
  })

  // Persist a user-approved grant (approval UX happens in the caller)
  server.handle(RPC_CHANNELS.pages.ISSUE_GRANT, async (
    _ctx,
    workspaceId: string,
    pageSlug: string,
    input: import('@craft-agent/shared/pages').AddPageGrantInput,
  ) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { addPageGrant } = await import('@craft-agent/shared/pages')
    const grant = addPageGrant(workspace.rootPath, pageSlug, input)
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    const target = grant.action.kind === 'script' ? grant.action.script : grant.action.sourceSlug
    log.info(`Issued page grant ${grant.id} on ${pageSlug} (${grant.action.kind}:${target})`)
    return grant
  })

  // Revoke a grant
  server.handle(RPC_CHANNELS.pages.REVOKE_GRANT, async (_ctx, workspaceId: string, pageSlug: string, grantId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { revokePageGrant } = await import('@craft-agent/shared/pages')
    const removed = revokePageGrant(workspace.rootPath, pageSlug, grantId)
    if (removed) {
      deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
      await broadcastChanged(workspaceId, workspace.rootPath)
      log.info(`Revoked page grant ${grantId} on ${pageSlug}`)
    }
    return removed
  })

  // Issue a render lease. Returns the lease AND the exact content it is bound
  // to — the renderer must render THIS content string (not a separately
  // fetched copy), closing the read/lease race.
  server.handle(RPC_CHANNELS.pages.CREATE_LEASE, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { loadPageContent, computePageContentDigest } = await import('@craft-agent/shared/pages')

    const content = loadPageContent(workspace.rootPath, pageSlug)
    if (content === null) throw new Error(`Page has no content: ${pageSlug}`)

    const broker = await getBroker(workspaceId, workspace.rootPath)
    const lease = broker.createLease({ pageSlug, contentDigest: computePageContentDigest(content) })
    return { lease, content }
  })

  // Release a render lease (page unmounted)
  server.handle(RPC_CHANNELS.pages.RELEASE_LEASE, async (_ctx, workspaceId: string, leaseId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return
    const broker = await getBroker(workspaceId, workspace.rootPath)
    broker.releaseLease(leaseId)
  })

  // Execute a granted source action. Page config is re-read from disk per
  // request so revocations and content changes apply immediately.
  server.handle(RPC_CHANNELS.pages.EXECUTE_ACTION, async (_ctx, workspaceId: string, request: PageActionRequest) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { loadPageConfig } = await import('@craft-agent/shared/pages')

    const page = loadPageConfig(workspace.rootPath, request.pageSlug)
    if (!page) throw new Error(`Page not found: ${request.pageSlug}`)

    const broker = await getBroker(workspaceId, workspace.rootPath)
    return broker.executeAction(page, request)
  })

  // Cancel an in-flight action
  server.handle(RPC_CHANNELS.pages.CANCEL_ACTION, async (_ctx, workspaceId: string, requestId: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return false
    const broker = await getBroker(workspaceId, workspace.rootPath)
    return broker.cancelAction(requestId)
  })

  // ------------------------------------------------------------------
  // Sharing (Cloudflare publication) — server-evaluated feature flag.
  // Publish/password are gated; unpublish never is, so disabling the flag
  // cannot strand a published page.
  // ------------------------------------------------------------------

  async function buildPublisher() {
    const { PagePublisher, createCredentialPagePublishTokenStore } = await import('@craft-agent/shared/pages')
    return new PagePublisher({
      tokenStore: createCredentialPagePublishTokenStore(),
      log: (msg: string) => log.info(msg),
    })
  }

  // Whether the renderer may offer publish/update UI (unpublish is always allowed)
  server.handle(RPC_CHANNELS.pages.GET_SHARE_CAPABILITIES, async () => {
    const { isPagesSharingEnabled } = await import('@craft-agent/shared/feature-flags')
    return { sharingEnabled: isPagesSharingEnabled() }
  })

  // What would `includeData` publish, and does any of it look like a secret?
  // Best-effort warning input for the Share dialog — never blocks publishing.
  server.handle(RPC_CHANNELS.pages.GET_SHARE_DATA_SCAN, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const { scanPageShareData } = await import('@craft-agent/shared/pages')
    return scanPageShareData(workspace.rootPath, pageSlug)
  })

  // Publish (create) or republish (upload a new revision) a page
  server.handle(RPC_CHANNELS.pages.PUBLISH, async (
    _ctx,
    workspaceId: string,
    pageSlug: string,
    options: { includeData: boolean; password?: string; viewOnlyAcknowledged?: boolean },
  ) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const publisher = await buildPublisher()
    const updated = await publisher.publish(workspace.rootPath, workspace.id, pageSlug, {
      includeData: options.includeData === true,
      password: options.password,
      viewOnlyAcknowledged: options.viewOnlyAcknowledged,
    })
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    return updated
  })

  // Set or clear the viewer password on an existing publication
  server.handle(RPC_CHANNELS.pages.SET_PUBLICATION_PASSWORD, async (
    _ctx,
    workspaceId: string,
    pageSlug: string,
    password: string | null,
  ) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const publisher = await buildPublisher()
    const updated = await publisher.setPassword(workspace.rootPath, workspace.id, pageSlug, password)
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    return updated
  })

  // Unpublish (revoke the public copy, clear the local pointer + vault token)
  server.handle(RPC_CHANNELS.pages.UNPUBLISH, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) throw new Error(`Workspace not found: ${workspaceId}`)
    const publisher = await buildPublisher()
    const result = await publisher.unpublish(workspace.rootPath, workspace.id, pageSlug)
    deps.sessionManager.notifyConfigFileChange(workspace.rootPath, `pages/${pageSlug}/page.json`)
    await broadcastChanged(workspaceId, workspace.rootPath)
    return { config: result.config, warning: result.warning }
  })

  // ------------------------------------------------------------------
  // Thumbnails (cached poster). Generation is Electron-main-only; these
  // handlers serve the stored file and enqueue regeneration (a no-op on hosts
  // without an injected capturer).
  // ------------------------------------------------------------------

  // Read a page's poster as a data URL, but ONLY when it is fresh (the stored
  // digest matches the current content). Stale/missing → null → tile falls back.
  server.handle(RPC_CHANNELS.pages.GET_THUMBNAIL, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return null
    const { loadPageConfig, getPageThumbnailPath, isThumbnailFresh } = await import('@craft-agent/shared/pages')
    const config = loadPageConfig(workspace.rootPath, pageSlug)
    if (!config || !isThumbnailFresh(config)) return null
    const path = getPageThumbnailPath(workspace.rootPath, pageSlug)
    const { readFileSync, existsSync } = await import('node:fs')
    if (!existsSync(path)) return null
    try {
      const b64 = readFileSync(path).toString('base64')
      return { dataUrl: `data:image/jpeg;base64,${b64}`, digest: config.contentDigest! }
    } catch {
      return null
    }
  })

  // Manually request a (re)capture (e.g. an agent/user "refresh preview").
  server.handle(RPC_CHANNELS.pages.REGENERATE_THUMBNAIL, async (_ctx, workspaceId: string, pageSlug: string) => {
    const workspace = getWorkspaceByNameOrId(workspaceId)
    if (!workspace) return false
    deps.sessionManager.enqueuePageThumbnail(workspaceId, workspace.rootPath, pageSlug)
    return true
  })
}
