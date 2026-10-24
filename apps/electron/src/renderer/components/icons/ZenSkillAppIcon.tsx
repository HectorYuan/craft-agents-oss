interface ZenSkillAppIconProps {
  className?: string
  size?: number
}

/**
 * ZenSkillAppIcon — 品牌标记「容器版」：靛紫渐变方块 + 冷白斜切 Z + 琥珀点 + 靛紫环。
 * 与应用图标（resources/zenskill-logos/craft_app_icon.png）同源同形；
 * 矢量源见 resources/zenskill-logos/zen-icon.svg。
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
        <linearGradient id="zs-icon-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#312E81" />
          <stop offset="1" stopColor="#4F46E5" />
        </linearGradient>
        <radialGradient id="zs-icon-dot" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0.5" stopColor="#F59E0B" stopOpacity="0.42" />
          <stop offset="1" stopColor="#F59E0B" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="24" height="24" rx="5.4" fill="url(#zs-icon-bg)" />
      <circle cx="12" cy="12" r="8.1" fill="none" stroke="#4338CA" strokeWidth="1.5" opacity="0.55" />
      <g transform="translate(2.48 6.55) scale(0.66)" fill="#E0E7FF">
        <polygon points="1.4,2.2 18.4,2.2 17.5,5.0 4.2,5.0" />
        <polygon points="16.6,5.0 18.4,2.2 5.4,15.8 2.2,15.8 8.6,5.0" />
        <polygon points="2.2,15.8 19.2,15.8 18.3,13.0 4.9,13.0" />
      </g>
      <circle cx="19.1" cy="5.4" r="3.5" fill="url(#zs-icon-dot)" />
      <circle cx="19.1" cy="5.4" r="1.9" fill="#F59E0B" />
    </svg>
  )
}
