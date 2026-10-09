/**
 * Windows 系统托盘驻留（状态栏图标）。
 *
 * 2026-10-07 用户反馈：Windows 无状态栏驻留——macOS 有 Dock 常驻语义，
 * Windows 关窗即退（window-all-closed → quit），托盘不存在。本模块补齐：
 * 托盘图标常驻 + 单击唤起主界面 + 菜单（显示主界面/退出）；
 * window-all-closed 在 Windows 改为驻留后台（index.ts 配套改动）。
 *
 * 仅 win32 启用：macOS 用 Dock（activate 已有复建逻辑），Linux 托盘依赖
 * libappindicator 环境差异大，暂不开启。失败静默降级（托盘属增强件，
 * 不得阻塞启动——与 notification/power-manager 同策略）。
 */
import { app, Menu, Tray, BrowserWindow, nativeImage } from 'electron'
import path from 'path'
import { mainLog } from './logger'
import type { WindowManager } from './window-manager'

let tray: Tray | null = null

function trayIcon(): Electron.NativeImage | undefined {
  // 打包与开发一致：dist/resources 是 resources 的构建期副本
  // （electron-build-resources.ts cpSync；asar: false）
  const iconPath = path.join(__dirname, 'resources', 'icon.ico')
  try {
    const img = nativeImage.createFromPath(iconPath)
    if (img.isEmpty()) return undefined
    return img
  } catch {
    return undefined
  }
}

export function createTray(
  windowManager: WindowManager,
  reopenLastWorkspace: () => void,
): void {
  if (process.platform !== 'win32') return
  if (process.env.CRAFT_HEADLESS) return
  try {
    if (tray) return
    const icon = trayIcon()
    if (!icon) {
      mainLog.error('[tray] icon.ico missing, tray skipped')
      return
    }
    tray = new Tray(icon)
    tray.setToolTip('ZenSkill')

    const zh = app.getLocale().toLowerCase().startsWith('zh')
    const show = (): void => {
      const windows = BrowserWindow.getAllWindows()
      if (windows.length > 0) {
        const win = windows[0]
        if (win.isMinimized()) win.restore()
        win.show()
        win.focus()
        return
      }
      // 无窗口（关窗驻留后）——复用 index.ts 的 activate 复建语义
      try {
        reopenLastWorkspace()
      } catch (error) {
        mainLog.error('[tray] failed to reopen window:', error)
      }
    }

    const menu = Menu.buildFromTemplate([
      { label: zh ? '显示主界面' : 'Show ZenSkill', click: show },
      { type: 'separator' },
      {
        label: zh ? '退出 ZenSkill' : 'Quit ZenSkill',
        click: () => {
          // before-quit 钩子负责 flush + performQuitCleanup
          app.quit()
        },
      },
    ])
    tray.setContextMenu(menu)
    // 单击：唤起主界面（Windows 惯例）
    tray.on('click', show)
    mainLog.info('[tray] Windows tray created (close-to-tray residency on)')
  } catch (error) {
    mainLog.error('[tray] creation failed (non-fatal):', error)
    tray = null
  }
}

export function isTrayActive(): boolean {
  return tray !== null
}

export function destroyTray(): void {
  try {
    tray?.destroy()
  } catch {
    // ignore
  }
  tray = null
}
