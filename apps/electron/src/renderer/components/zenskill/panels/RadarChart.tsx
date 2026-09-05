/**
 * RadarChart — SVG 五维雷达图
 *
 * 零依赖，~100 行。五边形网格 + 数据多边形 + 维度标签 + hover 高亮。
 * 只展示 5 个核心维度（排除 composite）。
 */
import React, { useState } from 'react'

export interface RadarChartProps {
  scores: Record<string, number> // 0-100 per dimension
  size?: number
  highlight?: string
  onHover?: (key: string | null) => void
}

const DIM_LABELS: Record<string, string> = {
  proficiency: '熟练度',
  stability: '稳定性',
  satisfaction: '满意度',
  responsiveness: '响应力',
  memory: '记忆力',
}

function pentagonPoints(cx: number, cy: number, r: number, n: number): string[] {
  const points: string[] = []
  for (let i = 0; i < n; i++) {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    points.push(`${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`)
  }
  return points
}

export function RadarChart({ scores, size = 200, highlight, onHover }: RadarChartProps) {
  const [internalHighlight, setInternalHighlight] = useState<string | null>(null)
  const activeHighlight = highlight ?? internalHighlight

  const cx = size / 2
  const cy = size / 2
  const r = size * 0.4
  const n = 5
  const dims = Object.keys(scores)

  if (dims.length === 0) return null

  // 网格顶点（5 层）
  const gridLayers = [0.2, 0.4, 0.6, 0.8, 1.0]

  // 数据多边形顶点
  const dataPoints = dims.map((dim, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    const val = (scores[dim] ?? 0) / 100
    return `${cx + r * val * Math.cos(angle)},${cy + r * val * Math.sin(angle)}`
  })

  // 标签位置（外移 15%）
  const labelPoints = dims.map((dim, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    const lr = r * 1.18
    return { dim, x: cx + lr * Math.cos(angle), y: cy + lr * Math.sin(angle) }
  })

  const handleMouseEnter = (dim: string) => {
    setInternalHighlight(dim)
    onHover?.(dim)
  }

  const handleMouseLeave = () => {
    setInternalHighlight(null)
    onHover?.(null)
  }

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* 网格 */}
      {gridLayers.map((layer) => (
        <polygon
          key={layer}
          points={pentagonPoints(cx, cy, r * layer, n).join(' ')}
          fill="none"
          stroke="currentColor"
          className="text-border/30"
          strokeWidth={activeHighlight ? 0.5 : 1}
        />
      ))}

      {/* 数据多边形 */}
      <polygon
        points={dataPoints.join(' ')}
        fill="currentColor"
        className="text-accent/20"
        stroke="currentColor"
        strokeWidth={1.5}
      />

      {/* 维度标签 */}
      {labelPoints.map(({ dim, x, y }) => (
        <text
          key={dim}
          x={x}
          y={y}
          textAnchor="middle"
          dominantBaseline="middle"
          className={`text-[9px] fill-current transition-colors ${
            activeHighlight === dim ? 'text-accent font-medium' : 'text-muted-foreground/70'
          }`}
          onMouseEnter={() => handleMouseEnter(dim)}
          onMouseLeave={handleMouseLeave}
        >
          {DIM_LABELS[dim] ?? dim}
        </text>
      ))}
    </svg>
  )
}
