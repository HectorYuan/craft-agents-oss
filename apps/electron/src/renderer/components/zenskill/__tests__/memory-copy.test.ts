/**
 * memory-copy.test.ts — 记忆页文案 + 维度名收敛（第二十二批 D-3 第二批）
 *
 * ★ 为什么要有这条测试
 * -------------------
 * ① `pages/MemoryBrowser.tsx` 的 5 处中文（升华中… / 整合记忆 / L1 工作 / L2 情景 / L3 语义）
 *    曾是**纯硬编码** ⇒ 没有 locale key ⇒ 任何门禁都管不到
 * ② ★ **维度名曾有**两套 key**（`zenskill.profile.dim.*` 与 `zenskill.skillGraph.dim.*`，
 *    值逐字相同）⇒ ★ 同一句话被登记两遍 ⇒ 本批**收敛为一套**
 * ③ `ZenSkillOverview` / `ErrorBoundary` 的兜底文案 ⇒ ★ **复用现成 key**
 *    （`common.unknown` / `toast.unknownError` / `common.retry`）⇒ ★ 零新增键
 */
import { describe, expect, it } from 'bun:test'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const LOCALES_DIR = join(
  import.meta.dir,
  '../../../../../../../packages/shared/src/i18n/locales',
)

const read = (p: string) => readFileSync(join(import.meta.dir, '..', p), 'utf8')

/** ★ 断言只针对**代码**，不含注释（注释里的说明文字不是硬编码文案）。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const memoryCode = stripComments(read('pages/MemoryBrowser.tsx'))
const radarCode = stripComments(read('panels/RadarChart.tsx'))
const graphCode = stripComments(read('pages/ZenSkillSkillGraph.tsx'))
const overviewCode = stripComments(read('pages/ZenSkillOverview.tsx'))
const boundaryCode = stripComments(read('panels/ErrorBoundary.tsx'))

describe('记忆页文案 · 真相源化（D-3 第二批）', () => {
  it('MemoryBrowser 的 5 处硬编码中文已全部迁走', () => {
    expect(memoryCode).not.toContain('升华中…')
    expect(memoryCode).not.toContain('整合记忆')
    expect(memoryCode).not.toContain('L1 工作')
    expect(memoryCode).not.toContain('L2 情景')
    expect(memoryCode).not.toContain('L3 语义')
    expect(memoryCode).not.toContain('暂无语义事实')
  })

  it('MemoryBrowser 改从 locale 取用', () => {
    expect(memoryCode).toContain("t('zenskill.memoryCopy.consolidating')")
    expect(memoryCode).toContain("t('zenskill.memoryCopy.consolidate')")
    expect(memoryCode).toContain("t('zenskill.memoryCopy.layerL1')")
    expect(memoryCode).toContain("t('zenskill.memoryCopy.layerL2')")
    expect(memoryCode).toContain("t('zenskill.memoryCopy.layerL3')")
  })

  it('★ 维度名只有一套 key（重复的 skillGraph.dim.* 已收敛掉）', () => {
    expect(graphCode).not.toContain('zenskill.skillGraph.dim.')
    expect(graphCode).toContain("t('zenskill.profile.dim.proficiency')")
    // ★ RadarChart 的兜底默认值也走同一套
    expect(radarCode).not.toContain('熟练度')
    expect(radarCode).toContain('zenskill.profile.dim.${dim}')
  })

  it('兜底文案复用现成 key（零新增键）', () => {
    expect(overviewCode).not.toContain("'未知'")
    expect(overviewCode).toContain("t('common.unknown')")
    expect(boundaryCode).not.toContain('未知错误')
    expect(boundaryCode).toContain("i18n.t('toast.unknownError')")
    expect(boundaryCode).not.toContain('重试')
    expect(boundaryCode).toContain("i18n.t('common.retry')")
  })

  it('7 个 locale 都有记忆页文案键，且重复的维度名键已删除', () => {
    const files = readdirSync(LOCALES_DIR).filter((f) => f.endsWith('.json'))
    expect(files.length).toBeGreaterThanOrEqual(7)
    const keys = [
      'zenskill.memoryCopy.consolidating',
      'zenskill.memoryCopy.consolidate',
      'zenskill.memoryCopy.layerL1',
      'zenskill.memoryCopy.layerL2',
      'zenskill.memoryCopy.layerL3',
      'zenskill.memoryCopy.noSemanticFacts',
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
      // ★ 重复的维度名键必须已删除
      expect(data['zenskill.skillGraph.dim.proficiency'], `${f} 仍留着重复键`).toBeUndefined()
    }
  })
})
