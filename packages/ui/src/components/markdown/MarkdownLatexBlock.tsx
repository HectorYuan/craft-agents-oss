import * as React from 'react'
import { cn } from '../../lib/utils'

interface MarkdownLatexBlockProps {
  code: string
  className?: string
}

/**
 * MarkdownLatexBlock - Renders fenced ```latex / ```math code blocks as display math.
 *
 * Uses KaTeX to render LaTeX source into styled HTML.
 * On parse errors, shows the raw source with an error message.
 */
export function MarkdownLatexBlock({ code, className }: MarkdownLatexBlockProps) {
  // KaTeX (~589 kB source) is loaded on demand — latex fences are rare, and
  // the library must not sit in the entry chunk. While the dynamic import
  // resolves (or on error) the raw source is shown in a code block, mirroring
  // the MarkdownMermaidBlock fallback pattern.
  const [html, setHtml] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    setHtml(null)
    import('katex')
      .then((katex) => {
        if (cancelled) return
        try {
          setHtml(katex.renderToString(code.trim(), {
            displayMode: true,
            throwOnError: false,
            strict: false,
          }))
        } catch {
          setHtml(null)
        }
      })
      .catch(() => {
        if (!cancelled) setHtml(null)
      })
    return () => {
      cancelled = true
    }
  }, [code])

  if (!html) {
    return (
      <pre className={cn('font-mono text-sm whitespace-pre-wrap text-destructive', className)}>
        <code>{code}</code>
      </pre>
    )
  }

  return (
    <div
      className={cn('overflow-x-auto py-2', className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
