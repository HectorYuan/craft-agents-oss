/**
 * ErrorBoundary — 通用 React 错误边界组件
 *
 * 捕获子组件渲染错误，显示降级 UI 而非白屏。
 * 支持自定义 fallback、错误上报、重试按钮。
 */
import React, { Component, type ReactNode, type ErrorInfo } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
// ★ 第二十二批 D-3 第二批：本组件是**类组件** ⇒ 不能用 `useTranslation` hook，
// ★ 也不用给 `withTranslation` HOC（★ vendor 里无先例 ⇒ 会引入类型风险）⇒
// ★ 直接用 i18n 实例（★ 与 `CalendarPanel` 同样从 `@craft-agent/shared/i18n` 取）
import { i18n } from '@craft-agent/shared/i18n'

interface ErrorBoundaryProps {
  children: ReactNode
  /** 自定义 fallback UI */
  fallback?: ReactNode
  /** 错误上报回调 */
  onError?: (error: Error, errorInfo: ErrorInfo) => void
  /** 组件名称（用于错误日志） */
  componentName?: string
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[ErrorBoundary${this.props.componentName ? `:${this.props.componentName}` : ''}]`, error, errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="rounded border border-destructive/20 bg-destructive/5 p-3 text-xs">
          <div className="flex items-center gap-2 text-destructive mb-2">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span className="font-medium">组件渲染错误</span>
          </div>
          <div className="text-muted-foreground mb-2 truncate" title={this.state.error?.message}>
            {this.state.error?.message || i18n.t('toast.unknownError')}
          </div>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-1 px-2 py-1 rounded bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground text-sm transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            {i18n.t('common.retry')}
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
