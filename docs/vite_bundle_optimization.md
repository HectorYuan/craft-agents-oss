# Vite Renderer Bundle 优化方案 v2

> v1（manualChunks 分组搬运）已被 v2 取代：sourcemap 字节级分析发现优化收益主要在
> 源码级改造（lazy 化 + 修复 tree-shaking 失效），而非 chunk 分组搬运。
> 分析基线：2026-09-09 构建（docs 同期 commit）。

## 优化点清单（按收益排序）

### P0-1 lucide-react 全量打包（1,417 kB 源码）— tree-shaking 失效

- 根因：3 个文件使用命名空间导入，显式绕过 tree-shaking，全量 1,500+ 图标进包：
  - `src/renderer/components/app-menu/MobileMenuPage.tsx:2`
  - `src/renderer/components/app-menu/DesktopAppMenu.tsx:3`
  - `src/renderer/components/browser/BrowserTabStrip.tsx:10`
- 副作用：lucide 被三入口（main/playground/toolbar）共享，rollup 将其与 sonner
  同桶，导致 sonner chunk 2.2MB 名不副实
- 修法：枚举显式导入。三处均为"图标名 → 组件"的固定菜单映射，把清单内图标
  逐个 `import { X, Y } from 'lucide-react'` 后建局部映射表即可，业务逻辑零改动
- 预期：lucide 1,417 kB → ~30-80 kB；sonner chunk 2.2MB → ~100 kB

### P0-2 elkjs 1,589 kB（经 beautiful-mermaid 静态进主包）

- 引用链：`packages/ui/src/components/markdown/MarkdownMermaidBlock.tsx:2`
  静态 `import { renderMermaidSVG } from 'beautiful-mermaid'`
  → beautiful-mermaid 依赖 elkjs（`elk.bundled.js`，预打包 bundle，不可 tree-shake）
- 不合理点：mermaid 图仅在消息含 mermaid 代码围栏时才需要，所有会话首屏却
  为其付出全量代价
- 修法：组件已有 CodeBlock error-fallback 路径，改造模式：
  1. `React.lazy(() => import('./MermaidDiagram'))` 拆出内层渲染组件
  2. 外层默认渲染 CodeBlock（现有 fallback UI），Suspense resolved 后替换为 SVG
  3. `renderMermaidSVG` 调用移入内层组件（接口不变）
- 预期：主包 -1.6MB 源码（min 后约 -700 kB）

### P1-3 katex 589 kB（数学公式渲染）

- 引用：`packages/ui/src/components/markdown/Markdown.tsx:3` 的 `rehype-katex`
  插件 + `katex.min.css`
- 修法（成本中等）：unified 管线按「是否含公式定界符」条件挂载插件，
  rehype-katex 与 katex 经 dynamic import 加载；CSS 移入公式组件作用域
- 备选：若管线条件化侵入性强，先做 markdown 渲染器整体 lazy（见 P1-5）

### P1-4 pdfjs-dist 766 kB（PDF 渲染）

- 引用：`packages/ui/src/components/markdown/MarkdownPdfBlock.tsx`、
  `packages/ui/src/components/overlay/PDFPreviewOverlay.tsx`
- 修法：两处均为"PDF 块 / 预览浮层"组件，天然 lazy 边界——
  `React.lazy` 包裹即可，导出接口不变
- 预期：主包 -766 kB 源码

### P2-5 其余主包常驻（可视情况）

- markdown-it 230 kB + parse5 337 kB + unified 生态：核心消息渲染路径，
  **不建议拆**（首屏必需，拆了只增请求数）
- motion-dom 310 kB（framer-motion）：应用级动画基座，保留
- prosemirror-view 239 kB + @tiptap/core 214 kB：编辑器，若编辑器入口已
  按需（仅进入编辑态挂载）可随编辑器 lazy；当前静态进主包，改造点在
  TiptapMarkdownEditor 的挂载方式
- @pierre/diffs 204 kB：私有包，耦合未知，不动

## 已排除的误判

- ~~语法高亮语言包（emacs-lisp 780 kB 等）~~：已是按语言 dynamic import 的
  独立 chunk，无需处理
- ~~sonner 本体过大~~：实际仅 64 kB，2.2MB 是 lucide 全量打包的连带症状

## 实施批次与验证

| 批次 | 内容 | 预期主包收益 | 风险 |
|------|------|-------------|------|
| B1 | P0-1 lucide 显式导入 | min 后 -600 kB 量级 | 低（纯导入改写） |
| B2 | P0-2 mermaid lazy | min 后 -700 kB 量级 | 中（异步渲染时序） |
| B3 | P1-4 pdf lazy | min 后 -350 kB 量级 | 低（组件级 lazy） |
| B4 | P1-3 katex 条件化 | min 后 -250 kB 量级 | 中（管线重构） |
| 备选 | v1 的 manualChunks | 零收益搬运 | 见 git 历史 |

每个批次落地后验证：`vite build` 成功 → `electron:dev` 真机
（首帧 / PDF / mermaid 图 / 数学公式 / 图标菜单五点回归）→ `validate:dev` 全绿。

## 当前基线指标（优化前）

```
index-bs6RhbaU.js           4,510.69 kB │ gzip: 1,376.86 kB
sonner-B1zgbkYK.js          2,261.82 kB │ gzip:   552.55 kB
```

主包 Top10（sourcemap sourcesContent 字节）：elkjs 1589k / pdfjs-dist 766k /
katex 589k / parse5 337k / beautiful-mermaid 328k / motion-dom 310k /
prosemirror-view 239k / markdown-it 230k / @tiptap/core 214k / @pierre/diffs 204k
