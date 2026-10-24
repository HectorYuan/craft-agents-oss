/**
 * 完整模块 mock 助手 —— 让「只 stub 部分导出」这件事**在结构上无法表达**。
 *
 * 为什么必须有它（2026-10-24 CI `Vendor Tests` 红灯的根因）：
 *
 *   bun 的 `mock.module(spec, factory)` 是**进程级**的：它把该 spec 在模块注册表里
 *   **整块替换**掉，且**持续到本进程之后加载的所有测试文件**。
 *   ⇒ 如果 factory 只给出一部分导出，任何**之后**加载、且**静态导入**了缺失导出的
 *     文件，会在**链接期**抛：
 *       SyntaxError: export 'updatePreferences' not found in '.../preferences.ts'
 *     而那个路径是**真实文件路径** ⇒ 极具误导性（文件明明导出了该符号）。
 *   ⇒ 本助手强制「转发真实模块的全部导出 + 只覆盖要测的那几个」，
 *     从结构上消灭这类跨文件污染。
 *
 * 用法：
 *   import * as actual from '../../config/preferences.ts'
 *   mock.module('../../config/preferences.ts', () =>
 *     completeModuleMock(actual, { getCoAuthorPreference: () => true }))
 */
export function completeModuleMock<T extends object>(
  actual: T,
  overrides: Partial<T> = {},
): T {
  // 转发全部真实导出，再叠加要测的覆盖项 ⇒ 缺失导出这件事**无法被表达**。
  return { ...actual, ...overrides }
}
