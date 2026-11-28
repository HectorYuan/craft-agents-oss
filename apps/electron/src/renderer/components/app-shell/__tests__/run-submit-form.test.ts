/**
 * run:submit 派发表单纯逻辑单测（D4）。
 *
 * 只测「表单字符串 → 契约请求」与体验级校验；服务端校验（capId 白名单真值、
 * budget 语义、会话可见性）不在本文件覆盖。
 */
import { describe, test, expect } from 'bun:test'
import {
  RUN_SUBMIT_CAP_IDS,
  RUN_SUBMIT_MAX_STEPS,
  RUN_SUBMIT_TIMEOUT_SEC,
  canSubmitRunSubmitForm,
  parseRunSubmitInput,
  type RunSubmitFormValues,
} from '../runSubmitModel'

const base: RunSubmitFormValues = {
  title: '整理本周复盘',
  description: '',
  capId: RUN_SUBMIT_CAP_IDS[0],
  maxSteps: '',
  timeoutSec: '',
}

describe('parseRunSubmitInput', () => {
  test('空白标题 → chat.runSubmitInvalidTitle', () => {
    for (const title of ['', '   ', '\n\t']) {
      const r = parseRunSubmitInput({ ...base, title }, 'sess-1')
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.error).toBe('chat.runSubmitInvalidTitle')
    }
  })

  test('最小合法输入 → taskContract + capId + sessionId，且无 budget 键', () => {
    const r = parseRunSubmitInput({ ...base, title: '  整理复盘  ' }, 'sess-1')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.request).toEqual({
      taskContract: { title: '整理复盘' },
      capId: RUN_SUBMIT_CAP_IDS[0],
      sessionId: 'sess-1',
    })
    expect('budget' in r.request).toBe(false)
  })

  test('描述去空白后作为 taskContract.description 透传，不影响 title', () => {
    const r = parseRunSubmitInput({ ...base, description: '  读最近的提交  ' }, 'sess-1')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.request.taskContract).toEqual({ title: base.title, description: '读最近的提交' })

    const empty = parseRunSubmitInput({ ...base, description: '   ' }, 'sess-1')
    expect(empty.ok).toBe(true)
    if (!empty.ok) return
    expect('description' in empty.request.taskContract).toBe(false)
  })

  test('maxSteps 越界（0 / 201 / 2.5 / 非数字）→ chat.runSubmitInvalidMaxSteps', () => {
    for (const maxSteps of ['0', '201', '2.5', 'abc', '-1']) {
      const r = parseRunSubmitInput({ ...base, maxSteps }, 'sess-1')
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.error).toBe('chat.runSubmitInvalidMaxSteps')
    }
    const ok = parseRunSubmitInput(
      { ...base, maxSteps: String(RUN_SUBMIT_MAX_STEPS.max) },
      'sess-1',
    )
    expect(ok.ok).toBe(true)
  })

  test('timeoutSec 越界（0 / 86401）→ chat.runSubmitInvalidTimeout；合法值转 number', () => {
    for (const timeoutSec of ['0', String(RUN_SUBMIT_TIMEOUT_SEC.max + 1)]) {
      const r = parseRunSubmitInput({ ...base, timeoutSec }, 'sess-1')
      expect(r.ok).toBe(false)
      if (!r.ok) expect(r.error).toBe('chat.runSubmitInvalidTimeout')
    }
    const r = parseRunSubmitInput({ ...base, maxSteps: '5', timeoutSec: '600' }, 'sess-1')
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.request.budget).toEqual({ maxSteps: 5, timeoutSec: 600 })
  })

  test('capId 不在声明清单 → chat.runSubmitInvalidCap；canSubmit 只看标题', () => {
    const r = parseRunSubmitInput({ ...base, capId: 'other-cap' }, 'sess-1')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toBe('chat.runSubmitInvalidCap')

    expect(canSubmitRunSubmitForm(base)).toBe(true)
    expect(canSubmitRunSubmitForm({ ...base, title: '  ' })).toBe(false)
  })
})
