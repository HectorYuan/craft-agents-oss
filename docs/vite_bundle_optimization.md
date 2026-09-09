# Vite Renderer Bundle 优化方案（待有 GUI 验证的机器落地）

## 现状（2026-09-09 构建数据）

| Chunk | 原始 | gzip | 说明 |
|-------|------|------|------|
| index | 4,510 kB | 1,377 kB | 主包，含全部未拆分依赖 |
| sonner | 2,262 kB | 553 kB | 已独立（多入口共享自动拆分） |
| playground | 680 kB | 255 kB | 独立入口 |
| wasm | 622 kB | 230 kB | wasm 相关 |
| emacs-lisp / cpp / wolfram… | 172-780 kB | - | 语法高亮语言包，**已按需 dynamic import** |

主包构成（sourcemap 统计，按模块数）：framer-motion/motion-dom(254)、@pierre/diffs(74)、
lucide-react(57)、markdown 生态 markdown-it/mdast/micromark/hast(~200)、react-pdf/pdfjs(19)。

结论：语言包与 sonner 已解决，剩余优化点即 index 主包内的三组大依赖。

## 方案：manualChunks 分组拆分

在 `apps/electron/vite.config.ts` 的 `build.rollupOptions` 中加入（函数式，按生态整组拆，
避免把互引模块拆散触发 "Cannot access before initialization"）：

```typescript
manualChunks(id) {
  if (!id.includes('node_modules')) return
  // PDF 渲染：react-pdf + pdfjs 整组
  if (/(react-pdf|pdfjs)/.test(id)) return 'vendor-pdf'
  // 动画：framer-motion + motion 整组
  if (/(framer-motion|motion-(dom|utils))/.test(id)) return 'vendor-motion'
  // Markdown 渲染生态：markdown-it + unified/mdast/micromark/hast 整组
  if (/(markdown-it|micromark|mdast|hast|unist|remark|rehype|unified|parse5|property-information|vfile)/.test(id)) {
    return 'vendor-markdown'
  }
}
```

预期效果：index 4.5MB → ~2.5-3MB，三个 vendor chunk 合计 ~2MB 且可并行加载、
独立缓存（升级应用代码时 vendor chunk 命中缓存，增量更新更快）。

## 落地验证清单（必须在有 GUI 的机器执行）

1. `bun run electron:build:renderer` 构建成功，无 rollup circular-dependency 警告
2. `bun run electron:dev` 启动后：
   - 主窗口首帧正常渲染（无白屏 / "Cannot access X before initialization"）
   - 打开一个带 PDF 的会话 → PDF 正常渲染（vendor-pdf chunk 按需加载路径）
   - 消息流动画正常（vendor-motion 路径）
   - Markdown 消息渲染正常，代码块高亮正常（vendor-markdown 路径）
3. DevTools Network 面板确认 file:// 下 chunk 加载顺序无 404
4. `bun run validate:dev` 全绿

## 风险与回退

- 风险：manualChunks 改变模块初始化顺序；framer-motion 与 markdown 生态互引密集，
  是循环初始化问题的高发区
- 回退：删除 manualChunks 配置即可完全恢复原状（纯构建配置，无代码耦合）
- 不建议进一步拆分 lucide-react（图标单模块极小，拆分徒增请求）与 @pierre/diffs
  （私有包，模块间耦合未知）
