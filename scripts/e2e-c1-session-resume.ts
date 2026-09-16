/**
 * C1 会话续接 E2E 验收（context-loss-optimization-review.md · 原文验收 D1）
 *
 * 场景：30 轮 faux 会话（第 1 轮给出 A/B/C 选项）→ destroy 子进程（模拟
 * 应用重启/崩溃）→ 以持久化 sdkSessionId 重建 agent → 断言：
 *   A1  续接成功（onDebug 出现 "engine session resumed"）
 *   A2  模型可见回放计数一致（get_state.messageCount 续接前后相等）
 *   A3  「我选A」可接住——第 1 轮选项文本在 get_messages 回放中逐字在场
 *
 * faux 为回显 provider，不调 LLM；引擎经真实 wrapper+uv 子进程启动。
 * 运行：bun scripts/e2e-c1-session-resume.ts
 * 环境要求：PATH 含 uv；仓库 venv（UV_PROJECT_ENVIRONMENT）已装 zenskill。
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { ZenskillAgent } from '../packages/shared/src/agent/backend/zenskill-agent.ts'

const REPO_ROOT = join(import.meta.dir, '..', '..', '..') // D:/zenskill
const VENV = join(REPO_ROOT, '.venv')
const TURNS = 30
const OPTION_MARKER = 'A=清测试条目'

function fail(msg: string): never {
  console.error(`E2E-FAIL: ${msg}`)
  process.exit(1)
}

// ---- 环境准备：wrapper 需要的 CRAFT_* 与 uv ---------------------------------
const uv = spawnSync('where', ['uv'], { shell: true }).stdout?.toString().split(/\r?\n/)[0]?.trim()
if (!uv || !existsSync(VENV)) fail('前置缺失：需要 uv 在 PATH 且 D:/zenskill/.venv 存在（python 3.12 + zenskill）')
process.env.CRAFT_DEV_RUNTIME = '1'
process.env.CRAFT_ZENSKILL = REPO_ROOT
process.env.CRAFT_UV = uv
process.env.UV_PROJECT_ENVIRONMENT = VENV

// 引擎会话根（spawn 未传 --session-root，落默认目录；结束清理本测试产物）
const ENGINE_SESSIONS = join(homedir(), '.zenskill', 'agent', 'sessions')

function makeAgent(sessionSdkSessionId: string | undefined, onSid: (sid: string) => void) {
  const debugLines: string[] = []
  const agent = new ZenskillAgent({
    workspace: { rootPath: join(tmpdir(), 'c1-e2e-ws'), name: 'c1-e2e' },
    skipConfigWatcher: true,
    faux: true,
    session: { id: 'c1-e2e-host', sdkSessionId: sessionSdkSessionId },
    onSdkSessionIdUpdate: onSid,
  } as any)
  agent.onDebug = (m: string) => debugLines.push(m)
  return { agent, debugLines }
}

async function rpc(agent: ZenskillAgent, cmd: Record<string, unknown>, timeoutMs = 15000): Promise<Record<string, any>> {
  const readline = (agent as any).readline
  if (!readline) fail('子进程 readline 不存在（未 spawn？）')
  const id = `e2e-${Math.random().toString(36).slice(2)}`
  return await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`rpc ${cmd.type} 超时`)), timeoutMs)
    const handler = (line: string) => {
      try {
        const msg = JSON.parse(line)
        if (msg.type === 'response' && msg.id === id) {
          clearTimeout(timeout)
          readline.off('line', handler)
          resolve(msg)
        }
      } catch { /* ignore */ }
    }
    readline.on('line', handler)
    ;(agent as any).send({ ...cmd, id })
  })
}

async function driveTurn(agent: ZenskillAgent, message: string): Promise<string> {
  let text = ''
  for await (const ev of agent.chat(message) as AsyncGenerator<any>) {
    if (ev.type === 'text_delta') text += ev.text
    if (ev.type === 'error') fail(`回合出错：${ev.message}`)
  }
  return text
}

