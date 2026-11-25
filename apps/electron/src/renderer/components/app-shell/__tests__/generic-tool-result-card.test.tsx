/**
 * GenericToolResultCard 单测：普通工具结果渲染、isError 视觉区分、空内容不占位、
 * 超长结果折叠截断并标注「已截断」。
 */
import React from 'react'
import { describe, test, expect } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'
import i18next from 'i18next'
import { initReactI18next, I18nextProvider } from 'react-i18next'
import { GenericToolResultCard } from '../GenericToolResultCard'

const i18n = i18next.createInstance()
await new Promise<void>((resolve) => {
  i18n.use(initReactI18next).init(
    {
      lng: 'zh',
      resources: {
        zh: {
          translation: {
            'common.error': '错误',
            'common.resultTruncated': '已截断',
          },
        },
      },
      interpolation: { escapeValue: false },
    },
    () => resolve(),
  )
})
expect(i18n.isInitialized).toBe(true)

function render(props: React.ComponentProps<typeof GenericToolResultCard>) {
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>
      <GenericToolResultCard {...props} />
    </I18nextProvider>,
  )
}

describe('GenericToolResultCard', () => {
  test('渲染工具名与结果正文', () => {
    const html = render({ toolName: 'write', resultText: 'Wrote 18 bytes to allow.txt' })
    expect(html).toContain('write')
    expect(html).toContain('Wrote 18 bytes to allow.txt')
    expect(html).toContain('text-success')
  })

  test('isError 活动走 destructive 区分并展示错误文本', () => {
    const html = render({
      toolName: 'write',
      resultText: 'generic fallback',
      isError: true,
      errorText: 'APPROVAL DENIED: write',
    })
    expect(html).toContain('destructive')
    expect(html).toContain('APPROVAL DENIED: write')
    expect(html).toContain('错误')
    // 错误态不渲染成功图标
    expect(html).not.toContain('text-success')
  })

  test('空 / 纯空白结果返回 null（不占位）', () => {
    expect(render({ toolName: 'echo', resultText: '' })).toBe('')
    expect(render({ toolName: 'echo', resultText: '   \n\t ' })).toBe('')
  })

  test('超长结果折叠到阈值并标注已截断，尾部不落稿', () => {
    const longBody = 'x'.repeat(2000)
    const html = render({ toolName: 'long_stdout', resultText: longBody })
    expect(html).toContain('已截断')
    // 正文被切到 1200 + 省略号，尾部 800 字符不落稿
    expect(html).not.toContain('x'.repeat(1201))
    expect(html).toContain('…')
  })
})
