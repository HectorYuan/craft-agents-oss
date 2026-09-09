# 上游 react-hooks/exhaustive-deps 101 处批次计划

> 全部为 warning，不阻塞任何门禁。本计划供上游同步 / 专项批次使用。
> 原则：每批只动 1-2 个文件，修完即跑组件测试 + 真机冒烟。
> zenskill 自有文件的 3 处已于 5262ca25 修复，不在本计划内。

## 分布（33 文件，Top6 占 55 处）

```
14  components/app-shell/input/FreeFormInput.tsx
11  App.tsx
10  components/app-shell/AppShell.tsx
 8  pages/ChatPage.tsx
 7  hooks/useEntityListInteractions.ts
 5  components/app-shell/ChatDisplay.tsx
 5  components/app-shell/SessionList.tsx
 4  hooks/useAutomations.ts
 3  components/app-shell/SendToWorkspaceDialog.tsx
 3  pages/SourceInfoPage.tsx
46  其余 23 文件各 1-2 处
```

## 四种模式与修法（按风险分组）

### 模式 A：缺失稳定引用 — 直接补依赖（零风险，~40 处）

抽样实据：App.tsx 的 `setWindowWorkspaceId`（×4 处缺失）、i18n `t`（×2）。
React setState setter 引用恒定；`t` 由 useTranslation 返回且引用稳定。
补进依赖数组不改变行为，纯消除警告。

### 模式 B：`?? []` / `||` 兜底逻辑表达式未 memo 化 — 提为 useMemo（低风险，~15 处）

抽样实据：FreeFormInput.tsx:327 的 `llmConnections` 逻辑表达式被 3 个
下游 useMemo 依赖。与 zenskill 批次（5262ca25 ZenSkillSkillGraph 修复）同款：
表达式提为 `useMemo(..., [源头 data])`，下游 memo 恢复缓存语义。
附带真实性能收益（消除每帧新引用）。

### 模式 C：缺失回调 / 对象依赖 — 需逐一分析（中风险，~30 处）

抽样实据：App.tsx 的 `handleInputChange`、`handleOpenSettings`、
`store` + `windowWorkspaceSlug`（1431 行 useCallback）。补依赖前必须确认：
回调是否已 useCallback 化？补入后 effect 触发面是否扩大（如触发保存/重连）？
未 memo 化的回调补依赖 = 每帧重触发 effect，反而引入 bug。
修法顺序：先给回调补 useCallback → 再补 effect 依赖 → 验证触发时序。

### 模式 D：ref 值捕获 / unnecessary dependency — 个案（~15 处）

- `draftSaveTimeoutRef.current`（App.tsx:1463）：cleanup 引用 ref.current 会在
  执行时取到最新值而非挂载时值——经典 bug 温床，修法是 effect 体内先
  `const timeout = ref.current` 再在 cleanup 用局部变量。**这是潜在真 bug，优先修**
- `unnecessary dependency: sessionOptions`（App.tsx:1454）：删除多余依赖，
  但需确认删除后 effect 读到的确实是快照而非过期值

## 批次划分

| 批次 | 文件 | 处数 | 模式 | 预估 |
|------|------|------|------|------|
| W1 | App.tsx | 11 | D(1真bug) + A + C | 0.5 天 |
| W2 | FreeFormInput.tsx | 14 | B(3) + C | 0.5 天 |
| W3 | AppShell.tsx + ChatDisplay.tsx | 15 | 混合 | 0.5 天 |
| W4 | ChatPage.tsx + SessionList.tsx | 13 | 混合 | 0.5 天 |
| W5 | useEntityListInteractions + useAutomations + 其余 hooks | 13 | 混合 | 0.5 天 |
| W6 | 其余 23 小文件 | 35 | 多为 A | 1 天 |

每批验收：`bun x eslint <files>` 归零 → `bun test apps/electron` 全绿 →
真机冒烟（该文件对应 UI：输入框发消息 / 会话切换 / 设置打开等）。

## 建议优先级

W1（含模式 D 的 ref 捕获真 bug）> W2 > 其余。W6 可在用户无感知的
A 类模式下批量快跑。
