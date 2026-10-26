/**
 * ZenSkillSettingsPage — ZenSkill 设置（第十八批 D 段 D2）
 *
 * 落点：**人称模式**（智能体怎么说话）。
 * ★ 口径（真相源 `specs/design/copy_terminology.json` 的 persona 段）：
 *   - 智能体**只有一个称呼**：「智能体」；人称模式**只改口吻，不改称呼**。
 *   - 三种模式都提供：同修（我）/ 护法（我）/ 系统（第三人称）。
 * ★ 写入后**读回对账**：set 工具返回的是**读回后的 mode**，不是回显入参
 *   （后端 `write_mode` 的既有契约）⇒ 前端按返回值更新 UI，不按入参乐观更新。
 *
 * 注册方式（craft settings 的既有扩展流程，`shared/settings-registry.ts` 头部注释）：
 *   1. SETTINGS_PAGES 加一条 → 2. 组件 → 3. SETTINGS_PAGE_COMPONENTS
 *   → 4. SETTINGS_ICONS 加图标 ⇒ 类型、路由、校验全部自动派生。
 */

import * as React from 'react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PanelHeader } from '@/components/app-shell/PanelHeader'
import { HeaderMenu } from '@/components/ui/HeaderMenu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { routes } from '@/lib/navigate'
import { Spinner } from '@craft-agent/ui'
import { toast } from 'sonner'
import { User, ShieldCheck, Cpu } from 'lucide-react'
import {
  SettingsSection,
  SettingsCard,
  SettingsRow,
  SettingsSegmentedControl,
} from '@/components/settings'
import { useAppShellContext } from '@/context/AppShellContext'
import { extractMcpJson } from '@/hooks/zenskill/useMcpTool'
import { ZENSKILL_SOURCE_SLUG } from '@/components/zenskill/zenskill-registry'
import type { DetailsPageMeta } from '@/lib/navigation-registry'

export const meta: DetailsPageMeta = {
  navigator: 'settings',
  slug: 'zenskill',
}

interface PersonaMode {
  id: string
  name: string
  pronoun?: string
  voice?: string
  sample?: string
  current?: boolean
}

interface PersonaStatus {
  ok?: boolean
  mode?: string
  mode_name?: string
  modes?: PersonaMode[]
  referring_term?: string
  current_lines?: Record<string, string>
  message?: string
}

const MODE_ICONS: Record<string, React.ReactNode> = {
  tongxiu: <User className="h-3.5 w-3.5 text-muted-foreground" />,
  hufa: <ShieldCheck className="h-3.5 w-3.5 text-muted-foreground" />,
  xitong: <Cpu className="h-3.5 w-3.5 text-muted-foreground" />,
}

export default function ZenSkillSettingsPage() {
  const { t } = useTranslation()
  const { activeWorkspaceId } = useAppShellContext()
  const [status, setStatus] = useState<PersonaStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!activeWorkspaceId) {
      setError(t('settings.zenskill.noWorkspace', '没有活动工作区 —— 先打开一个工作区'))
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await window.electronAPI.callMcpTool(
        activeWorkspaceId,
        ZENSKILL_SOURCE_SLUG,
        'persona_mode',
        { action: 'status' },
      )
      const data = extractMcpJson(result) as PersonaStatus | null
      if (!data) {
        setError(t('settings.zenskill.readFailed', '读不到人称模式'))
        setStatus(null)
      } else {
        setStatus(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('settings.zenskill.readFailed', '读不到人称模式'))
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [activeWorkspaceId, t])

  useEffect(() => {
    void load()
  }, [load])

  const switchMode = async (mode: string) => {
    if (!activeWorkspaceId || busy) return
    setBusy(true)
    try {
      const result = await window.electronAPI.callMcpTool(
        activeWorkspaceId,
        ZENSKILL_SOURCE_SLUG,
        'persona_mode',
        { action: 'set', mode },
      )
      const data = extractMcpJson(result) as PersonaStatus | null
      // ★ 按**读回值**更新（不是按入参乐观更新）—— 后端写后读回对账
      if (data && data.mode) {
        setStatus((prev) => (prev ? { ...prev, ...data } : data))
        toast.success(
          t('settings.zenskill.switched', '已切换到「{{name}}」', { name: data.mode_name ?? mode }),
        )
      } else {
        toast.error(t('settings.zenskill.switchFailed', '切换失败'))
        void load()
      }
    } catch {
      toast.error(t('settings.zenskill.switchFailed', '切换失败'))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner className="text-lg text-muted-foreground" />
      </div>
    )
  }

  const modes = status?.modes ?? []
  const current = modes.find((m) => m.id === status?.mode)
  const adviceLine = status?.current_lines?.['6:404'] ?? ''

  return (
    <div className="h-full flex flex-col">
      <PanelHeader
        title={t('settings.zenskill.title')}
        actions={<HeaderMenu route={routes.view.settings('zenskill')} />}
      />
      <div className="flex-1 min-h-0 mask-fade-y">
        <ScrollArea className="h-full">
          <div className="px-5 py-7 max-w-3xl mx-auto space-y-8">
            {error && (
              <div className="max-w-sm rounded-[8px] border border-destructive/20 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {/* 人称模式 */}
            <SettingsSection
              title={t('settings.zenskill.persona.title', '人称模式')}
              description={t(
                'settings.zenskill.persona.description',
                '只改智能体说话的口吻，不改它的称呼 —— 称呼恒为「智能体」。',
              )}
            >
              <SettingsCard divided={false}>
                <div className="px-4 py-3.5">
                  {modes.length === 0 ? (
                    <div className="text-sm text-muted-foreground">
                      {t('settings.zenskill.persona.empty', '读不到可选模式')}
                    </div>
                  ) : (
                    <SettingsSegmentedControl
                      value={status?.mode ?? ''}
                      onValueChange={(v) => void switchMode(v)}
                      options={modes.map((m) => ({
                        value: m.id,
                        label: m.name,
                        icon: MODE_ICONS[m.id],
                      }))}
                    />
                  )}
                </div>
                {current?.voice && (
                  <SettingsRow
                    label={t('settings.zenskill.persona.voice', '口吻')}
                    description={current.voice}
                    inCard
                  />
                )}
                {current?.sample && (
                  <SettingsRow
                    label={t('settings.zenskill.persona.sample', '示例')}
                    description={current.sample}
                    inCard
                  />
                )}
                {adviceLine && (
                  <SettingsRow
                    label={t('settings.zenskill.persona.adviceLine', '修炼域 · 同修建议')}
                    description={adviceLine}
                    inCard
                  />
                )}
              </SettingsCard>
            </SettingsSection>

            {/* 称呼（恒定，只读） */}
            <SettingsSection
              title={t('settings.zenskill.term.title', '称呼')}
              description={t(
                'settings.zenskill.term.description',
                '智能体只有一个称呼，三种模式都不换。',
              )}
            >
              <SettingsCard divided={false}>
                <SettingsRow
                  label={t('settings.zenskill.term.label', '对智能体的称呼')}
                  description={status?.referring_term ?? t('settings.zenskill.term.default', '智能体')}
                  inCard
                />
              </SettingsCard>
            </SettingsSection>
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
