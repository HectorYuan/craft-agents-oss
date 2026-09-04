/**
 * ZenSkillMarketSearch — Marketplace search + one-click install UI backed by
 * the zenskill-4 MCP source (skill_search / skill_install). Rendered at the
 * top of SkillsListPanel when a workspace is active.
 */
import * as React from 'react'
import { Search, Download, Loader2, Check } from 'lucide-react'
import { toast } from 'sonner'

export function ZenSkillMarketSearch({ workspaceId }: { workspaceId?: string }) {
  const [marketQuery, setMarketQuery] = React.useState('')
  const [marketResults, setMarketResults] = React.useState<Array<{name: string; description: string; uri?: string; skill_id?: string; score?: number}>>([])
  const [marketLoading, setMarketLoading] = React.useState(false)
  const [installingUri, setInstallingUri] = React.useState<string | null>(null)
  const [installedUris, setInstalledUris] = React.useState<Set<string>>(new Set())
  const marketTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const searchMarketplace = React.useCallback((query: string) => {
    if (marketTimerRef.current) clearTimeout(marketTimerRef.current)
    if (!query.trim()) { setMarketResults([]); return }
    marketTimerRef.current = setTimeout(async () => {
      setMarketLoading(true)
      try {
        const res = await window.electronAPI.callMcpTool(workspaceId!, 'zenskill-4', 'skill_search', { query: query.trim(), top_k: 6 })
        const text = (res as any)?.result?.content?.[0]?.text
        if (text) {
          const data = JSON.parse(text)
          setMarketResults(data.results || [])
        }
      } catch { setMarketResults([]) }
      finally { setMarketLoading(false) }
    }, 400)
  }, [workspaceId])

  const installSkill = React.useCallback(async (uri: string, name: string) => {
    setInstallingUri(uri)
    try {
      const res = await window.electronAPI.callMcpTool(workspaceId!, 'zenskill-4', 'skill_install', { uri })
      const text = (res as any)?.result?.content?.[0]?.text
      const data = text ? JSON.parse(text) : {}
      if (data.ok) {
        setInstalledUris(prev => new Set(prev).add(uri))
        toast.success(`Installed: ${name}`)
      } else {
        toast.error(data.message || `Failed to install ${name}`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Install failed')
    } finally {
      setInstallingUri(null)
    }
  }, [workspaceId])

  if (!workspaceId) return null

  return (
    <div className="px-2 pt-2 pb-1 space-y-1.5">
      <div className="relative">
        <Search className="h-3 w-3 text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2" />
        <input
          value={marketQuery}
          onChange={(e) => { setMarketQuery(e.target.value); searchMarketplace(e.target.value) }}
          placeholder="Search ZenSkill marketplace..."
          className="w-full text-xs bg-muted/40 rounded pl-6 pr-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
        />
      </div>
      {marketLoading && (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground pl-1">
          <Loader2 className="h-3 w-3 animate-spin" /> Searching...
        </div>
      )}
      {marketResults.length > 0 && (
        <div className="space-y-0.5 max-h-40 overflow-y-auto">
          {marketResults.map((r) => {
            const uri = r.uri || `clawhub://${r.skill_id || r.name}`
            return (
            <div key={r.uri || r.name} className="flex items-center gap-2 text-xs rounded px-2 py-1 hover:bg-muted/50 group">
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium">{r.name}</div>
                <div className="truncate text-[10px] text-muted-foreground">{r.description}</div>
              </div>
              {installedUris.has(uri) ? (
                <span className="text-[10px] text-green-500 shrink-0 flex items-center gap-0.5"><Check className="h-3 w-3" /> Installed</span>
              ) : (
                <button
                  className="opacity-0 group-hover:opacity-100 shrink-0 flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
                  disabled={installingUri === uri}
                  onClick={() => installSkill(uri, r.name)}
                >
                  {installingUri === uri ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                  Install
                </button>
              )}
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
