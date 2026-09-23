/**
 * SkillMarketPage — 技能市场页（四区布局）
 *
 * 1. 源管理：market_sources 清单 + 健康/启用状态 + 折叠表单 market_add
 * 2. 发现：market_search（300ms 防抖）+ market_browse 前 8 类 + market_trending
 * 3. 安装与扫描：卡片/URI 直装统一走 skill_install 三分支（ok / need_confirm / blocked）
 * 4. 我的技能：skill_scan 全量清单 + 风险/可用性徽章 + skill_uninstall（二次确认）
 */
import React, { useCallback, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Store, Search, Download, Loader2, Check, Server, Plus, ChevronDown,
  ShieldAlert, ShieldCheck, AlertTriangle, Trash2, Flame, Link, Upload, Package,
} from 'lucide-react'
import { toast } from 'sonner'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'
import { ZENSKILL_SOURCE_SLUG } from '../zenskill-registry'

/* ------------------------------------------------------------------ */
/*  Data shapes                                                        */
/* ------------------------------------------------------------------ */

interface MarketSkill {
  skill_id?: string
  name?: string
  description?: string
  market?: string
  source?: string
  uri?: string
}

interface SourceItem {
  name?: string
  id?: string
  type?: string
  url?: string
  enabled?: boolean
  healthy?: boolean
  health?: boolean | string
  status?: string
}

interface BrowseCategory {
  name?: string
  count?: number
  skills?: MarketSkill[]
}

interface ScanDetail {
  skill_id?: string
  risk_level?: string
  usability?: string
  rules?: string[]
  findings_count?: number
}

interface InstallReport {
  uri: string
  name: string
  ok?: boolean
  blocked?: boolean
  needConfirm?: boolean
  risk?: string
  findings?: number
  rules?: string[]
}

function skillUri(s: MarketSkill): string {
  return s.uri || `clawhub://${s.skill_id || s.name}`
}

function marketBadge(s: MarketSkill): string {
  return s.market || s.source || 'clawhub'
}

function asList<T>(data: any, key?: string): T[] {
  if (Array.isArray(data)) return data as T[]
  return (key ? data?.[key] : data?.results ?? data?.sources ?? data?.items) ?? []
}

function findingsCount(security: any): number {
  if (!security) return 0
  if (Array.isArray(security.findings)) return security.findings.length
  return security.findings ?? security.findings_count ?? 0
}

function riskBadgeClass(level?: string): string {
  const l = (level || '').toLowerCase()
  if (l.includes('danger') || l === 'high' || l === 'blocked') return 'bg-red-500/10 text-red-500'
  if (l.includes('warn') || l === 'medium' || l === 'degraded') return 'bg-amber-500/10 text-amber-500'
  return 'bg-green-500/10 text-green-500'
}

