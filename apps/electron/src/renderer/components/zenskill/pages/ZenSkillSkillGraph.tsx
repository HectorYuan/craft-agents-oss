/**
 * ZenSkillSkillGraph — Circle Packing 技能图谱（磁盘 Pages 版的 React 实体）
 *
 * 对齐 zenskill-skill-graph/index.html 的能力基线：
 * - 两级 Circle Packing：域聚合视图（气泡+域间弦+top-3 高频小圆）→ 点击下钻域明细
 * - 节点半径对数缩放（usage 0/1/1717 极不均匀，线性会压成同尺寸）
 * - 使用热度着色（0=灰 / <10=蓝 / <100=橙 / 100+=红）
 * - 治理编码（B4，字段防御性读取）：dormant 虚线描边 / T0 金描边 / T2 淡化
 * - hover tooltip、click 滑出详情面板（五维雷达 + 强关联 + 弱共现）
 * - 选中高亮 top-8 强关联边、无关节点降透明度
 * - 域 chips 显隐、技能搜索（300ms 防抖）、viewBox 缩放平移、archived 开关
 * - 五类关系色图例 + 治理图例 + 统计面板
 *
 * 数据源 skill_graph（SkillDependencyGraph 全量图，与磁盘 refresh 同源；
 * growth_dashboard 只覆盖有运行态的个位数技能，不可用作图谱数据源）：
 * 治理字段（tier/state/quality_score/last_used_at）由 backend 增补，
 * 此处全部防御性读取，缺失走默认值不崩。
 */
import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Network, Search, ChevronLeft, X } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ErrorBoundary } from '../panels/ErrorBoundary'
import { RadarChart } from '../panels/RadarChart'
import { PageToChatBridge } from '../PageToChatBridge'
import { ZS } from '../panels/tokens'
import { ZENSKILL_SOURCE_SLUG, type ZenSkillPageProps } from '../zenskill-registry'

interface SkillNode {
  // growth_dashboard 口径
  skill_id?: string
  id?: string
  name?: string
  category?: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number> | null
  last_used?: string
  // snapshot 口径（磁盘版 refresh.py 产出），防御性兼容
  usage?: number
  five_dims?: Record<string, number> | null
  last_used_at?: string
  // 治理字段（B4，backend 并行增补），缺失不崩
  tier?: string
  state?: string
  status?: string
  quality_score?: number
}

interface SkillEdge {
  source?: string
  target?: string
  from?: string
  to?: string
  relation?: string
  type?: string
  strength?: number
}

interface GrowthData {
  count?: number
  skills?: SkillNode[]
  edges?: SkillEdge[]
  source?: string
  stats?: { node_count?: number; edge_count?: number }
}

/** 归一化后的节点 */
interface GNode {
  id: string
  name: string
  category: string
  level: string
  usage: number
  successRate?: number
  five?: Record<string, number>
  lastUsed?: string
  tier?: string
  state?: string
  quality?: number
}

/** 归一化后的边 */
interface GEdge {
  from: string
  to: string
  type: string
  strength: number
}

interface PackedItem<T> {
  x: number
  y: number
  r: number
  data: T
}

interface TooltipState {
  x: number
  y: number
  title: string
  meta: string
  five?: Record<string, number>
}

const VIEW_W = 800
const VIEW_H = 500
const INIT_VIEWBOX = { x: 0, y: 0, w: VIEW_W, h: VIEW_H }

const DOMAIN_COLORS: Record<string, string> = {
  lark: '#4080FF', arkcli: '#FF8C40', agentswarm: '#9B59B6', dev: '#2ECC71',
  data: '#3498DB', ai: '#E74C3C', design: '#F39C12', ops: '#95A5A6',
  life: '#1ABC9C', general: '#BDC3C7',
}

/** 域名词表（对齐磁盘版 DOMAIN_NAMES，产品内固定词表） */
const DOMAIN_NAMES: Record<string, string> = {
  lark: '飞书', arkcli: 'ArkCLI', agentswarm: 'AgentSwarm', dev: '开发',
  data: '数据', ai: 'AI', design: '设计', ops: '运维',
  life: '生活', general: '通用',
}

const RELATION_COLORS: Record<string, string> = {
  prerequisite: '#3b82f6',
  complementary: '#22c55e',
  competing: '#ef4444',
  transfer: '#a855f7',
  co_occurrence: '#f59e0b',
}

const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']

const LEVEL_ORDER: Record<string, number> = { MASTER: 0, EXPERT: 1, ADEPT: 2, APPRENTICE: 3, NOVICE: 4 }

const LEVEL_I18N: Record<string, string> = {
  NOVICE: 'zenskill.skillGraph.level.NOVICE',
  APPRENTICE: 'zenskill.skillGraph.level.APPRENTICE',
  ADEPT: 'zenskill.skillGraph.level.ADEPT',
  EXPERT: 'zenskill.skillGraph.level.EXPERT',
  MASTER: 'zenskill.skillGraph.level.MASTER',
}

const TIER_I18N: Record<string, string> = {
  T0: 'zenskill.skillGraph.tier.T0',
  T1: 'zenskill.skillGraph.tier.T1',
  T2: 'zenskill.skillGraph.tier.T2',
}

const STATE_I18N: Record<string, string> = {
  active: 'zenskill.skillGraph.state.active',
  dormant: 'zenskill.skillGraph.state.dormant',
  archived: 'zenskill.skillGraph.state.archived',
  deleted: 'zenskill.skillGraph.state.deleted',
}

// 治理描边调色板（磁盘版 CSS 变量的字面值）
const GOLD = '#d97706'
const EXPERT_STROKE = '#7c5cff'
const DIM_STROKE = '#6b7280'

