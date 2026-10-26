/**
 * errors.ts — ZenSkill 读取错误的**语义分类**（纯函数，无 React 依赖）
 *
 * ★ 为什么要分类：MCP 工具失败有两种**性质完全不同**的形态，
 *   混在一起会把「没配数据源」误报成「这一块坏了」：
 *
 *   1. **没数据源**（`Source not found` / `Not an MCP source`）
 *      —— 工作区里没有 ZenSkill 数据源 ⇒ **不是故障**，重试无用
 *      ⇒ 走**无权限态**（稿 `24:20` SystemMessage/system），
 *         给出「去添加数据源」的下一步动作，而不是一个骗人的「重试」按钮。
 *   2. **真故障**（连接失败、工具内部异常、超时……）
 *      —— 重试有意义 ⇒ 走通用错误卡 + 「重试」按钮。
 *
 * ★ 事实来源：server-core `packages/server-core/src/handlers/rpc/sources.ts`
 *   的 `callMcpTool` 在工作区里找不到该 slug 的 source 时返回
 *   `{ success: false, error: 'Source not found' }`；
 *   source 存在但不是 MCP source 时返回 `'Not an MCP source'`；
 *   连接失败时返回 `'Source connection failed'`（**属于真故障**）。
 */

/** 判定：这条错误是不是「工作区没有 ZenSkill 数据源」（⇒ 无权限态，不是故障） */
export function isNoDataSourceError(message: string | null | undefined): boolean {
  if (!message) return false
  return /source not found|not an mcp source/i.test(message)
}

/** 判定：这条错误是不是真故障（⇒ 错误卡 + 重试） */
export function isTransientToolError(message: string | null | undefined): boolean {
  if (!message) return false
  if (isNoDataSourceError(message)) return false
  return true
}
