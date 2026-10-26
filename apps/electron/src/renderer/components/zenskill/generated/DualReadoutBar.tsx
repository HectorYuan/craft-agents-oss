// ===== ZENSKILL VENDOR PROJECTION (generated) =====
// ⚠️ **这是投影，不是真相源。**
// 真源：`specs/design/generated/zenskill-ui/`（主仓，ardot 导出链）
// 改法：改 ardot → sync_ardot_components → gen_zenskill_components → 本脚本 --write
// 对账：`python3 scripts/sync_vendor_contracts.py --check`（CI 门禁 G-11）
// ===== END ZENSKILL VENDOR PROJECTION =====
/**
 * DualReadoutBar/双读数分账条
 *
 *
 * ★ 两段宽度是**设计分栏**（来自 ardot 的固定像素），**不是占比** ——
 *   两种单位不可相加，因此不把宽度暴露成比例 prop。
 * ⚠️ 由 `scripts/gen_zenskill_components.py` 生成，**勿手改**。
 * 真源：ardot 组件 `14:133`（文件 739815654967152）
 *      → `specs/design/ardot_zenskill_components.json`
 * 改法：改 ardot → `scripts/sync_ardot_components.py --write` →
 *      `scripts/gen_zenskill_components.py --write` → 跑守卫。
 */
import type { CSSProperties } from 'react'

export interface DualReadoutBarProps {
  taskLabel?: string
  attentionLabel?: string
  footnote?: string
  className?: string
  style?: CSSProperties
}

export function DualReadoutBar({ taskLabel, attentionLabel, footnote, className, style }: DualReadoutBarProps) {
  const taskLabelText = taskLabel ?? "任务能量（点）"
  const attentionLabelText = attentionLabel ?? "注意力预算（分钟）"
  const footnoteText = footnote ?? "两种单位不可相加：能量是燃料，注意力是闸门"
  return (
    <div className={className} style={{ display: 'flex', flexDirection: 'column', gap: 6, background: 'var(--Semantic-bg-surface)', width: 240, flex: '0 0 auto', ...style }}>
      <div style={{position: 'relative', borderRadius: 6, background: 'color-mix(in oklab, var(--accent) 5%, transparent)', overflow: 'hidden', width: '100%', height: 24}}>
        <div style={{display: 'flex', flexDirection: 'row', alignItems: 'center', borderRadius: 6, background: 'var(--Semantic-accent-primary)', width: '51.6667%', flex: '0 0 auto', height: 24}}>
          <span style={{fontSize: 10, fontWeight: 500, color: 'var(--Semantic-text-on-brand)', whiteSpace: 'nowrap'}}>{taskLabelText}</span>
        </div>
        <div style={{display: 'flex', flexDirection: 'row', alignItems: 'center', borderRadius: 6, background: 'color-mix(in oklab, var(--accent) 8%, transparent)', width: '48.3333%', flex: '0 0 auto', height: 24}}>
          <span style={{fontSize: 10, fontWeight: 500, color: 'var(--Semantic-text-primary)', whiteSpace: 'nowrap'}}>{attentionLabelText}</span>
        </div>
      </div>
      <span style={{fontSize: 10, fontWeight: 400, color: 'var(--Semantic-text-muted)', whiteSpace: 'nowrap', flex: '1 1 0%'}}>{footnoteText}</span>
    </div>
  )
}
