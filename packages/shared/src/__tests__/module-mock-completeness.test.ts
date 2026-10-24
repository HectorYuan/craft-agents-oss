import { describe, it, expect } from 'bun:test'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

/**
 * 守卫：`mock.module()` 的工厂必须覆盖被 mock 模块的**全部运行时导出**。
 *
 * 背景（2026-10-24，CI `Vendor Tests` 红灯的根因）：
 *   bun 的 `mock.module(spec, factory)` 是**进程级整块替换**，且持续到之后加载的
 *   所有测试文件。⇒ factory 只给部分导出时，之后任何**静态导入**了缺失导出的文件
 *   会在链接期抛 `SyntaxError: export 'X' not found in '<真实文件路径>'`
 *   —— 那个路径是真实文件（文件明明导出了该符号）⇒ 极具误导性，
 *   当年的排查成本几乎全花在「文件是不是坏了」上。
 *
 * 实证：`src/prompts/__tests__/system.test.ts` 的 preferences mock 只给了
 * 10 个运行时导出里的 2 个（`getCoAuthorPreference` / `formatPreferencesForPrompt`），
 * 而 `src/agent/claude-context.ts` 静态导入 `updatePreferences`
 * ⇒ 谁先加载谁中招（**顺序相关 ⇒ 表现为偶发红**）。
 *
 * 本守卫的判据：
 *   - 被 mock 的模块的**运行时**导出集合（类型导出在运行时不存在，不计入）
 *     必须 ⊆ 工厂给出的键集合。
 *   - 工厂若经 `completeModuleMock(...)`（转发全部 + 覆盖少数）⇒ 结构上无法缺 ⇒ 放行。
 *   - 无法静态判定（内置模块 / 非相对路径 / 工厂含展开 / 目标无法独立导入）
 *     ⇒ 跳过，但**必须计数**：一个都判定不了 ⇒ 守卫形同虚设 ⇒ 判红。
 *
 * 只扫 `*.test.ts`：bun 默认 glob 认它，而 `*.isolated.ts`（本仓另有约定）
 * 不在 bun 的默认 glob 内 ⇒ 不参与进程内加载 ⇒ 不会造成跨文件污染。
 */

const SRC_ROOT = resolve(import.meta.dir, '..')
const PACKAGE_ROOT = resolve(SRC_ROOT, '..')

// ── 源码扫描：找出所有 `mock.module(spec, factory)` 调用 ──────────────────────

interface MockCall {
  spec: string
  factory: string
}

function splitArgs(src: string, openIdx: number): { args: string[]; end: number } | null {
  const args: string[] = []
  let depth = 0
  let cur = ''
  let quote: string | null = null
  for (let i = openIdx + 1; i < src.length; i++) {
    const ch = src[i]!
    if (quote) {
      cur += ch
      if (ch === '\\') {
        cur += src[++i] ?? ''
        continue
      }
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      cur += ch
      continue
    }
    if (ch === '(' || ch === '[' || ch === '{') {
      depth++
      cur += ch
      continue
    }
    if (ch === ')' || ch === ']' || ch === '}') {
      if (depth === 0) {
        args.push(cur)
        return { args, end: i }
      }
      depth--
      cur += ch
      continue
    }
    if (ch === ',' && depth === 0) {
      args.push(cur)
      cur = ''
      continue
    }
    cur += ch
  }
  return null
}

