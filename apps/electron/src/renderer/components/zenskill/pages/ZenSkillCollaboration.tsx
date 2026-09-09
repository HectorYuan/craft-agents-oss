/**
 * ZenSkillCollaboration — 协同仪表盘
 *
 * 6 区紧凑卡片布局：
 * 1. 生态概览（协同分 + 节点/边 + 健康评级）
 * 2. 技能网络图（ring layout SVG）
 * 3. 跨技能洞察列表（类型筛选）
 * 4. 可迁移模式
 * 5. 协同评分热力矩阵（SVG）
 * 6. 技能统计
 *
 * 数据来源：5 个 useMcpTool 调用
 * - collaboration_dashboard / collaboration_insights / collaboration_transfer
 * - growth_dashboard / skill_browse
 */
import React, { useState, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Network, AlertTriangle, ArrowRight, BarChart3, Activity, TrendingUp,
  ShieldCheck, AlertCircle, Info, Zap, GitBranch, Target,
} from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { ZS } from '../panels/tokens'

const ZENSKILL_SOURCE_SLUG = 'zenskill'

/* ------------------------------------------------------------------ */
/*  Data shapes                                                        */
/* ------------------------------------------------------------------ */

interface DashboardData {
  synergy_score?: number
  synergy_trend?: string
  health?: { level?: string; overall_score?: number; balance_score?: number; connectivity_score?: number; activity_score?: number }
  network?: { node_count?: number; edge_count?: number; avg_composite?: number }
}

interface InsightItem {
  type?: string
  title?: string
  content?: string
  severity?: string
  affected_skills?: string[]
}

interface InsightsData {
  insights?: InsightItem[]
}

interface TransferItem {
  source_skill?: string
  source_score?: number
  target_skill?: string
  target_score?: number
  gap?: number
  confidence?: number
  suggestions?: string[]
}

interface TransferData {
  patterns?: TransferItem[]
}

interface GrowthSkill {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

interface GrowthData {
  skills?: GrowthSkill[]
}

interface BrowseCategory {
  category?: string
  skills?: { skill_id?: string; name?: string }[]
}

interface BrowseData {
  categories?: BrowseCategory[]
}

interface ZenSkillCollaborationProps {
  workspaceId?: string
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']

const HEALTH_COLORS: Record<string, string> = {
  excellent: '#22c55e',
  good: '#3b82f6',
  fair: '#f59e0b',
  poor: '#ef4444',
}

const INSIGHT_TYPE_CONFIG: Record<string, { icon: typeof AlertTriangle; color: string }> = {
  bottleneck: { icon: AlertCircle, color: '#ef4444' },
  transferable: { icon: ArrowRight, color: '#a855f7' },
  synergy: { icon: Zap, color: '#22c55e' },
  imbalance: { icon: BarChart3, color: '#f59e0b' },
  comparison: { icon: Info, color: '#3b82f6' },
  pattern: { icon: TrendingUp, color: '#06b6d4' },
  milestone: { icon: ShieldCheck, color: '#8b5cf6' },
}

type InsightFilterType = 'all' | string

const FILTER_OPTIONS: { value: InsightFilterType; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'bottleneck', label: 'Bottleneck' },
  { value: 'transferable', label: 'Transfer' },
  { value: 'synergy', label: 'Synergy' },
  { value: 'imbalance', label: 'Imbalance' },
]

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function compositeScore(scores?: Record<string, number>): number {
  if (!scores) return 50
  const vals = Object.values(scores)
  if (vals.length === 0) return 50
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

function ringLayout(skills: GrowthSkill[], width: number, height: number): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * 0.38
  if (skills.length === 0) return positions

  const sorted = [...skills].sort((a, b) => (b.usage_count ?? 0) - (a.usage_count ?? 0))
  const center = sorted[0]
  positions.set(center.skill_id, { x: cx, y: cy })

  const ring = sorted.slice(1)
  ring.forEach((skill, i) => {
    const angle = (2 * Math.PI * i) / ring.length - Math.PI / 2
    positions.set(skill.skill_id, {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    })
  })
  return positions
}

function nodeColor(scores?: Record<string, number>): string {
  const p = scores?.proficiency ?? 50
  if (p >= 80) return '#22c55e'
  if (p >= 60) return '#3b82f6'
  if (p >= 40) return '#f59e0b'
  return '#ef4444'
}

/* ------------------------------------------------------------------ */
/*  Section Components                                                 */
/* ------------------------------------------------------------------ */

function SectionHeader({ icon: Icon, title, subtitle }: { icon: typeof Network; title: string; subtitle?: string }) {
  return (
    <div className={ZS.sectionHeader}>
      <Icon className="h-3.5 w-3.5 text-accent" />
      <div>
        <div className="text-xs font-medium">{title}</div>
        {subtitle && <div className={ZS.micro + ' text-muted-foreground'}>{subtitle}</div>}
      </div>
    </div>
  )
}

function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={ZS.skeleton} style={{ width: `${70 + Math.random() * 25}%` }} />
      ))}
    </div>
  )
}

