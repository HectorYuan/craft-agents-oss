import * as React from 'react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { PageTemplateInfo } from '@craft-agent/shared/pages/types'

interface NewPageFromTemplateDialogProps {
  open: boolean
  workspaceId: string | null
  onOpenChange: (open: boolean) => void
  /** Called with the new page's slug after a successful create (navigation) */
  onCreated: (slug: string) => void
}

type TemplateLoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; templates: PageTemplateInfo[] }

/**
 * "New from template" — lists the on-disk template pool, optionally renames,
 * then instantiates via CREATE_FROM_TEMPLATE (mirrors `zenskill pages create
 * --from-template`). The pages list refreshes through the pages:changed push;
 * on success we navigate straight to the new page (same as blank create).
 */
export function NewPageFromTemplateDialog({
  open,
  workspaceId,
  onOpenChange,
  onCreated,
}: NewPageFromTemplateDialogProps) {
  const { t } = useTranslation()
  const [state, setState] = React.useState<TemplateLoadState>({ status: 'loading' })
  const [selected, setSelected] = React.useState<string | null>(null)
  const [name, setName] = React.useState('')
  const [creating, setCreating] = React.useState(false)

  // Load the pool on every open (cheap local fs scan), reset transient state
  React.useEffect(() => {
    if (!open) return
    let stale = false
    setState({ status: 'loading' })
    setSelected(null)
    setName('')
    void window.electronAPI.listPageTemplates().then(
      templates => {
        if (!stale) setState({ status: 'ready', templates })
      },
      err => {
        if (!stale) {
          setState({ status: 'error', message: err instanceof Error ? err.message : String(err) })
        }
      },
    )
    return () => {
      stale = true
    }
  }, [open])

  const handleCreate = React.useCallback(async () => {
    if (!workspaceId || !selected || creating) return
    setCreating(true)
    try {
      const trimmed = name.trim()
      const created = await window.electronAPI.createPageFromTemplate({
        workspaceId,
        templateSlug: selected,
        ...(trimmed ? { name: trimmed } : {}),
      })
      onOpenChange(false)
      onCreated(created.slug)
    } catch (err) {
      toast.error(t('toast.pageCreateFromTemplateFailed'), {
        description: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setCreating(false)
    }
  }, [workspaceId, selected, creating, name, onOpenChange, onCreated, t])

  const templates = state.status === 'ready' ? state.templates : []
  const canCreate = state.status === 'ready' && !!selected && !creating

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('pages.templatePicker.title')}</DialogTitle>
          <DialogDescription>{t('pages.templatePicker.description')}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[40vh] overflow-y-auto">
          {state.status === 'loading' ? (
            <div className="py-6 text-center text-sm text-foreground/50">
              {t('pages.templatePicker.loading')}
            </div>
          ) : state.status === 'error' ? (
            <div className="py-6 text-center text-sm text-destructive">{state.message}</div>
          ) : templates.length === 0 ? (
            <div className="py-6 text-center text-sm text-foreground/50">
              {t('pages.templatePicker.empty')}
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {templates.map(template => (
                <button
                  key={template.slug}
                  type="button"
                  onClick={() => setSelected(template.slug)}
                  className={
                    selected === template.slug
                      ? 'rounded-lg border border-foreground/25 bg-foreground/[0.05] px-3 py-2 text-left'
                      : 'rounded-lg border border-border px-3 py-2 text-left transition-colors hover:bg-foreground/[0.03]'
                  }
                >
                  <span className="block text-sm font-medium">{template.name}</span>
                  {template.description ? (
                    <span className="mt-0.5 block text-xs text-foreground/50">
                      {template.description}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="page-template-name" className="text-xs font-medium text-foreground/70">
            {t('pages.templatePicker.nameLabel')}
          </label>
          <Input
            id="page-template-name"
            value={name}
            onChange={event => setName(event.target.value)}
            placeholder={t('pages.templatePicker.namePlaceholder')}
          />
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={creating}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleCreate} disabled={!canCreate}>
            {creating ? t('pages.templatePicker.creating') : t('pages.templatePicker.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
