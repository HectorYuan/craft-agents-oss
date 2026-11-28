/**
 * 2026-11-28 D2：`sessions:respondToPermission` 的理由位在 zenskill 后端的行为契约。
 *
 * 判据（与主仓契约 specs/swarm_integration_contract_v1.yaml 对齐）：
 * - 否决带理由 ⇒ stdio 报文含 `reason`（引擎侧读它落审计）；
 * - 允许带理由 ⇒ 报文**不发** reason 键（理由只对否决有意义，旧报文形状不变）；
 * - 去空白 + 按 500 上限截断。
 *
 * 只测报文构造，不 spawn 子进程（Object.create 绕开构造函数，仅注入 send）。
 */
import { describe, expect, it } from 'bun:test'
import { ZenskillAgent } from '../backend/zenskill-agent.ts'

function agentWithSent(): { agent: any; sent: any[] } {
  const sent: any[] = []
  const agent: any = Object.create(ZenskillAgent.prototype)
  agent.send = (msg: any) => sent.push(msg)
  return { agent, sent }
}

describe('zenskill respondToPermission reason', () => {
  it('否决带理由 ⇒ 报文含 reason', () => {
    const { agent, sent } = agentWithSent()
    agent.respondToPermission('ptu-1', false, false, '  会删掉未提交的改动  ')
    expect(sent).toHaveLength(1)
    expect(sent[0]).toEqual({
      type: 'pre_tool_use_response',
      requestId: 'ptu-1',
      action: 'block',
      reason: '会删掉未提交的改动',
    })
  })

  it('允许带理由 ⇒ 不发 reason 键', () => {
    const { agent, sent } = agentWithSent()
    agent.respondToPermission('ptu-2', true, false, '看起来没问题')
    expect(sent[0]).toEqual({
      type: 'pre_tool_use_response',
      requestId: 'ptu-2',
      action: 'allow',
    })
    expect('reason' in sent[0]).toBe(false)
  })

  it('否决无理由 ⇒ 不发 reason 键（旧客户端零差异）', () => {
    const { agent, sent } = agentWithSent()
    agent.respondToPermission('ptu-3', false)
    expect('reason' in sent[0]).toBe(false)
  })

  it('超长理由截断到 500', () => {
    const { agent, sent } = agentWithSent()
    agent.respondToPermission('ptu-4', false, false, 'x'.repeat(800))
    expect(sent[0].reason).toHaveLength(500)
  })
})
