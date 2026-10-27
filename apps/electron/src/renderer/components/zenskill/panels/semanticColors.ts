/**
 * semanticColors.ts — ZenSkill **语义色集中表**（第二十一批 D 段）
 *
 * ★ 为什么要有这张表
 * ------------------
 * 实测（第二十一批 A 段）：`components/zenskill/` 里散着 **34 处 Tailwind 默认色**
 * （purple 16 / amber 15 / gray 3）+ **74 处字面量 hex**。逐项归类后发现：
 *
 *   · ★ **purple 被 4 类完全不同的语义共用** —— 分类色（建议类型）/ ZenLoop 阶段色 /
 *     **境界色阶**（EXPERT 档）/ **记忆层级色**（L3）⇒ ★ 「purple → 某个语义变量」的
 *     **机械替换必然改错语义**（A 段实证）。
 *   · ★ 而这些色的**真正家当早就存在** —— 上游 craft 的语义类
 *     （`--accent` 本身就是**紫** hue 293、`--info` 是**琥珀** hue 70、
 *     `--success` 绿、`--energy-low` 橙红、`--destructive` 红、`--muted` 灰）
 *     **全部自带双模**（`:root` 与 `.dark` 各一份 ⇒ 暗色自动跟随）
 *     ⇒ ★ **不需要新建任何 CSS 变量、不需要碰 ardot** —— 只需把散落处**归位**。
 *
 * ★ 三条纪律
 * ---------
 * 1. ★ **同一族内不许撞色**：一族里的每一档必须用**不同**的语义类
 *    （原实现里 `reflect` 与 `consolidate` 其实**都是紫** ⇒ 标签分不开 ⇒ 本表修掉）。
 * 2. ★ **固定枚举 ⇒ 语义类；动态分类 ⇒ 数据表**（分类名不可穷举成变量名）
 *    ⇒ 动态那部分（技能图谱的域名色、协作页的按分数插值色）**不在本表**，
 *      它们需要各自的**暗色变体**（第二十一批 D-2）。
 * 3. ★ **色相不承载档位**：像「记忆层级 L1/L2/L3」这种**技术分层**
 *    ⇒ 档位由**文字**承载（标签写着「L1 工作 / L2 情景 / L3 语义」），
 *    三层**同色** ⇒ ★ 不给「技术分层」配三种色相。
 *
 * ★ 唯一例外：**境界色阶**（NOVICE → MASTER）**保留色阶**
 *   —— 等级的身份色是产品价值的一部分（游戏化），但它必须**集中在一张表里**
 *   ⇒ 将来要换整条色阶，只改这一处。
 */

/** 一档的完整三态（底 / 字 / 描边）—— 与 `ReadoutCell` 的「各带自己的口径」同族。 */
// ★ 第二十一批 D-2：动态分类色的**双模定义**（色值只在这份 CSS 里）
//   —— 集中表只持有**变量名** ⇒ 「色值两份副本」的隐患从根上消除。
import './dataColors.css'

export interface SemanticSwatch {
  /** 底色（浅染：用 `bg-<语义>/<alpha>`） */
  bg: string
  /** 文字色（用 `text-<语义>-text` 优先，保证暗色下可读） */
  text: string
  /** 描边色（用 `border-<语义>/<alpha>`） */
  border: string
}

/**
 * 境界 5 档（NOVICE → MASTER）—— 灰 → 绿 → 蓝 → 紫 → 琥珀。
 *
 * ★ 色阶**由低到高**递进（越高越暖），全部用上游**双模**语义类。
 * ★ 原实现里 MASTER/EXPERT/NOVICE 三档是 Tailwind 默认色（amber/purple/gray），
 *   ADEPT/APPRENTICE 已是 accent/success ⇒ ★ 现在**五档同族同源**。
 */
export const LEVEL_COLORS: Record<string, SemanticSwatch> = {
  NOVICE: {
    bg: 'bg-muted/10',
    text: 'text-muted-foreground',
    border: 'border-border/40',
  },
  APPRENTICE: {
    bg: 'bg-success/10',
    text: 'text-success-text',
    border: 'border-success/60',
  },
  ADEPT: {
    bg: 'bg-accent/10',
    text: 'text-accent',
    border: 'border-accent/60',
  },
  EXPERT: {
    bg: 'bg-info/10',
    text: 'text-info-text',
    border: 'border-info/60',
  },
  MASTER: {
    bg: 'bg-energy-low/10',
    text: 'text-energy-low-text',
    border: 'border-energy-low/60',
  },
}

