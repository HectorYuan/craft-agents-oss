// ===== ZENSKILL VENDOR PROJECTION (generated) =====
// ⚠️ **这是投影，不是真相源。**
// 真源：`specs/design/generated/zenskill-ui/`（主仓，ardot 导出链）
// 改法：改 ardot → sync_ardot_components → gen_zenskill_components → 本脚本 --write
// 对账：`python3 scripts/sync_vendor_contracts.py --check`（CI 门禁 G-11）
// ===== END ZENSKILL VENDOR PROJECTION =====
/**
 * AgentCoverageMeter/智能体覆盖率
 *
 * ⚠️ 由 `scripts/gen_zenskill_components.py` 生成，**勿手改**。
 * 真源：ardot 组件 `14:64`（文件 739815654967152）
 *      → `specs/design/ardot_zenskill_components.json`
 * 改法：改 ardot → `scripts/sync_ardot_components.py --write` →
 *      `scripts/gen_zenskill_components.py --write` → 跑守卫。
 */
import type { CSSProperties } from 'react'

export interface AgentCoverageMeterProps {
  /** 消耗占比 0~1 —— 填充宽度由它表达，不烘像素；**宽度可自由覆写** */
  ratio: number
  caption?: string
  value?: string
  /** 读数默认由 ratio 派生；也可显式覆写 */
  footnote?: string
  className?: string
  style?: CSSProperties
}

export function AgentCoverageMeter({ ratio, caption, value, footnote, className, style }: AgentCoverageMeterProps) {
  const pct = Math.round(ratio * 100)
  const captionText = caption ?? "智能体替你承担"
  const valueText = value ?? "52 点"
  const footnoteText = footnote ?? `覆盖率 ${pct}% · 已计入审核成本`
  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '9 11 9 11', borderRadius: 8, background: 'color-mix(in oklab, var(--success) 5%, transparent)', width: 230, flex: '0 0 auto', ...style }}>
      <span style={{fontSize: 10, fontWeight: 400, color: 'var(--Semantic-text-secondary)', whiteSpace: 'nowrap', flex: '1 1 0%'}}>{captionText}</span>
      <span style={{fontSize: 18, fontWeight: 500, color: 'var(--success-text)', whiteSpace: 'nowrap', flex: '1 1 0%'}}>{valueText}</span>
      <div style={{position: 'relative', borderRadius: 999, background: 'color-mix(in oklab, var(--success) 8%, transparent)', overflow: 'hidden', width: '100%', height: 6}}>
        <div style={{position: 'absolute', borderRadius: 999, background: 'var(--Semantic-semantic-success)', top: '0', bottom: '0', left: '0', width: `${pct}%`, height: 6}}>
        
        </div>
      </div>
      <span style={{fontSize: 10, fontWeight: 400, color: 'var(--Semantic-text-secondary)', whiteSpace: 'nowrap', flex: '1 1 0%'}}>{footnoteText}</span>
    </div>
  )
}
