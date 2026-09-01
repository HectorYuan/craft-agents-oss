# 已删除的上游文件清单

> 本仓库（HectorYuan/craft-agents-oss fork）为 ZenSkill 专用发行版，已移除
> Pi / Claude 后端（唯一后端为 zenskill）。上游自动同步产生合并冲突时，
> 按本清单复删并重放类型收窄，然后删除本清单中对应条目。

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
