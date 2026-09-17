/**
 * Markdown component exports for @craft-agent/ui
 */

export { Markdown, MemoizedMarkdown, type MarkdownProps, type RenderMode, type DisablablePreviewBlock } from './Markdown'
export { CodeBlock, InlineCode, type CodeBlockProps } from './CodeBlock'
export { preprocessLinks, detectLinks, hasLinks } from './linkify'
export { CollapsibleSection } from './CollapsibleSection'
export { CollapsibleMarkdownProvider, useCollapsibleMarkdown } from './CollapsibleMarkdownContext'
export { MarkdownDatatableBlock, type MarkdownDatatableBlockProps } from './MarkdownDatatableBlock'
export { MarkdownSpreadsheetBlock, type MarkdownSpreadsheetBlockProps } from './MarkdownSpreadsheetBlock'
export { MarkdownImageBlock, type MarkdownImageBlockProps } from './MarkdownImageBlock'
export { MarkdownDocBlock, type MarkdownDocBlockProps } from './MarkdownDocBlock'
export {
  parseMarkdownPreviewSpec,
  normalizePreviewItems,
  type MarkdownPreviewItem,
  type MarkdownPreviewSpec,
} from './markdown-preview-helpers'
export { ImageCardStack, type ImageCardStackProps, type ImageCardStackItem } from './ImageCardStack'
// TiptapMarkdownEditor is NOT re-exported here: it pulls @tiptap/extension-mathematics
// → katex (~589 kB source) into the entry chunk. Consumers import the file directly
// via '@craft-agent/ui/markdown/TiptapMarkdownEditor'.
export type { TiptapMarkdownEditorProps, MarkdownEngine } from './TiptapMarkdownEditor'
