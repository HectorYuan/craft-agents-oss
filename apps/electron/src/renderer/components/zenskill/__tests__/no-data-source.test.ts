/**
 * 无权限态判定 —— 纯函数单元测试（`panels/errors.ts`）
 *
 * ★ 判据来自 server-core 的真实返回串（`callMcpTool`）：
 *   - 工作区里没有该 slug 的 source ⇒ 'Source not found'
 *   - source 存在但不是 MCP source ⇒ 'Not an MCP source'
 *   - 连接失败 ⇒ 'Source connection failed'（**真故障**，不是无权限）
 *
 * ★ 为什么单测这条：它决定「用户看到的是『没配数据源，去添加』还是『这一块坏了，重试』」
 *   —— 判错的代价是**误导用户去反复重试一件不可能成功的事**。
 */
import { describe, test, expect } from 'bun:test'
import { isNoDataSourceError, isTransientToolError } from '../panels/errors'

describe('isNoDataSourceError', () => {
  test("'Source not found' → 无权限态", () => {
    expect(isNoDataSourceError('Source not found')).toBe(true)
  })

  test("'Not an MCP source' → 无权限态", () => {
    expect(isNoDataSourceError('Not an MCP source')).toBe(true)
  })

  test('大小写不敏感', () => {
    expect(isNoDataSourceError('source not found')).toBe(true)
    expect(isNoDataSourceError('SOURCE NOT FOUND')).toBe(true)
  })

  test("'Source connection failed' → **不是**无权限态（是真故障）", () => {
    expect(isNoDataSourceError('Source connection failed')).toBe(false)
  })

  test("'Workspace not found' → 不是无权限态（是别的问题）", () => {
    expect(isNoDataSourceError('Workspace not found')).toBe(false)
  })

  test('其它错误 → 不是无权限态', () => {
    expect(isNoDataSourceError('Tool zenloop_status failed: timeout')).toBe(false)
    expect(isNoDataSourceError('boom')).toBe(false)
  })

  test('空值 → 不是无权限态（不能把「没读到」当成「没数据源」）', () => {
    expect(isNoDataSourceError(null)).toBe(false)
    expect(isNoDataSourceError(undefined)).toBe(false)
    expect(isNoDataSourceError('')).toBe(false)
  })
})

describe('isTransientToolError', () => {
  test('真故障 → 走错误卡 + 重试', () => {
    expect(isTransientToolError('Source connection failed')).toBe(true)
    expect(isTransientToolError('Tool failed: timeout')).toBe(true)
  })

  test('无数据源 → **不**走错误卡（不给骗人的「重试」）', () => {
    expect(isTransientToolError('Source not found')).toBe(false)
    expect(isTransientToolError('Not an MCP source')).toBe(false)
  })

  test('空值 → 不算错误', () => {
    expect(isTransientToolError(null)).toBe(false)
    expect(isTransientToolError(undefined)).toBe(false)
  })
})
