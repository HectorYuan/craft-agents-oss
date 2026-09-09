/**
 * ZenSkillSkillGraph — Fork React 全页技能关系图
 *
 * 从 zenskill-skill-graph Pages 形态 fork 而来，用 React 组件重写。
 * 支持 hover tooltip、click 展开技能详情、五类关系色图例、统计信息。
 * 数据来源：growth_dashboard。
 */
import React, { useState, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Network } from 'lucide-react'
import { useMcpTool } from '@/hooks/zenskill/useMcpTool'
import { PageToChatBridge } from '../PageToChatBridge'
import { ZS } from '../panels/tokens'

const ZENSKILL_SOURCE_SLUG = 'zenskill'

interface SkillNode {
  skill_id: string
  level?: string
  usage_count?: number
  success_rate?: number
  scores?: Record<string, number>
}

interface SkillEdge {
  source: string
  target: string
  relation: string
}

interface GrowthData {
  skills?: SkillNode[]
  edges?: SkillEdge[]
}

interface ZenSkillSkillGraphProps {
  workspaceId?: string
}

const RELATION_COLORS: Record<string, string> = {
  prerequisite: '#3b82f6',
  complementary: '#22c55e',
  competing: '#ef4444',
  transfer: '#a855f7',
  co_occurrence: '#f59e0b',
}

const FIVE_DIMS = ['proficiency', 'stability', 'satisfaction', 'responsiveness', 'memory']

/** Ring layout: place nodes in a circle with center node */
function ringLayout(skills: SkillNode[], width: number, height: number): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const cx = width / 2
  const cy = height / 2
  const radius = Math.min(width, height) * 0.38

  if (skills.length === 0) return positions

  // Center node (highest usage_count or first)
  const sorted = [...skills].sort((a, b) => (b.usage_count ?? 0) - (a.usage_count ?? 0))
  const center = sorted[0]
  positions.set(center.skill_id, { x: cx, y: cy })

  // Ring nodes
  const ringSkills = sorted.slice(1)
  ringSkills.forEach((skill, i) => {
    const angle = (2 * Math.PI * i) / ringSkills.length - Math.PI / 2
    positions.set(skill.skill_id, {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    })
  })

  return positions
}

/** Get node color based on proficiency score */
function nodeColor(scores?: Record<string, number>): string {
  if (!scores) return 'hsl(var(--muted-foreground))'
  const p = scores.proficiency ?? 50
  if (p >= 80) return '#22c55e'
  if (p >= 60) return '#3b82f6'
  if (p >= 40) return '#f59e0b'
  return '#ef4444'
}

