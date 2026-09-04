/**
 * MemoryBrowser — ZenSkill top-level memory browser page (L2).
 *
 * Second registry page: proves the L1/L3 stack generalizes beyond GtdWorkspace.
 * Recent memories come from memory_list (also feeds the total count header);
 * a debounced search switches to memory_search. Both read through the
 * useMcpTool L3 hook — the search hook is parked (workspaceId undefined)
 * while the query is empty, since memory_search requires a query arg.
 * No write tools here (memory_remember is agent-side by design).
 */
import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Brain, Search } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG, type ZenSkillPageProps } from '../zenskill-registry'

const CONTENT_TRUNCATE = 200

interface MemoryItem {
  id?: string
  content: string
  skill_id?: string
  action?: string
  date?: string
}

interface MemoryListData {
  count?: number
  showing?: number
  items?: MemoryItem[]
}

interface MemorySearchData {
  count?: number
  showing?: number
  items?: MemoryItem[]
}

function itemKey(item: MemoryItem, index: number): string {
  return item.id ?? `${item.skill_id ?? ''}:${item.date ?? ''}:${index}`
}

function truncateContent(content: string, expanded: boolean): string {
  if (expanded || content.length <= CONTENT_TRUNCATE) return content
  return `${content.slice(0, CONTENT_TRUNCATE)}…`
}

function ListSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-muted/60 animate-pulse"
          style={{ width: `${80 - i * 10}%` }}
        />
      ))}
    </div>
  )
}

export function MemoryBrowser({ workspaceId }: ZenSkillPageProps) {
  const { t } = useTranslation()
  const [queryInput, setQueryInput] = useState('')
  // Committed after the 300ms debounce; drives the search hook args
  const [query, setQuery] = useState('')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(queryInput.trim())
      setExpandedKey(null)
    }, 300)
    return () => clearTimeout(timer)
  }, [queryInput])

  const searching = query.length > 0

  // Recent memories (default view) — also feeds the total count header
  const recent = useMcpTool<MemoryListData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'memory_list',
    { skill_id: 'all', n: 30 },
  )
  // Search — parked while query is empty (memory_search requires a query)
  const search = useMcpTool<MemorySearchData>(
    searching ? workspaceId : undefined,
    ZENSKILL_SOURCE_SLUG,
    'memory_search',
    { query, n: 20 },
  )

  const items = searching ? (search.data?.items ?? []) : (recent.data?.items ?? [])
  const loading = searching ? search.loading : recent.loading
  const error = searching ? search.error : recent.error
  const totalCount = recent.data?.count ?? 0

  const showSkeleton = loading && items.length === 0

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-border/30 shrink-0">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-accent" />
          <div className="text-sm font-medium">{t('zenskill.memory.title')}</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground tabular-nums">{totalCount}</span>
          {loading && (
            <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
              <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="mx-5 mt-3 text-xs text-destructive bg-destructive/5 rounded p-2">
          {t('zenskill.memory.error')}{error ? `: ${error}` : ''}
        </div>
      )}

      {/* Search bar */}
      <div className="px-5 pt-3 shrink-0">
        <div className="relative max-w-2xl">
          <Search className="h-3.5 w-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder={t('zenskill.memory.searchPlaceholder')}
            className="w-full text-xs bg-muted/40 rounded pl-7 pr-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40"
          />
        </div>
      </div>

      {/* Memory list */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl">
          {showSkeleton ? (
            <ListSkeleton rows={6} />
          ) : items.length === 0 ? (
            <div className="text-xs text-muted-foreground italic py-8 text-center">
              {t('zenskill.memory.empty')}
            </div>
          ) : (
            <div className="space-y-1.5">
              {items.map((item, i) => {
                const key = itemKey(item, i)
                const expanded = expandedKey === key
                return (
                  <button
                    key={key}
                    onClick={() => setExpandedKey(expanded ? null : key)}
                    className="w-full text-left text-xs rounded px-2.5 py-2 border border-border/40 bg-muted/20 hover:bg-muted/50 transition-colors"
                  >
                    <div className={expanded ? 'whitespace-pre-wrap break-words' : 'truncate'}>
                      {truncateContent(item.content, expanded)}
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {item.action && (
                        <span className="text-[9px] px-1 py-px rounded bg-accent/10 text-accent shrink-0">{item.action}</span>
                      )}
                      {item.skill_id && (
                        <span className="text-[10px] text-muted-foreground truncate">{item.skill_id}</span>
                      )}
                      {item.date && (
                        <span className="text-[10px] text-muted-foreground/60 shrink-0 ml-auto">{item.date}</span>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