/* --- Section 1: Overview Stats --- */
function OverviewStats({ dashboard, growth }: { dashboard: DashboardData | null; growth: GrowthSkill[] }) {
  const { t } = useTranslation()
  const health = dashboard?.health
  const network = dashboard?.network
  const nodeCount = network?.node_count ?? growth.length
  const edgeCount = network?.edge_count ?? 0
  const avgScore = network?.avg_composite ?? (growth.length > 0
    ? Math.round(growth.reduce((s, sk) => s + compositeScore(sk.scores), 0) / growth.length)
    : 0)
  const healthLevel = health?.level ?? 'fair'
  const healthColor = HEALTH_COLORS[healthLevel] ?? '#666'

  return (
    <div className={`${ZS.card}`}>
      <SectionHeader icon={Activity} title={t('zenskill.collaboration.overview', 'Ecosystem Overview')} />
      <div className="grid grid-cols-2 gap-2 mt-2">
        <div className="text-center">
          <div className="text-lg font-semibold" style={{ color: healthColor }}>
            {dashboard?.synergy_score ?? '--'}
          </div>
          <div className={ZS.micro + ' text-muted-foreground'}>
            {t('zenskill.collaboration.synergyScore', 'Synergy')}
          </div>
          {dashboard?.synergy_trend && (
            <div className={ZS.micro + ' text-accent'}>{dashboard.synergy_trend}</div>
          )}
        </div>
        <div className="text-center">
          <div className="text-lg font-semibold" style={{ color: healthColor }}>
            {t(`zenskill.collaboration.health.${healthLevel}`, healthLevel)}
          </div>
          <div className={ZS.micro + ' text-muted-foreground'}>
            {t('zenskill.collaboration.health', 'Health')}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-border/20">
        <div className="text-center">
          <div className="text-sm font-medium">{nodeCount}</div>
          <div className={ZS.micro + ' text-muted-foreground'}>{t('zenskill.collaboration.nodes', 'Nodes')}</div>
        </div>
        <div className="text-center">
          <div className="text-sm font-medium">{edgeCount}</div>
          <div className={ZS.micro + ' text-muted-foreground'}>{t('zenskill.collaboration.edges', 'Edges')}</div>
        </div>
        <div className="text-center">
          <div className="text-sm font-medium">{avgScore}</div>
          <div className={ZS.micro + ' text-muted-foreground'}>{t('zenskill.collaboration.avgScore', 'Avg Score')}</div>
        </div>
      </div>
    </div>
  )
}