/**
 * Circle Packing — 螺旋放置法（从磁盘版 index.html 原样移植）。
 * 按半径降序，从中心向外螺旋找第一个不重叠且不出容器的位置。
 */
function packCircles<T>(items: { r: number; data: T }[], containerRadius: number): PackedItem<T>[] {
  if (!items.length) return []
  const sorted = [...items].sort((a, b) => b.r - a.r)
  const placed: PackedItem<T>[] = []
  let angle = 0
  const step = 2
  const maxIter = sorted.length * 200
  let iter = 0

  for (let i = 0; i < sorted.length && iter < maxIter; i++) {
    const item = sorted[i]
    let x = 0
    let y = 0
    let found = false
    let spiralRadius = 0

    while (!found && iter < maxIter) {
      iter++
      x = spiralRadius * Math.cos(angle)
      y = spiralRadius * Math.sin(angle)

      const distFromCenter = Math.sqrt(x * x + y * y)
      if (distFromCenter + item.r > containerRadius) {
        spiralRadius += step
        angle += 0.3
        continue
      }

      let overlap = false
      for (let j = 0; j < placed.length; j++) {
        const dx = x - placed[j].x
        const dy = y - placed[j].y
        if (Math.sqrt(dx * dx + dy * dy) < item.r + placed[j].r + 2) {
          overlap = true
          break
        }
      }

      if (!overlap) found = true
      else {
        spiralRadius += step
        angle += 0.3
      }
    }

    placed.push({ x, y, r: item.r, data: item.data })
  }
  return placed
}

/** 对数缩放半径：usage 0→14px, 1→24px, 10→42px, 100→60px, 1717→86px（封顶 90） */
function nodeRadius(usage: number): number {
  return Math.min(90, 14 + Math.log(1 + Math.max(0, usage)) * 10)
}

/** 使用热度着色（B-3）：0=灰 / 1-10=蓝 / 10-100=橙 / 100+=红 */
function usageHeat(usage: number): { fill: string; opacity: number } {
  if (!usage || usage <= 0) return { fill: '#9CA3AF', opacity: 0.45 }
  if (usage < 10) return { fill: '#3B82F6', opacity: 0.65 }
  if (usage < 100) return { fill: '#F59E0B', opacity: 0.7 }
  return { fill: '#EF4444', opacity: 0.75 }
}

