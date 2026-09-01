# 已删除的上游文件清单

> 本仓库（HectorYuan/craft-agents-oss fork）为 ZenSkill 专用发行版，已移除
> Pi / Claude 后端（唯一后端为 zenskill）。上游自动同步产生合并冲突时，
> 按本清单复删并重放类型收窄，然后删除本清单中对应条目。

## P2 — Claude 线（P1 之后提交）

### 删除的文件
- `packages/shared/src/agent/claude-agent.ts`（3175 行，ClaudeAgent 主类）
- `packages/shared/src/agent/claude-llm-query.ts`、`claude-sdk-error-mapper.ts`
- `packages/shared/src/agent/backend/internal/drivers/anthropic.ts` + test
- `packages/shared/src/agent/backend/claude/`（event-adapter / persistent-input
  / task-notification / session-tool-parity 等）
- Claude 专属测试：claude-event-adapter / claude-sdk-error-mapper /
  claude-background-message-routing / claude-thinking-config /
  claude-agent-handoff / query-llm-partial-output / claude-agent-spawn-cwd /
  browser-tools 等

### 抢救到中性位置
- `backend/persistent-input.ts`（自 backend/claude/ 移出）——
  `resolveKeepBackgroundTasksAlive` 被 SessionManager 活引用
- `agent/json-prop-to-zod.ts`（自 claude-agent.ts 抽出）——纯 zod 工具，
  json-prop-to-zod.test 继续使用
- `AgentEvent` 类型 re-export 改为直连 `@craft-agent/core/types`

### 修改的行为（上游 sync 冲突高发点）
- `ModelProvider = 'zenskill'`（唯一值）；`ANTHROPIC_MODELS = MODEL_REGISTRY` 别名
- factory：anthropic driver/case/分支全删；`resolveSessionBackendContext`
  provider 恒 zenskill；`validateStoredBackendConnection` 恒 success；
  `resolveSetupTestConnectionHint` 签名放宽 provider: string（恒 zenskill 返回）
- `domain/connection-setup-logic.ts`：validateSetupTestInput 简化（pi 校验移除）
- SessionManager：branch anchor 的 anthropropic/pi 分支折叠为统一 turnId 语义

### ⚠️ 依赖保留（P3 待做）
- `@anthropic-ai/claude-agent-sdk` 未卸载：共享工具层
  `llm-tool.ts` / `session-scoped-tools.ts` / `browser-tools.ts` 的
  `tool()`/`createSdkMcpServer()` 被 zenskill-agent 复用。卸载需先把工具
  schema 构造去 SDK 化（zod 直构），属独立重构

## P1 — Pi 线（commit：本文件引入的提交）

### 删除的文件/目录
- `packages/shared/src/agent/pi-agent.ts`（PiAgent 主类）
- `packages/shared/src/agent/backend/pi/`（event-adapter / constants / index）
- `packages/shared/src/agent/backend/internal/drivers/pi.ts` + `pi.test.ts`
- `packages/shared/src/auth/github-copilot.ts` + 其 test（Pi 的 copilot auth）
- `packages/pi-agent-server/`（整包——Pi 后端运行时，27MB bundle 根源）
- Pi 专属测试：`pi-agent-*.test.ts`、`pi-event-adapter.test.ts`、
  `pi-query-llm.test.ts`、`pi-browser-tool*.test.ts`、
  `browser-tools-remote.test.ts`（读 pi-agent.ts 源码做契约断言）

### 保留但不再导出运行时
- `packages/shared/src/config/models-pi.ts` —— 仅迁移测试的 fixture 数据依赖；
  `piModelToDefinition` 的 `provider` 字段已标 `'zenskill'`（原 'pi'）

### 修改的类型（上游 sync 冲突高发点）
- `config/models.ts`：`ModelProvider = 'anthropic' | 'zenskill'`（去 `'pi'`）
- `config/llm-connections.ts`：`LlmProviderType` 仍含 `'pi'/'pi_compat'`
  （storage legacy 迁移需要），但运行时不 import pi SDK
- `protocol/dto.ts`：`TestLlmConnectionParams.provider = 'anthropic' | 'zenskill'`

### 修改的行为（上游 sync 时需保留我方语义）
- `factory.ts`：case 'pi' 删除；`getAvailableProviders() → ['zenskill']`；
  `resolveSetupTestConnectionHint` 恒返回 zenskill
- `domain/connection-setup-logic.ts`：`validateSetupTestInput` 恒 valid（pi
  custom-endpoint 校验删除）
- `server-core/handlers/rpc/llm-connections.ts`：copilot 4 个 + pi 3 个 RPC
  handler 删除
- `package.json` 脚本：`server:build:subprocess` / `typecheck:all` 去掉
  pi-agent-server 环节

### 卸载的依赖
- `@earendil-works/pi-agent-core`（packages/shared）
- `packages/pi-agent-server` 的整棵依赖树（pi-coding-agent / koffi / jiti 等，
  随包删除）

### 收益
- server bundle 27.19MB → 4.55MB（-83%）
- 源码 -8,500+ 行
