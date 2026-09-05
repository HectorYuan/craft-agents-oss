/**
 * ZenSkill Design Tokens — 统一的间距/字号/颜色常量
 *
 * 所有新组件使用 ZS.xxx 替代内联 Tailwind 值，确保视觉一致性。
 * 修改一处即可全局生效。
 */
export const ZS = {
  // 间距
  pagePad: 'px-5 pt-4 pb-3',
  contentPad: 'px-5 py-4',
  card: 'rounded border border-border/30 p-2',
  input: 'text-xs bg-muted/40 rounded px-2 py-1.5 outline-none focus:ring-1 focus:ring-accent/40 disabled:opacity-50',

  // 字号
  title: 'text-sm font-medium',
  subtitle: 'text-[11px] text-muted-foreground',
  body: 'text-xs',
  badge: 'text-[10px]',
  micro: 'text-[9px]',

  // 布局
  hoverRow: 'text-xs rounded px-2 py-1 hover:bg-muted/50 group',
  sectionHeader: 'flex items-center gap-1.5 mb-1.5',

  // Tab bar
  tabBar: 'flex gap-1 shrink-0 border-b border-border/30',
  tabActive: 'border-b-2 -mb-px border-accent text-accent',
  tabInactive: 'border-transparent text-muted-foreground hover:text-foreground',

  // 状态
  skeleton: 'h-4 rounded bg-muted/60 animate-pulse',
  errorBanner: 'text-xs text-destructive bg-destructive/5 rounded p-2',
  emptyState: 'text-xs text-muted-foreground italic',
} as const
