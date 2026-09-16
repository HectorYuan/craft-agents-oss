# 多会话产物整合工作流（craft-agents fork）

> 背景：多个并行会话（fork 主线会话、GUI 批次会话、主仓库 zenskill 会话、
> windows 合并会话）在同一仓库工作，产物散落在分支、工作区、stash、游离
> 提交中。本文沉淀 2026-09-15/16 两轮整合的实战流程，供后续会话复用。

## 一、盘点：先找齐所有产物（5 个位置）

```bash
git fetch --all                      # 1. remote 分支（fork/* 与 origin/*）
git branch -vv                       # 2. 本地分支与领先/落后
git status --short                   # 3. 工作区（注意：不要带过滤 grep，
                                     #    过滤曾漏看 DU 冲突与 package.json 标记）
git stash list                       # 4. stash（历史 WIP）
git reflog --date=short | head -30   # 5. reflog——丢失的 rebase/pick/reset 痕迹
find . -name "*.rej" -o -name "*.orig" | grep -v node_modules   # 6. 补丁残渣
```

实战教训：本轮 reflog 发现了另一会话 `pull --rebase` 中止的现场
（rebase abort 会静默丢弃工作区改动），git status 则漏过 5 个带
冲突标记的文件（filter 把非 UU 状态的 modified 行滤掉了）。

## 二、整合顺序（安全边界从大到小）

### 1. 已推送的 remote 分支 → `git merge`（不 rebase 已推分支）
- 冲突解决原则：**语义优先于文本**——对比两侧修法，取更完整的一方，
  并把另一方的根因信息以注释并入（实例：zenskill-agent.ts 的 --model
  冲突，取主仓库侧的注册表校验版本 + 并入我方 401 挂起根因注释）。
- 冲突类型不止 UU：**DU/UD/AU/UA/DD**（一方删除另一方修改）同样阻断
  提交。检查用 `git status --short | grep -E "^(DD|AU|UD|UA|DU|AA|UU)"`。

### 2. 游离提交（reflog 中的 rebase pick 残留）
- 判定是否为空提交：`git diff <parent> <commit> --stat`；树相同 = 空提交。
- 内容是否已在主线：`git show <commit>` 的功能清单与主线代码比对
  （本轮 f5fda599 "ZenskillBackend full optimization" 的全部功能点
  已在 main 的 zenskill-agent.ts，实为空提交，无需找回）。

### 3. 工作区残骸（最高风险，逐文件判定）
- **冲突标记文件**：`grep -rln "^<<<<<<< HEAD" --include=...` 全仓扫
  （只查 .ts/.tsx 会漏 .json/.yml）。先分清三方：HEAD 版本 /
  基点版本 / 来线版本，与对应分支 `git show <branch>:<file>` 比对后
  取正确版本或手工融合；**JSON 文件必须 `python3 -m json.tool` 验证**
  （本轮 5 个带标记 JSON 破坏了 exports 解析，引发 139 个测试假失败）。
- **untracked 半成品**：先 `git log --all -- <path>` 查是否已有权威版本，
  再决定入库 / 移入备份目录（`/tmp/<repo>-debris-backup/`）保留观察期，
  不直接 rm。
- **DU 等删除类冲突**：确认删除方意图（grep 主线代码验证功能已被替代）
  后按删除方收口。

### 4. stash
逐个 `git stash show --stat` 比对主线：内容已被后续提交覆盖的 stash
可 drop；仍独特的（如 stash@{1} 的 zenskill-agent 4 行改动）需人工
合并。stash 不是保险箱——abort/reset 不影响它，但容易遗忘腐化。

### 5. 提交后验证闭环（每次整合必跑）
```
typecheck:all（0 错误）
bun run lint（0 error）
bun test（与基线对比，新失败逐个归因）
真机冒烟（涉及 renderer/engine 时）
```

## 三、预防规范（本轮事故对应的每一条）

1. **提交前核对**：`git diff --cached --stat` 的文件数与改动内容是否
   符合预期——`git add -A` 曾把 2352 个 .mimosa 会话状态文件卷入
   commit（已回滚重提，.gitignore 已补 .mimosa/）。
2. **status 不加过滤**：查看工作区一律裸 `git status --short`，
   需要聚焦再临时 grep——过滤曾导致 DU 冲突与 package.json 标记漏检。
3. **分支切换前清场**：status 非空不切分支（win-merge 会话切分支
   曾导致并行会话的提交落错分支）。
4. **rebase 中止后立刻盘点**：abort 丢弃的工作区改动不进 stash、
   不进 reflog 的可恢复区，等价于丢失——中止后立即 `git status` +
   比对分支内容（本轮实测：空提交场景无损失，但流程必须走）。
5. **跨会话提交互相通报**：并行会话共用工作区时（实例：主仓库会话
   08dd2bc0 补交了我方工作区的 W2 改动），提交/合并前先看
   `git log --oneline -5` 是否有他人新提交。

## 四、本轮（2026-09-16）整合台账

| 产物 | 位置 | 处置 | 结果 |
|------|------|------|------|
| zenskill-main 20 提交 | fork/zenskill-main | merge（3 UU 冲突解决） | 739af257 |
| rebase 中断残骸（5 冲突标记 JSON + DU 文件 + untracked 半成品） | 工作区 | HEAD 恢复 + 备份 /tmp/zenskill-rebase-debris-backup | 门禁恢复全绿 |
| tsconfig.base.json（session-mcp-server 既有引用） | 工作区 untracked | 入库 | 1f6b510c |
| W2 FreeFormInput 改动 | 工作区（主仓库会话已补交 08dd2bc0） | 确认已在历史 | — |
| f5fda599 ZenskillBackend optimization | reflog（rebase pick 残留） | 空提交，功能已在 main | 无需处理 |
| OAuth UA / playground 品牌残留 | 工作区 | 替换 | a808cd27 |

## 五、当前待整合清单（按优先级）

1. **origin/main 的 v0.13.3（e8963854）**：上游版本提交，63 文件
   （含官方 tsconfig.base.json——与本轮入库版本重合，需比对收敛；
   scripts/check-i18n-coverage.ts、release-notes 机制等）。
   合并预计冲突面大（vs main 的 149 个 fork 提交），建议独立一轮执行。
2. **stash@{1}**：zenskill-agent.ts 4 行改动 + SessionManager 2 行——
   人工比对是否已被我方/主仓库会话修复覆盖，未覆盖则并入。
3. **stash@{0} / stash@{2}**：i18n locale 调整与 ZenSkillDataPanel
   重组——zenskill-main 已做同类变更，比对后大概率可 drop。
4. **win-merge 本地分支**：其唯一提交 0b33f437 内容已被 main 的
   35d4de13 替代 → `git branch -D win-merge`（fork/windows remote
   不受影响，需另行同步）。
5. **fork remote 其他分支**（fix/issues-804-798、obalint/feb-5）：
   未评估，整合前先 `git log main..` 看独有提交量。
6. **/tmp/zenskill-rebase-debris-backup/**：观察期后删除。
