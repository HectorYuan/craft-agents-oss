interface ZenSkillAppIconProps {
  className?: string
  size?: number
}

/**
 * ZenSkillAppIcon — 品牌标记「容器版」（定稿 T3 同源同形）：
 * 深靛紫面板 + 纯白斜切平行四边形 Z + 靛紫闭合 orbit 环 + 压在环上的琥珀点。
 *
 * 几何由应用图标位图（resources/zenskill-logos/craft_app_icon.png，T3）逐行反解得到，
 * 24 栅格参数见 resources/zenskill-logos/zen-icon.svg（矢量源，同形）。
 * ⚠️ 与 zen-icon.svg / webui favicon.svg / site favicon.svg 必须保持一致 ——
 *    由父仓 scripts/check_brand_icon_sync.py 守卫。
 */
export function ZenSkillAppIcon({ className, size = 64 }: ZenSkillAppIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="ZenSkill"
    >
      <defs>
        <linearGradient id="zs-icon-bg" x1="0.92" y1="0.95" x2="0.14" y2="0.04">
          <stop offset="0" stopColor="#0F0E3C" />
          <stop offset="0.38" stopColor="#191A5E" />
          <stop offset="0.72" stopColor="#262994" />
          <stop offset="1" stopColor="#3B40B4" />
        </linearGradient>
        <radialGradient id="zs-icon-sweep" cx="0.13" cy="0.10" r="0.78">
          <stop offset="0" stopColor="#A3AAFF" stopOpacity="0.92" />
          <stop offset="0.22" stopColor="#8F97F9" stopOpacity="0.58" />
          <stop offset="0.48" stopColor="#6C74EC" stopOpacity="0.22" />
          <stop offset="0.76" stopColor="#454AC4" stopOpacity="0.05" />
          <stop offset="1" stopColor="#3B41B8" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="zs-icon-rim" x1="0.05" y1="0" x2="0.95" y2="1">
          <stop offset="0" stopColor="#9BA3FA" stopOpacity="0.80" />
          <stop offset="0.42" stopColor="#5A61DC" stopOpacity="0.16" />
          <stop offset="1" stopColor="#8F97F9" stopOpacity="0.58" />
        </linearGradient>
        <linearGradient id="zs-icon-z" x1="0.12" y1="0" x2="0.5" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.52" stopColor="#FBFCFF" />
          <stop offset="0.84" stopColor="#EDF1FF" />
          <stop offset="1" stopColor="#D9DFF8" />
        </linearGradient>
        <radialGradient id="zs-icon-dot" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFD066" stopOpacity="0.92" />
          <stop offset="0.42" stopColor="#FCA20C" stopOpacity="0.55" />
          <stop offset="0.72" stopColor="#F59E0B" stopOpacity="0.18" />
          <stop offset="1" stopColor="#F59E0B" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect x="1.83" y="1.83" width="20.37" height="20.08" rx="4.75" fill="url(#zs-icon-bg)" />
      <rect x="1.83" y="1.83" width="20.37" height="20.08" rx="4.75" fill="url(#zs-icon-sweep)" />
      <rect
        x="2.02"
        y="2.02"
        width="20"
        height="19.70"
        rx="4.58"
        fill="none"
        stroke="url(#zs-icon-rim)"
        strokeWidth="0.2"
      />
      <circle cx="12.01" cy="11.87" r="7.11" fill="none" stroke="#7E88F5" strokeWidth="0.62" />
      <g fill="url(#zs-icon-z)">
        <path d="M7.44 7.40 L16.63 7.40 L16.08 9.62 L7.91 9.62 Z" />
        <path d="M11.16 9.62 L14.99 9.62 L11.05 13.68 L7.83 13.68 Z" />
        <path d="M7.54 13.68 L16.31 13.68 L17.09 15.95 L6.38 15.95 Z" />
      </g>
      <circle cx="17.43" cy="6.95" r="1.34" fill="url(#zs-icon-dot)" />
      <circle cx="17.43" cy="6.95" r="0.79" fill="#F7A81A" />
    </svg>
  )
}
