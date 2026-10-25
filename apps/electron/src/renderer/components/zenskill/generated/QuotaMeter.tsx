// ===== ZENSKILL VENDOR PROJECTION (generated) =====
// ⚠️ **这是投影，不是真相源。**
// 真源：`specs/design/generated/zenskill-ui/`（主仓，ardot 导出链）
// 改法：改 ardot → sync_ardot_components → gen_zenskill_components → 本脚本 --write
// 对账：`python3 scripts/sync_vendor_contracts.py --check`（CI 门禁 G-11）
// ===== END ZENSKILL VENDOR PROJECTION =====
/**
 * QuotaMeter/额度条
 *
 * ⚠️ 由 `scripts/gen_zenskill_components.py` 生成，**勿手改**。
 * 真源：ardot 组件 `12:1`（文件 739815654967152）
 *      → `specs/design/ardot_zenskill_components.json`
 * 改法：改 ardot → `scripts/sync_ardot_components.py --write` →
 *      `scripts/gen_zenskill_components.py --write` → 跑守卫。
 */
import type { CSSProperties } from 'react'

export interface QuotaMeterProps {
  /** 消耗占比 0~1 —— 填充宽度由它表达，不烘像素；**宽度可自由覆写** */
  ratio: number
  /** 读数默认由 ratio 派生；也可显式覆写 */
  value?: string
  className?: string
  style?: CSSProperties
}

export function QuotaMeter({ ratio, value, className, style }: QuotaMeterProps) {
  const pct = Math.round(ratio * 100)
  const valueText = value ?? `${pct}%`
  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 7.5, background: 'var(--Semantic-bg-surface)', width: 240, flex: '0 0 auto', ...style }}>
      <div style={{position: 'relative', borderRadius: 999, background: 'color-mix(in oklab, var(--foreground) 5%, transparent)', overflow: 'hidden', flex: '1 1 0%', height: 6}}>
        <div style={{position: 'absolute', borderRadius: 999, background: 'var(--Semantic-semantic-success)', top: '0', bottom: '0', left: '0', width: `${pct}%`, height: 6}}>
        
        </div>
      </div>
      <span style={{fontSize: 11.25, fontWeight: 400, color: 'var(--Semantic-text-secondary)', textAlign: 'right', whiteSpace: 'nowrap', width: 30, flex: '0 0 auto'}}>{valueText}</span>
    </div>
  )
}