export function ZenSkillSkillGraph({ workspaceId }: ZenSkillSkillGraphProps) {
  const { t } = useTranslation()
  const growth = useMcpTool<GrowthData>(workspaceId, ZENSKILL_SOURCE_SLUG, 'growth_dashboard', {})

  const [hoveredSkill, setHoveredSkill] = useState<string | null>(null)
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null)

  const skills = growth.data?.skills ?? []
  const edges = growth.data?.edges ?? []

  const SVG_WIDTH = 400
  const SVG_HEIGHT = 320

  const positions = useMemo(() => ringLayout(skills, SVG_WIDTH, SVG_HEIGHT), [skills])

  const nodeMap = useMemo(() => {
    const map = new Map<string, SkillNode>()
    for (const s of skills) map.set(s.skill_id, s)
    return map
  }, [skills])

  const hoveredNode = hoveredSkill ? nodeMap.get(hoveredSkill) : null
  const selectedNode = selectedSkill ? nodeMap.get(selectedSkill) : null

  const handleNodeClick = useCallback((skillId: string) => {
    setSelectedSkill((prev) => prev === skillId ? null : skillId)
  }, [])

  const isLoading = growth.loading && !growth.data
  const hasError = growth.error && !growth.data

  // Day 1 PageToChatBridge prompt — graph stats as a synergy-analysis request
  const buildBridgePrompt = useCallback((data: { skills?: unknown[]; edges?: unknown[] }) => {
    const nodes = data.skills?.length ?? 0
    const edgeCount = data.edges?.length ?? 0
    if (nodes === 0) return ''
    return `技能图谱有 ${nodes} 个节点，${edgeCount} 条关系。帮我分析协同机会。`
  }, [])

  return (
    <div className="flex flex-col h-full">
      <div className={`${ZS.pagePad} border-b border-border/30 shrink-0`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-accent" />
            <div>
              <div className={ZS.title}>{t('zenskill.skillGraph.title', 'Skill Graph')}</div>
              <div className={ZS.subtitle}>{t('zenskill.skillGraph.subtitle', 'Skill relationships & stats')}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isLoading && (
              <div className="h-1.5 w-16 rounded bg-muted/60 overflow-hidden">
                <div className="h-full w-1/2 bg-accent/50 animate-pulse" />
              </div>
            )}
            <PageToChatBridge
              pageName="Skill Graph"
              workspaceId={workspaceId}
              contextData={{ skills: growth.data?.skills, edges: growth.data?.edges }}
              buildPrompt={buildBridgePrompt}
            />
          </div>
        </div>
      </div>

      {hasError && (
        <div className={`${ZS.errorBanner} mx-5 mt-3`}>{growth.error}</div>
      )}

      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="max-w-2xl space-y-4">
          {/* Stats */}
          <div className={`${ZS.card}`}>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div>
                <div className="text-lg font-semibold">{skills.length}</div>
                <div className="text-[9px] text-muted-foreground">{t('zenskill.skillGraph.nodes', 'Nodes')}</div>
              </div>
              <div>
                <div className="text-lg font-semibold">{edges.length}</div>
                <div className="text-[9px] text-muted-foreground">{t('zenskill.skillGraph.edges', 'Edges')}</div>
              </div>
              <div>
                <div className="text-lg font-semibold">
                  {skills.length > 0
                    ? Math.round(skills.reduce((sum, s) => {
                        const composite = s.scores
                          ? Object.values(s.scores).reduce((a, b) => a + b, 0) / Object.keys(s.scores).length
                          : 50
                        return sum + composite
                      }, 0) / skills.length)
                    : 0}
                </div>
                <div className="text-[9px] text-muted-foreground">{t('zenskill.skillGraph.avgScore', 'Avg Score')}</div>
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className={`${ZS.card}`}>
            <div className="flex flex-wrap gap-2">
              {Object.entries(RELATION_COLORS).map(([relation, color]) => (
                <div key={relation} className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-[9px] text-muted-foreground capitalize">{relation}</span>
                </div>
              ))}
            </div>
          </div>

          {/* SVG Graph */}
          <div className={`${ZS.card} relative`}>
            <svg width={SVG_WIDTH} height={SVG_HEIGHT} className="w-full">
              {/* Edges */}
              {edges.map((edge, i) => {
                const from = positions.get(edge.source)
                const to = positions.get(edge.target)
                if (!from || !to) return null
                const color = RELATION_COLORS[edge.relation] ?? '#666'
                return (
                  <line
                    key={i}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={color}
                    strokeWidth={1}
                    strokeOpacity={0.4}
                  />
                )
              })}

              {/* Nodes */}
              {skills.map((skill) => {
                const pos = positions.get(skill.skill_id)
                if (!pos) return null
                const isHovered = hoveredSkill === skill.skill_id
                const isSelected = selectedSkill === skill.skill_id
                const r = 12
                const color = nodeColor(skill.scores)

                return (
                  <g
                    key={skill.skill_id}
                    onMouseEnter={() => setHoveredSkill(skill.skill_id)}
                    onMouseLeave={() => setHoveredSkill(null)}
                    onClick={() => handleNodeClick(skill.skill_id)}
                    className="cursor-pointer"
                  >
                    <circle
                      cx={pos.x}
                      cy={pos.y}
                      r={r}
                      fill={color}
                      fillOpacity={isHovered || isSelected ? 0.9 : 0.6}
                      stroke={isSelected ? 'white' : 'none'}
                      strokeWidth={isSelected ? 2 : 0}
                    />
                    <text
                      x={pos.x}
                      y={pos.y + r + 10}
                      textAnchor="middle"
                      className="text-[8px] fill-current text-muted-foreground"
                    >
                      {skill.skill_id.length > 12 ? skill.skill_id.slice(0, 12) + '...' : skill.skill_id}
                    </text>
                  </g>
                )
              })}
            </svg>

            {/* Hover tooltip */}
            {hoveredNode && (
              <div className="absolute top-2 right-2 bg-popover border border-border/30 rounded p-2 shadow-modal-small pointer-events-none" style={{ minWidth: 140 }}>
                <div className="text-[10px] font-medium mb-1">{hoveredNode.skill_id}</div>
                {hoveredNode.level && (
                  <div className="text-[9px] text-muted-foreground">Level: {hoveredNode.level}</div>
                )}
                {hoveredNode.usage_count != null && (
                  <div className="text-[9px] text-muted-foreground">Uses: {hoveredNode.usage_count}</div>
                )}
                {hoveredNode.scores && (
                  <div className="mt-1 space-y-0.5">
                    {FIVE_DIMS.map((dim) => (
                      <div key={dim} className="flex items-center gap-1">
                        <span className="text-[8px] text-muted-foreground w-8">{dim.slice(0, 4)}</span>
                        <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                          <div className="h-full bg-accent/70" style={{ width: `${hoveredNode.scores![dim] ?? 0}%` }} />
                        </div>
                        <span className="text-[8px] text-muted-foreground w-4 text-right">{hoveredNode.scores![dim] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Selected skill detail */}
          {selectedNode && (
            <div className={`${ZS.card}`}>
              <div className={ZS.sectionHeader}>
                <Network className="h-3.5 w-3.5 text-muted-foreground" />
                <span className={ZS.body + ' font-medium text-muted-foreground'}>
                  {selectedNode.skill_id}
                </span>
                {selectedNode.level && (
                  <span className="text-[9px] px-1 py-0.5 rounded bg-accent/10 text-accent ml-auto">{selectedNode.level}</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                {FIVE_DIMS.map((dim) => (
                  <div key={dim} className="flex items-center gap-1">
                    <span className="text-muted-foreground w-20">{dim}</span>
                    <div className="flex-1 h-1 rounded bg-muted/60 overflow-hidden">
                      <div className="h-full bg-accent/70" style={{ width: `${selectedNode.scores?.[dim] ?? 0}%` }} />
                    </div>
                    <span className="text-muted-foreground w-4 text-right">{selectedNode.scores?.[dim] ?? 0}</span>
                  </div>
                ))}
              </div>
              {selectedNode.usage_count != null && (
                <div className="text-[10px] text-muted-foreground mt-2">
                  {t('zenskill.skillGraph.uses', 'Usage count:')} {selectedNode.usage_count}
                </div>
              )}
              {selectedNode.success_rate != null && (
                <div className="text-[10px] text-muted-foreground">
                  {t('zenskill.skillGraph.successRate', 'Success rate:')} {Math.round(selectedNode.success_rate * 100)}%
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
