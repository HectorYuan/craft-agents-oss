interface ZenSkillSymbolProps {
  className?: string
}

/**
 * ZenSkill "Z-core" symbol - the small mark (derived from resources/icon.svg).
 * Uses accent color from theme (currentColor from className).
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
        <polygon points="1.4,2.2 18.4,2.2 17.5,5.0 4.2,5.0" />
        <polygon points="16.6,5.0 18.4,2.2 5.4,15.8 2.2,15.8 8.6,5.0" />
        <polygon points="2.2,15.8 19.2,15.8 18.3,13.0 4.9,13.0" />
      </g>
      <circle cx="20.6" cy="1.9" r="1.6" fill="currentColor" opacity="0.6" />
    </svg>
  )
}
