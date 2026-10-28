/**
 * units-disjoint-copy.test.ts — 量纲纪律文案的真相源化（第二十二批 D 段）
 *
 * ★ 为什么要有这条测试
 * -------------------
 * GTD 工作台的分账条上曾有一句**用户可见的量纲纪律说明**
 * 「两种单位不可相加：能量是燃料，注意力是闸门」——
 * 它是**代码里硬写的中文** ⇒ 与真相源（`copy_terminology.json` 的 `units` 段 role）
 * **构成分叉** ⇒ 真相源改口径 ⇒ 代码那份不会跟着改。
 *
 * ★ 本测试把「已迁移」钉住：
 *   ① 那句**不再以中文字面量**出现在代码里（改成 `t(...)` 取 locale）
 *   ② 其余 4 处（能量标签 / 点单位 / 注意力标签 / 分钟单位）**复用现有键**，
 *      不新增近义词（★「同一概念不另造同义词」在实现层的落点）
 *   ③ 7 个 locale 都有新键且**非空**（key 集合一致性由 i18n 门禁另行守住）
 */
import { describe, expect, it } from 'bun:test'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const GTD_PATH = join(import.meta.dir, '..', 'pages', 'GtdWorkspace.tsx')
const LOCALES_DIR = join(
  import.meta.dir,
  '../../../../../../../packages/shared/src/i18n/locales',
)

const gtd = readFileSync(GTD_PATH, 'utf8')

/**
 * ★ 断言只针对**代码**，不含注释。
 * ★ 理由：★ 注释里出现「还剩 N 分钟」「不再是『任务能量』」是**有意的说明文字**
 * ⇒ ★ 若直接扫全文 ⇒ 断言必然假红（★ 与「负控/断言的内容必须真的落在违规形态上」同源）。
 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const gtdCode = stripComments(gtd)

describe('量纲纪律文案 · 真相源化（第二十二批 D 段）', () => {
  it('那句跨单位说明不再以中文字面量硬编码在代码里', () => {
    expect(gtdCode).not.toContain('两种单位不可相加')
    expect(gtdCode).not.toContain('能量是燃料')
    expect(gtdCode).not.toContain('注意力是闸门')
  })

  it('改为从 locale 取用（locale 是载体，真相源才是源）', () => {
    expect(gtdCode).toContain("t('zenskill.readout.unitsDisjoint')")
  })

  it('能量 / 注意力标签与单位复用现有键，不造近义词', () => {
    expect(gtdCode).toContain("t('zenskill.readout.energy')")
    expect(gtdCode).toContain("t('zenskill.readout.attention')")
    expect(gtdCode).toContain("t('zenskill.unit.point')")
    expect(gtdCode).toContain("t('zenskill.unit.minute')")
    // ★ 「至多」改作前缀（与读数条 prefix 同形）⇒ 「还剩」这个词一并消失
    expect(gtdCode).toContain("t('zenskill.readout.atMost')")
    expect(gtdCode).not.toContain('还剩')
    expect(gtdCode).not.toContain('任务能量')
    expect(gtdCode).not.toContain('注意力预算')
  })

  it('7 个 locale 都有新键且非空', () => {
    const files = readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json'))
    expect(files.length).toBeGreaterThanOrEqual(7)
    for (const f of files) {
      const data = JSON.parse(readFileSync(join(LOCALES_DIR, f), 'utf8')) as Record<
        string,
        string
      >
      const v = data['zenskill.readout.unitsDisjoint']
      expect(typeof v, `${f} 缺 zenskill.readout.unitsDisjoint`).toBe('string')
      expect(v.length, `${f} 的 unitsDisjoint 为空`).toBeGreaterThan(0)
    }
  })
})
