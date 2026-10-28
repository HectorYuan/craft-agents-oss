/**
 * visible-copy.test.ts — 用户可见界面文案的真相源化（第二十二批 D-3 第一批）
 *
 * ★ 为什么要有这条测试
 * -------------------
 * `components/zenskill/**` 里有一批**用户直接可见**的中文（tooltip / toast / 按钮）
 * 此前是**代码里的硬编码** ⇒ 没有 locale key ⇒ 任何门禁都管不到
 * （★ G-14「真相源文案副本检测」只抓**真相源已登记**的文案，⇒ 这类未登记的仍需迁移）。
 *
 * ★ 本测试把「已迁移」钉住：
 *   ① 那几句**不再以中文字面量**出现在代码里（改成 `t()` 取 locale）
 *   ② 顺带修掉**同一界面两种语言**的混用（`'Delete'` 英文 vs 中文确认提示）
 *   ③ 7 个 locale 都有新键且**非空**
 */
import { describe, expect, it } from 'bun:test'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const LOCALES_DIR = join(
  import.meta.dir,
  '../../../../../../../packages/shared/src/i18n/locales',
)

const ACTIONS = readFileSync(
  join(import.meta.dir, '..', 'panels', 'ActionsPanel.tsx'),
  'utf8',
)
const DATA_PANEL = readFileSync(
  join(import.meta.dir, '..', 'ZenSkillDataPanel.tsx'),
  'utf8',
)

/** ★ 断言只针对**代码**，不含注释（注释里的说明文字不是硬编码文案）。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const actionsCode = stripComments(ACTIONS)
const dataPanelCode = stripComments(DATA_PANEL)

describe('用户可见界面文案 · 真相源化（D-3 第一批）', () => {
  it('ActionsPanel 的 tooltip 不再硬编码中文', () => {
    expect(actionsCode).not.toContain('用 Agent 执行')
    expect(actionsCode).not.toContain('点击再次确认删除')
    expect(actionsCode).not.toContain('切换看板')
    expect(actionsCode).not.toContain('切换列表')
  })

  it('★ 同一界面两种语言的混用已修（Delete 不再是英文硬编码）', () => {
    expect(actionsCode).not.toContain("'Delete'")
    expect(actionsCode).toContain("t('zenskill.readout.deleteAction')")
  })

  it('ActionsPanel 的 tooltip 改从 locale 取用', () => {
    expect(actionsCode).toContain("t('zenskill.readout.agentExecute')")
    expect(actionsCode).toContain("t('zenskill.readout.confirmDeleteAgain')")
    expect(actionsCode).toContain("t('zenskill.readout.switchBoard')")
    expect(actionsCode).toContain("t('zenskill.readout.switchList')")
  })

  it('ZenSkillDataPanel 的 toast 不再硬编码（含模板字面量那处）', () => {
    expect(dataPanelCode).not.toContain('能量不足，建议休息一下')
    expect(dataPanelCode).not.toContain('个行动已逾期')
    expect(dataPanelCode).toContain("t('zenskill.readout.energyLowToast')")
    expect(dataPanelCode).toContain("t('zenskill.readout.actionsOverdue', { n: c.overdue })")
  })

  it('7 个 locale 都有这批新键且非空', () => {
    const files = readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json'))
    expect(files.length).toBeGreaterThanOrEqual(7)
    const keys = [
      'zenskill.readout.agentExecute',
      'zenskill.readout.confirmDeleteAgain',
      'zenskill.readout.deleteAction',
      'zenskill.readout.switchBoard',
      'zenskill.readout.switchList',
      'zenskill.readout.energyLowToast',
      'zenskill.readout.actionsOverdue',
    ]
    for (const f of files) {
      const data = JSON.parse(readFileSync(join(LOCALES_DIR, f), 'utf8')) as Record<
        string,
        string
      >
      for (const k of keys) {
        const v = data[k]
        expect(typeof v, `${f} 缺 ${k}`).toBe('string')
        expect(v.length, `${f} 的 ${k} 为空`).toBeGreaterThan(0)
      }
    }
  })
})
