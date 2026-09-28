/**
 * LevelUpCeremony — 全屏境界突破仪式 overlay (W4).
 *
 * 数据源: level_ceremony MCP 工具（action='latest' / 'celebrate'）。
 * 触发: ProgressionBar 检测到 level_up 类 progression 时通过
 *       context/CustomEvent 或 prop 传入 open。
 *
 * 独立组件——不依赖 ProgressionBar 内部状态，可从任意 zenskill 页面挂载。
 */
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sparkles, X } from 'lucide-react'
import { useMcpTool, extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG, type ZenSkillPageProps } from '../zenskill-registry'

interface CeremonyData {
  action?: string
  text?: string
  level?: string
  level_name?: string
  previous_level?: string
  skill_id?: string
  unlocked_abilities?: string[]
}

interface LevelUpCeremonyProps {
  workspaceId?: string
  /** 外部控制显示/隐藏（ProgressionBar 检测到升级时设 true） */
  open?: boolean
  onClose?: () => void
}

const LEVEL_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  MASTER: { bg: 'bg-amber-500/10', text: 'text-amber-500', border: 'border-amber-400/60' },
  EXPERT: { bg: 'bg-purple-500/10', text: 'text-purple-500', border: 'border-purple-400/60' },
  ADEPT: { bg: 'bg-blue-500/10', text: 'text-blue-500', border: 'border-blue-400/60' },
  APPRENTICE: { bg: 'bg-green-500/10', text: 'text-green-500', border: 'border-green-400/60' },
  NOVICE: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-400/40' },
}

export function LevelUpCeremony({ workspaceId, open, onClose }: LevelUpCeremonyProps) {
  const { t } = useTranslation()
  const [closing, setClosing] = useState(false)

  const ceremony = useMcpTool<CeremonyData>(
    workspaceId,
    ZENSKILL_SOURCE_SLUG,
    'level_ceremony',
    { action: 'latest' },
  )

  const handleClose = useCallback(() => {
    setClosing(true)
    setTimeout(() => {
      setClosing(false)
      onClose?.()
    }, 300)
  }, [onClose])

  // Escape 关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, handleClose])

  if (!open || closing) return null

  const data = ceremony.data
  const level = (data?.level ?? 'NOVICE').toUpperCase()
  const color = LEVEL_COLORS[level] ?? LEVEL_COLORS.NOVICE
  const text = data?.text ?? ''

  // 从 ASCII art text 中提取境界名
  const nameMatch = text.match(/【(.+?)】/)
  const levelName = data?.level_name ?? nameMatch?.[1] ?? level

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm transition-opacity duration-300 ${
        closing ? 'opacity-0' : 'opacity-100'
      }`}
      onClick={handleClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`relative mx-4 max-w-md w-full rounded-2xl border-2 ${color.border} ${color.bg} p-8 text-center shadow-2xl transform transition-all duration-500 ${
          closing ? 'scale-90 opacity-0' : 'scale-100 opacity-100'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 关闭按钮 */}
        <button
          onClick={handleClose}
          className="absolute right-3 top-3 rounded-full p-1 text-muted-foreground hover:bg-muted/50 transition-colors"
          aria-label="close"
        >
          <X className="h-4 w-4" />
        </button>

        {/* 星光动画 */}
        <div className="mb-4 flex justify-center gap-2">
          {[...Array(5)].map((_, i) => (
            <Sparkles
              key={i}
              className={`h-5 w-5 ${color.text}`}
              style={{
                animation: `pulse 1.5s ease-in-out ${i * 0.2}s infinite`,
                opacity: 0.6 + i * 0.1,
              }}
            />
          ))}
        </div>

        {/* 标题 */}
        <div className={`text-lg font-bold tracking-wide ${color.text}`}>
          {t('zenskill.ceremony.title', '境界突破')}
        </div>

        {/* 境界名 */}
        <div className={`mt-3 text-3xl font-extrabold tracking-widest ${color.text}`}>
          {levelName}
        </div>

        {/* 分隔线 */}
        <div className={`mx-auto mt-4 h-px w-3/4 bg-gradient-to-r from-transparent via-current to-transparent ${color.text} opacity-30`} />

        {/* 描述 */}
        {text && (
          <p className="mt-4 text-xs text-muted-foreground whitespace-pre-line line-clamp-3">
            {text.replace(/═|║|╔|╗|╚|╝|╠|╣/g, '').trim()}
          </p>
        )}

        {/* 解锁能力 */}
        {data?.unlocked_abilities && data.unlocked_abilities.length > 0 && (
          <div className="mt-4">
            <div className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">
              {t('zenskill.ceremony.unlocked', '解锁能力')}
            </div>
            <div className="mt-2 flex flex-wrap justify-center gap-1.5">
              {data.unlocked_abilities.slice(0, 5).map((ab, i) => (
                <span key={i} className="rounded-full bg-foreground/5 px-2 py-0.5 text-[10px] text-foreground/80">
                  {ab}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 底部提示 */}
        <div className="mt-6 text-[10px] text-muted-foreground/50">
          {t('zenskill.ceremony.pressEsc', '按 Esc 或点击空白处关闭')}
        </div>
      </div>
    </div>
  )
}