function findMockCalls(src: string): MockCall[] {
  const out: MockCall[] = []
  const re = /mock\.module\s*\(/g
  let m: RegExpExecArray | null
  while ((m = re.exec(src)) !== null) {
    const openIdx = m.index + m[0].length - 1
    const parsed = splitArgs(src, openIdx)
    if (!parsed) continue
    out.push({
      spec: (parsed.args[0] ?? '').trim().replace(/^['"]|['"]$/g, ''),
      factory: parsed.args[1] ?? '',
    })
    re.lastIndex = parsed.end
  }
  return out
}

/** 取工厂返回的对象字面量的顶层键；含展开或无法判定 ⇒ 返回 null。 */
function literalKeys(factory: string): string[] | null {
  let objStart = -1
  const retIdx = factory.lastIndexOf('return')
  const arrowIdx = factory.indexOf('=>')
  if (retIdx >= 0) {
    const brace = factory.indexOf('{', retIdx)
    if (brace >= 0) objStart = brace
  } else if (arrowIdx >= 0) {
    let i = arrowIdx + 2
    while (i < factory.length && /\s/.test(factory[i]!)) i++
    if (factory[i] === '(') {
      i++
      while (i < factory.length && /\s/.test(factory[i]!)) i++
      if (factory[i] === '{') objStart = i
    } else if (factory[i] === '{') {
      objStart = i
    }
  }
  if (objStart < 0) return null

  // 取对象字面量的平衡范围
  let depth = 0
  let end = -1
  let quote: string | null = null
  for (let i = objStart; i < factory.length; i++) {
    const ch = factory[i]!
    if (quote) {
      if (ch === '\\') {
        i++
        continue
      }
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      continue
    }
    if (ch === '{' || ch === '[' || ch === '(') depth++
    else if (ch === '}' || ch === ']' || ch === ')') {
      depth--
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  if (end < 0) return null

  const body = factory.slice(objStart + 1, end)
  const keys: string[] = []
  let d = 0
  let q: string | null = null
  for (let i = 0; i < body.length; i++) {
    const ch = body[i]!
    if (q) {
      if (ch === '\\') {
        i++
        continue
      }
      if (ch === q) q = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      q = ch
      continue
    }
    if (ch === '{' || ch === '[' || ch === '(') {
      d++
      continue
    }
    if (ch === '}' || ch === ']' || ch === ')') {
      d--
      continue
    }
    if (d === 0 && body.startsWith('...', i)) return null // 展开 ⇒ 无法静态判定
    if (d === 0) {
      const m = /^([A-Za-z_$][\w$]*)\s*:/.exec(body.slice(i))
      if (m) {
        keys.push(m[1]!)
        i += m[0].length - 1
        continue
      }
      const qm = /^(['"])([A-Za-z_$][\w$]*)\1\s*:/.exec(body.slice(i))
      if (qm) {
        keys.push(qm[2]!)
        i += qm[0].length - 1
      }
    }
  }
  return keys
}

function resolveTarget(fromDir: string, spec: string): string | null {
  if (!spec.startsWith('.')) return null
  const base = resolve(fromDir, spec)
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    `${base}.js`,
    join(base, 'index.ts'),
    join(base, 'index.tsx'),
  ]
  for (const c of candidates) {
    if (existsSync(c) && statSync(c).isFile()) return c
  }
  return null
}

function listTestFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) listTestFiles(full, out)
    else if (entry.endsWith('.test.ts') || entry.endsWith('.test.tsx')) out.push(full)
  }
  return out
}

describe('模块 mock 完整性守卫', () => {
  it('每个 mock.module 工厂都覆盖被 mock 模块的全部运行时导出', async () => {
    // 守卫自身排除：它的诊断文案里含 `mock.module(` 字面量，会被自己的扫描器当成调用。
    const files = listTestFiles(SRC_ROOT).filter(f => !f.endsWith('module-mock-completeness.test.ts'))
    expect(files.length).toBeGreaterThan(0)

    const violations: string[] = []
    const skipped: string[] = []
    let verified = 0

    for (const file of files) {
      const src = readFileSync(file, 'utf-8')
      const calls = findMockCalls(src)
      if (calls.length === 0) continue
      const rel = file.replace(`${PACKAGE_ROOT}/`, '')

      for (const call of calls) {
        if (call.factory.includes('completeModuleMock(')) {
          // 转发全部 + 覆盖少数 ⇒ 结构上不可能缺导出
          verified++
          continue
        }
        const target = resolveTarget(dirname(file), call.spec)
        if (!target) {
          skipped.push(`${rel}: mock.module('${call.spec}') 目标非本地相对路径 ⇒ 跳过`)
          continue
        }
        let runtimeExports: string[]
        try {
          const mod = (await import(pathToFileURL(target).href)) as Record<string, unknown>
          runtimeExports = Object.keys(mod)
        } catch {
          skipped.push(`${rel}: mock.module('${call.spec}') 目标无法独立导入 ⇒ 跳过`)
          continue
        }
        const keys = literalKeys(call.factory)
        if (!keys) {
          skipped.push(`${rel}: mock.module('${call.spec}') 工厂含展开/无法静态判定 ⇒ 跳过`)
          continue
        }
        const missing = runtimeExports.filter(e => !keys.includes(e))
        if (missing.length > 0) {
          violations.push(
            `${rel}: mock.module('${call.spec}') 缺少导出 ${missing.join(', ')}` +
              ` —— bun 的 mock 是进程级整块替换，会让之后加载的文件链接失败` +
              `（改用 completeModuleMock(actual, overrides) 转发全部导出）`,
          )
        } else {
          verified++
        }
      }
    }

    expect({ violations, skipped, verified }).toEqual({ violations: [], skipped, verified })
    // 一个都判定不了 ⇒ 守卫形同虚设 ⇒ 必须判红
    expect(verified).toBeGreaterThan(0)
  })
})
