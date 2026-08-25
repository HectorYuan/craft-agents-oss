# ZenSkill for Craft Agents

此目录是 ZenSkill 的打包入口。构建时由 `build-win.ps1` / `build-dmg.sh` 从
`/home/hector/DevSpace/ZenSkill/` 复制源码到此处。

## 目录结构

```
zenskill/
├── pyproject.toml          # uv 项目配置
├── uv.lock                 # 依赖锁（构建时生成）
├── zenskill/               # 源码（从 ZenSkill 仓库复制）
│   ├── __init__.py
│   ├── __main__.py
│   ├── core/               # 核心模块
│   ├── runtime/            # Agent 引擎
│   ├── tui/                # TUI (Rich)
│   ├── server/             # WebUI server
│   └── ...
└── vendor/                 # 子模块（可选）
```

## 构建流程

```bash
# Windows
.\scripts\build-win.ps1

# macOS
./scripts/build-dmg.sh
```

构建脚本会：
1. 复制 ZenSkill 源码到此目录
2. 用 uv 生成 uv.lock
3. 打包到 Electron extraResources