function truncate(text: string, max: number): string {
  const s = String(text || '')
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

/** top-8 强关联边（strength >= 0.3，按强度降序） */
function getStrongEdges(nodeId: string, edges: GEdge[]): GEdge[] {
  return edges
    .filter((e) => (e.from === nodeId || e.to === nodeId) && e.strength >= 0.3)
    .sort((a, b) => b.strength - a.strength)
    .slice(0, 8)
}

function getWeakCount(nodeId: string, edges: GEdge[]): number {
  return edges.filter((e) => (e.from === nodeId || e.to === nodeId) && e.strength < 0.3).length
}

export function ZenSkillSkillGraph({ workspaceId }: ZenSkillPageProps) {
  const { t } = useTranslation()
  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_graph', {})

  const [activeDomain, setActiveDomain] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hiddenDomains, setHiddenDomains] = useState<Record<string, boolean>>({})
  const [showArchived, setShowArchived] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const [searchResults, setSearchResults] = useState<GNode[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [viewBox, setViewBoxState] = useState(INIT_VIEWBOX)

  const svgRef = useRef<SVGSVGElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const searchWrapRef = useRef<HTMLDivElement>(null)
  const viewBoxRef = useRef(INIT_VIEWBOX)
  const panRef = useRef<{ x: number; y: number } | null>(null)
  const draggedRef = useRef(false)

  const applyViewBox = useCallback((fn: (v: typeof INIT_VIEWBOX) => typeof INIT_VIEWBOX) => {
    const next = fn(viewBoxRef.current)
    viewBoxRef.current = next
    setViewBoxState(next)
  }, [])

  const resetViewBox = useCallback(() => {
    viewBoxRef.current = INIT_VIEWBOX
    setViewBoxState(INIT_VIEWBOX)
  }, [])

  // ---------------------------------------------------------------
  // 数据归一化（growth_dashboard / snapshot 双口径 + 治理字段防御读取）
  // ---------------------------------------------------------------
  const nodes: GNode[] = useMemo(() => {
    const raw = growth.data?.skills ?? []
    return raw
      .map((n) => {
        const id = n.skill_id ?? n.id ?? ''
        return {
          id,
          name: n.name ?? id,
          category: n.category || 'general',
          level: n.level || 'NOVICE',
          usage: Math.max(0, n.usage_count ?? n.usage ?? 0),
          successRate: n.success_rate,
          five: (n.five_dims ?? n.scores ?? undefined) as Record<string, number> | undefined,
          lastUsed: n.last_used_at || n.last_used || '',
          tier: n.tier,
          state: n.state ?? n.status,
          quality: n.quality_score,
        }
      })
      .filter((n) => n.id)
  }, [growth.data])

  const edges: GEdge[] = useMemo(
    () =>
      (growth.data?.edges ?? [])
        .map((e) => ({
          from: e.from ?? e.source ?? '',
          to: e.to ?? e.target ?? '',
          type: e.type ?? e.relation ?? 'co_occurrence',
          strength: typeof e.strength === 'number' ? e.strength : 0.3,
        }))
        .filter((e) => e.from && e.to),
    [growth.data],
  )

  const nodeById = useMemo(() => {
    const m = new Map<string, GNode>()
    for (const n of nodes) m.set(n.id, n)
    return m
  }, [nodes])

  const { domainGroups, domainStats } = useMemo(() => {
    const groups: Record<string, GNode[]> = {}
    for (const n of nodes) {
      ;(groups[n.category] ??= []).push(n)
    }
    const stats: Record<string, { count: number; masterCount: number; top?: GNode }> = {}
    for (const cat of Object.keys(groups)) {
      const ns = groups[cat]
      let top: GNode | undefined
      for (const n of ns) if (!top || n.usage > top.usage) top = n
      stats[cat] = {
        count: ns.length,
        masterCount: ns.filter((n) => n.level === 'MASTER').length,
        top,
      }
    }
    return { domainGroups: groups, domainStats: stats }
  }, [nodes])

  const hasTier = useMemo(() => nodes.some((n) => !!n.tier), [nodes])
  const archivedCount = useMemo(() => nodes.filter((n) => n.state === 'archived').length, [nodes])

  const detailNodes = useMemo(() => {
    if (!activeDomain) return []
    return nodes
      .filter((n) => n.category === activeDomain && (showArchived || n.state !== 'archived'))
      .sort((a, b) => (LEVEL_ORDER[a.level] ?? 4) - (LEVEL_ORDER[b.level] ?? 4))
  }, [nodes, activeDomain, showArchived])

  // 域聚合 packing：面积∝count（对数 sqrt 让小域不被大域完全遮挡）
  const domainPacked = useMemo(() => {
    const bubbles = Object.keys(domainGroups)
      .filter((cat) => !hiddenDomains[cat])
      .map((cat) => ({ r: Math.max(22, Math.sqrt(domainStats[cat].count) * 12), data: cat }))
    return packCircles(bubbles, Math.min(VIEW_W, VIEW_H) * 0.55)
  }, [domainGroups, domainStats, hiddenDomains])

  // 域间聚合弦（strength >= 0.3 的跨域边聚合为二次贝塞尔）
  const chords = useMemo(() => {
    if (activeDomain) return []
    const pairs: Record<string, { count: number }> = {}
    for (const e of edges) {
      if (e.strength < 0.3) continue
      const a = nodeById.get(e.from)
      const b = nodeById.get(e.to)
      if (!a || !b || a.category === b.category) continue
      const key = [a.category, b.category].sort().join(':')
      ;(pairs[key] ??= { count: 0 }).count++
    }
    const pos = new Map<string, { x: number; y: number }>()
    for (const p of domainPacked) pos.set(p.data, { x: p.x, y: p.y })
    const cx = VIEW_W / 2
    const cy = VIEW_H / 2
    const paths: { d: string; width: number }[] = []
    for (const key of Object.keys(pairs)) {
      const [d1, d2] = key.split(':')
      const a = pos.get(d1)
      const b = pos.get(d2)
      if (!a || !b) continue
      const mx = (a.x + b.x) / 2 + cx
      const my = (a.y + b.y) / 2 + cy
      const qx = mx + (cx - mx) * 0.15
      const qy = my + (cy - my) * 0.15
      paths.push({
        d: `M ${cx + a.x} ${cy + a.y} Q ${qx} ${qy} ${cx + b.x} ${cy + b.y}`,
        width: Math.min(4, 1 + pairs[key].count * 0.5),
      })
    }
    return paths
  }, [edges, nodeById, domainPacked, activeDomain])

  // 域明细 packing（对数缩放）
  const detailPacked = useMemo(() => {
    if (!activeDomain) return []
    return packCircles(
      detailNodes.map((n) => ({ r: nodeRadius(n.usage), data: n })),
      Math.min(VIEW_W, VIEW_H) * 0.52,
    )
  }, [detailNodes, activeDomain])

  const selectedNode = selectedId ? (nodeById.get(selectedId) ?? null) : null

  // 选中高亮：top-8 强关联的 related 集合 + 顶点位置（用于画高亮边）
  const highlight = useMemo(() => {
    if (!selectedId || !activeDomain) return null
    const strong = getStrongEdges(selectedId, edges)
    const related = new Set<string>([selectedId])
    for (const e of strong) {
      related.add(e.from)
      related.add(e.to)
    }
    const pos = new Map<string, { x: number; y: number }>()
    const cx = VIEW_W / 2
    const cy = VIEW_H / 2
    for (const p of detailPacked) pos.set(p.data.id, { x: cx + p.x, y: cy + p.y })
    const paths: { d: string; width: number; color: string }[] = []
    for (const e of strong) {
      const a = pos.get(e.from)
      const b = pos.get(e.to)
      if (!a || !b) continue
      const mx = (a.x + b.x) / 2
      const my = (a.y + b.y) / 2
      const qx = mx + (cx - mx) * 0.15
      const qy = my + (cy - my) * 0.15
      paths.push({
        d: `M ${a.x} ${a.y} Q ${qx} ${qy} ${b.x} ${b.y}`,
        width: 1 + e.strength * 3,
        color: RELATION_COLORS[e.type] ?? '#7c5cff',
      })
    }
    return { related, paths, strong }
  }, [selectedId, activeDomain, edges, detailPacked])

  // 统计面板（node_count/edge_count 防御读取 + 磁盘版 footer 指标）
  const footerStats = useMemo(() => {
    const nodeCount = growth.data?.stats?.node_count ?? nodes.length
    const edgeCount = growth.data?.stats?.edge_count ?? edges.length
    let masterCount = 0
    let top: GNode | undefined
    for (const n of nodes) {
      if (n.level === 'MASTER') masterCount++
      if (!top || n.usage > top.usage) top = n
    }
    const strongCount = edges.filter((e) => e.strength >= 0.3).length
    const domainCount = Object.keys(domainStats).length
    const generalCount = domainStats.general?.count ?? 0
    const uncategorizedPct =
      generalCount > nodeCount * 0.5 && nodeCount > 10
        ? Math.round((generalCount / nodeCount) * 100)
        : null
    const avgScore =
      nodeCount > 0
        ? Math.round(
            nodes.reduce((sum, n) => {
              const vals = n.five ? Object.values(n.five) : null
              const composite = vals && vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 50
              return sum + composite
            }, 0) / nodeCount,
          )
        : 0
    return { nodeCount, edgeCount, masterCount, top, strongCount, domainCount, uncategorizedPct, avgScore }
  }, [nodes, edges, domainStats, growth.data])

  // 搜索（300ms 防抖，对齐磁盘版）
  useEffect(() => {
    const term = searchInput.trim().toLowerCase()
    if (!term) {
      setSearchResults([])
      setSearchOpen(false)
      return
    }
    const timer = setTimeout(() => {
      const matches = nodes
        .filter((n) => n.name.toLowerCase().includes(term) || n.id.toLowerCase().includes(term))
        .slice(0, 20)
      setSearchResults(matches)
      setSearchOpen(true)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput, nodes])

  // 点击搜索框外部关闭结果
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!searchWrapRef.current?.contains(e.target as Node)) setSearchOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // ESC 关闭详情/搜索
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedId(null)
        setSearchOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // 滚轮缩放（non-passive 监听，围绕鼠标位置，范围 200-3000，对齐磁盘版）
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = svg.getBoundingClientRect()
      const mouseX = (e.clientX - rect.left) / rect.width
      const mouseY = (e.clientY - rect.top) / rect.height
      const factor = e.deltaY > 0 ? 1.1 : 0.9
      applyViewBox((v) => {
        const newW = v.w * factor
        const newH = v.h * factor
        if (newW < 200 || newW > 3000) return v
        return {
          x: v.x + (v.w - newW) * mouseX,
          y: v.y + (v.h - newH) * mouseY,
          w: newW,
          h: newH,
        }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [applyViewBox])

  const onCanvasPointerDown = useCallback((e: React.PointerEvent) => {
    if ((e.target as Element).closest('circle')) return
    panRef.current = { x: e.clientX, y: e.clientY }
    draggedRef.current = false
    ;(e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId)
  }, [])

  const onCanvasPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const p = panRef.current
      if (!p) return
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const dx = ((e.clientX - p.x) / rect.width) * viewBoxRef.current.w
      const dy = ((e.clientY - p.y) / rect.height) * viewBoxRef.current.h
      if (Math.abs(e.clientX - p.x) > 2 || Math.abs(e.clientY - p.y) > 2) draggedRef.current = true
      panRef.current = { x: e.clientX, y: e.clientY }
      applyViewBox((v) => ({ ...v, x: v.x - dx, y: v.y - dy }))
    },
    [applyViewBox],
  )

  const onCanvasPointerUp = useCallback((e: React.PointerEvent) => {
    panRef.current = null
    const svg = e.currentTarget as SVGSVGElement
    if (svg.hasPointerCapture(e.pointerId)) svg.releasePointerCapture(e.pointerId)
  }, [])

  // 点击空白处取消选中（拖拽后不触发）
  const onCanvasClick = useCallback(() => {
    if (draggedRef.current) return
    if (selectedId) setSelectedId(null)
  }, [selectedId])

  const drillDown = useCallback(
    (cat: string) => {
      setActiveDomain(cat)
      setSelectedId(null)
      setTooltip(null)
      resetViewBox()
    },
    [resetViewBox],
  )

  const backToDomains = useCallback(() => {
    setActiveDomain(null)
    setSelectedId(null)
    setTooltip(null)
    resetViewBox()
  }, [resetViewBox])

  const handleNodeClick = useCallback((id: string) => {
    setSelectedId((prev) => (prev === id ? null : id))
  }, [])

  const pickSearchResult = useCallback((n: GNode) => {
    setActiveDomain(n.category)
    setSelectedId(n.id)
    setSearchOpen(false)
    setSearchInput(n.name)
    resetViewBox()
  }, [resetViewBox])

  const showTooltipAt = useCallback((e: React.MouseEvent, title: string, meta: string, five?: Record<string, number>) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, title, meta, five })
  }, [])

  const moveTooltip = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    setTooltip((prev) => (prev ? { ...prev, x: e.clientX - rect.left, y: e.clientY - rect.top } : prev))
  }, [])

  const domainLabel = useCallback((cat: string) => DOMAIN_NAMES[cat] ?? cat, [])
  const levelLabel = useCallback(
    (lv: string) => (LEVEL_I18N[lv] ? t(LEVEL_I18N[lv], lv) : lv),
    [t],
  )
  const tierLabel = useCallback(
    (tv: string) => (TIER_I18N[tv] ? t(TIER_I18N[tv], tv) : tv),
    [t],
  )
  const stateLabel = useCallback(
    (sv: string) => (STATE_I18N[sv] ? t(STATE_I18N[sv], sv) : sv),
    [t],
  )

  const dimLabels = useMemo<Record<string, string>>(
    () => ({
      proficiency: t('zenskill.skillGraph.dim.proficiency', '熟练度'),
      stability: t('zenskill.skillGraph.dim.stability', '稳定性'),
      satisfaction: t('zenskill.skillGraph.dim.satisfaction', '满意度'),
      responsiveness: t('zenskill.skillGraph.dim.responsiveness', '响应力'),
      memory: t('zenskill.skillGraph.dim.memory', '记忆力'),
    }),
    [t],
  )

  // 详情面板五维雷达数据（只取五维、钳制 0-100，排除 composite 等额外键）
  const radarScores = useMemo(() => {
    const out: Record<string, number> = {}
    const five = selectedNode?.five
    if (five) {
      for (const d of FIVE_DIMS) {
        const v = five[d]
        if (typeof v === 'number') out[d] = Math.min(100, Math.max(0, v))
      }
    }
    return out
  }, [selectedNode])

  const isLoading = growth.loading && !growth.data
  const hasError = growth.error && !growth.data

  const buildBridgePrompt = useCallback((data: GrowthData | null) => {
    const n = data?.skills?.length ?? 0
    const m = data?.edges?.length ?? 0
    if (n === 0) return ''
    return `技能图谱有 ${n} 个节点，${m} 条关系。帮我分析协同机会。`
  }, [])

  const tooltipFlip = tooltip && tooltip.x > (canvasRef.current?.clientWidth ?? 600) - 230

  // 域聚合视图的空态
  const allHidden = !activeDomain && domainPacked.length === 0 && nodes.length > 0

  const cx = VIEW_W / 2
  const cy = VIEW_H / 2

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.skillGraph.title', 'Skill Graph')}</div>
              <div className={ZS.subtitle}>{t('zenskill.skillGraph.subtitle', 'Skill relationships & stats')}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-1 min-w-[200px] max-w-[320px] justify-end">
            {/* 搜索 */}
            <div ref={searchWrapRef} className="relative flex-1 min-w-[160px]">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={t('zenskill.skillGraph.searchPlaceholder', 'Search skills...')}
                className={`${ZS.input} w-full pl-7`}
                autoComplete="off"
              />
              {searchOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 z-50 bg-popover border border-border/30 rounded-md shadow-modal-small max-h-60 overflow-y-auto">
                  {searchResults.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">
                      {t('zenskill.skillGraph.searchEmpty', 'No skills found, try a domain like lark')}
                    </div>
                  ) : (
                    searchResults.map((n) => (
                      <button
                        key={n.id}
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => pickSearchResult(n)}
                        className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-accent/10 text-left"
                      >
                        <span className="truncate">{n.name}</span>
                        <span className="shrink-0 text-[10px] px-1 py-0.5 rounded bg-accent/10 text-accent">
                          {domainLabel(n.category)}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
            {/* archived 开关（有 archived 节点才显示，默认隐藏，对齐磁盘版 B4） */}
            {archivedCount > 0 && (
              <button
                type="button"
                onClick={() => setShowArchived((v) => !v)}
                className={`${showArchived ? 'bg-accent text-accent-foreground border-accent' : ''} px-2 py-1 rounded border border-border/30 text-[11px] text-muted-foreground hover:border-accent shrink-0`}
              >
                {showArchived
                  ? t('zenskill.skillGraph.hideArchived', 'Hide archived ({{n}})', { n: archivedCount })
                  : t('zenskill.skillGraph.showArchived', 'Show archived ({{n}})', { n: archivedCount })}
              </button>
            )}
            <div className="flex items-center gap-2 shrink-0">
              {isLoading && (
                <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
                  <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
                </div>
              )}
              <PageToChatBridge
                pageName="Skill Graph"
                workspaceId={workspaceId}
                contextData={growth.data}
                buildPrompt={buildBridgePrompt}
              />
            </div>
          </div>
        </div>
      </div>

      {hasError && <div className={`${ZS.errorBanner} mx-5 mt-3`}>{growth.error}</div>}

      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="space-y-4">
          {/* 域 chips（显隐切换，按数量降序，对齐磁盘版） */}
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setHiddenDomains({})}
              className={`px-2.5 py-1 rounded-full border text-xs transition-colors ${
                Object.keys(hiddenDomains).length === 0
                  ? 'bg-accent text-accent-foreground border-accent'
                  : 'border-border/30 text-muted-foreground hover:border-accent'
              }`}
            >
              {t('zenskill.skillGraph.allDomains', 'All')}
            </button>
            {Object.keys(domainGroups)
              .sort((a, b) => domainStats[b].count - domainStats[a].count)
              .map((cat) => {
                const active = !hiddenDomains[cat]
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setHiddenDomains((h) => ({ ...h, [cat]: !h[cat] }))}
                    className={`px-2.5 py-1 rounded-full border text-xs transition-colors flex items-center gap-1 ${
                      active ? 'bg-accent text-accent-foreground border-accent' : 'border-border/30 text-muted-foreground hover:border-accent'
                    }`}
                  >
                    <span
                      className="h-2 w-2 rounded-full inline-block"
                      style={{ backgroundColor: DOMAIN_COLORS[cat] ?? '#BDC3C7' }}
                    />
                    {domainLabel(cat)}·{domainStats[cat].count}
                  </button>
                )
              })}
          </div>

          {/* 图例：治理（B4，有 tier 字段才显示）+ 五类关系色 */}
          <div className={`${ZS.card} flex flex-wrap items-center gap-x-4 gap-y-1.5`}>
            {hasTier && (
              <>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <span className="h-3 w-3 rounded-full border-[2.5px]" style={{ borderColor: GOLD }} />
                  {tierLabel('T0')}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <span className="h-3 w-3 rounded-full border-2" style={{ borderColor: EXPERT_STROKE }} />
                  {tierLabel('T1')}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground opacity-70">
                  <span className="h-3 w-3 rounded-full border-2 border-border" />
                  {tierLabel('T2')}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <span className="h-3 w-3 rounded-full border-[1.5px] border-dashed" style={{ borderColor: DIM_STROKE }} />
                  {stateLabel('dormant')}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground opacity-70">
                  <span className="h-3 w-3 rounded-full border-2 border-dotted border-muted-foreground" />
                  {stateLabel('archived')}
                </span>
                <span className="w-px h-3 bg-border/30" />
              </>
            )}
            {Object.entries(RELATION_COLORS).map(([relation, color]) => (
              <span key={relation} className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                <span className="capitalize">{relation}</span>
              </span>
            ))}
          </div>

          {/* 统计面板 */}
          <div className={ZS.card}>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <div className="text-lg font-semibold">{footerStats.nodeCount}</div>
                <div className="text-xs text-muted-foreground">{t('zenskill.skillGraph.nodes', 'Nodes')}</div>
              </div>
              <div>
                <div className="text-lg font-semibold">{footerStats.edgeCount}</div>
                <div className="text-xs text-muted-foreground">{t('zenskill.skillGraph.edges', 'Edges')}</div>
              </div>
              <div>
                <div className="text-lg font-semibold">{footerStats.avgScore}</div>
                <div className="text-xs text-muted-foreground">{t('zenskill.skillGraph.avgScore', 'Avg Score')}</div>
              </div>
            </div>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mt-2 pt-2 border-t border-border/30 text-xs">
              <span>
                <b className="text-base font-bold text-accent">{footerStats.masterCount}</b>
                <span className="text-[11px] text-muted-foreground ml-1">MASTER</span>
              </span>
              {footerStats.top && footerStats.top.usage > 0 && (
                <span>
                  <b className="text-base font-bold text-accent">{truncate(footerStats.top.name, 12)}</b>
                  <span className="text-[11px] text-muted-foreground ml-1">
                    {t('zenskill.skillGraph.topUsage', 'Top usage')} ({footerStats.top.usage})
                  </span>
                </span>
              )}
              <span>
                <b className="text-base font-bold text-accent">{footerStats.domainCount}</b>
                <span className="text-[11px] text-muted-foreground ml-1">
                  {t('zenskill.skillGraph.domains', 'Domains')}
                </span>
              </span>
              {footerStats.strongCount > 0 && (
                <span>
                  <b className="text-base font-bold text-accent">{footerStats.strongCount}</b>
                  <span className="text-[11px] text-muted-foreground ml-1">
                    {t('zenskill.skillGraph.strongEdges', 'Strong links')}
                  </span>
                </span>
              )}
              {growth.data?.source && (
                <span className="ml-auto text-[11px] text-muted-foreground bg-accent/10 rounded-full px-2.5 py-0.5">
                  {t('zenskill.skillGraph.dataSource', 'Source {{source}}', { source: growth.data.source })}
                </span>
              )}
              {footerStats.uncategorizedPct !== null && (
                <span className="text-[11px] text-muted-foreground bg-accent/10 rounded-full px-2.5 py-0.5">
                  {t('zenskill.skillGraph.uncategorized', '{{pct}}% skills pending classification', {
                    pct: footerStats.uncategorizedPct,
                  })}
                </span>
              )}
            </div>
          </div>

          {/* 画布 */}
          <div ref={canvasRef} className={`${ZS.card} relative`}>
            {/* 面包屑（域明细视图） */}
            {activeDomain && (
              <button
                type="button"
                onClick={backToDomains}
                className="absolute top-2 left-3 z-10 flex items-center gap-0.5 text-xs text-muted-foreground bg-card px-2 py-1 rounded border border-border/30 hover:text-accent"
              >
                <ChevronLeft className="h-3 w-3" />
                {t('zenskill.skillGraph.backToDomains', 'Back to domains')}
              </button>
            )}

            <ErrorBoundary componentName="SkillGraphCanvas">
              <svg
                ref={svgRef}
                viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
                className="w-full block touch-none select-none"
                style={{ height: 460, cursor: 'grab' }}
                preserveAspectRatio="xMidYMid meet"
                onPointerDown={onCanvasPointerDown}
                onPointerMove={onCanvasPointerMove}
                onPointerUp={onCanvasPointerUp}
                onPointerCancel={onCanvasPointerUp}
                onClick={onCanvasClick}
              >
                {/* 空态 */}
                {(nodes.length === 0 || allHidden || (activeDomain && detailPacked.length === 0)) && (
                  <g>
                    <text x={cx} y={cy - 6} textAnchor="middle" fontSize={14} className="fill-current text-muted-foreground">
                    {nodes.length === 0 ? (
                      t('zenskill.skillGraph.empty', 'No data')
                    ) : allHidden ? (
                      t(
                        'zenskill.skillGraph.allHidden',
                        'All domains hidden — click a chip above to restore',
                      )
                    ) : (
                      t('zenskill.skillGraph.emptyDomain', 'No skills in this domain')
                    )}
                  </text>
                </g>
                )}

                {/* 域聚合视图 */}
                {!activeDomain && (
                  <g>
                    {/* 域间弦 */}
                    {chords.map((c, i) => (
                      <path
                        key={i}
                        d={c.d}
                        fill="none"
                        stroke="#6b7280"
                        strokeWidth={c.width}
                        strokeOpacity={0.35}
                        pointerEvents="none"
                      />
                    ))}
                    {/* 域气泡 */}
                    {domainPacked.map((p) => {
                      const cat = p.data
                      const color = DOMAIN_COLORS[cat] ?? '#BDC3C7'
                      const stat = domainStats[cat]
                      return (
                        <g key={cat}>
                          <circle
                            cx={cx + p.x}
                            cy={cy + p.y}
                            r={p.r}
                            fill={color}
                            fillOpacity={0.2}
                            stroke={color}
                            strokeWidth={2}
                            strokeOpacity={0.6}
                            className="cursor-pointer"
                            onClick={(e) => {
                              e.stopPropagation()
                              drillDown(cat)
                            }}
                            onMouseEnter={(e) =>
                              showTooltipAt(
                                e,
                                domainLabel(cat),
                                `${stat.count} ${t('zenskill.skillGraph.nodes', 'Nodes')}` +
                                  (stat.masterCount > 0 ? ` | ${stat.masterCount} MASTER` : ''),
                              )
                            }
                            onMouseMove={moveTooltip}
                            onMouseLeave={() => setTooltip(null)}
                          />
                          <text
                            x={cx + p.x}
                            y={cy + p.y - 6}
                            textAnchor="middle"
                            fontSize={p.r > 50 ? 14 : 12}
                            fontWeight={600}
                            className="fill-current text-foreground pointer-events-none"
                          >
                            {truncate(domainLabel(cat), 12)}
                          </text>
                          <text
                            x={cx + p.x}
                            y={cy + p.y + 10}
                            textAnchor="middle"
                            fontSize={11}
                            className="fill-current text-muted-foreground pointer-events-none"
                          >
                            {stat.count}
                          </text>
                          {/* top-3 高频技能小圆 */}
                          {stat.top &&
                            domainGroups[cat]
                              .slice()
                              .sort((a, b) => b.usage - a.usage)
                              .slice(0, 3)
                              .map((skill, idx) => {
                                const angle = -Math.PI / 2 + idx * ((2 * Math.PI) / 3)
                                const skillR = Math.max(3, Math.min(6, skill.usage / 100))
                                return (
                                  <circle
                                    key={skill.id}
                                    cx={cx + p.x + p.r * 0.6 * Math.cos(angle)}
                                    cy={cy + p.y + p.r * 0.6 * Math.sin(angle)}
                                    r={skillR}
                                    fill={color}
                                    fillOpacity={0.8}
                                    pointerEvents="none"
                                  />
                                )
                              })}
                        </g>
                      )
                    })}
                  </g>
                )}

                {/* 域明细视图：节点 */}
                {activeDomain && (
                  <g>
                    {detailPacked.map((p) => {
                      const n = p.data
                      const heat = usageHeat(n.usage)
                      const isRelated = highlight?.related.has(n.id)
                      const isSelected = selectedId === n.id
                      const fillOpacity = selectedId ? (isRelated ? 0.9 : 0.15) : heat.opacity

                      // 描边优先级：dormant 虚线 > T0 金 > MASTER > EXPERT（对齐磁盘版 B4）
                      let stroke = 'none'
                      let strokeWidth = 0
                      let strokeDash = ''
                      if (n.state === 'dormant') {
                        stroke = DIM_STROKE
                        strokeWidth = 1.5
                        strokeDash = '4,3'
                      } else if (n.tier === 'T0') {
                        stroke = GOLD
                        strokeWidth = 2.5
                      } else if (n.level === 'MASTER') {
                        stroke = GOLD
                        strokeWidth = 2.5
                      } else if (n.level === 'EXPERT') {
                        stroke = EXPERT_STROKE
                        strokeWidth = 1.5
                      }

                      // 标签 LOD：usage > 0 或半径足够大才显示
                      const showLabel = n.usage > 0 || p.r > 20

                      const metaParts = [
                        levelLabel(n.level),
                        `${n.usage}`,
                        ...(n.tier || n.state ? [`${tierLabel(n.tier ?? 'T2')} · ${stateLabel(n.state ?? 'active')}`] : []),
                        ...(typeof n.quality === 'number' && n.quality >= 0 ? [`quality ${n.quality}`] : []),
                      ]

                      return (
                        <g key={n.id} opacity={n.tier === 'T2' ? 0.55 : 1}>
                          <circle
                            cx={cx + p.x}
                            cy={cy + p.y}
                            r={p.r}
                            fill={heat.fill}
                            fillOpacity={fillOpacity}
                            stroke={isSelected ? '#7c5cff' : stroke}
                            strokeWidth={isSelected ? Math.max(2, strokeWidth) : strokeWidth}
                            strokeDasharray={strokeDash}
                            className="cursor-pointer"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleNodeClick(n.id)
                            }}
                            onMouseEnter={(e) => showTooltipAt(e, n.name, metaParts.join(' | '), n.five)}
                            onMouseMove={moveTooltip}
                            onMouseLeave={() => setTooltip(null)}
                          />
                          {showLabel && (
                            <text
                              x={cx + p.x}
                              y={cy + p.y + 1}
                              textAnchor="middle"
                              dominantBaseline="middle"
                              fontSize={Math.min(11, p.r * 0.4).toFixed(0)}
                              fill="#fff"
                              pointerEvents="none"
                            >
                              {truncate(n.name, 10)}
                            </text>
                          )}
                        </g>
                      )
                    })}

                    {/* 选中高亮：top-8 强关联边 */}
                    {highlight?.paths.map((p, i) => (
                      <path
                        key={i}
                        d={p.d}
                        fill="none"
                        stroke={p.color}
                        strokeWidth={p.width}
                        strokeOpacity={0.7}
                        pointerEvents="none"
                      />
                    ))}
                  </g>
                )}
              </svg>
            </ErrorBoundary>

            {/* hover tooltip（跟随光标，对齐磁盘版） */}
            {tooltip && (
              <div
                className="absolute z-40 pointer-events-none bg-popover border border-border/30 rounded-md px-2.5 py-1.5 shadow-modal-small max-w-[220px]"
                style={{
                  left: tooltipFlip ? tooltip.x - 228 : tooltip.x + 12,
                  top: tooltip.y - 10,
                }}
              >
                <div className="text-xs font-semibold">{tooltip.title}</div>
                {tooltip.meta && <div className="text-[11px] text-muted-foreground">{tooltip.meta}</div>}
                {tooltip.five && (
                  <div className="mt-1 space-y-0.5">
                    {FIVE_DIMS.filter((d) => typeof tooltip.five?.[d] === 'number').map((dim) => (
                      <div key={dim} className="flex items-center gap-1">
                        <span className="text-[9px] text-muted-foreground w-12">{dimLabels[dim] ?? dim}</span>
                        <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                          <div
                            className="h-full bg-accent/70"
                            style={{ width: `${Math.min(100, tooltip.five![dim] ?? 0)}%` }}
                          />
                        </div>
                        <span className="text-[9px] text-muted-foreground w-5 text-right">
                          {Math.round(tooltip.five![dim] ?? 0)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 详情面板（右侧滑出，对齐磁盘版 detail-panel） */}
            {selectedNode && (
              <div className="absolute top-0 right-0 h-full w-80 max-w-full bg-card border-l border-border/30 shadow-panel-focused z-30 overflow-y-auto p-4">
                <button
                  type="button"
                  onClick={() => setSelectedId(null)}
                  className="absolute top-2 right-2 h-6 w-6 flex items-center justify-center rounded text-muted-foreground hover:bg-accent/10"
                  aria-label="close"
                >
                  <X className="h-4 w-4" />
                </button>

                <div className="text-base font-semibold pr-7 break-all">{selectedNode.name}</div>
                <div className="flex flex-wrap items-center gap-1 mt-1 text-xs">
                  <span
                    className="px-1.5 py-0.5 rounded text-[11px] font-medium"
                    style={{
                      color:
                        selectedNode.level === 'MASTER'
                          ? GOLD
                          : selectedNode.level === 'EXPERT'
                            ? EXPERT_STROKE
                            : (DOMAIN_COLORS[selectedNode.category] ?? '#BDC3C7'),
                      backgroundColor: `${
                        selectedNode.level === 'MASTER'
                          ? GOLD
                          : selectedNode.level === 'EXPERT'
                            ? EXPERT_STROKE
                            : (DOMAIN_COLORS[selectedNode.category] ?? '#BDC3C7')
                      }22`,
                    }}
                  >
                    {levelLabel(selectedNode.level)}
                  </span>
                  <span
                    className="px-1.5 py-0.5 rounded text-[11px]"
                    style={{
                      color: DOMAIN_COLORS[selectedNode.category] ?? '#BDC3C7',
                      backgroundColor: `${DOMAIN_COLORS[selectedNode.category] ?? '#BDC3C7'}22`,
                    }}
                  >
                    {domainLabel(selectedNode.category)}
                  </span>
                  <span className="text-muted-foreground">
                    {t('zenskill.skillGraph.uses', 'Usage count:')} {selectedNode.usage}
                  </span>
                </div>

                {/* 治理行（B4，字段防御性读取） */}
                {(selectedNode.tier || selectedNode.state || typeof selectedNode.quality === 'number') && (
                  <div className="flex flex-wrap items-center gap-1 mt-1.5 text-xs">
                    {selectedNode.tier && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[11px]"
                        style={{
                          color: selectedNode.tier === 'T0' ? GOLD : DIM_STROKE,
                          backgroundColor: `${selectedNode.tier === 'T0' ? GOLD : DIM_STROKE}22`,
                        }}
                      >
                        {tierLabel(selectedNode.tier)}
                      </span>
                    )}
                    {selectedNode.state && (
                      <span
                        className="px-1.5 py-0.5 rounded text-[11px]"
                        style={{
                          color:
                            selectedNode.state === 'dormant' ? '#d97706' : selectedNode.state === 'active' ? '#16a34a' : '#9ca3af',
                          backgroundColor: `${
                            selectedNode.state === 'dormant' ? '#d97706' : selectedNode.state === 'active' ? '#16a34a' : '#9ca3af'
                          }22`,
                        }}
                      >
                        {stateLabel(selectedNode.state)}
                      </span>
                    )}
                    {typeof selectedNode.quality === 'number' && selectedNode.quality >= 0 && (
                      <span className="px-1.5 py-0.5 rounded text-[11px] bg-accent/10 text-accent">
                        quality {selectedNode.quality}
                      </span>
                    )}
                  </div>
                )}
                {selectedNode.lastUsed && (
                  <div className="text-xs text-muted-foreground mt-1">
                    {t('zenskill.skillGraph.lastUsed', 'Last used {{when}}', { when: selectedNode.lastUsed })}
                  </div>
                )}
                {selectedNode.successRate != null && (
                  <div className="text-xs text-muted-foreground">
                    {t('zenskill.skillGraph.successRate', 'Success rate:')}{' '}
                    {Math.round(selectedNode.successRate * 100)}%
                  </div>
                )}

                {/* 五维能力雷达（有使用数据时展示，对齐磁盘版） */}
                {Object.keys(radarScores).length > 0 && (
                  <div className="mt-3">
                    <div className="text-[11px] text-muted-foreground tracking-wide mb-1.5">
                      {t('zenskill.skillGraph.fiveDims', 'Five Dimensions')}
                    </div>
                    <div className="flex justify-center">
                      <RadarChart scores={radarScores} size={170} labels={dimLabels} />
                    </div>
                  </div>
                )}

                {/* 强关联技能 top-8 */}
                {selectedId &&
                  highlight &&
                  highlight.strong.length > 0 &&
                  (() => {
                    const links = highlight.strong
                      .map((e) => nodeById.get(e.from === selectedId ? e.to : e.from))
                      .filter((n): n is GNode => !!n)
                    return (
                      <div className="mt-3">
                        <div className="text-[11px] text-muted-foreground tracking-wide mb-1.5">
                          {t('zenskill.skillGraph.strongLinks', 'Related skills ({{n}})', { n: links.length })}
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {links.map((n) => (
                            <button
                              key={n.id}
                              type="button"
                              onClick={() => handleNodeClick(n.id)}
                              className="text-xs px-2 py-0.5 rounded bg-accent/10 text-accent hover:bg-accent/20"
                            >
                              {truncate(n.name, 15)}
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  })()}

                {/* 弱共现计数 */}
                {selectedId && getWeakCount(selectedId, edges) > 0 && (
                  <div className="text-xs text-muted-foreground mt-2">
                    {t('zenskill.skillGraph.weakCo', '{{n}} weak links (collapsed)', {
                      n: getWeakCount(selectedId, edges),
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
