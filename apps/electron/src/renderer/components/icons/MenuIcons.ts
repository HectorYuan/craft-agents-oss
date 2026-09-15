/**
 * Menu Icons
 *
 * Explicit icon mapping for the app menu schema (shared/menu-schema.ts).
 * Replaces `import * as Icons from 'lucide-react'` + dynamic `Icons[name]`
 * indexing, which defeated tree-shaking and pulled the full lucide icon set
 * (~1.4 MB source) into the renderer bundle.
 *
 * When adding an `icon: 'Name'` value to menu-schema.ts, import and register
 * it here; unknown names degrade to no icon (same as the previous dynamic
 * lookup returning undefined).
 */

import {
  AppWindow,
  Bug,
  ClipboardPaste,
  Copy,
  Download,
  Eye,
  Focus,
  HelpCircle,
  Keyboard,
  LogOut,
  Maximize2,
  Minimize2,
  PanelLeft,
  Pencil,
  Redo2,
  RotateCcw,
  Scissors,
  Settings,
  SquarePen,
  TextSelect,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export const MENU_ICONS: Record<string, LucideIcon> = {
  AppWindow,
  Bug,
  ClipboardPaste,
  Copy,
  Download,
  Eye,
  Focus,
  HelpCircle,
  Keyboard,
  LogOut,
  Maximize2,
  Minimize2,
  PanelLeft,
  Pencil,
  Redo2,
  RotateCcw,
  Scissors,
  Settings,
  SquarePen,
  TextSelect,
  Undo2,
  ZoomIn,
  ZoomOut,
}
