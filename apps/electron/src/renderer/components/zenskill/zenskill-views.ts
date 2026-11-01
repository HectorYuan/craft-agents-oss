/**
 * ZenSkill 视图注册表 —— 「视图归哪个域 / 以什么形态出现」的唯一真相源。
 *
 * ★ 为什么要有这一层
 *   旧形态：侧边栏一个扁平 `ZenSkill` 分组下 11 个平铺页
 *         ⇒ 用户的「我的东西散在 11 个地方」。
 *   新形态：三个对象域（会话 / 项目 / 技能）+ 三条横切线（额度 / 成长 / 认知）。
 *   ⇒ 「这个能力归哪个域」「它以面板还是页签还是独立页出现」是**载体选择**，
 *     不该写死在组件实现里 ⇒ 落到本文件的两个字段上。
 *
 * ★ 本模块是**纯数据 + 纯函数**
 *   - 不 import 任何 React / 页面组件 ⇒ 任何地方都能安全 import（无循环依赖、无副作用）
 *   - 组件与图标在 zenskill-registry.ts；两者按 slug 关联
 *   - 1:1 完整性由 `__tests__/view-registry.test.ts` 守住（防止漏登记 / 拼错 slug）
 *
 * 真相源文档：docs/spec_zenskill_domain_architecture_v1_20261031.md（§5 信息架构）
 */

/** 宿主对象域 —— 用户心智里的三个抽屉 + 今日读模型 + 运维面。 */
export type HostDomain = 'conversation' | 'project' | 'skill' | 'today' | 'settings'

/**
 * 视图形态：
 * - `panel` —— 宿主页内的一块（侧栏 / 卡片），**不进侧边栏**
 * - `tab`   —— 宿主页的一个页签，侧边栏点它 = 深链到宿主页锚点
 * - `page`  —— 一级导航里的独立页（当前 11 个页的现状）
 * - `quick` —— 不进侧边栏，但**可直达**（命令面板 / 快捷键 / 深链）
 */
export type ViewMode = 'panel' | 'tab' | 'page' | 'quick'

export interface ZenSkillViewSpec {
  /** 与 zenskill-registry.ts 的 slug 一一对应（由 view-registry.test.ts 守卫） */
  slug: string
  /** 归谁 —— 决定侧边栏分到哪一组 */
  hostDomain: HostDomain
  /** 以什么形态出现 —— 决定侧边栏是否列它、点击去哪 */
  mode: ViewMode
  /** 宿主页内的锚点（如 'project.actions'）；P1+ 随内容归位生效 */
  slot?: string
  /** 命令面板检索词（`mode: 'quick'` 时使用） */
  keywords?: string[]
  /** 归位后的目标路由（P1+ 生效）；未定义则仍走 `zenskill/<slug>` */
  targetRoute?: string
}

/**
 * 视图登记表。
 *
 * ★ `mode` 描述的是**当前真实呈现形态**，不是设计意图 ——
 *   它必须始终等于「代码现在怎么渲染它」，
 *   否则侧边栏/命令面板会按一个不存在的形态去找页面。
 *   ⇒ P1~P5 把某个视图真正搬进宿主域时，同步把它的 `mode` 翻成 'tab'/'panel'。
 */
export const ZENSKILL_VIEW_SPECS: ZenSkillViewSpec[] = [
  // ── 会话域（Conversation）：做事的地方 ─────────────────────────────
  { slug: 'insights', hostDomain: 'conversation', mode: 'page', slot: 'conversation.insights' },
  { slug: 'zenloop', hostDomain: 'conversation', mode: 'page', slot: 'conversation.loop' },

  // ── 项目域（Project）：推进的地方 ─────────────────────────────────
  { slug: 'gtd', hostDomain: 'project', mode: 'page', slot: 'project.actions' },

  // ── 技能域（Skill）：能力的地方 ───────────────────────────────────
  { slug: 'memory', hostDomain: 'skill', mode: 'page', slot: 'skill.knowledge' },
  { slug: 'profile', hostDomain: 'skill', mode: 'page', slot: 'skill.growth' },
  { slug: 'skill-graph', hostDomain: 'skill', mode: 'page', slot: 'skill.graph' },
  { slug: 'skill-market', hostDomain: 'skill', mode: 'page', slot: 'skill.market' },
  { slug: 'learning-path', hostDomain: 'skill', mode: 'page', slot: 'skill.learningPath' },
  { slug: 'cultivation', hostDomain: 'skill', mode: 'page', slot: 'skill.cultivation' },

  // ── 今日（Today）：跨域读模型 —— 唯一保留的 ZenSkill 顶级页 ────────
  { slug: 'overview', hostDomain: 'today', mode: 'page', slot: 'today.summary' },

  // ── 运维面（Settings）：通用域，不占产品导航 ───────────────────────
  { slug: 'collaboration', hostDomain: 'settings', mode: 'page', slot: 'settings.collaboration' },
]

/**
 * 侧边栏分组顺序 —— 按用户的行动逻辑排，不是字母序：
 * 做事 → 推进 → 学会 → 今天怎么看 → 运维。
 */
export const HOST_DOMAIN_ORDER: HostDomain[] = [
  'conversation',
  'project',
  'skill',
  'today',
  'settings',
]

/** 宿主域 → i18n 键（分组标题）。 */
export const HOST_DOMAIN_LABEL_KEYS: Record<HostDomain, string> = {
  conversation: 'zenskill.domain.conversation',
  project: 'zenskill.domain.project',
  skill: 'zenskill.domain.skill',
  today: 'zenskill.domain.today',
  settings: 'zenskill.domain.settings',
}

/** 按 slug 查视图规格。 */
export function resolveViewSpec(slug?: string): ZenSkillViewSpec | undefined {
  if (!slug) return undefined
  return ZENSKILL_VIEW_SPECS.find((v) => v.slug === slug)
}

/**
 * 该形态是否出现在侧边栏。
 * - `panel`：它在宿主页**内部** ⇒ 侧边栏不再重复列一份
 * - `quick`：低频能力 ⇒ 靠命令面板直达，不占导航位
 */
export function isSidebarVisibleMode(mode: ViewMode): boolean {
  return mode === 'page' || mode === 'tab'
}

/**
 * 按宿主域分组视图规格。
 *
 * @param specs     待分组的规格（默认全量）
 * @param onlyVisible 为 true 时只保留会出现在侧边栏的形态
 * @returns 按 HOST_DOMAIN_ORDER 排好序的分组；空组不产出
 */
export function groupViewsByHostDomain(
  specs: ZenSkillViewSpec[] = ZENSKILL_VIEW_SPECS,
  onlyVisible = false,
): Array<{ hostDomain: HostDomain; labelKey: string; views: ZenSkillViewSpec[] }> {
  const buckets = new Map<HostDomain, ZenSkillViewSpec[]>()
  for (const view of specs) {
    if (onlyVisible && !isSidebarVisibleMode(view.mode)) continue
    const list = buckets.get(view.hostDomain)
    if (list) list.push(view)
    else buckets.set(view.hostDomain, [view])
  }
  return HOST_DOMAIN_ORDER.filter((d) => (buckets.get(d)?.length ?? 0) > 0).map((hostDomain) => ({
    hostDomain,
    labelKey: HOST_DOMAIN_LABEL_KEYS[hostDomain],
    views: buckets.get(hostDomain)!,
  }))
}