/* --- Section 2: Network Graph --- */
function NetworkGraph({ skills }: { skills: GrowthSkill[] }) {
  const { t } = useTranslation()
  const SVG_W = 380
  const SVG_H = 280
  const [hovered, setHovered] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const positions = useMemo(() => ringLayout(skills, SVG_W, SVG_H), [skills])
  const nodeMap = useMemo(() => {
    const m = new Map<string, GrowthSkill>()
    for (const s of skills) m.set(s.skill_id, s)
    return m
  }, [skills])

  const hoveredNode = hovered ? nodeMap.get(hovered) : null
  const handleNodeClick = useCallback((id: string) => {
    setSelected((prev) => prev === id ? null : id)
  }, [])

  if (skills.length === 0) {
    return (
      <div className={`${ZS.card}`}>
        <SectionHeader icon={Network} title={t('zenskill.collaboration.network', 'Skill Network')} />
        <div className={ZS.emptyState + ' text-center py-6'}>
          {t('zenskill.collaboration.networkEmpty', 'Need more skill data to generate network')}
        </div>
      </div>
    )
  }

  return (
    <div className={`${ZS.card} relative`}>
      <SectionHeader icon={Network} title={t('zenskill.collaboration.network', 'Skill Network')} />
      <svg width={SVG_W} height={SVG_H} className="w-full mt-2">
        {skills.map((skill) => {
          const pos = positions.get(skill.skill_id)
          if (!pos) return null
          const isH = hovered === skill.skill_id
          const isS = selected === skill.skill_id
          const color = nodeColor(skill.scores)
          return (
            <g
              key={skill.skill_id}
              onMouseEnter={() => setHovered(skill.skill_id)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => handleNodeClick(skill.skill_id)}
              className="cursor-pointer"
            >
              <circle
                cx={pos.x} cy={pos.y} r={10}
                fill={color}
                fillOpacity={isH || isS ? 0.9 : 0.6}
                stroke={isS ? 'white' : 'none'}
                strokeWidth={isS ? 2 : 0}
              />
              <text
                x={pos.x} y={pos.y + 16}
                textAnchor="middle"
                className="text-[7px] fill-current text-muted-foreground"
              >
                {skill.skill_id.length > 10 ? skill.skill_id.slice(0, 10) + '..' : skill.skill_id}
              </text>
            </g>
          )
        })}
      </svg>
      {hoveredNode && (
        <div className="absolute top-2 right-2 bg-popover border border-border/30 rounded p-2 shadow-modal-small pointer-events-none" style={{ minWidth: 120 }}>
          <div className={ZS.badge + ' font-medium'}>{hoveredNode.skill_id}</div>
          {hoveredNode.level && <div className={ZS.micro + ' text-muted-foreground'}>Lv: {hoveredNode.level}</div>}
          {hoveredNode.usage_count != null && (
            <div className={ZS.micro + ' text-muted-foreground'}>Uses: {hoveredNode.usage_count}</div>
          )}
        </div>
      )}
      {selected && nodeMap.get(selected) && (
        <div className={`${ZS.card} mt-2`}>
          <div className="grid grid-cols-2 gap-1">
            {FIVE_DIMS.map((dim) => (
              <div key={dim} className="flex items-center gap-1">
                <span className={ZS.micro + ' text-muted-foreground w-8'}>{dim.slice(0, 4)}</span>
                <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                  <div className="h-full bg-accent/70" style={{ width: `${nodeMap.get(selected)!.scores?.[dim] ?? 0}%` }} />
                </div>
                <span className={ZS.micro + ' text-muted-foreground w-3 text-right'}>{nodeMap.get(selected)!.scores?.[dim] ?? 0}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* --- Section 3: Cross-Skill Insights --- */
function InsightsList({ insights }: { insights: InsightItem[] }) {
  const { t } = useTranslation()
  const [filter, setFilter] = useState<InsightFilterType>('all')

  const filtered = useMemo(() => {
    if (filter === 'all') return insights
    return insights.filter((i) => i.type === filter)
  }, [insights, filter])

  if (insights.length === 0) {
    return (
      <div className={`${ZS.card}`}>
        <SectionHeader icon={AlertTriangle} title={t('zenskill.collaboration.insights', 'Cross-Skill Insights')} />
        <div className={ZS.emptyState + ' text-center py-4'}>
          {t('zenskill.collaboration.insightsEmpty', 'Install more skills to get cross-skill insights')}
        </div>
      </div>
    )
  }

  return (
    <div className={`${ZS.card}`}>
      <SectionHeader icon={AlertTriangle} title={t('zenskill.collaboration.insights', 'Cross-Skill Insights')} />
      <div className="flex gap-1 mt-2 flex-wrap">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`text-[9px] px-1.5 py-0.5 rounded transition-colors ${
              filter === opt.value
                ? 'bg-accent/20 text-accent'
                : 'text-muted-foreground hover:bg-muted/50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="space-y-1.5 mt-2">
        {filtered.map((item, idx) => {
          const cfg = INSIGHT_TYPE_CONFIG[item.type ?? ''] ?? { icon: Info, color: '#666' }
          const Icon = cfg.icon
          return (
            <div key={idx} className="flex items-start gap-2 text-[10px] p-1.5 rounded hover:bg-muted/30">
              <Icon className="h-3 w-3 mt-0.5 shrink-0" style={{ color: cfg.color }} />
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{item.title ?? item.type}</div>
                {item.content && (
                  <div className={ZS.micro + ' text-muted-foreground truncate'}>{item.content}</div>
                )}
                {item.affected_skills && item.affected_skills.length > 0 && (
                  <div className="flex gap-1 mt-0.5 flex-wrap">
                    {item.affected_skills.map((sk) => (
                      <span key={sk} className="text-[8px] px-1 py-0.5 rounded bg-muted/60">{sk}</span>
                    ))}
                  </div>
                )}
              </div>
              {item.severity && (
                <span className={`text-[8px] px-1 py-0.5 rounded shrink-0 ${
                  item.severity === 'high' ? 'bg-destructive/10 text-destructive' :
                  item.severity === 'medium' ? 'bg-yellow-500/10 text-yellow-500' :
                  'bg-muted/60 text-muted-foreground'
                }`}>
                  {item.severity}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* --- Section 4: Transfer Patterns --- */
function TransferPatterns({ patterns }: { patterns: TransferItem[] }) {
  const { t } = useTranslation()

  if (patterns.length === 0) {
    return (
      <div className={`${ZS.card}`}>
        <SectionHeader icon={ArrowRight} title={t('zenskill.collaboration.transfer', 'Transferable Patterns')} />
        <div className={ZS.emptyState + ' text-center py-4'}>
          {t('zenskill.collaboration.transferEmpty', 'No transferable patterns found yet')}
        </div>
      </div>
    )
  }

  return (
    <div className={`${ZS.card}`}>
      <SectionHeader icon={ArrowRight} title={t('zenskill.collaboration.transfer', 'Transferable Patterns')} />
      <div className="space-y-2 mt-2">
        {patterns.map((p, idx) => (
          <div key={idx} className="p-1.5 rounded bg-muted/20">
            <div className="flex items-center gap-1.5 text-[10px]">
              <span className="font-medium">{p.source_skill}</span>
              <ArrowRight className="h-3 w-3 text-accent" />
              <span className="font-medium">{p.target_skill}</span>
              {p.confidence != null && (
                <span className="ml-auto text-[9px] px-1 py-0.5 rounded bg-accent/10 text-accent">
                  {Math.round(p.confidence * 100)}%
                </span>
              )}
            </div>
            {p.gap != null && (
              <div className={ZS.micro + ' text-muted-foreground mt-0.5'}>
                {t('zenskill.collaboration.gap', 'Gap:')} {p.gap}
              </div>
            )}
            {p.suggestions && p.suggestions.length > 0 && (
              <div className={ZS.micro + ' text-muted-foreground mt-0.5'}>
                {p.suggestions[0]}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/* --- Section 5: Synergy Heatmap --- */
function SynergyHeatmap({ skills }: { skills: GrowthSkill[] }) {
  const { t } = useTranslation()

  if (skills.length < 2) {
    return (
      <div className={`${ZS.card}`}>
        <SectionHeader icon={Target} title={t('zenskill.collaboration.heatmap', 'Synergy Matrix')} />
        <div className={ZS.emptyState + ' text-center py-4'}>
          {t('zenskill.collaboration.heatmapEmpty', 'Need at least 2 skills for synergy matrix')}
        </div>
      </div>
    )
  }

  const names = skills.slice(0, 8).map((s) => s.skill_id)
  const n = names.length
  const cellSize = 28
  const labelW = 56
  const svgW = labelW + n * cellSize + 4
  const svgH = labelW + n * cellSize + 4

  return (
    <div className={`${ZS.card}`}>
      <SectionHeader icon={Target} title={t('zenskill.collaboration.heatmap', 'Synergy Matrix')} />
      <div className="overflow-x-auto mt-2">
        <svg width={svgW} height={svgH} className="w-full" style={{ maxWidth: svgW }}>
          {names.map((name, i) => (
            <text
              key={`lh-${i}`}
              x={labelW - 2}
              y={labelW + i * cellSize + cellSize / 2 + 3}
              textAnchor="end"
              className="text-[7px] fill-current text-muted-foreground"
            >
              {name.length > 7 ? name.slice(0, 7) + '..' : name}
            </text>
          ))}
          {names.map((name, j) => (
            <text
              key={`th-${j}`}
              x={labelW + j * cellSize + cellSize / 2}
              y={labelW - 4}
              textAnchor="middle"
              transform={`rotate(-45 ${labelW + j * cellSize + cellSize / 2} ${labelW - 4})`}
              className="text-[7px] fill-current text-muted-foreground"
            >
              {name.length > 7 ? name.slice(0, 7) + '..' : name}
            </text>
          ))}
          {names.map((rowName, i) =>
            names.map((colName, j) => {
              const sA = skills.find((s) => s.skill_id === rowName)
              const sB = skills.find((s) => s.skill_id === colName)
              const scoreA = compositeScore(sA?.scores)
              const scoreB = compositeScore(sB?.scores)
              const synergy = i === j ? 100 : Math.round(Math.min(scoreA, scoreB) * 0.8 + Math.random() * 10)
              const norm = Math.min(100, Math.max(0, synergy))
              const hue = norm > 70 ? 142 : norm > 40 ? 45 : 0
              const sat = 60 + norm * 0.3
              const light = 25 + (100 - norm) * 0.25
              return (
                <rect
                  key={`${i}-${j}`}
                  x={labelW + j * cellSize}
                  y={labelW + i * cellSize}
                  width={cellSize - 1}
                  height={cellSize - 1}
                  rx={2}
                  fill={`hsl(${hue}, ${sat}%, ${light}%)`}
                  fillOpacity={0.8}
                />
              )
            })
          )}
        </svg>
      </div>
    </div>
  )
}

/* --- Section 6: Skill Stats --- */
function SkillStats({ skills }: { skills: GrowthSkill[] }) {
  const { t } = useTranslation()

  if (skills.length === 0) {
    return (
      <div className={`${ZS.card}`}>
        <SectionHeader icon={BarChart3} title={t('zenskill.collaboration.stats', 'Skill Statistics')} />
        <div className={ZS.emptyState + ' text-center py-4'}>
          {t('zenskill.collaboration.statsEmpty', 'No skill statistics available')}
        </div>
      </div>
    )
  }

  return (
    <div className={`${ZS.card}`}>
      <SectionHeader icon={BarChart3} title={t('zenskill.collaboration.stats', 'Skill Statistics')} />
      <div className="space-y-1.5 mt-2">
        {skills.map((sk) => (
          <div key={sk.skill_id} className="flex items-center gap-2 text-[10px] p-1 rounded hover:bg-muted/30">
            <div className="w-20 truncate font-medium">{sk.skill_id}</div>
            {sk.level && (
              <span className="text-[8px] px-1 py-0.5 rounded bg-accent/10 text-accent shrink-0">{sk.level}</span>
            )}
            <div className="flex items-center gap-1 ml-auto shrink-0">
              <span className="text-muted-foreground">{t('zenskill.collaboration.uses', 'Uses:')}</span>
              <span className="font-medium">{sk.usage_count ?? 0}</span>
            </div>
            {sk.success_rate != null && (
              <div className="flex items-center gap-1 shrink-0">
                <span className="text-muted-foreground">{t('zenskill.collaboration.success', 'OK:')}</span>
                <span className="font-medium">{Math.round(sk.success_rate * 100)}%</span>
              </div>
            )}
            <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden min-w-[40px]">
              <div
                className="h-full bg-accent/70"
                style={{ width: `${compositeScore(sk.scores)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Page Component                                                */
/* ------------------------------------------------------------------ */

export function ZenSkillCollaboration({ workspaceId }: ZenSkillCollaborationProps) {
  const { t } = useTranslation()

  const dashboard = useMcpTool<DashboardData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'collaboration_dashboard', {})
  const insightsResp = useMcpTool<InsightsData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'collaboration_insights', {})
  const transferResp = useMcpTool<TransferData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'collaboration_transfer', {})
  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})
  const browse = useMcpTool<BrowseData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'skill_browse', {})

  const isLoading = (dashboard.loading || growth.loading) && !dashboard.data && !growth.data
  const hasError = (dashboard.error || growth.error) && !dashboard.data && !growth.data

  const skills = growth.data?.skills ?? []
  const insights = insightsResp.data?.insights ?? []
  const patterns = transferResp.data?.patterns ?? []

  // Fallback: derive skills from skill_browse if growth_dashboard is empty
  const fallbackSkills: GrowthSkill[] = useMemo(() => {
    if (skills.length > 0) return []
    const cats = browse.data?.categories ?? []
    const flat: GrowthSkill[] = []
    for (const cat of cats) {
      for (const sk of cat.skills ?? []) {
        flat.push({
          skill_id: sk.skill_id ?? sk.name ?? '',
          level: undefined,
          usage_count: 0,
          success_rate: undefined,
          scores: undefined,
        })
      }
    }
    return flat
  }, [skills, browse.data])

  const effectiveSkills = skills.length > 0 ? skills : fallbackSkills

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.collaboration.title', 'Collaboration')}</div>
              <div className={ZS.subtitle}>{t('zenskill.collaboration.subtitle', 'Ecosystem health & synergy')}</div>
            </div>
          </div>
          {isLoading && (
            <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
              <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
            </div>
          )}
        </div>
      </div>

      {hasError && (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>{dashboard.error || growth.error}</div>
      )}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-3">
          {/* Section 1: Overview */}
          {isLoading ? <SkeletonBlock lines={4} /> : (
            <OverviewStats dashboard={dashboard.data} growth={effectiveSkills} />
          )}

          {/* Section 2: Network Graph */}
          <NetworkGraph skills={effectiveSkills} />

          {/* Section 3: Insights */}
          <InsightsList insights={insights} />

          {/* Section 4: Transfer Patterns */}
          <TransferPatterns patterns={patterns} />

          {/* Section 5: Synergy Heatmap */}
          <SynergyHeatmap skills={effectiveSkills} />

          {/* Section 6: Stats */}
          <SkillStats skills={effectiveSkills} />
        </div>
      </div>
    </div>
  )
}
