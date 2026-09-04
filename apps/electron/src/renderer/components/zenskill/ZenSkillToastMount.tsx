/**
 * ZenSkillToastMount — Global listener for zenskill:changed achievement
 * unlocks. Mounted from AppShell so unlock toasts surface even when the
 * user is in the chat view (the main unlock scene) where ZenSkillDataPanel
 * is not mounted. Toast-only; data refresh stays in ZenSkillDataPanel.
 */
import * as React from 'react'
import { toast } from 'sonner'

export function ZenSkillToastMount() {
  React.useEffect(() => {
    if (!window.electronAPI?.onZenSkillChanged) return
    const cleanup = window.electronAPI.onZenSkillChanged((_wsId, data) => {
      const unlocks = (data as { newAchievements?: string[] })?.newAchievements
      if (Array.isArray(unlocks) && unlocks.length > 0) {
        toast.success(`🏆 解锁成就：${unlocks.join('、')}`)
      }
    })
    return cleanup
  }, [])

  return null
}