const createdSid: string[] = []
try {
  // ---- Phase 1：agent A，30 轮会话（第 1 轮含选项）--------------------------
  const sidsA: string[] = []
  const A = makeAgent(undefined, (sid) => sidsA.push(sid))
  const first = await driveTurn(A.agent, `请记住以下选项供我稍后选择：${OPTION_MARKER}，B=保留，C=延后`)
  if (!first.includes(OPTION_MARKER)) fail(`faux 回显未包含第 1 轮选项回显：${first.slice(0, 80)}`)
  for (let i = 2; i <= TURNS; i++) await driveTurn(A.agent, `第${i}轮：继续，不要丢失第 1 轮的选项`)
  if (sidsA.length === 0) fail('引擎 sid 未回传（C1 捕获链断裂）')
  const engineSid = sidsA[0]
  createdSid.push(engineSid)

  const stateA = await rpc(A.agent, { type: 'get_state' })
  const countA = stateA.data?.messageCount
  if (typeof countA !== 'number' || countA < TURNS * 2) fail(`A 侧回放计数异常：${countA}（期望 ≥ ${TURNS * 2}）`)
  console.log(`EVIDENCE: agent A 完成 ${TURNS} 轮，engineSid=${engineSid}，模型可见回放=${countA} 条`)

  // ---- Phase 2：销毁子进程（模拟应用重启）→ 以持久化 sid 重建 --------------
  A.agent.destroy()
  await new Promise((r) => setTimeout(r, 1500)) // 等待子进程退出

  const sidsB: string[] = []
  const B = makeAgent(engineSid, (sid) => sidsB.push(sid)) // host header 已持久化的 sid
  await (B.agent as any).ensureSubprocess() // 触发 spawn + resumeEngineSession
  const resumed = B.debugLines.some((l) => l.includes(`engine session resumed: ${engineSid}`))
  if (!resumed) fail(`A1 续接未成功：debug=${JSON.stringify(B.debugLines.slice(-5))}`)
  console.log(`EVIDENCE: A1 续接成功 — ${B.debugLines.find((l) => l.includes('resumed'))}`)

  const stateB = await rpc(B.agent, { type: 'get_state' })
  const countB = stateB.data?.messageCount
  if (countB !== countA) fail(`A2 回放计数不一致：重建前 ${countA} vs 重建后 ${countB}`)
  console.log(`EVIDENCE: A2 回放计数一致 — 重建前=${countA} 重建后=${countB}`)

  const msgs = await rpc(B.agent, { type: 'get_messages' })
  const replayed: string[] = (msgs.data?.messages ?? []).map((m: any) =>
    typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
  )
  if (!replayed.some((t) => t.includes(OPTION_MARKER))) fail('A3 第 1 轮选项文本不在回放中')
  console.log(`EVIDENCE: A3 选项文本在场 — 回放 ${replayed.length} 条中含「${OPTION_MARKER}」`)
  B.agent.destroy()

  // ---- Phase 3：真回合「我选A」（faux 回显；上下文完整性已由 A1-A3 证明）----
  console.log('EVIDENCE: 「我选A」回合上下文完整性由 A1-A3 证明（faux 不做语义推理）')
  console.log('E2E-PASS: C1 会话续接验收通过（30 轮重启后历史完整回放，选项未丢失）')
} catch (e) {
  fail(e instanceof Error ? e.message : String(e))
} finally {
  // 清理本测试产生的引擎会话文件
  for (const sid of createdSid) {
    try { rmSync(join(ENGINE_SESSIONS, `${sid}.jsonl`), { force: true }) } catch { /* ignore */ }
  }
  try { rmSync(join(tmpdir(), 'c1-e2e-ws'), { recursive: true, force: true }) } catch { /* ignore */ }
}
process.exit(0)
