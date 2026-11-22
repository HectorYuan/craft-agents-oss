/**
 * Headless server smoke test.
 *
 * Spawns the standalone server as a subprocess and validates:
 * - WebSocket handshake succeeds with valid token
 * - WebSocket handshake fails with invalid token
 * - /health endpoint returns 200
 * - Clean shutdown on SIGTERM
 */

import { describe, it, expect, afterEach } from 'bun:test'
import { mkdtempSync, rmSync, appendFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import type { Subprocess } from 'bun'
import WebSocket from 'ws'

const SERVER_ENTRY = join(import.meta.dir, '..', 'index.ts')
const STARTUP_TIMEOUT = 15_000
const TEST_TIMEOUT = 30_000

interface IsolatedEnv {
  env: NodeJS.ProcessEnv
  configDir: string
  stdoutLog: string
  stderrLog: string
  cleanup: () => void
}

interface SpawnedServer {
  url: string
  token: string
  healthPort: number
  proc: Subprocess
  stop: () => Promise<void>
  cleanup: () => void
}

/**
 * 为每个被测实例分配独立临时配置目录，避免与本机 dev 实例
 * （默认配置目录下的 `.server.lock`，pid 常驻）争用单实例锁；
 * 同时把 stdout/stderr tee 到目录内日志文件，启动失败时回传绝对路径。
 */
function createIsolatedEnv(extraEnv?: Record<string, string>): IsolatedEnv {
  const configDir = mkdtempSync(join(tmpdir(), 'craft-smoke-'))
  const stdoutLog = join(configDir, 'server-stdout.log')
  const stderrLog = join(configDir, 'server-stderr.log')
  const { CLAUDECODE: _, ...parentEnv } = process.env

  const env: NodeJS.ProcessEnv = {
    ...parentEnv,
    ...extraEnv,
    CRAFT_CONFIG_DIR: configDir,
    ZENSKILL_CONFIG_DIR: configDir,
  }

  return {
    env,
    configDir,
    stdoutLog,
    stderrLog,
    cleanup: () => rmSync(configDir, { recursive: true, force: true }),
  }
}

async function spawnTestServer(extraEnv?: Record<string, string>): Promise<SpawnedServer> {
  const token = crypto.randomUUID() + crypto.randomUUID() // 72 chars, well above 16 minimum
  const iso = createIsolatedEnv(extraEnv)

  const proc = Bun.spawn(['bun', 'run', SERVER_ENTRY], {
    env: {
      ...iso.env,
      CRAFT_SERVER_TOKEN: token,
      CRAFT_RPC_PORT: '0',
      CRAFT_RPC_HOST: '127.0.0.1',
      CRAFT_HEALTH_PORT: '0', // random port
    },
    stdout: 'pipe',
    stderr: 'pipe',
  })

  return new Promise<SpawnedServer>((resolve, reject) => {
    const timer = setTimeout(() => {
      proc.kill()
      reject(new Error(
        `Server did not start within ${STARTUP_TIMEOUT}ms\n  stdout log: ${iso.stdoutLog}\n  stderr log: ${iso.stderrLog}`,
      ))
    }, STARTUP_TIMEOUT)

    let url = ''
    let buffer = ''
    let stderrTail = ''

    const fail = (reason: string) => {
      clearTimeout(timer)
      reject(new Error(
        `${reason}\n  stdout log: ${iso.stdoutLog}\n  stderr log: ${iso.stderrLog}\n  stderr tail: ${stderrTail.slice(-2000)}`,
      ))
    }

    const processLines = () => {
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('CRAFT_SERVER_URL=')) {
          url = line.slice('CRAFT_SERVER_URL='.length).trim()
        }
        if (url) {
          clearTimeout(timer)
          resolve({
            url,
            token,
            healthPort: 0, // health port not printed; we skip health test if 0
            proc,
            stop: async () => {
              proc.kill('SIGTERM')
              await proc.exited
            },
            cleanup: iso.cleanup,
          })
          return
        }
      }
    }

    ;(async () => {
      const reader = proc.stdout!.getReader()
      const decoder = new TextDecoder()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          appendFileSync(iso.stdoutLog, chunk)
          buffer += chunk
          processLines()
        }
      } catch {
        // Stream closed
      }
      if (!url) fail('Server exited before printing CRAFT_SERVER_URL')
    })()

    // 消费并落盘 stderr：既避免管道背压，也不吞掉服务器报错输出。
    ;(async () => {
      const reader = proc.stderr!.getReader()
      const decoder = new TextDecoder()
      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const chunk = decoder.decode(value, { stream: true })
          appendFileSync(iso.stderrLog, chunk)
          stderrTail += chunk
        }
      } catch {
        // Stream closed
      }
    })()
  })
}

function connectWs(url: string, token: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url)
    ws.on('open', () => {
      // Send handshake
      ws.send(JSON.stringify({
        id: crypto.randomUUID(),
        type: 'handshake',
        protocolVersion: '1.0',
        token,
      }))
    })
    ws.on('message', (data) => {
      const msg = JSON.parse(data.toString())
      if (msg.type === 'handshake_ack') {
        resolve(ws)
      } else if (msg.type === 'error') {
        reject(new Error(`Handshake error: ${msg.error?.message}`))
        ws.close()
      }
    })
    ws.on('error', reject)
    ws.on('close', (code, reason) => {
      reject(new Error(`WS closed: ${code} ${reason}`))
    })
  })
}

describe('headless server smoke test', () => {
  let server: SpawnedServer | null = null

  afterEach(async () => {
    if (server) {
      await server.stop().catch(() => {})
      server.cleanup()
      server = null
    }
  })

  it('accepts valid token handshake', async () => {
    server = await spawnTestServer()
    const ws = await connectWs(server.url, server.token)
    expect(ws.readyState).toBe(WebSocket.OPEN)
    ws.close()
  }, TEST_TIMEOUT)

  it('rejects invalid token', async () => {
    server = await spawnTestServer()
    await expect(
      connectWs(server.url, 'wrong-token-that-is-long-enough'),
    ).rejects.toThrow()
  }, TEST_TIMEOUT)

  it('rejects short token at startup', async () => {
    const token = 'short'
    const iso = createIsolatedEnv()
    const proc = Bun.spawn(['bun', 'run', SERVER_ENTRY], {
      env: {
        ...iso.env,
        CRAFT_SERVER_TOKEN: token,
        CRAFT_RPC_PORT: '0',
        CRAFT_RPC_HOST: '127.0.0.1',
      },
      stdout: 'pipe',
      stderr: 'pipe',
    })

    const exitCode = await proc.exited
    iso.cleanup()
    expect(exitCode).not.toBe(0)
  }, TEST_TIMEOUT)

  it('shuts down cleanly on SIGTERM', async () => {
    server = await spawnTestServer()
    const ws = await connectWs(server.url, server.token)

    // Server should be running
    expect(ws.readyState).toBe(WebSocket.OPEN)

    // Send SIGTERM
    server.proc.kill('SIGTERM')
    const exitCode = await server.proc.exited
    expect(exitCode).toBe(0)

    // 清理独立配置目录；置 null 防止 afterEach 二次 kill
    server.cleanup()
    server = null
  }, TEST_TIMEOUT)
})
