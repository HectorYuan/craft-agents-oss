# Bundled Resources

This folder contains assets that are bundled with the Electron app and synced to the user's `~/.craft-agent/` directory on every launch.

## How It Works

1. **Build time**: `scripts/copy-assets.ts` copies this folder to `dist/resources/`
2. **Package time**: electron-builder includes `dist/resources/` in the app bundle
3. **Runtime**: `getBundledAssetsDir()` resolves paths to these bundled assets
4. **Launch**: Each asset type syncs to the user's home directory

## Asset Types

| Folder/File | Synced To | Sync Behavior |
|-------------|-----------|---------------|
| `docs/` | `~/.craft-agent/docs/` | Always overwrite on launch |
| `themes/` | `~/.craft-agent/themes/` | Always overwrite on launch |
| `permissions/` | `~/.craft-agent/permissions/` | Always overwrite on launch |
| `tool-icons/` | `~/.craft-agent/tool-icons/` | Always overwrite on launch |
| `release-notes/` | `~/.craft-agent/release-notes/` | Always overwrite on launch |
| `config-defaults.json` | `~/.craft-agent/config-defaults.json` | Always overwrite on launch |

## Why Sync on Every Launch?

- Ensures users always have the latest defaults/docs when the app updates
- Consistent behavior between debug and release builds
- No stale configuration causing confusion

## Other Files (Not Synced)

These files are used by electron-builder or the app directly, not synced to user home:

| File | Purpose |
|------|---------|
| `icon.*` | App icons (icns, ico, png, svg) |
| `Assets.car` | macOS compiled asset catalog |
| `dmg-background.*` | DMG installer background |
| `zenskill-logos/` | Branding assets |
| `source.png` | Default source icon |
| `generate-icons.sh` | Icon generation script |
| `bridge-mcp-server/` | Bundled MCP server for Codex/Copilot API source bridge |
| `session-mcp-server/` | Bundled MCP server for session tools |

## Single Source of Truth

The files in this folder are the **source of truth** for bundled defaults:
- Edit `config-defaults.json` here to change default settings
- Edit files in `docs/` to update documentation
- Edit files in `themes/` to update bundled themes

There is no TypeScript fallback - if the bundled JSON file is missing, the app will fail with a clear error.

## Release Notes Authoring

**`release-notes/*.md` 是生成物，禁止手写。** 唯一真相源是主仓根 `CHANGELOG.md`，由主仓 `scripts/sync_release_notes.py` 生成落盘（只含 ≤ 当前版本的精确 semver 段；`.gitattributes` 钉 `eol=lf`）。

- feature PR 的可见变更写主仓根 `CHANGELOG.md` 的 `## [Unreleased]` 段（发版时升级为版本段）；发版流程跑生成脚本落盘并随 vendor 提交。
- **`next.md` 约定已退役**（上游 craft-agents 的草稿机制，随上游 sync 可能重新带入，跑脚本即清理）。
- 门禁：CI `--check`（文件集合一致）+ 发版 G0 `--check --strict`（内容逐字节一致）。

**Why:** 原机制（版本文件由 release skill 手工归档、PR 往 next.md 追加 bullet，源自 craft-agents 上游约定）导致 GUI What's New 展示的是上游英文更新日志、与 ZenSkill 版本线错位（未读红点比对上游 0.13.3）。2026-10-10 换源为根 CHANGELOG 生成；上游 sync 的更新日志整合规则见主仓 `docs/gui_upgrade_mechanism.md` §3.4 与 `DELETED_UPSTREAM_FILES.md`。