function SectionHeader({ icon: Icon, title, right }: { icon: typeof Server; title: string; right?: React.ReactNode }) {
  return (
    <div className={ZS.sectionHeader}>
      <Icon className="h-3.5 w-3.5 text-accent" />
      <span className="text-xs font-medium">{title}</span>
      {right && <span className="ml-auto">{right}</span>}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Market skill card（发现/分类/热门共用，含安装三分支）                */
/* ------------------------------------------------------------------ */

interface CardState {
  installed: Set<string>
  installing: string | null
  pendingConfirm: Record<string, { risk?: string; findings: number }>
  blocked: Record<string, string[]>
  onInstall: (uri: string, name: string, confirm?: boolean) => void
}

function MarketSkillCard({ skill, state }: { skill: MarketSkill; state: CardState }) {
  const { t } = useTranslation()
  const uri = skillUri(skill)
  const name = skill.name || skill.skill_id || uri
  const isInstalled = state.installed.has(uri)
  const confirm = state.pendingConfirm[uri]
  const rules = state.blocked[uri]

  return (
    <div className="text-xs rounded border border-border/30 px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="truncate font-medium">{name}</span>
            <span className="text-[9px] px-1 py-px rounded bg-accent/10 text-accent shrink-0">{marketBadge(skill)}</span>
          </div>
          {skill.description && (
            <div className="truncate text-[10px] text-muted-foreground">{skill.description}</div>
          )}
        </div>
        {isInstalled ? (
          <span className="shrink-0 flex items-center gap-0.5 text-[10px] text-green-500">
            <Check className="h-3 w-3" /> {t('zenskill.market.installed')}
          </span>
        ) : rules ? (
          <span className="shrink-0 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-500">
            <ShieldAlert className="h-3 w-3" /> {t('zenskill.market.blocked')}
          </span>
        ) : confirm ? (
          <button
            className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 hover:bg-amber-500/20"
            disabled={state.installing === uri}
            onClick={() => state.onInstall(uri, name, true)}
            title={t('zenskill.market.riskFindings', { risk: confirm.risk ?? '—', n: confirm.findings })}
          >
            {state.installing === uri ? <Loader2 className="h-3 w-3 animate-spin" /> : <AlertTriangle className="h-3 w-3" />}
            {t('zenskill.market.needConfirm')}
            <span className="opacity-70">{confirm.risk ?? ''} · {confirm.findings}</span>
          </button>
        ) : (
          <button
            className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
            disabled={state.installing === uri}
            onClick={() => state.onInstall(uri, name)}
          >
            {state.installing === uri ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
            {t('zenskill.market.install')}
          </button>
        )}
      </div>
      {rules && rules.length > 0 && (
        <div className="text-[10px] text-red-500/80">{t('zenskill.market.rules', { rules: rules.join(', ') })}</div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Section 1: Sources                                                 */
/* ------------------------------------------------------------------ */

function SourcesSection({ workspaceId }: { workspaceId?: string }) {
  const { t } = useTranslation()
  const sources = useMcpTool<any>(workspaceId, ZENSKILL_SOURCE_SLUG, 'market_sources', { health: true })
  const [formOpen, setFormOpen] = useState(false)
  const [name, setName] = useState('')
  const [type, setType] = useState('generic-http')
  const [url, setUrl] = useState('')
  const [fieldMapping, setFieldMapping] = useState('')
  const [adding, setAdding] = useState(false)

  const list = useMemo(() => asList<SourceItem>(sources.data, 'sources'), [sources.data])

  const addSource = useCallback(async () => {
    if (!workspaceId || !name.trim() || adding) return
    setAdding(true)
    try {
      let field_mapping: Record<string, string> | undefined
      if (fieldMapping.trim()) {
        try {
          field_mapping = JSON.parse(fieldMapping)
        } catch {
          field_mapping = Object.fromEntries(
            fieldMapping.split(',').map((p) => p.split('=').map((s) => s.trim())).filter((kv) => kv[0] && kv[1]),
          )
        }
      }
      const res = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'market_add', {
        config: { name: name.trim(), type, url: url.trim() || undefined, field_mapping },
      })
      const data = (extractMcpJson(res) ?? {}) as any
      if (data.ok || data.success || !data.error) {
        toast.success(`${name.trim()}: added`)
        setName(''); setUrl(''); setFieldMapping(''); setFormOpen(false)
        sources.refresh()
      } else {
        toast.error(data.error || data.message || 'market_add failed')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'market_add failed')
    } finally {
      setAdding(false)
    }
  }, [workspaceId, name, type, url, fieldMapping, adding, sources])

  return (
    <div className={ZS.card}>
      <SectionHeader
        icon={Server}
        title={t('zenskill.market.sources')}
        right={
          <button
            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
            onClick={() => setFormOpen((v) => !v)}
          >
            {formOpen ? <ChevronDown className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
            {t('zenskill.market.sources.add')}
          </button>
        }
      />
      {sources.loading && !list.length && <div className={`${ZS.skeleton} w-40`} />}
      {!sources.loading && !list.length && <div className={ZS.emptyState}>{t('zenskill.market.empty')}</div>}
      <div className="space-y-1">
        {list.map((s, i) => {
          const healthy = typeof s.healthy === 'boolean' ? s.healthy : typeof s.health === 'boolean' ? s.health : s.status !== 'unhealthy'
          return (
            <div key={s.name || s.id || i} className="flex items-center gap-2 text-xs rounded px-1.5 py-1 hover:bg-muted/50">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="truncate font-medium">{s.name || s.id}</span>
                  {s.type && <span className="text-[9px] px-1 py-px rounded bg-muted text-muted-foreground shrink-0">{s.type}</span>}
                </div>
                {s.url && <div className="truncate text-[10px] text-muted-foreground">{s.url}</div>}
              </div>
              {s.enabled === false && <span className="text-[9px] px-1 py-px rounded bg-muted text-muted-foreground shrink-0">off</span>}
              <span className={`shrink-0 inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded ${healthy ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`}>
                {healthy ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
                {healthy ? t('zenskill.market.sources.healthy') : t('zenskill.market.sources.unhealthy')}
              </span>
            </div>
          )
        })}
      </div>
      {formOpen && (
        <div className="mt-2 space-y-1.5 border-t border-border/30 pt-2">
          <div className="grid grid-cols-2 gap-1.5">
            <input className={ZS.input} placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
            <select className={ZS.input} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="generic-http">generic-http</option>
              <option value="search_url">search_url</option>
            </select>
          </div>
          <input className={ZS.input} placeholder="https://... (url)" value={url} onChange={(e) => setUrl(e.target.value)} />
          <input
            className={ZS.input}
            placeholder='field_mapping: {"k":"v"} 或 k=v,k2=v2'
            value={fieldMapping}
            onChange={(e) => setFieldMapping(e.target.value)}
          />
          <button
            className="w-full text-xs py-1 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"
            disabled={!name.trim() || adding}
            onClick={() => void addSource()}
          >
            {adding ? <Loader2 className="h-3 w-3 animate-spin inline" /> : t('zenskill.market.sources.add')}
          </button>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export function SkillMarketPage({ workspaceId }: { workspaceId?: string; initialTab?: string; onNavigateToChat?: (msg: string) => void }) {
  const { t } = useTranslation()

  // 区2 发现
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MarketSkill[]>([])
  const [searching, setSearching] = useState(false)
  const [activeCat, setActiveCat] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const browse = useMcpTool<{ total?: number; categories?: BrowseCategory[] }>(workspaceId, ZENSKILL_SOURCE_SLUG, 'market_browse', { limit: 8 })
  const trending = useMcpTool<any>(workspaceId, ZENSKILL_SOURCE_SLUG, 'market_trending', { top_k: 5 })
  const scan = useMcpTool<{ total?: number; dangerous?: number; warn?: number; safe?: number; details?: ScanDetail[] }>(
    workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_scan', {},
  )

  // 区3 安装与扫描
  const [installed, setInstalled] = useState<Set<string>>(new Set())
  const [installing, setInstalling] = useState<string | null>(null)
  const [pendingConfirm, setPendingConfirm] = useState<Record<string, { risk?: string; findings: number }>>({})
  const [blocked, setBlocked] = useState<Record<string, string[]>>({})
  const [lastReport, setLastReport] = useState<InstallReport | null>(null)
  const [uriInput, setUriInput] = useState('')

  const runInstall = useCallback(async (uri: string, name: string, confirm = false) => {
    if (!workspaceId || installing) return
    setInstalling(uri)
    try {
      const res = await window.electronAPI.callMcpTool(
        workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_install', confirm ? { uri, confirm: true } : { uri },
      )
      const data = (extractMcpJson(res) ?? {}) as any
      const security = data.security ?? {}
      const findings = findingsCount(security)
      const rules: string[] = Array.isArray(security.rules) ? security.rules : []
      if (data.blocked) {
        setBlocked((prev) => ({ ...prev, [uri]: rules }))
        setPendingConfirm((prev) => { const next = { ...prev }; delete next[uri]; return next })
        setLastReport({ uri, name, blocked: true, risk: security.risk_level, findings, rules })
        toast.error(`${name}: ${t('zenskill.market.blocked')}`)
        return
      }
      if (data.need_confirm) {
        setPendingConfirm((prev) => ({ ...prev, [uri]: { risk: security.risk_level, findings } }))
        setLastReport({ uri, name, needConfirm: true, risk: security.risk_level, findings, rules })
        return
      }
      if (data.ok) {
        setInstalled((prev) => new Set(prev).add(uri))
        setPendingConfirm((prev) => { const next = { ...prev }; delete next[uri]; return next })
        setLastReport({ uri, name, ok: true, risk: security.risk_level, findings })
        const usability = data.usability ?? {}
        if (usability.status === 'degraded' && Array.isArray(usability.issues) && usability.issues.length > 0) {
          toast.warning(`${t('zenskill.market.installed')}: ${name}`, { description: usability.issues.join('；') })
        } else {
          toast.success(`${t('zenskill.market.installed')}: ${name}`)
        }
        scan.refresh()
        return
      }
      toast.error(data.message || data.error || `${name}: install failed`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Install failed')
    } finally {
      setInstalling(null)
    }
  }, [workspaceId, installing, scan, t])

  const onSearchChange = useCallback((value: string) => {
    setQuery(value)
    setActiveCat(null)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!value.trim()) { setResults([]); setSearching(false); return }
    debounceRef.current = setTimeout(async () => {
      if (!workspaceId) return
      setSearching(true)
      try {
        const res = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'market_search', { query: value.trim(), top_k: 8 })
        const data = (extractMcpJson(res) ?? {}) as any
        setResults(asList<MarketSkill>(data))
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
  }, [workspaceId])

  const cardState: CardState = { installed, installing, pendingConfirm, blocked, onInstall: (uri, name, confirm) => void runInstall(uri, name, confirm) }
  const categories = (browse.data?.categories ?? []).slice(0, 8)
  const activeCategory = categories.find((c) => c.name === activeCat)
  const trendingList = asList<MarketSkill>(trending.data).slice(0, 5)
  const scanDetails = scan.data?.details ?? []

  // 区4 卸载（二次确认）
  const [arming, setArming] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  // 区4 发布/部署（W5 出站：dry_run 校验→真部署，两段式确认）
  const [deployPlatform, setDeployPlatform] = useState('codex')
  const [deployArming, setDeployArming] = useState<string | null>(null)
  const [deploying, setDeploying] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const deploy = useCallback(async (skillId: string) => {
    if (!workspaceId || deploying) return
    setDeploying(skillId)
    try {
      const dry = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_deploy',
        { skill_id: skillId, platform: deployPlatform, dry_run: true })
      const dryData = (extractMcpJson(dry) ?? {}) as any
      if (!dryData.ok) {
        toast.error(dryData.error || 'skill_deploy dry_run failed')
        return
      }
      const res = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_deploy',
        { skill_id: skillId, platform: deployPlatform })
      const data = (extractMcpJson(res) ?? {}) as any
      if (data.ok) {
        toast.success(`${skillId} → ${deployPlatform}: ${data.deployed_to ?? 'deployed'}`)
      } else {
        toast.error(data.error || 'skill_deploy failed')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'skill_deploy failed')
    } finally {
      setDeploying(null)
      setDeployArming(null)
    }
  }, [workspaceId, deploying, deployPlatform])

  const exportManifest = useCallback(async () => {
    if (!workspaceId || exporting) return
    setExporting(true)
    try {
      const res = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_export', {})
      const data = (extractMcpJson(res) ?? {}) as any
      if (data.ok) {
        try {
          await navigator.clipboard.writeText(JSON.stringify(data.manifest, null, 2))
          toast.success(`${t('zenskill.market.exportManifest')}: ${data.count}`)
        } catch {
          toast.success(`${t('zenskill.market.exportManifest')}: ${data.count} (clipboard unavailable)`)
        }
      } else {
        toast.error(data.error || 'skill_export failed')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'skill_export failed')
    } finally {
      setExporting(false)
    }
  }, [workspaceId, exporting, t])
  const uninstall = useCallback(async (skillId: string) => {
    if (!workspaceId || removing) return
    setRemoving(skillId)
    try {
      const res = await window.electronAPI.callMcpTool(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_uninstall', { skill_id: skillId })
      const data = (extractMcpJson(res) ?? {}) as any
      if (data.ok || data.success || !data.error) {
        toast.success(`${skillId}: uninstalled`)
        scan.refresh()
      } else {
        toast.error(data.error || data.message || 'skill_uninstall failed')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'skill_uninstall failed')
    } finally {
      setRemoving(null)
      setArming(null)
    }
  }, [workspaceId, removing, scan])

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center gap-2">
          <Store className="h-4 w-4 text-accent" />
          <div>
            <div className={ZS.title}>{t('zenskill.market.title')}</div>
            <div className={ZS.subtitle}>{t('zenskill.market.subtitle')}</div>
          </div>
        </div>
      </div>

      {!workspaceId ? (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>No active workspace</div>
      ) : (
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="space-y-4 max-w-3xl">
            {/* 区1 源管理 */}
            <SourcesSection workspaceId={workspaceId} />

            {/* 区2 发现 */}
            <div className={ZS.card}>
              <SectionHeader icon={Search} title={t('zenskill.market.discover')} />
              <div className="relative mb-2">
                <Search className="h-3 w-3 text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2" />
                <input
                  value={query}
                  onChange={(e) => onSearchChange(e.target.value)}
                  placeholder={t('zenskill.market.searchPlaceholder')}
                  className={`${ZS.input} w-full pl-6`}
                />
                {searching && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground absolute right-2 top-1/2 -translate-y-1/2" />}
              </div>
              {results.length > 0 && (
                <div className="space-y-1 mb-3">
                  {results.map((r) => <MarketSkillCard key={skillUri(r)} skill={r} state={cardState} />)}
                </div>
              )}
              {!results.length && !searching && query.trim() && <div className={`${ZS.emptyState} mb-3`}>{t('zenskill.market.empty')}</div>}

              {/* 分类浏览（前 8 类，点开看类内技能） */}
              {categories.length > 0 && (
                <div className="mb-3">
                  <div className={ZS.subtitle + ' mb-1'}>
                    {t('zenskill.market.categories')} ({browse.data?.total ?? categories.reduce((s, c) => s + (c.count ?? 0), 0)})
                  </div>
                  <div className="flex flex-wrap gap-1.5 mb-1.5">
                    {categories.map((c) => (
                      <button
                        key={c.name}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-sm font-medium ${activeCat === c.name ? 'bg-accent text-accent-foreground' : 'bg-accent/10 text-accent hover:bg-accent/20'}`}
                        onClick={() => setActiveCat(activeCat === c.name ? null : c.name ?? null)}
                      >
                        {c.name}
                        <span className="opacity-70">{c.count}</span>
                      </button>
                    ))}
                  </div>
                  {activeCategory && (
                    <div className="space-y-1">
                      {(activeCategory.skills ?? []).map((s) => <MarketSkillCard key={skillUri(s)} skill={s} state={cardState} />)}
                    </div>
                  )}
                </div>
              )}

              {/* 热门 */}
              {trendingList.length > 0 && (
                <div>
                  <div className={ZS.subtitle + ' mb-1 flex items-center gap-1'}>
                    <Flame className="h-3 w-3 text-accent" /> {t('zenskill.market.trending')}
                  </div>
                  <div className="space-y-1">
                    {trendingList.map((r) => <MarketSkillCard key={skillUri(r)} skill={r} state={cardState} />)}
                  </div>
                </div>
              )}
            </div>

            {/* 区3 安装与扫描（URI 直装 + 最近安装安全报告） */}
            <div className={ZS.card}>
              <SectionHeader icon={Link} title={t('zenskill.market.uriInstall')} />
              <div className="flex items-center gap-1.5">
                <input
                  className={`${ZS.input} flex-1`}
                  placeholder={t('zenskill.market.uriPlaceholder')}
                  value={uriInput}
                  onChange={(e) => setUriInput(e.target.value)}
                />
                <button
                  className="shrink-0 inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-40"
                  disabled={!uriInput.trim() || installing === uriInput.trim()}
                  onClick={() => void runInstall(uriInput.trim(), uriInput.trim())}
                >
                  {installing === uriInput.trim() ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                  {t('zenskill.market.install')}
                </button>
              </div>
              {lastReport && (
                <div className="mt-2 text-xs rounded border border-border/30 px-2 py-1.5 space-y-1">
                  <div className="flex items-center gap-1.5">
                    {lastReport.blocked ? (
                      <ShieldAlert className="h-3.5 w-3.5 text-red-500" />
                    ) : lastReport.ok ? (
                      <ShieldCheck className="h-3.5 w-3.5 text-green-500" />
                    ) : (
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                    )}
                    <span className="truncate font-medium">{lastReport.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${riskBadgeClass(lastReport.risk)}`}>
                      {lastReport.risk ?? '—'} · {lastReport.findings ?? 0}
                    </span>
                  </div>
                  {lastReport.rules && lastReport.rules.length > 0 && (
                    <div className="text-[10px] text-red-500/80">{t('zenskill.market.rules', { rules: lastReport.rules.join(', ') })}</div>
                  )}
                </div>
              )}
            </div>

            {/* 区4 我的技能（skill_scan 全量 + 卸载 + 导出/部署） */}
            <div className={ZS.card}>
              <SectionHeader
                icon={Check}
                title={`${t('zenskill.market.mySkills')} (${scan.data?.total ?? scanDetails.length})`}
                right={
                  <button
                    className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded text-muted-foreground hover:bg-muted disabled:opacity-50"
                    disabled={exporting}
                    onClick={() => void exportManifest()}
                  >
                    {exporting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Package className="h-3 w-3" />}
                    {t('zenskill.market.exportManifest')}
                  </button>
                }
              />
              {scan.loading && !scanDetails.length && <div className={`${ZS.skeleton} w-40`} />}
              {scan.error && !scanDetails.length && <div className={ZS.errorBanner}>{scan.error}</div>}
              {!scan.loading && !scanDetails.length && !scan.error && <div className={ZS.emptyState}>{t('zenskill.market.empty')}</div>}
              <div className="space-y-1">
                {scanDetails.map((d) => {
                  const skillId = d.skill_id ?? ''
                  return (
                    <div key={skillId} className="flex items-center gap-2 text-xs rounded px-1.5 py-1 hover:bg-muted/50">
                      <div className="flex-1 min-w-0">
                        <span className="truncate font-medium">{skillId}</span>
                      </div>
                      <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded ${riskBadgeClass(d.risk_level)}`}>{d.risk_level ?? 'safe'}</span>
                      {d.usability && (
                        <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded ${riskBadgeClass(d.usability)}`}>{d.usability}</span>
                      )}
                      {deployArming === skillId ? (
                        <>
                          <select
                            className="shrink-0 text-[10px] px-1 py-0.5 rounded border border-border/50 bg-background"
                            value={deployPlatform}
                            onChange={(e) => setDeployPlatform(e.target.value)}
                          >
                            {['local', 'codex', 'cursor', 'opencode'].map((p) => (
                              <option key={p} value={p}>{p}</option>
                            ))}
                          </select>
                          <button
                            className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent hover:bg-accent/25"
                            disabled={deploying === skillId}
                            onClick={() => void deploy(skillId)}
                          >
                            {deploying === skillId ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                            {t('zenskill.market.deployConfirm')}
                          </button>
                        </>
                      ) : (
                        <button
                          className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded text-muted-foreground hover:bg-muted"
                          onClick={() => setDeployArming(skillId)}
                        >
                          <Upload className="h-3 w-3" /> {t('zenskill.market.deploy')}
                        </button>
                      )}
                      {arming === skillId ? (
                        <button
                          className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-500 hover:bg-red-500/20"
                          disabled={removing === skillId}
                          onClick={() => void uninstall(skillId)}
                        >
                          {removing === skillId ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                          {t('zenskill.market.uninstallConfirm')}
                        </button>
                      ) : (
                        <button
                          className="shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded text-muted-foreground hover:bg-muted"
                          onClick={() => setArming(skillId)}
                        >
                          <Trash2 className="h-3 w-3" /> {t('zenskill.market.uninstall')}
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
