/**
 * SkillGraphRedirect — 跳转到 Craft Pages 版技能图谱。
 *
 * GUI 存在两个技能图谱入口（页面区 Craft Page + ZenSkill 导航区 React 组件）。
 * Circle Packing 重写只落在 Craft Page（index.html），为消除双维护，
 * ZenSkill 导航区的 skill-graph 统一重定向到 Pages 版：
 * routes.pages('zenskill-skill-graph') → pages/page/zenskill-skill-graph。
 */
import { useEffect } from 'react'
import { useNavigation } from '@/contexts/NavigationContext'
import { routes } from '@/lib/navigate'
import { LoadingIndicator } from '@craft-agent/ui'
import type { ZenSkillPageProps } from '../zenskill-registry'

export function SkillGraphRedirect(_props: ZenSkillPageProps) {
  const { navigate } = useNavigation()

  useEffect(() => {
    navigate(routes.view.pages('zenskill-skill-graph'))
  }, [navigate])

  return (
    <div className="flex h-full items-center justify-center">
      <LoadingIndicator label="Skill Graph" />
    </div>
  )
}