/**
 * ZenLoop 四通道（reflect / consolidate / insight / purify）。
 *
 * ★ 四档**互不撞色**（原实现 reflect 与 consolidate 都是紫 ⇒ 分不开）。
 * ★ ★ **既有语义保持不变**：insight=琥珀、purify=绿 是原实现**有意**的设计
 *   （既有测试就在守护它）⇒ 本表只把「默认色」那一档（consolidate）换掉，
 *   **不为了统一而重排**（重排 = 破坏有意设计）。
 */
export const LOOP_CHANNEL_COLORS: Record<string, string> = {
  reflect: 'bg-accent/15 text-accent',
  // ★ consolidate 原是 `purple`（Tailwind 默认色）⇒ 归位为**中性灰**
  //   （「整理 / 沉淀」⇒ 沉稳；也不用彩色以免与 reflect 的紫撞）。
  consolidate: 'bg-muted/15 text-muted-foreground',
  // ★ insight=琥珀、purify=绿 是**既有有意设计**（原实现如此，既有测试就在守护）
  //   ⇒ 本表**保持不变**，只把「默认色」那一档换掉 —— 不为了统一而重排。
  insight: 'bg-info/15 text-info-text',
  purify: 'bg-success/15 text-success-text',
}

/**
 * 建议类型 4 类（自动分类徽标：action / project / reference / calendar）。
 *
 * ★ 四类**互不撞色**；★ `project` 用**中性灰** —— 避免与 craft 自己的
 *   `PROJECT_COLOR_PALETTE`（项目色板）打架（两套「项目色」并存会让人误以为是同一族）。
 */
export const SUGGEST_TYPE_COLORS: Record<string, string> = {
  action: 'bg-accent/15 text-accent',
  project: 'bg-muted/15 text-muted-foreground',
  reference: 'bg-info/15 text-info-text',
  calendar: 'bg-success/15 text-success-text',
}

/**
 * 技能关系 5 种（技能图谱的边）—— 用 **CSS 变量**（那边是 inline `style={{ color }}`，
 * 用不了 Tailwind 类）。
 *
 * ★ 语义对应：前置=品牌紫 / 互补=琥珀 / 竞争=红 / 迁移=绿 / 共现=橙红。
 */
export const RELATION_COLORS: Record<string, string> = {
  prerequisite: 'var(--accent)',
  complementary: 'var(--info)',
  competing: 'var(--destructive)',
  transfer: 'var(--success)',
  co_occurrence: 'var(--energy-low)',
}

/**
 * 记忆层级 3 层（L1 工作 / L2 情景 / L3 语义）。
 *
 * ★ ★ **三层同色** —— 这是「**色相不承载档位**」的兑现：
 *   L1/L2/L3 是**技术分层**，用户靠**标签文字**区分，不靠颜色
 *   （原实现 L1/L2 是 accent、L3 是 purple ⇒ 技术分层被画成了「等级」）。
 */
export const MEMORY_LAYER_COLORS: Record<string, string> = {
  L1: 'bg-accent/60',
  L2: 'bg-accent/60',
  L3: 'bg-accent/60',
}

/**
 * 技能**域名色**（10 个分类）—— 分类来自技能数据，**不可穷举成语义类**
 * ⇒ 只能留在数据表；★ 用 CSS 变量引用 ⇒ **双模自动跟随**（亮/暗各一套值）。
 *
 * ★ 色值在 `panels/dataColors.css`（亮色用加深版、暗色用鲜艳版）。
 */
export const DOMAIN_COLOR_VARS: Record<string, string> = {
  lark: 'var(--zenskill-domain-lark)',
  arkcli: 'var(--zenskill-domain-arkcli)',
  agentswarm: 'var(--zenskill-domain-agentswarm)',
  dev: 'var(--zenskill-domain-dev)',
  data: 'var(--zenskill-domain-data)',
  ai: 'var(--zenskill-domain-ai)',
  design: 'var(--zenskill-domain-design)',
  ops: 'var(--zenskill-domain-ops)',
  life: 'var(--zenskill-domain-life)',
  general: 'var(--zenskill-domain-general)',
}

/**
 * 协作页**洞察类型色**（7 类）—— 同上：多值分类 ⇒ 数据表 + CSS 变量双模。
 */
export const INSIGHT_COLOR_VARS: Record<string, string> = {
  bottleneck: 'var(--zenskill-insight-bottleneck)',
  transferable: 'var(--zenskill-insight-transferable)',
  synergy: 'var(--zenskill-insight-synergy)',
  imbalance: 'var(--zenskill-insight-imbalance)',
  comparison: 'var(--zenskill-insight-comparison)',
  pattern: 'var(--zenskill-insight-pattern)',
  milestone: 'var(--zenskill-insight-milestone)',
}
