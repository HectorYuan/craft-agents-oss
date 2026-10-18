"use strict";

// src/preload/browser-toolbar.ts
var import_electron = require("electron");
var CHANNELS = {
  NAVIGATE: "browser-toolbar:navigate",
  GO_BACK: "browser-toolbar:go-back",
  GO_FORWARD: "browser-toolbar:go-forward",
  RELOAD: "browser-toolbar:reload",
  STOP: "browser-toolbar:stop",
  MENU_GEOMETRY: "browser-toolbar:menu-geometry",
  FORCE_CLOSE_MENU: "browser-toolbar:force-close-menu",
  HIDE: "browser-toolbar:hide",
  DESTROY: "browser-toolbar:destroy",
  STATE_UPDATE: "browser-toolbar:state-update",
  THEME_COLOR: "browser-toolbar:theme-color"
};
var instanceId = new URLSearchParams(location.search).get("instanceId") || "";
import_electron.contextBridge.exposeInMainWorld("browserToolbar", {
  instanceId,
  navigate: (url) => import_electron.ipcRenderer.invoke(CHANNELS.NAVIGATE, instanceId, url),
  goBack: () => import_electron.ipcRenderer.invoke(CHANNELS.GO_BACK, instanceId),
  goForward: () => import_electron.ipcRenderer.invoke(CHANNELS.GO_FORWARD, instanceId),
  reload: () => import_electron.ipcRenderer.invoke(CHANNELS.RELOAD, instanceId),
  stop: () => import_electron.ipcRenderer.invoke(CHANNELS.STOP, instanceId),
  setMenuGeometry: (open, height = 0) => import_electron.ipcRenderer.invoke(CHANNELS.MENU_GEOMETRY, instanceId, open, height),
  hideWindow: () => import_electron.ipcRenderer.invoke(CHANNELS.HIDE, instanceId),
  closeWindowEntirely: () => import_electron.ipcRenderer.invoke(CHANNELS.DESTROY, instanceId),
  onStateUpdate: (callback) => {
    const handler = (_event, state) => callback(state);
    import_electron.ipcRenderer.on(CHANNELS.STATE_UPDATE, handler);
    return () => {
      import_electron.ipcRenderer.removeListener(CHANNELS.STATE_UPDATE, handler);
    };
  },
  onThemeColor: (callback) => {
    const handler = (_event, color) => callback(color);
    import_electron.ipcRenderer.on(CHANNELS.THEME_COLOR, handler);
    return () => {
      import_electron.ipcRenderer.removeListener(CHANNELS.THEME_COLOR, handler);
    };
  },
  onForceCloseMenu: (callback) => {
    const handler = (_event, payload) => callback(payload);
    import_electron.ipcRenderer.on(CHANNELS.FORCE_CLOSE_MENU, handler);
    return () => {
      import_electron.ipcRenderer.removeListener(CHANNELS.FORCE_CLOSE_MENU, handler);
    };
  }
});
