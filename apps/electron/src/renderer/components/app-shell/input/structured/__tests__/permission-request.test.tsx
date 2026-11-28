/**
 * PermissionRequest 单测（D3）：否决理由 + run chip + 倒计时。
 *
 * 覆盖（与主仓契约 approval.reason_rules 对齐）：
 * - 初始态只出三按钮，不出理由输入框（理由只在开始否决后要求）；
 * - `buildDenyResponse`：空白返回 null（不可提交）、去首尾空白、500 截断；
 * - bridge 请求带 runId 时渲染 run chip；
 * - 带 timeoutMs 时渲染倒计时文案（取整秒）。
 */
import React from 'react'
import { describe, test, expect } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import i18next from 'i18next'
import { initReactI18next, I18nextProvider } from 'react-i18next'
import { PermissionRequest, buildDenyResponse } from '../PermissionRequest'
import type { PermissionRequest as PermissionRequestType } from '../../../../../../shared/types'

const i18n = i18next.createInstance()
await new Promise<void>((resolve) => {
  i18n.use(initReactI18next).init(
    {
      lng: 'zh',
      resources: {
        zh: {
          translation: {
            'chat.permissionRequired': '需要确认',
            'chat.permissionAllow': '允许',
            'chat.permissionAlwaysAllow': '始终允许',
            'chat.permissionDeny': '否决',
            'chat.permissionDenySubmit': '否决并提交',
            'chat.permissionReasonLabel': '理由（否决必填）',
            'chat.permissionReasonPlaceholder': '写清为什么否决这次调用',
            'chat.permissionTimeout': '{{seconds}} 秒后自动否决',
            'common.cancel': '取消',
          },
        },
      },
    },
    () => resolve()
  )
})

function baseRequest(overrides: Partial<PermissionRequestType> = {}): PermissionRequestType {
  return {
    requestId: 'apv-1',
    toolName: 'bash',
    description: 'bash requires approval',
    command: 'rm -rf build',
    ...overrides,
  } as PermissionRequestType
}

function markup(req: PermissionRequestType): string {
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <PermissionRequest request={req} onResponse={() => {}} />
    </I18nextProvider>
  )
}

describe('PermissionRequest（D3）', () => {
  test('初始态：三按钮在位，理由输入框不出现', () => {
    const html = markup(baseRequest())
    expect(html).toContain('允许')
    expect(html).toContain('始终允许')
    expect(html).toContain('否决')
    expect(html).not.toContain('permission-deny-reason-input')
    expect(html).not.toContain('permission-deny-submit')
  })

  test('runId 在位 ⇒ 渲染 run chip', () => {
    const html = markup(baseRequest({ runId: 'run-abc', subtaskId: 'st-1', depth: 1 }))
    expect(html).toContain('data-testid="permission-run-chip"')
    expect(html).toContain('run run-abc')
  })

  test('timeoutMs 在位 ⇒ 渲染倒计时（30 秒）', () => {
    const html = markup(baseRequest({ timeoutMs: 30_000 }))
    expect(html).toContain('30 秒后自动否决')
  })

  test('buildDenyResponse：空白不可提交', () => {
    expect(buildDenyResponse('')).toBeNull()
    expect(buildDenyResponse('   \n  ')).toBeNull()
  })

  test('buildDenyResponse：去空白并带 allowed=false', () => {
    const payload = buildDenyResponse('  不要删构建产物  ')
    expect(payload).toEqual({
      type: 'permission',
      allowed: false,
      alwaysAllow: false,
      reason: '不要删构建产物',
    })
  })

  test('buildDenyResponse：超长截断 500（与后端同口径）', () => {
    const payload = buildDenyResponse('x'.repeat(800))
    expect(payload?.reason).toHaveLength(500)
  })
})
