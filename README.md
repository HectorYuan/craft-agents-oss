# ZenSkill

ZenSkill 是一个 agent 原生的桌面工作台：在统一的界面中管理多会话、连接 MCP 服务器 / REST API / 本地文件系统等多种数据源，并以技能（Skills）、自动化与权限分级组织人机协作工作流。

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

## 从源码构建

依赖：[Bun](https://bun.sh/) ≥ 1.2、Node.js（供 npx/electron-builder 使用）。

```bash
# 1. 安装依赖（monorepo 根目录）
bun install

# 2. 构建 Electron 各端产物（main / preload / renderer / resources / assets）
bun run electron:build

# 3. 打包安装程序
npx electron-builder --win --x64     # Windows（NSIS，产物 ZenSkill-x64.exe）
npx electron-builder --mac --arm64   # macOS（产物 ZenSkill-arm64.dmg）
npx electron-builder --linux --x64   # Linux（产物 ZenSkill-x86_64.AppImage）
```

也可使用各平台的端到端脚本（含 Bun 运行时内置、SDK 暂存等完整流程）：

- Windows：`apps/electron/scripts/build-win.ps1`
- macOS：`apps/electron/scripts/build-dmg.sh`
- Linux：`apps/electron/scripts/build-linux.sh`

日常开发：

```bash
bun run electron:dev     # 热重载开发
bun run electron:start   # 构建并运行
bun run typecheck:all    # 类型检查
```

## 数据目录

桌面端数据（配置、凭据、会话、来源、技能等）默认存放于 **`~/.zenskill/desktop/`**：

```
~/.zenskill/desktop/
├── config.json              # 主配置（workspaces、LLM 连接）
├── credentials.enc          # 加密凭据（AES-256-GCM）
├── preferences.json         # 用户偏好
├── theme.json               # 应用级主题
└── workspaces/
    └── {id}/
        ├── config.json      # 工作区设置
        ├── sessions/        # 会话数据（JSONL）
        ├── sources/         # 已连接来源
        ├── skills/          # 自定义技能
        └── statuses/        # 状态配置
```

- 可用 `ZENSKILL_CONFIG_DIR` 环境变量覆盖数据目录；遗留的 `CRAFT_CONFIG_DIR` 仍被兼容读取。
- 从旧版本（`~/.craft-agent`）升级时，应用会在启动最早期执行一次性迁移：复制 → 校验 → 旧目录改名为 `~/.craft-agent.migrated-bak`（不删除）。设置 `ZENSKILL_DATA_MIGRATE=0` 可跳过迁移。

## 深链

外部应用可通过 `zenskill://` URL 唤起导航，例如 `zenskill://settings`、`zenskill://action/new-chat`。

## 致谢与上游

本项目 fork 自 [craft-agents-oss](https://github.com/lukilabs/craft-agents-oss)（Craft Agents，by Craft Docs Ltd.），并在此基础上完成了 ZenSkill 品牌化改造与功能集成。感谢上游项目的开源贡献。

- 本仓库基于 Apache License 2.0 许可发布，见 [LICENSE](LICENSE)。
- 依据 Apache-2.0 的保留义务，上游版权与商标声明保留于 [NOTICE](NOTICE) 与 [TRADEMARK.md](TRADEMARK.md)。
- 本项目使用 [Claude Agent SDK](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)，其受 [Anthropic Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms) 约束。
