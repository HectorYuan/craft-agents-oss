interface ZenSkillSymbolProps {
  className?: string
}

/**
 * ZenSkill "Z-core" symbol - the small mark (derived from resources/icon.svg).
 * Uses accent color from theme (currentColor from className).
 *
 * Z 几何与应用图标定稿 T3 同源：三笔「斜切平行四边形」
 * （由 T3 位图逐行反解后映射到本标记原有的位置与尺寸，保持既有光学关系）。
 */
export function ZenSkillSymbol({ className }: ZenSkillSymbolProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="ZenSkill"
    >
      <g transform="translate(2.6 2.2)" fill="currentColor">
        <polygon points="3.88,2.2 18.47,2.2 17.59,5.73 4.63,5.73" />
        <polygon points="9.79,5.73 15.86,5.73 9.61,12.19 4.50,12.19" />
        <polygon points="4.04,12.19 17.96,12.19 19.20,15.80 2.20,15.80" />
      </g>
      <circle cx="20.6" cy="1.9" r="1.6" fill="currentColor" opacity="0.6" />
    </svg>
  )
}
