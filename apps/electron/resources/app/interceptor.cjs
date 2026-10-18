"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __commonJS = (cb, mod) => function __require() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// ../../node_modules/electron/index.js
var require_electron = __commonJS({
  "../../node_modules/electron/index.js"(exports2, module2) {
    var fs = require("fs");
    var path = require("path");
    var pathFile = path.join(__dirname, "path.txt");
    function getElectronPath() {
      let executablePath;
      if (fs.existsSync(pathFile)) {
        executablePath = fs.readFileSync(pathFile, "utf-8");
      }
      if (process.env.ELECTRON_OVERRIDE_DIST_PATH) {
        return path.join(process.env.ELECTRON_OVERRIDE_DIST_PATH, executablePath || "electron");
      }
      if (executablePath) {
        return path.join(__dirname, "dist", executablePath);
      } else {
        throw new Error("Electron failed to install correctly, please delete node_modules/electron and try installing again");
      }
    }
    module2.exports = getElectronPath();
  }
});

// ../../node_modules/electron-log/src/node/packageJson.js
var require_packageJson = __commonJS({
  "../../node_modules/electron-log/src/node/packageJson.js"(exports2, module2) {
    "use strict";
    var fs = require("fs");
    var path = require("path");
    module2.exports = {
      findAndReadPackageJson,
      tryReadJsonAt
    };
    function findAndReadPackageJson() {
      return tryReadJsonAt(getMainModulePath()) || tryReadJsonAt(extractPathFromArgs()) || tryReadJsonAt(process.resourcesPath, "app.asar") || tryReadJsonAt(process.resourcesPath, "app") || tryReadJsonAt(process.cwd()) || { name: void 0, version: void 0 };
    }
    function tryReadJsonAt(...searchPaths) {
      if (!searchPaths[0]) {
        return void 0;
      }
      try {
        const searchPath = path.join(...searchPaths);
        const fileName = findUp("package.json", searchPath);
        if (!fileName) {
          return void 0;
        }
        const json = JSON.parse(fs.readFileSync(fileName, "utf8"));
        const name = json?.productName || json?.name;
        if (!name || name.toLowerCase() === "electron") {
          return void 0;
        }
        if (name) {
          return { name, version: json?.version };
        }
        return void 0;
      } catch (e) {
        return void 0;
      }
    }
    function findUp(fileName, cwd) {
      let currentPath = cwd;
      while (true) {
        const parsedPath = path.parse(currentPath);
        const root = parsedPath.root;
        const dir = parsedPath.dir;
        if (fs.existsSync(path.join(currentPath, fileName))) {
          return path.resolve(path.join(currentPath, fileName));
        }
        if (currentPath === root) {
          return null;
        }
        currentPath = dir;
      }
    }
    function extractPathFromArgs() {
      const matchedArgs = process.argv.filter((arg) => {
        return arg.indexOf("--user-data-dir=") === 0;
      });
      if (matchedArgs.length === 0 || typeof matchedArgs[0] !== "string") {
        return null;
      }
      const userDataDir = matchedArgs[0];
      return userDataDir.replace("--user-data-dir=", "");
    }
    function getMainModulePath() {
      try {
        return require.main?.filename;
      } catch {
        return void 0;
      }
    }
  }
});

// ../../node_modules/electron-log/src/node/NodeExternalApi.js
var require_NodeExternalApi = __commonJS({
  "../../node_modules/electron-log/src/node/NodeExternalApi.js"(exports2, module2) {
    "use strict";
    var childProcess = require("child_process");
    var os = require("os");
    var path = require("path");
    var packageJson = require_packageJson();
    var NodeExternalApi = class {
      appName = void 0;
      appPackageJson = void 0;
      platform = process.platform;
      getAppLogPath(appName = this.getAppName()) {
        if (this.platform === "darwin") {
          return path.join(this.getSystemPathHome(), "Library/Logs", appName);
        }
        return path.join(this.getAppUserDataPath(appName), "logs");
      }
      getAppName() {
        const appName = this.appName || this.getAppPackageJson()?.name;
        if (!appName) {
          throw new Error(
            "electron-log can't determine the app name. It tried these methods:\n1. Use `electron.app.name`\n2. Use productName or name from the nearest package.json`\nYou can also set it through log.transports.file.setAppName()"
          );
        }
        return appName;
      }
      /**
       * @private
       * @returns {undefined}
       */
      getAppPackageJson() {
        if (typeof this.appPackageJson !== "object") {
          this.appPackageJson = packageJson.findAndReadPackageJson();
        }
        return this.appPackageJson;
      }
      getAppUserDataPath(appName = this.getAppName()) {
        return appName ? path.join(this.getSystemPathAppData(), appName) : void 0;
      }
      getAppVersion() {
        return this.getAppPackageJson()?.version;
      }
      getElectronLogPath() {
        return this.getAppLogPath();
      }
      getMacOsVersion() {
        const release = Number(os.release().split(".")[0]);
        if (release <= 19) {
          return `10.${release - 4}`;
        }
        return release - 9;
      }
      /**
       * @protected
       * @returns {string}
       */
      getOsVersion() {
        let osName = os.type().replace("_", " ");
        let osVersion = os.release();
        if (osName === "Darwin") {
          osName = "macOS";
          osVersion = this.getMacOsVersion();
        }
        return `${osName} ${osVersion}`;
      }
      /**
       * @return {PathVariables}
       */
      getPathVariables() {
        const appName = this.getAppName();
        const appVersion = this.getAppVersion();
        const self = this;
        return {
          appData: this.getSystemPathAppData(),
          appName,
          appVersion,
          get electronDefaultDir() {
            return self.getElectronLogPath();
          },
          home: this.getSystemPathHome(),
          libraryDefaultDir: this.getAppLogPath(appName),
          libraryTemplate: this.getAppLogPath("{appName}"),
          temp: this.getSystemPathTemp(),
          userData: this.getAppUserDataPath(appName)
        };
      }
      getSystemPathAppData() {
        const home = this.getSystemPathHome();
        switch (this.platform) {
          case "darwin": {
            return path.join(home, "Library/Application Support");
          }
          case "win32": {
            return process.env.APPDATA || path.join(home, "AppData/Roaming");
          }
          default: {
            return process.env.XDG_CONFIG_HOME || path.join(home, ".config");
          }
        }
      }
      getSystemPathHome() {
        return os.homedir?.() || process.env.HOME;
      }
      getSystemPathTemp() {
        return os.tmpdir();
      }
      getVersions() {
        return {
          app: `${this.getAppName()} ${this.getAppVersion()}`,
          electron: void 0,
          os: this.getOsVersion()
        };
      }
      isDev() {
        return process.env.NODE_ENV === "development" || process.env.ELECTRON_IS_DEV === "1";
      }
      isElectron() {
        return Boolean(process.versions.electron);
      }
      onAppEvent(_eventName, _handler) {
      }
      onAppReady(handler) {
        handler();
      }
      onEveryWebContentsEvent(eventName, handler) {
      }
      /**
       * Listen to async messages sent from opposite process
       * @param {string} channel
       * @param {function} listener
       */
      onIpc(channel, listener) {
      }
      onIpcInvoke(channel, listener) {
      }
      /**
       * @param {string} url
       * @param {Function} [logFunction]
       */
      openUrl(url, logFunction = console.error) {
        const startMap = { darwin: "open", win32: "start", linux: "xdg-open" };
        const start = startMap[process.platform] || "xdg-open";
        childProcess.exec(`${start} ${url}`, {}, (err) => {
          if (err) {
            logFunction(err);
          }
        });
      }
      setAppName(appName) {
        this.appName = appName;
      }
      setPlatform(platform) {
        this.platform = platform;
      }
      setPreloadFileForSessions({
        filePath,
        // eslint-disable-line no-unused-vars
        includeFutureSession = true,
        // eslint-disable-line no-unused-vars
        getSessions = () => []
        // eslint-disable-line no-unused-vars
      }) {
      }
      /**
       * Sent a message to opposite process
       * @param {string} channel
       * @param {any} message
       */
      sendIpc(channel, message) {
      }
      showErrorBox(title, message) {
      }
    };
    module2.exports = NodeExternalApi;
  }
});

// ../../node_modules/electron-log/src/main/ElectronExternalApi.js
var require_ElectronExternalApi = __commonJS({
  "../../node_modules/electron-log/src/main/ElectronExternalApi.js"(exports2, module2) {
    "use strict";
    var path = require("path");
    var NodeExternalApi = require_NodeExternalApi();
    var ElectronExternalApi = class extends NodeExternalApi {
      /**
       * @type {typeof Electron}
       */
      electron = void 0;
      /**
       * @param {object} options
       * @param {typeof Electron} [options.electron]
       */
      constructor({ electron } = {}) {
        super();
        this.electron = electron;
      }
      getAppName() {
        let appName;
        try {
          appName = this.appName || this.electron.app?.name || this.electron.app?.getName();
        } catch {
        }
        return appName || super.getAppName();
      }
      getAppUserDataPath(appName) {
        return this.getPath("userData") || super.getAppUserDataPath(appName);
      }
      getAppVersion() {
        let appVersion;
        try {
          appVersion = this.electron.app?.getVersion();
        } catch {
        }
        return appVersion || super.getAppVersion();
      }
      getElectronLogPath() {
        return this.getPath("logs") || super.getElectronLogPath();
      }
      /**
       * @private
       * @param {any} name
       * @returns {string|undefined}
       */
      getPath(name) {
        try {
          return this.electron.app?.getPath(name);
        } catch {
          return void 0;
        }
      }
      getVersions() {
        return {
          app: `${this.getAppName()} ${this.getAppVersion()}`,
          electron: `Electron ${process.versions.electron}`,
          os: this.getOsVersion()
        };
      }
      getSystemPathAppData() {
        return this.getPath("appData") || super.getSystemPathAppData();
      }
      isDev() {
        if (this.electron.app?.isPackaged !== void 0) {
          return !this.electron.app.isPackaged;
        }
        if (typeof process.execPath === "string") {
          const execFileName = path.basename(process.execPath).toLowerCase();
          return execFileName.startsWith("electron");
        }
        return super.isDev();
      }
      onAppEvent(eventName, handler) {
        this.electron.app?.on(eventName, handler);
        return () => {
          this.electron.app?.off(eventName, handler);
        };
      }
      onAppReady(handler) {
        if (this.electron.app?.isReady()) {
          handler();
        } else if (this.electron.app?.once) {
          this.electron.app?.once("ready", handler);
        } else {
          handler();
        }
      }
      onEveryWebContentsEvent(eventName, handler) {
        this.electron.webContents?.getAllWebContents()?.forEach((webContents) => {
          webContents.on(eventName, handler);
        });
        this.electron.app?.on("web-contents-created", onWebContentsCreated);
        return () => {
          this.electron.webContents?.getAllWebContents().forEach((webContents) => {
            webContents.off(eventName, handler);
          });
          this.electron.app?.off("web-contents-created", onWebContentsCreated);
        };
        function onWebContentsCreated(_, webContents) {
          webContents.on(eventName, handler);
        }
      }
      /**
       * Listen to async messages sent from opposite process
       * @param {string} channel
       * @param {function} listener
       */
      onIpc(channel, listener) {
        this.electron.ipcMain?.on(channel, listener);
      }
      onIpcInvoke(channel, listener) {
        this.electron.ipcMain?.handle?.(channel, listener);
      }
      /**
       * @param {string} url
       * @param {Function} [logFunction]
       */
      openUrl(url, logFunction = console.error) {
        this.electron.shell?.openExternal(url).catch(logFunction);
      }
      setPreloadFileForSessions({
        filePath,
        includeFutureSession = true,
        getSessions = () => [this.electron.session?.defaultSession]
      }) {
        for (const session of getSessions().filter(Boolean)) {
          setPreload(session);
        }
        if (includeFutureSession) {
          this.onAppEvent("session-created", (session) => {
            setPreload(session);
          });
        }
        function setPreload(session) {
          if (typeof session.registerPreloadScript === "function") {
            session.registerPreloadScript({
              filePath,
              id: "electron-log-preload",
              type: "frame"
            });
          } else {
            session.setPreloads([...session.getPreloads(), filePath]);
          }
        }
      }
      /**
       * Sent a message to opposite process
       * @param {string} channel
       * @param {any} message
       */
      sendIpc(channel, message) {
        this.electron.BrowserWindow?.getAllWindows()?.forEach((wnd) => {
          if (wnd.webContents?.isDestroyed() === false && wnd.webContents?.isCrashed() === false) {
            wnd.webContents.send(channel, message);
          }
        });
      }
      showErrorBox(title, message) {
        this.electron.dialog?.showErrorBox(title, message);
      }
    };
    module2.exports = ElectronExternalApi;
  }
});

// ../../node_modules/electron-log/src/renderer/electron-log-preload.js
var require_electron_log_preload = __commonJS({
  "../../node_modules/electron-log/src/renderer/electron-log-preload.js"(exports2, module2) {
    "use strict";
    var electron = {};
    try {
      electron = require_electron();
    } catch (e) {
    }
    if (electron.ipcRenderer) {
      initialize(electron);
    }
    if (typeof module2 === "object") {
      module2.exports = initialize;
    }
    function initialize({ contextBridge, ipcRenderer }) {
      if (!ipcRenderer) {
        return;
      }
      ipcRenderer.on("__ELECTRON_LOG_IPC__", (_, message) => {
        window.postMessage({ cmd: "message", ...message });
      });
      ipcRenderer.invoke("__ELECTRON_LOG__", { cmd: "getOptions" }).catch((e) => console.error(new Error(
        `electron-log isn't initialized in the main process. Please call log.initialize() before. ${e.message}`
      )));
      const electronLog2 = {
        sendToMain(message) {
          try {
            ipcRenderer.send("__ELECTRON_LOG__", message);
          } catch (e) {
            console.error("electronLog.sendToMain ", e, "data:", message);
            ipcRenderer.send("__ELECTRON_LOG__", {
              cmd: "errorHandler",
              error: { message: e?.message, stack: e?.stack },
              errorName: "sendToMain"
            });
          }
        },
        log(...data) {
          electronLog2.sendToMain({ data, level: "info" });
        }
      };
      for (const level of ["error", "warn", "info", "verbose", "debug", "silly"]) {
        electronLog2[level] = (...data) => electronLog2.sendToMain({
          data,
          level
        });
      }
      if (contextBridge && process.contextIsolated) {
        try {
          contextBridge.exposeInMainWorld("__electronLog", electronLog2);
        } catch {
        }
      }
      if (typeof window === "object") {
        window.__electronLog = electronLog2;
      } else {
        __electronLog = electronLog2;
      }
    }
  }
});

// ../../node_modules/electron-log/src/main/initialize.js
var require_initialize = __commonJS({
  "../../node_modules/electron-log/src/main/initialize.js"(exports2, module2) {
    "use strict";
    var fs = require("fs");
    var os = require("os");
    var path = require("path");
    var preloadInitializeFn = require_electron_log_preload();
    var preloadInitialized = false;
    var spyConsoleInitialized = false;
    module2.exports = {
      initialize({
        externalApi,
        getSessions,
        includeFutureSession,
        logger,
        preload = true,
        spyRendererConsole = false
      }) {
        externalApi.onAppReady(() => {
          try {
            if (preload) {
              initializePreload({
                externalApi,
                getSessions,
                includeFutureSession,
                logger,
                preloadOption: preload
              });
            }
            if (spyRendererConsole) {
              initializeSpyRendererConsole({ externalApi, logger });
            }
          } catch (err) {
            logger.warn(err);
          }
        });
      }
    };
    function initializePreload({
      externalApi,
      getSessions,
      includeFutureSession,
      logger,
      preloadOption
    }) {
      let preloadPath = typeof preloadOption === "string" ? preloadOption : void 0;
      if (preloadInitialized) {
        logger.warn(new Error("log.initialize({ preload }) already called").stack);
        return;
      }
      preloadInitialized = true;
      try {
        preloadPath = path.resolve(
          __dirname,
          "../renderer/electron-log-preload.js"
        );
      } catch {
      }
      if (!preloadPath || !fs.existsSync(preloadPath)) {
        preloadPath = path.join(
          externalApi.getAppUserDataPath() || os.tmpdir(),
          "electron-log-preload.js"
        );
        const preloadCode = `
      try {
        (${preloadInitializeFn.toString()})(require('electron'));
      } catch(e) {
        console.error(e);
      }
    `;
        fs.writeFileSync(preloadPath, preloadCode, "utf8");
      }
      externalApi.setPreloadFileForSessions({
        filePath: preloadPath,
        includeFutureSession,
        getSessions
      });
    }
    function initializeSpyRendererConsole({ externalApi, logger }) {
      if (spyConsoleInitialized) {
        logger.warn(
          new Error("log.initialize({ spyRendererConsole }) already called").stack
        );
        return;
      }
      spyConsoleInitialized = true;
      const levels = ["debug", "info", "warn", "error"];
      externalApi.onEveryWebContentsEvent(
        "console-message",
        (event, level, message) => {
          logger.processMessage({
            data: [message],
            level: levels[level],
            variables: { processType: "renderer" }
          });
        }
      );
    }
  }
});

// ../../node_modules/electron-log/src/core/scope.js
var require_scope = __commonJS({
  "../../node_modules/electron-log/src/core/scope.js"(exports2, module2) {
    "use strict";
    module2.exports = scopeFactory;
    function scopeFactory(logger) {
      return Object.defineProperties(scope, {
        defaultLabel: { value: "", writable: true },
        labelPadding: { value: true, writable: true },
        maxLabelLength: { value: 0, writable: true },
        labelLength: {
          get() {
            switch (typeof scope.labelPadding) {
              case "boolean":
                return scope.labelPadding ? scope.maxLabelLength : 0;
              case "number":
                return scope.labelPadding;
              default:
                return 0;
            }
          }
        }
      });
      function scope(label) {
        scope.maxLabelLength = Math.max(scope.maxLabelLength, label.length);
        const newScope = {};
        for (const level of logger.levels) {
          newScope[level] = (...d) => logger.logData(d, { level, scope: label });
        }
        newScope.log = newScope.info;
        return newScope;
      }
    }
  }
});

// ../../node_modules/electron-log/src/core/Buffering.js
var require_Buffering = __commonJS({
  "../../node_modules/electron-log/src/core/Buffering.js"(exports2, module2) {
    "use strict";
    var Buffering = class {
      constructor({ processMessage }) {
        this.processMessage = processMessage;
        this.buffer = [];
        this.enabled = false;
        this.begin = this.begin.bind(this);
        this.commit = this.commit.bind(this);
        this.reject = this.reject.bind(this);
      }
      addMessage(message) {
        this.buffer.push(message);
      }
      begin() {
        this.enabled = [];
      }
      commit() {
        this.enabled = false;
        this.buffer.forEach((item) => this.processMessage(item));
        this.buffer = [];
      }
      reject() {
        this.enabled = false;
        this.buffer = [];
      }
    };
    module2.exports = Buffering;
  }
});

// ../../node_modules/electron-log/src/core/Logger.js
var require_Logger = __commonJS({
  "../../node_modules/electron-log/src/core/Logger.js"(exports2, module2) {
    "use strict";
    var scopeFactory = require_scope();
    var Buffering = require_Buffering();
    var Logger = class _Logger {
      static instances = {};
      dependencies = {};
      errorHandler = null;
      eventLogger = null;
      functions = {};
      hooks = [];
      isDev = false;
      levels = null;
      logId = null;
      scope = null;
      transports = {};
      variables = {};
      constructor({
        allowUnknownLevel = false,
        dependencies = {},
        errorHandler,
        eventLogger,
        initializeFn,
        isDev = false,
        levels = ["error", "warn", "info", "verbose", "debug", "silly"],
        logId,
        transportFactories = {},
        variables
      } = {}) {
        this.addLevel = this.addLevel.bind(this);
        this.create = this.create.bind(this);
        this.initialize = this.initialize.bind(this);
        this.logData = this.logData.bind(this);
        this.processMessage = this.processMessage.bind(this);
        this.allowUnknownLevel = allowUnknownLevel;
        this.buffering = new Buffering(this);
        this.dependencies = dependencies;
        this.initializeFn = initializeFn;
        this.isDev = isDev;
        this.levels = levels;
        this.logId = logId;
        this.scope = scopeFactory(this);
        this.transportFactories = transportFactories;
        this.variables = variables || {};
        for (const name of this.levels) {
          this.addLevel(name, false);
        }
        this.log = this.info;
        this.functions.log = this.log;
        this.errorHandler = errorHandler;
        errorHandler?.setOptions({ ...dependencies, logFn: this.error });
        this.eventLogger = eventLogger;
        eventLogger?.setOptions({ ...dependencies, logger: this });
        for (const [name, factory] of Object.entries(transportFactories)) {
          this.transports[name] = factory(this, dependencies);
        }
        _Logger.instances[logId] = this;
      }
      static getInstance({ logId }) {
        return this.instances[logId] || this.instances.default;
      }
      addLevel(level, index = this.levels.length) {
        if (index !== false) {
          this.levels.splice(index, 0, level);
        }
        this[level] = (...args) => this.logData(args, { level });
        this.functions[level] = this[level];
      }
      catchErrors(options) {
        this.processMessage(
          {
            data: ["log.catchErrors is deprecated. Use log.errorHandler instead"],
            level: "warn"
          },
          { transports: ["console"] }
        );
        return this.errorHandler.startCatching(options);
      }
      create(options) {
        if (typeof options === "string") {
          options = { logId: options };
        }
        return new _Logger({
          dependencies: this.dependencies,
          errorHandler: this.errorHandler,
          initializeFn: this.initializeFn,
          isDev: this.isDev,
          transportFactories: this.transportFactories,
          variables: { ...this.variables },
          ...options
        });
      }
      compareLevels(passLevel, checkLevel, levels = this.levels) {
        const pass = levels.indexOf(passLevel);
        const check = levels.indexOf(checkLevel);
        if (check === -1 || pass === -1) {
          return true;
        }
        return check <= pass;
      }
      initialize(options = {}) {
        this.initializeFn({ logger: this, ...this.dependencies, ...options });
      }
      logData(data, options = {}) {
        if (this.buffering.enabled) {
          this.buffering.addMessage({ data, date: /* @__PURE__ */ new Date(), ...options });
        } else {
          this.processMessage({ data, ...options });
        }
      }
      processMessage(message, { transports = this.transports } = {}) {
        if (message.cmd === "errorHandler") {
          this.errorHandler.handle(message.error, {
            errorName: message.errorName,
            processType: "renderer",
            showDialog: Boolean(message.showDialog)
          });
          return;
        }
        let level = message.level;
        if (!this.allowUnknownLevel) {
          level = this.levels.includes(message.level) ? message.level : "info";
        }
        const normalizedMessage = {
          date: /* @__PURE__ */ new Date(),
          logId: this.logId,
          ...message,
          level,
          variables: {
            ...this.variables,
            ...message.variables
          }
        };
        for (const [transName, transFn] of this.transportEntries(transports)) {
          if (typeof transFn !== "function" || transFn.level === false) {
            continue;
          }
          if (!this.compareLevels(transFn.level, message.level)) {
            continue;
          }
          try {
            const transformedMsg = this.hooks.reduce((msg, hook) => {
              return msg ? hook(msg, transFn, transName) : msg;
            }, normalizedMessage);
            if (transformedMsg) {
              transFn({ ...transformedMsg, data: [...transformedMsg.data] });
            }
          } catch (e) {
            this.processInternalErrorFn(e);
          }
        }
      }
      processInternalErrorFn(_e) {
      }
      transportEntries(transports = this.transports) {
        const transportArray = Array.isArray(transports) ? transports : Object.entries(transports);
        return transportArray.map((item) => {
          switch (typeof item) {
            case "string":
              return this.transports[item] ? [item, this.transports[item]] : null;
            case "function":
              return [item.name, item];
            default:
              return Array.isArray(item) ? item : null;
          }
        }).filter(Boolean);
      }
    };
    module2.exports = Logger;
  }
});

// ../../node_modules/electron-log/src/node/ErrorHandler.js
var require_ErrorHandler = __commonJS({
  "../../node_modules/electron-log/src/node/ErrorHandler.js"(exports2, module2) {
    "use strict";
    var ErrorHandler = class {
      externalApi = void 0;
      isActive = false;
      logFn = void 0;
      onError = void 0;
      showDialog = true;
      constructor({
        externalApi,
        logFn = void 0,
        onError = void 0,
        showDialog = void 0
      } = {}) {
        this.createIssue = this.createIssue.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleRejection = this.handleRejection.bind(this);
        this.setOptions({ externalApi, logFn, onError, showDialog });
        this.startCatching = this.startCatching.bind(this);
        this.stopCatching = this.stopCatching.bind(this);
      }
      handle(error, {
        logFn = this.logFn,
        onError = this.onError,
        processType = "browser",
        showDialog = this.showDialog,
        errorName = ""
      } = {}) {
        error = normalizeError(error);
        try {
          if (typeof onError === "function") {
            const versions = this.externalApi?.getVersions() || {};
            const createIssue = this.createIssue;
            const result = onError({
              createIssue,
              error,
              errorName,
              processType,
              versions
            });
            if (result === false) {
              return;
            }
          }
          errorName ? logFn(errorName, error) : logFn(error);
          if (showDialog && !errorName.includes("rejection") && this.externalApi) {
            this.externalApi.showErrorBox(
              `A JavaScript error occurred in the ${processType} process`,
              error.stack
            );
          }
        } catch {
          console.error(error);
        }
      }
      setOptions({ externalApi, logFn, onError, showDialog }) {
        if (typeof externalApi === "object") {
          this.externalApi = externalApi;
        }
        if (typeof logFn === "function") {
          this.logFn = logFn;
        }
        if (typeof onError === "function") {
          this.onError = onError;
        }
        if (typeof showDialog === "boolean") {
          this.showDialog = showDialog;
        }
      }
      startCatching({ onError, showDialog } = {}) {
        if (this.isActive) {
          return;
        }
        this.isActive = true;
        this.setOptions({ onError, showDialog });
        process.on("uncaughtException", this.handleError);
        process.on("unhandledRejection", this.handleRejection);
      }
      stopCatching() {
        this.isActive = false;
        process.removeListener("uncaughtException", this.handleError);
        process.removeListener("unhandledRejection", this.handleRejection);
      }
      createIssue(pageUrl, queryParams) {
        this.externalApi?.openUrl(
          `${pageUrl}?${new URLSearchParams(queryParams).toString()}`
        );
      }
      handleError(error) {
        this.handle(error, { errorName: "Unhandled" });
      }
      handleRejection(reason) {
        const error = reason instanceof Error ? reason : new Error(JSON.stringify(reason));
        this.handle(error, { errorName: "Unhandled rejection" });
      }
    };
    function normalizeError(e) {
      if (e instanceof Error) {
        return e;
      }
      if (e && typeof e === "object") {
        if (e.message) {
          return Object.assign(new Error(e.message), e);
        }
        try {
          return new Error(JSON.stringify(e));
        } catch (serErr) {
          return new Error(`Couldn't normalize error ${String(e)}: ${serErr}`);
        }
      }
      return new Error(`Can't normalize error ${String(e)}`);
    }
    module2.exports = ErrorHandler;
  }
});

// ../../node_modules/electron-log/src/node/EventLogger.js
var require_EventLogger = __commonJS({
  "../../node_modules/electron-log/src/node/EventLogger.js"(exports2, module2) {
    "use strict";
    var EventLogger = class {
      disposers = [];
      format = "{eventSource}#{eventName}:";
      formatters = {
        app: {
          "certificate-error": ({ args }) => {
            return this.arrayToObject(args.slice(1, 4), [
              "url",
              "error",
              "certificate"
            ]);
          },
          "child-process-gone": ({ args }) => {
            return args.length === 1 ? args[0] : args;
          },
          "render-process-gone": ({ args: [webContents, details] }) => {
            return details && typeof details === "object" ? { ...details, ...this.getWebContentsDetails(webContents) } : [];
          }
        },
        webContents: {
          "console-message": ({ args: [level, message, line, sourceId] }) => {
            if (level < 3) {
              return void 0;
            }
            return { message, source: `${sourceId}:${line}` };
          },
          "did-fail-load": ({ args }) => {
            return this.arrayToObject(args, [
              "errorCode",
              "errorDescription",
              "validatedURL",
              "isMainFrame",
              "frameProcessId",
              "frameRoutingId"
            ]);
          },
          "did-fail-provisional-load": ({ args }) => {
            return this.arrayToObject(args, [
              "errorCode",
              "errorDescription",
              "validatedURL",
              "isMainFrame",
              "frameProcessId",
              "frameRoutingId"
            ]);
          },
          "plugin-crashed": ({ args }) => {
            return this.arrayToObject(args, ["name", "version"]);
          },
          "preload-error": ({ args }) => {
            return this.arrayToObject(args, ["preloadPath", "error"]);
          }
        }
      };
      events = {
        app: {
          "certificate-error": true,
          "child-process-gone": true,
          "render-process-gone": true
        },
        webContents: {
          // 'console-message': true,
          "did-fail-load": true,
          "did-fail-provisional-load": true,
          "plugin-crashed": true,
          "preload-error": true,
          "unresponsive": true
        }
      };
      externalApi = void 0;
      level = "error";
      scope = "";
      constructor(options = {}) {
        this.setOptions(options);
      }
      setOptions({
        events,
        externalApi,
        level,
        logger,
        format,
        formatters,
        scope
      }) {
        if (typeof events === "object") {
          this.events = events;
        }
        if (typeof externalApi === "object") {
          this.externalApi = externalApi;
        }
        if (typeof level === "string") {
          this.level = level;
        }
        if (typeof logger === "object") {
          this.logger = logger;
        }
        if (typeof format === "string" || typeof format === "function") {
          this.format = format;
        }
        if (typeof formatters === "object") {
          this.formatters = formatters;
        }
        if (typeof scope === "string") {
          this.scope = scope;
        }
      }
      startLogging(options = {}) {
        this.setOptions(options);
        this.disposeListeners();
        for (const eventName of this.getEventNames(this.events.app)) {
          this.disposers.push(
            this.externalApi.onAppEvent(eventName, (...handlerArgs) => {
              this.handleEvent({ eventSource: "app", eventName, handlerArgs });
            })
          );
        }
        for (const eventName of this.getEventNames(this.events.webContents)) {
          this.disposers.push(
            this.externalApi.onEveryWebContentsEvent(
              eventName,
              (...handlerArgs) => {
                this.handleEvent(
                  { eventSource: "webContents", eventName, handlerArgs }
                );
              }
            )
          );
        }
      }
      stopLogging() {
        this.disposeListeners();
      }
      arrayToObject(array, fieldNames) {
        const obj = {};
        fieldNames.forEach((fieldName, index) => {
          obj[fieldName] = array[index];
        });
        if (array.length > fieldNames.length) {
          obj.unknownArgs = array.slice(fieldNames.length);
        }
        return obj;
      }
      disposeListeners() {
        this.disposers.forEach((disposer) => disposer());
        this.disposers = [];
      }
      formatEventLog({ eventName, eventSource, handlerArgs }) {
        const [event, ...args] = handlerArgs;
        if (typeof this.format === "function") {
          return this.format({ args, event, eventName, eventSource });
        }
        const formatter = this.formatters[eventSource]?.[eventName];
        let formattedArgs = args;
        if (typeof formatter === "function") {
          formattedArgs = formatter({ args, event, eventName, eventSource });
        }
        if (!formattedArgs) {
          return void 0;
        }
        const eventData = {};
        if (Array.isArray(formattedArgs)) {
          eventData.args = formattedArgs;
        } else if (typeof formattedArgs === "object") {
          Object.assign(eventData, formattedArgs);
        }
        if (eventSource === "webContents") {
          Object.assign(eventData, this.getWebContentsDetails(event?.sender));
        }
        const title = this.format.replace("{eventSource}", eventSource === "app" ? "App" : "WebContents").replace("{eventName}", eventName);
        return [title, eventData];
      }
      getEventNames(eventMap) {
        if (!eventMap || typeof eventMap !== "object") {
          return [];
        }
        return Object.entries(eventMap).filter(([_, listen]) => listen).map(([eventName]) => eventName);
      }
      getWebContentsDetails(webContents) {
        if (!webContents?.loadURL) {
          return {};
        }
        try {
          return {
            webContents: {
              id: webContents.id,
              url: webContents.getURL()
            }
          };
        } catch {
          return {};
        }
      }
      handleEvent({ eventName, eventSource, handlerArgs }) {
        const log = this.formatEventLog({ eventName, eventSource, handlerArgs });
        if (log) {
          const logFns = this.scope ? this.logger.scope(this.scope) : this.logger;
          logFns?.[this.level]?.(...log);
        }
      }
    };
    module2.exports = EventLogger;
  }
});

// ../../node_modules/electron-log/src/core/transforms/transform.js
var require_transform = __commonJS({
  "../../node_modules/electron-log/src/core/transforms/transform.js"(exports2, module2) {
    "use strict";
    module2.exports = { transform };
    function transform({
      logger,
      message,
      transport,
      initialData = message?.data || [],
      transforms = transport?.transforms
    }) {
      return transforms.reduce((data, trans) => {
        if (typeof trans === "function") {
          return trans({ data, logger, message, transport });
        }
        return data;
      }, initialData);
    }
  }
});

// ../../node_modules/electron-log/src/core/transforms/format.js
var require_format = __commonJS({
  "../../node_modules/electron-log/src/core/transforms/format.js"(exports2, module2) {
    "use strict";
    var { transform } = require_transform();
    module2.exports = {
      concatFirstStringElements,
      formatScope,
      formatText,
      formatVariables,
      timeZoneFromOffset,
      format({ message, logger, transport, data = message?.data }) {
        switch (typeof transport.format) {
          case "string": {
            return transform({
              message,
              logger,
              transforms: [formatVariables, formatScope, formatText],
              transport,
              initialData: [transport.format, ...data]
            });
          }
          case "function": {
            return transport.format({
              data,
              level: message?.level || "info",
              logger,
              message,
              transport
            });
          }
          default: {
            return data;
          }
        }
      }
    };
    function concatFirstStringElements({ data }) {
      if (typeof data[0] !== "string" || typeof data[1] !== "string") {
        return data;
      }
      if (data[0].match(/%[1cdfiOos]/)) {
        return data;
      }
      return [`${data[0]} ${data[1]}`, ...data.slice(2)];
    }
    function timeZoneFromOffset(minutesOffset) {
      const minutesPositive = Math.abs(minutesOffset);
      const sign = minutesOffset > 0 ? "-" : "+";
      const hours = Math.floor(minutesPositive / 60).toString().padStart(2, "0");
      const minutes = (minutesPositive % 60).toString().padStart(2, "0");
      return `${sign}${hours}:${minutes}`;
    }
    function formatScope({ data, logger, message }) {
      const { defaultLabel, labelLength } = logger?.scope || {};
      const template = data[0];
      let label = message.scope;
      if (!label) {
        label = defaultLabel;
      }
      let scopeText;
      if (label === "") {
        scopeText = labelLength > 0 ? "".padEnd(labelLength + 3) : "";
      } else if (typeof label === "string") {
        scopeText = ` (${label})`.padEnd(labelLength + 3);
      } else {
        scopeText = "";
      }
      data[0] = template.replace("{scope}", scopeText);
      return data;
    }
    function formatVariables({ data, message }) {
      let template = data[0];
      if (typeof template !== "string") {
        return data;
      }
      template = template.replace("{level}]", `${message.level}]`.padEnd(6, " "));
      const date = message.date || /* @__PURE__ */ new Date();
      data[0] = template.replace(/\{(\w+)}/g, (substring, name) => {
        switch (name) {
          case "level":
            return message.level || "info";
          case "logId":
            return message.logId;
          case "y":
            return date.getFullYear().toString(10);
          case "m":
            return (date.getMonth() + 1).toString(10).padStart(2, "0");
          case "d":
            return date.getDate().toString(10).padStart(2, "0");
          case "h":
            return date.getHours().toString(10).padStart(2, "0");
          case "i":
            return date.getMinutes().toString(10).padStart(2, "0");
          case "s":
            return date.getSeconds().toString(10).padStart(2, "0");
          case "ms":
            return date.getMilliseconds().toString(10).padStart(3, "0");
          case "z":
            return timeZoneFromOffset(date.getTimezoneOffset());
          case "iso":
            return date.toISOString();
          default: {
            return message.variables?.[name] || substring;
          }
        }
      }).trim();
      return data;
    }
    function formatText({ data }) {
      const template = data[0];
      if (typeof template !== "string") {
        return data;
      }
      const textTplPosition = template.lastIndexOf("{text}");
      if (textTplPosition === template.length - 6) {
        data[0] = template.replace(/\s?{text}/, "");
        if (data[0] === "") {
          data.shift();
        }
        return data;
      }
      const templatePieces = template.split("{text}");
      let result = [];
      if (templatePieces[0] !== "") {
        result.push(templatePieces[0]);
      }
      result = result.concat(data.slice(1));
      if (templatePieces[1] !== "") {
        result.push(templatePieces[1]);
      }
      return result;
    }
  }
});

// ../../node_modules/electron-log/src/node/transforms/object.js
var require_object = __commonJS({
  "../../node_modules/electron-log/src/node/transforms/object.js"(exports2, module2) {
    "use strict";
    var util = require("util");
    module2.exports = {
      serialize,
      maxDepth({ data, transport, depth = transport?.depth ?? 6 }) {
        if (!data) {
          return data;
        }
        if (depth < 1) {
          if (Array.isArray(data)) return "[array]";
          if (typeof data === "object" && data) return "[object]";
          return data;
        }
        if (Array.isArray(data)) {
          return data.map((child) => module2.exports.maxDepth({
            data: child,
            depth: depth - 1
          }));
        }
        if (typeof data !== "object") {
          return data;
        }
        if (data && typeof data.toISOString === "function") {
          return data;
        }
        if (data === null) {
          return null;
        }
        if (data instanceof Error) {
          return data;
        }
        const newJson = {};
        for (const i in data) {
          if (!Object.prototype.hasOwnProperty.call(data, i)) continue;
          newJson[i] = module2.exports.maxDepth({
            data: data[i],
            depth: depth - 1
          });
        }
        return newJson;
      },
      toJSON({ data }) {
        return JSON.parse(JSON.stringify(data, createSerializer()));
      },
      toString({ data, transport }) {
        const inspectOptions = transport?.inspectOptions || {};
        const simplifiedData = data.map((item) => {
          if (item === void 0) {
            return void 0;
          }
          try {
            const str = JSON.stringify(item, createSerializer(), "  ");
            return str === void 0 ? void 0 : JSON.parse(str);
          } catch (e) {
            return item;
          }
        });
        return util.formatWithOptions(inspectOptions, ...simplifiedData);
      }
    };
    function createSerializer(options = {}) {
      const seen = /* @__PURE__ */ new WeakSet();
      return function(key, value) {
        if (typeof value === "object" && value !== null) {
          if (seen.has(value)) {
            return void 0;
          }
          seen.add(value);
        }
        return serialize(key, value, options);
      };
    }
    function serialize(key, value, options = {}) {
      const serializeMapAndSet = options?.serializeMapAndSet !== false;
      if (value instanceof Error) {
        return value.stack;
      }
      if (!value) {
        return value;
      }
      if (typeof value === "function") {
        return `[function] ${value.toString()}`;
      }
      if (value instanceof Date) {
        return value.toISOString();
      }
      if (serializeMapAndSet && value instanceof Map && Object.fromEntries) {
        return Object.fromEntries(value);
      }
      if (serializeMapAndSet && value instanceof Set && Array.from) {
        return Array.from(value);
      }
      return value;
    }
  }
});

// ../../node_modules/electron-log/src/core/transforms/style.js
var require_style = __commonJS({
  "../../node_modules/electron-log/src/core/transforms/style.js"(exports2, module2) {
    "use strict";
    module2.exports = {
      transformStyles,
      applyAnsiStyles({ data }) {
        return transformStyles(data, styleToAnsi, resetAnsiStyle);
      },
      removeStyles({ data }) {
        return transformStyles(data, () => "");
      }
    };
    var ANSI_COLORS = {
      unset: "\x1B[0m",
      black: "\x1B[30m",
      red: "\x1B[31m",
      green: "\x1B[32m",
      yellow: "\x1B[33m",
      blue: "\x1B[34m",
      magenta: "\x1B[35m",
      cyan: "\x1B[36m",
      white: "\x1B[37m",
      gray: "\x1B[90m"
    };
    function styleToAnsi(style) {
      const color = style.replace(/color:\s*(\w+).*/, "$1").toLowerCase();
      return ANSI_COLORS[color] || "";
    }
    function resetAnsiStyle(string) {
      return string + ANSI_COLORS.unset;
    }
    function transformStyles(data, onStyleFound, onStyleApplied) {
      const foundStyles = {};
      return data.reduce((result, item, index, array) => {
        if (foundStyles[index]) {
          return result;
        }
        if (typeof item === "string") {
          let valueIndex = index;
          let styleApplied = false;
          item = item.replace(/%[1cdfiOos]/g, (match) => {
            valueIndex += 1;
            if (match !== "%c") {
              return match;
            }
            const style = array[valueIndex];
            if (typeof style === "string") {
              foundStyles[valueIndex] = true;
              styleApplied = true;
              return onStyleFound(style, item);
            }
            return match;
          });
          if (styleApplied && onStyleApplied) {
            item = onStyleApplied(item);
          }
        }
        result.push(item);
        return result;
      }, []);
    }
  }
});

// ../../node_modules/electron-log/src/node/transports/console.js
var require_console = __commonJS({
  "../../node_modules/electron-log/src/node/transports/console.js"(exports2, module2) {
    "use strict";
    var {
      concatFirstStringElements,
      format
    } = require_format();
    var { maxDepth, toJSON } = require_object();
    var {
      applyAnsiStyles,
      removeStyles
    } = require_style();
    var { transform } = require_transform();
    var consoleMethods = {
      error: console.error,
      warn: console.warn,
      info: console.info,
      verbose: console.info,
      debug: console.debug,
      silly: console.debug,
      log: console.log
    };
    module2.exports = consoleTransportFactory;
    var separator = process.platform === "win32" ? ">" : "\u203A";
    var DEFAULT_FORMAT = `%c{h}:{i}:{s}.{ms}{scope}%c ${separator} {text}`;
    Object.assign(consoleTransportFactory, {
      DEFAULT_FORMAT
    });
    function consoleTransportFactory(logger) {
      return Object.assign(transport, {
        colorMap: {
          error: "red",
          warn: "yellow",
          info: "cyan",
          verbose: "unset",
          debug: "gray",
          silly: "gray",
          default: "unset"
        },
        format: DEFAULT_FORMAT,
        level: "silly",
        transforms: [
          addTemplateColors,
          format,
          formatStyles,
          concatFirstStringElements,
          maxDepth,
          toJSON
        ],
        useStyles: process.env.FORCE_STYLES,
        writeFn({ message }) {
          const consoleLogFn = consoleMethods[message.level] || consoleMethods.info;
          consoleLogFn(...message.data);
        }
      });
      function transport(message) {
        const data = transform({ logger, message, transport });
        transport.writeFn({
          message: { ...message, data }
        });
      }
    }
    function addTemplateColors({ data, message, transport }) {
      if (typeof transport.format !== "string" || !transport.format.includes("%c")) {
        return data;
      }
      return [
        `color:${levelToStyle(message.level, transport)}`,
        "color:unset",
        ...data
      ];
    }
    function canUseStyles(useStyleValue, level) {
      if (typeof useStyleValue === "boolean") {
        return useStyleValue;
      }
      const useStderr = level === "error" || level === "warn";
      const stream = useStderr ? process.stderr : process.stdout;
      return stream && stream.isTTY;
    }
    function formatStyles(args) {
      const { message, transport } = args;
      const useStyles = canUseStyles(transport.useStyles, message.level);
      const nextTransform = useStyles ? applyAnsiStyles : removeStyles;
      return nextTransform(args);
    }
    function levelToStyle(level, transport) {
      return transport.colorMap[level] || transport.colorMap.default;
    }
  }
});

// ../../node_modules/electron-log/src/node/transports/file/File.js
var require_File = __commonJS({
  "../../node_modules/electron-log/src/node/transports/file/File.js"(exports2, module2) {
    "use strict";
    var EventEmitter = require("events");
    var fs = require("fs");
    var os = require("os");
    var File = class extends EventEmitter {
      asyncWriteQueue = [];
      bytesWritten = 0;
      hasActiveAsyncWriting = false;
      path = null;
      initialSize = void 0;
      writeOptions = null;
      writeAsync = false;
      constructor({
        path,
        writeOptions = { encoding: "utf8", flag: "a", mode: 438 },
        writeAsync = false
      }) {
        super();
        this.path = path;
        this.writeOptions = writeOptions;
        this.writeAsync = writeAsync;
      }
      get size() {
        return this.getSize();
      }
      clear() {
        try {
          fs.writeFileSync(this.path, "", {
            mode: this.writeOptions.mode,
            flag: "w"
          });
          this.reset();
          return true;
        } catch (e) {
          if (e.code === "ENOENT") {
            return true;
          }
          this.emit("error", e, this);
          return false;
        }
      }
      crop(bytesAfter) {
        try {
          const content = readFileSyncFromEnd(this.path, bytesAfter || 4096);
          this.clear();
          this.writeLine(`[log cropped]${os.EOL}${content}`);
        } catch (e) {
          this.emit(
            "error",
            new Error(`Couldn't crop file ${this.path}. ${e.message}`),
            this
          );
        }
      }
      getSize() {
        if (this.initialSize === void 0) {
          try {
            const stats = fs.statSync(this.path);
            this.initialSize = stats.size;
          } catch (e) {
            this.initialSize = 0;
          }
        }
        return this.initialSize + this.bytesWritten;
      }
      increaseBytesWrittenCounter(text) {
        this.bytesWritten += Buffer.byteLength(text, this.writeOptions.encoding);
      }
      isNull() {
        return false;
      }
      nextAsyncWrite() {
        const file = this;
        if (this.hasActiveAsyncWriting || this.asyncWriteQueue.length === 0) {
          return;
        }
        const text = this.asyncWriteQueue.join("");
        this.asyncWriteQueue = [];
        this.hasActiveAsyncWriting = true;
        fs.writeFile(this.path, text, this.writeOptions, (e) => {
          file.hasActiveAsyncWriting = false;
          if (e) {
            file.emit(
              "error",
              new Error(`Couldn't write to ${file.path}. ${e.message}`),
              this
            );
          } else {
            file.increaseBytesWrittenCounter(text);
          }
          file.nextAsyncWrite();
        });
      }
      reset() {
        this.initialSize = void 0;
        this.bytesWritten = 0;
      }
      toString() {
        return this.path;
      }
      writeLine(text) {
        text += os.EOL;
        if (this.writeAsync) {
          this.asyncWriteQueue.push(text);
          this.nextAsyncWrite();
          return;
        }
        try {
          fs.writeFileSync(this.path, text, this.writeOptions);
          this.increaseBytesWrittenCounter(text);
        } catch (e) {
          this.emit(
            "error",
            new Error(`Couldn't write to ${this.path}. ${e.message}`),
            this
          );
        }
      }
    };
    module2.exports = File;
    function readFileSyncFromEnd(filePath, bytesCount) {
      const buffer = Buffer.alloc(bytesCount);
      const stats = fs.statSync(filePath);
      const readLength = Math.min(stats.size, bytesCount);
      const offset = Math.max(0, stats.size - bytesCount);
      const fd = fs.openSync(filePath, "r");
      const totalBytes = fs.readSync(fd, buffer, 0, readLength, offset);
      fs.closeSync(fd);
      return buffer.toString("utf8", 0, totalBytes);
    }
  }
});

// ../../node_modules/electron-log/src/node/transports/file/NullFile.js
var require_NullFile = __commonJS({
  "../../node_modules/electron-log/src/node/transports/file/NullFile.js"(exports2, module2) {
    "use strict";
    var File = require_File();
    var NullFile = class extends File {
      clear() {
      }
      crop() {
      }
      getSize() {
        return 0;
      }
      isNull() {
        return true;
      }
      writeLine() {
      }
    };
    module2.exports = NullFile;
  }
});

// ../../node_modules/electron-log/src/node/transports/file/FileRegistry.js
var require_FileRegistry = __commonJS({
  "../../node_modules/electron-log/src/node/transports/file/FileRegistry.js"(exports2, module2) {
    "use strict";
    var EventEmitter = require("events");
    var fs = require("fs");
    var path = require("path");
    var File = require_File();
    var NullFile = require_NullFile();
    var FileRegistry = class extends EventEmitter {
      store = {};
      constructor() {
        super();
        this.emitError = this.emitError.bind(this);
      }
      /**
       * Provide a File object corresponding to the filePath
       * @param {string} filePath
       * @param {WriteOptions} [writeOptions]
       * @param {boolean} [writeAsync]
       * @return {File}
       */
      provide({ filePath, writeOptions = {}, writeAsync = false }) {
        let file;
        try {
          filePath = path.resolve(filePath);
          if (this.store[filePath]) {
            return this.store[filePath];
          }
          file = this.createFile({ filePath, writeOptions, writeAsync });
        } catch (e) {
          file = new NullFile({ path: filePath });
          this.emitError(e, file);
        }
        file.on("error", this.emitError);
        this.store[filePath] = file;
        return file;
      }
      /**
       * @param {string} filePath
       * @param {WriteOptions} writeOptions
       * @param {boolean} async
       * @return {File}
       * @private
       */
      createFile({ filePath, writeOptions, writeAsync }) {
        this.testFileWriting({ filePath, writeOptions });
        return new File({ path: filePath, writeOptions, writeAsync });
      }
      /**
       * @param {Error} error
       * @param {File} file
       * @private
       */
      emitError(error, file) {
        this.emit("error", error, file);
      }
      /**
       * @param {string} filePath
       * @param {WriteOptions} writeOptions
       * @private
       */
      testFileWriting({ filePath, writeOptions }) {
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, "", { flag: "a", mode: writeOptions.mode });
      }
    };
    module2.exports = FileRegistry;
  }
});

// ../../node_modules/electron-log/src/node/transports/file/index.js
var require_file = __commonJS({
  "../../node_modules/electron-log/src/node/transports/file/index.js"(exports2, module2) {
    "use strict";
    var fs = require("fs");
    var os = require("os");
    var path = require("path");
    var FileRegistry = require_FileRegistry();
    var { transform } = require_transform();
    var { removeStyles } = require_style();
    var {
      format,
      concatFirstStringElements
    } = require_format();
    var { toString } = require_object();
    module2.exports = fileTransportFactory;
    var globalRegistry = new FileRegistry();
    function fileTransportFactory(logger, { registry = globalRegistry, externalApi } = {}) {
      let pathVariables;
      if (registry.listenerCount("error") < 1) {
        registry.on("error", (e, file) => {
          logConsole(`Can't write to ${file}`, e);
        });
      }
      return Object.assign(transport, {
        fileName: getDefaultFileName(logger.variables.processType),
        format: "[{y}-{m}-{d} {h}:{i}:{s}.{ms}] [{level}]{scope} {text}",
        getFile,
        inspectOptions: { depth: 5 },
        level: "silly",
        maxSize: 1024 ** 2,
        readAllLogs,
        sync: true,
        transforms: [removeStyles, format, concatFirstStringElements, toString],
        writeOptions: { flag: "a", mode: 438, encoding: "utf8" },
        archiveLogFn(file) {
          const oldPath = file.toString();
          const inf = path.parse(oldPath);
          try {
            fs.renameSync(oldPath, path.join(inf.dir, `${inf.name}.old${inf.ext}`));
          } catch (e) {
            logConsole("Could not rotate log", e);
            const quarterOfMaxSize = Math.round(transport.maxSize / 4);
            file.crop(Math.min(quarterOfMaxSize, 256 * 1024));
          }
        },
        resolvePathFn(vars) {
          return path.join(vars.libraryDefaultDir, vars.fileName);
        },
        setAppName(name) {
          logger.dependencies.externalApi.setAppName(name);
        }
      });
      function transport(message) {
        const file = getFile(message);
        const needLogRotation = transport.maxSize > 0 && file.size > transport.maxSize;
        if (needLogRotation) {
          transport.archiveLogFn(file);
          file.reset();
        }
        const content = transform({ logger, message, transport });
        file.writeLine(content);
      }
      function initializeOnFirstAccess() {
        if (pathVariables) {
          return;
        }
        pathVariables = Object.create(
          Object.prototype,
          {
            ...Object.getOwnPropertyDescriptors(
              externalApi.getPathVariables()
            ),
            fileName: {
              get() {
                return transport.fileName;
              },
              enumerable: true
            }
          }
        );
        if (typeof transport.archiveLog === "function") {
          transport.archiveLogFn = transport.archiveLog;
          logConsole("archiveLog is deprecated. Use archiveLogFn instead");
        }
        if (typeof transport.resolvePath === "function") {
          transport.resolvePathFn = transport.resolvePath;
          logConsole("resolvePath is deprecated. Use resolvePathFn instead");
        }
      }
      function logConsole(message, error = null, level = "error") {
        const data = [`electron-log.transports.file: ${message}`];
        if (error) {
          data.push(error);
        }
        logger.transports.console({ data, date: /* @__PURE__ */ new Date(), level });
      }
      function getFile(msg) {
        initializeOnFirstAccess();
        const filePath = transport.resolvePathFn(pathVariables, msg);
        return registry.provide({
          filePath,
          writeAsync: !transport.sync,
          writeOptions: transport.writeOptions
        });
      }
      function readAllLogs({ fileFilter = (f) => f.endsWith(".log") } = {}) {
        initializeOnFirstAccess();
        const logsPath = path.dirname(transport.resolvePathFn(pathVariables));
        if (!fs.existsSync(logsPath)) {
          return [];
        }
        return fs.readdirSync(logsPath).map((fileName) => path.join(logsPath, fileName)).filter(fileFilter).map((logPath) => {
          try {
            return {
              path: logPath,
              lines: fs.readFileSync(logPath, "utf8").split(os.EOL)
            };
          } catch {
            return null;
          }
        }).filter(Boolean);
      }
    }
    function getDefaultFileName(processType = process.type) {
      switch (processType) {
        case "renderer":
          return "renderer.log";
        case "worker":
          return "worker.log";
        default:
          return "main.log";
      }
    }
  }
});

// ../../node_modules/electron-log/src/node/transports/ipc.js
var require_ipc = __commonJS({
  "../../node_modules/electron-log/src/node/transports/ipc.js"(exports2, module2) {
    "use strict";
    var { maxDepth, toJSON } = require_object();
    var { transform } = require_transform();
    module2.exports = ipcTransportFactory;
    function ipcTransportFactory(logger, { externalApi }) {
      Object.assign(transport, {
        depth: 3,
        eventId: "__ELECTRON_LOG_IPC__",
        level: logger.isDev ? "silly" : false,
        transforms: [toJSON, maxDepth]
      });
      return externalApi?.isElectron() ? transport : void 0;
      function transport(message) {
        if (message?.variables?.processType === "renderer") {
          return;
        }
        externalApi?.sendIpc(transport.eventId, {
          ...message,
          data: transform({ logger, message, transport })
        });
      }
    }
  }
});

// ../../node_modules/electron-log/src/node/transports/remote.js
var require_remote = __commonJS({
  "../../node_modules/electron-log/src/node/transports/remote.js"(exports2, module2) {
    "use strict";
    var http = require("http");
    var https = require("https");
    var { transform } = require_transform();
    var { removeStyles } = require_style();
    var { toJSON, maxDepth } = require_object();
    module2.exports = remoteTransportFactory;
    function remoteTransportFactory(logger) {
      return Object.assign(transport, {
        client: { name: "electron-application" },
        depth: 6,
        level: false,
        requestOptions: {},
        transforms: [removeStyles, toJSON, maxDepth],
        makeBodyFn({ message }) {
          return JSON.stringify({
            client: transport.client,
            data: message.data,
            date: message.date.getTime(),
            level: message.level,
            scope: message.scope,
            variables: message.variables
          });
        },
        processErrorFn({ error }) {
          logger.processMessage(
            {
              data: [`electron-log: can't POST ${transport.url}`, error],
              level: "warn"
            },
            { transports: ["console", "file"] }
          );
        },
        sendRequestFn({ serverUrl, requestOptions, body }) {
          const httpTransport = serverUrl.startsWith("https:") ? https : http;
          const request = httpTransport.request(serverUrl, {
            method: "POST",
            ...requestOptions,
            headers: {
              "Content-Type": "application/json",
              "Content-Length": body.length,
              ...requestOptions.headers
            }
          });
          request.write(body);
          request.end();
          return request;
        }
      });
      function transport(message) {
        if (!transport.url) {
          return;
        }
        const body = transport.makeBodyFn({
          logger,
          message: { ...message, data: transform({ logger, message, transport }) },
          transport
        });
        const request = transport.sendRequestFn({
          serverUrl: transport.url,
          requestOptions: transport.requestOptions,
          body: Buffer.from(body, "utf8")
        });
        request.on("error", (error) => transport.processErrorFn({
          error,
          logger,
          message,
          request,
          transport
        }));
      }
    }
  }
});

// ../../node_modules/electron-log/src/node/createDefaultLogger.js
var require_createDefaultLogger = __commonJS({
  "../../node_modules/electron-log/src/node/createDefaultLogger.js"(exports2, module2) {
    "use strict";
    var Logger = require_Logger();
    var ErrorHandler = require_ErrorHandler();
    var EventLogger = require_EventLogger();
    var transportConsole = require_console();
    var transportFile = require_file();
    var transportIpc = require_ipc();
    var transportRemote = require_remote();
    module2.exports = createDefaultLogger;
    function createDefaultLogger({ dependencies, initializeFn }) {
      const defaultLogger = new Logger({
        dependencies,
        errorHandler: new ErrorHandler(),
        eventLogger: new EventLogger(),
        initializeFn,
        isDev: dependencies.externalApi?.isDev(),
        logId: "default",
        transportFactories: {
          console: transportConsole,
          file: transportFile,
          ipc: transportIpc,
          remote: transportRemote
        },
        variables: {
          processType: "main"
        }
      });
      defaultLogger.default = defaultLogger;
      defaultLogger.Logger = Logger;
      defaultLogger.processInternalErrorFn = (e) => {
        defaultLogger.transports.console.writeFn({
          message: {
            data: ["Unhandled electron-log error", e],
            level: "error"
          }
        });
      };
      return defaultLogger;
    }
  }
});

// ../../node_modules/electron-log/src/main/index.js
var require_main = __commonJS({
  "../../node_modules/electron-log/src/main/index.js"(exports2, module2) {
    "use strict";
    var electron = require_electron();
    var ElectronExternalApi = require_ElectronExternalApi();
    var { initialize } = require_initialize();
    var createDefaultLogger = require_createDefaultLogger();
    var externalApi = new ElectronExternalApi({ electron });
    var defaultLogger = createDefaultLogger({
      dependencies: { externalApi },
      initializeFn: initialize
    });
    module2.exports = defaultLogger;
    externalApi.onIpc("__ELECTRON_LOG__", (_, message) => {
      if (message.scope) {
        defaultLogger.Logger.getInstance(message).scope(message.scope);
      }
      const date = new Date(message.date);
      processMessage({
        ...message,
        date: date.getTime() ? date : /* @__PURE__ */ new Date()
      });
    });
    externalApi.onIpcInvoke("__ELECTRON_LOG__", (_, { cmd = "", logId }) => {
      switch (cmd) {
        case "getOptions": {
          const logger = defaultLogger.Logger.getInstance({ logId });
          return {
            levels: logger.levels,
            logId
          };
        }
        default: {
          processMessage({ data: [`Unknown cmd '${cmd}'`], level: "error" });
          return {};
        }
      }
    });
    function processMessage(message) {
      defaultLogger.Logger.getInstance(message)?.processMessage(message);
    }
  }
});

// ../../node_modules/electron-log/main.js
var require_main2 = __commonJS({
  "../../node_modules/electron-log/main.js"(exports2, module2) {
    "use strict";
    var main = require_main();
    module2.exports = main;
  }
});

// ../../packages/shared/src/unified-network-interceptor.ts
var unified_network_interceptor_exports = {};
__export(unified_network_interceptor_exports, {
  MalformedBodyError: () => MalformedBodyError,
  createAnthropicSseStrippingStream: () => createAnthropicSseStrippingStream,
  createOpenAiResponsesSseStrippingStream: () => createOpenAiResponsesSseStrippingStream,
  createOpenAiSseStrippingStream: () => createOpenAiSseStrippingStream,
  injectMetadataIntoToolSchema: () => injectMetadataIntoToolSchema,
  repairResponsesHistoryInPlace: () => repairResponsesHistoryInPlace,
  resolveAdapterNameFromPiApiHint: () => resolveAdapterNameFromPiApiHint,
  sanitizeEmptyTextCacheControl: () => sanitizeEmptyTextCacheControl,
  sanitizeOpenAiHistoryInPlace: () => sanitizeOpenAiHistoryInPlace,
  stripMetadataFieldsFromRawJson: () => stripMetadataFieldsFromRawJson,
  upgradePromptCacheTtl: () => upgradePromptCacheTtl,
  validateOpenAiChatBody: () => validateOpenAiChatBody,
  validateOpenAiResponsesBody: () => validateOpenAiResponsesBody
});
module.exports = __toCommonJS(unified_network_interceptor_exports);

// ../../packages/shared/src/interceptor-common.ts
var import_node_fs = require("node:fs");
var import_node_path = require("node:path");

// ../../packages/shared/src/config/paths.ts
var import_os = require("os");
var import_path = require("path");
var import_fs = require("fs");

// ../../packages/shared/src/utils/debug.ts
var debugEnabled = typeof process !== "undefined" && process.env?.CRAFT_DEBUG === "1";
function isCliJsonOnlyMode() {
  return typeof process !== "undefined" && process.env?.CRAFT_CLI_JSON_ONLY === "1";
}
function detectEnvironment() {
  if (typeof process === "undefined") {
    return "electron-renderer";
  }
  if (process.type === "browser") {
    return "electron-main";
  }
  if (process.type === "renderer") {
    return "electron-renderer";
  }
  return "cli";
}
var electronLog = null;
var electronLogChecked = false;
function getElectronLog() {
  if (electronLogChecked) {
    return electronLog ?? null;
  }
  electronLogChecked = true;
  try {
    const loaded = require_main2();
    electronLog = loaded?.default ?? loaded ?? null;
  } catch {
    electronLog = null;
  }
  return electronLog ?? null;
}
function isDebugEnabled() {
  if (isCliJsonOnlyMode()) return false;
  return debugEnabled;
}
function safeStringify(obj) {
  try {
    return JSON.stringify(obj);
  } catch {
    const seen = /* @__PURE__ */ new WeakSet();
    return JSON.stringify(obj, (_key, value) => {
      if (typeof value === "object" && value !== null) {
        if (seen.has(value)) {
          return "[Circular]";
        }
        seen.add(value);
      }
      return value;
    });
  }
}
function formatMessage(scope, message, args) {
  const timestamp = (/* @__PURE__ */ new Date()).toISOString();
  const scopeStr = scope ? `[${scope}] ` : "";
  const argsStr = args.length > 0 ? " " + args.map((a) => typeof a === "object" ? safeStringify(a) : String(a)).join(" ") : "";
  return `${timestamp} ${scopeStr}${message}${argsStr}
`;
}
function output(formatted) {
  const env = detectEnvironment();
  if (env === "electron-main") {
    const log = getElectronLog();
    log?.info?.(formatted.trim());
  }
  if (env === "electron-renderer") {
    console.log(formatted.trim());
  } else if (typeof process !== "undefined" && process.stderr) {
    process.stderr.write(formatted);
  } else {
    console.log(formatted.trim());
  }
}
function debug(message, ...args) {
  if (!isDebugEnabled()) return;
  output(formatMessage(void 0, message, args));
}

// ../../packages/shared/src/config/paths.ts
var ROOT_DIR_NAME = ".zenskill";
var PRE_MERGE_DESKTOP_DIR_NAME = ".zenskill/desktop";
var LEGACY_DIR_NAME = ".craft-agent";
var MIGRATED_BAK_SUFFIX = ".migrated-bak";
function getLegacyConfigDir() {
  return (0, import_path.join)((0, import_os.homedir)(), LEGACY_DIR_NAME);
}
var migrationNotice = null;
function describeError(error) {
  return error instanceof Error ? error.message : String(error);
}
function postResolutionFixups(dir) {
  const configPath = (0, import_path.join)(dir, "config.json");
  if (!(0, import_fs.existsSync)(configPath)) return;
  try {
    const config = JSON.parse((0, import_fs.readFileSync)(configPath, "utf8"));
    if (config?.setupDeferred === true) {
      const connections = config?.llmConnections;
      if (!(Array.isArray(connections) && connections.length > 0)) {
        delete config.setupDeferred;
        debug(`[paths] cleared stale setupDeferred in ${configPath}`);
      }
    }
    const prefixes = [`~/${PRE_MERGE_DESKTOP_DIR_NAME}`, `~/${LEGACY_DIR_NAME}`];
    const workspaces = config?.workspaces;
    let changed = false;
    for (const ws of workspaces ?? []) {
      if (typeof ws.rootPath !== "string") continue;
      const norm = ws.rootPath.replace(/\\/g, "/");
      for (const prefix of prefixes) {
        if (norm.startsWith(prefix)) {
          ws.rootPath = `~/${ROOT_DIR_NAME}` + norm.slice(prefix.length);
          changed = true;
          break;
        }
      }
    }
    if (changed) {
      (0, import_fs.writeFileSync)(configPath, JSON.stringify(config, null, 2), "utf8");
      debug(`[paths] rewrote workspace rootPaths into ${dir}`);
    }
  } catch (error) {
    debug(`[paths] failed post-resolution fixups on ${configPath}: ${describeError(error)}`);
  }
}
function countEntriesRecursive(dir) {
  let count = 0;
  for (const entry of (0, import_fs.readdirSync)(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink() || !entry.isDirectory()) {
      count += 1;
      continue;
    }
    count += countEntriesRecursive((0, import_path.join)(dir, entry.name));
  }
  return count;
}
function mergeDesktopDirIntoRoot(rootDir, desktopDir) {
  try {
    debug(`[paths] merging pre-D8 desktop dir ${desktopDir} -> ${rootDir}`);
    const cliConfig = (0, import_path.join)(rootDir, "config.json");
    if ((0, import_fs.existsSync)(cliConfig)) {
      (0, import_fs.copyFileSync)(cliConfig, (0, import_path.join)(rootDir, "config.json.cli-bak"));
    }
    (0, import_fs.cpSync)(desktopDir, rootDir, { recursive: true });
    for (const entry of (0, import_fs.readdirSync)(desktopDir, { withFileTypes: true })) {
      if (!(0, import_fs.existsSync)((0, import_path.join)(rootDir, entry.name))) {
        throw new Error(`merge verification failed: missing ${entry.name}`);
      }
    }
    (0, import_fs.renameSync)(desktopDir, `${desktopDir}${MIGRATED_BAK_SUFFIX}`);
    migrationNotice = `Merged pre-D8 desktop data (${desktopDir}) into ${rootDir} (backup at ${desktopDir}${MIGRATED_BAK_SUFFIX})`;
    debug(`[paths] ${migrationNotice}`);
    return true;
  } catch (error) {
    migrationNotice = `Desktop merge into ${rootDir} failed; continuing with the pre-merge desktop directory: ${describeError(error)}`;
    debug(`[paths] ${migrationNotice}`);
    return false;
  }
}
function migrateLegacyConfigDir(rootDir, legacyDir) {
  try {
    debug(`[paths] migrating config dir ${legacyDir} -> ${rootDir}`);
    (0, import_fs.cpSync)(legacyDir, rootDir, { recursive: true });
    const legacyCount = countEntriesRecursive(legacyDir);
    const rootCount = countEntriesRecursive(rootDir);
    if (rootCount !== legacyCount) {
      throw new Error(`copy verification failed (${legacyCount} entries -> ${rootCount})`);
    }
    (0, import_fs.renameSync)(legacyDir, `${legacyDir}${MIGRATED_BAK_SUFFIX}`);
    migrationNotice = `Migrated config data from ${legacyDir} to ${rootDir} (backup at ${legacyDir}${MIGRATED_BAK_SUFFIX})`;
    debug(`[paths] ${migrationNotice}`);
    return true;
  } catch (error) {
    try {
      (0, import_fs.rmSync)(rootDir, { recursive: true, force: true });
    } catch {
    }
    migrationNotice = `Config migration from ${legacyDir} failed; continuing with the legacy directory: ${describeError(error)}`;
    debug(`[paths] ${migrationNotice}`);
    return false;
  }
}
function resolveConfigDir() {
  const zenEnv = process.env.ZENSKILL_CONFIG_DIR;
  if (zenEnv) return zenEnv;
  const craftEnv = process.env.CRAFT_CONFIG_DIR;
  if (craftEnv) return craftEnv;
  const rootDir = (0, import_path.join)((0, import_os.homedir)(), ROOT_DIR_NAME);
  const preMergeDesktopDir = (0, import_path.join)(rootDir, "desktop");
  const legacyDir = getLegacyConfigDir();
  let resolved;
  if (process.env.ZENSKILL_DATA_MIGRATE === "0") {
    resolved = (0, import_fs.existsSync)(preMergeDesktopDir) ? preMergeDesktopDir : rootDir;
  } else if ((0, import_fs.existsSync)(preMergeDesktopDir)) {
    resolved = mergeDesktopDirIntoRoot(rootDir, preMergeDesktopDir) ? rootDir : preMergeDesktopDir;
  } else if (!(0, import_fs.existsSync)((0, import_path.join)(rootDir, "config.json")) && (0, import_fs.existsSync)(legacyDir)) {
    resolved = migrateLegacyConfigDir(rootDir, legacyDir) ? rootDir : legacyDir;
  } else {
    resolved = rootDir;
  }
  postResolutionFixups(resolved);
  return resolved;
}
var CONFIG_DIR = resolveConfigDir();

// ../../packages/shared/src/interceptor-common.ts
var IS_PACKAGED = process.argv.some((arg) => arg.includes("app.asar"));
var INTERCEPTOR_LOGGING_ENABLED = !IS_PACKAGED;
var DEBUG = INTERCEPTOR_LOGGING_ENABLED && (process.argv.includes("--debug") || process.env.CRAFT_DEBUG === "1");
var CONFIG_FILE = (0, import_node_path.join)(CONFIG_DIR, "config.json");
var _sessionDir = process.env.CRAFT_SESSION_DIR || null;
var LOG_DIR = (0, import_node_path.join)(CONFIG_DIR, "logs");
var LOG_FILE = (0, import_node_path.join)(LOG_DIR, "interceptor.log");
try {
  if (!(0, import_node_fs.existsSync)(LOG_DIR)) {
    (0, import_node_fs.mkdirSync)(LOG_DIR, { recursive: true });
  }
} catch {
}
var MAX_LOG_AGE_MS = 24 * 60 * 60 * 1e3;
try {
  if ((0, import_node_fs.existsSync)(LOG_FILE)) {
    const stat = (0, import_node_fs.statSync)(LOG_FILE);
    if (Date.now() - stat.mtimeMs > MAX_LOG_AGE_MS) {
      const prevLog = LOG_FILE + ".prev";
      (0, import_node_fs.renameSync)(LOG_FILE, prevLog);
    }
  }
} catch {
}
function debugLog(...args) {
  if (!DEBUG) return;
  const timestamp = (/* @__PURE__ */ new Date()).toISOString();
  const message = `${timestamp} [interceptor] ${args.map((a) => {
    if (typeof a === "object") {
      try {
        return JSON.stringify(a);
      } catch (e) {
        const keys = a && typeof a === "object" ? Object.keys(a).join(", ") : "unknown";
        return `[CYCLIC STRUCTURE, keys: ${keys}] (error: ${e})`;
      }
    }
    return String(a);
  }).join(" ")}`;
  try {
    (0, import_node_fs.appendFileSync)(LOG_FILE, message + "\n");
  } catch {
  }
}
var _cachedConfig = null;
var _cacheTimestamp = 0;
var CONFIG_CACHE_TTL_MS = 100;
function getInterceptorConfig() {
  const now = Date.now();
  if (_cachedConfig && now - _cacheTimestamp < CONFIG_CACHE_TTL_MS) return _cachedConfig;
  try {
    const content = (0, import_node_fs.readFileSync)(CONFIG_FILE, "utf-8");
    _cachedConfig = JSON.parse(content);
    _cacheTimestamp = now;
    return _cachedConfig;
  } catch {
    return null;
  }
}
function isRichToolDescriptionsEnabled() {
  const config = getInterceptorConfig();
  if (config?.richToolDescriptions !== void 0) {
    return config.richToolDescriptions;
  }
  return true;
}
function isExtendedPromptCacheEnabled() {
  const config = getInterceptorConfig();
  return config?.extendedPromptCache === true;
}
function is1MContextEnabled() {
  const config = getInterceptorConfig();
  return config?.enable1MContext === true;
}
var MAX_ERROR_AGE_MS = 5 * 60 * 1e3;
function getErrorFilePath() {
  if (_sessionDir) return (0, import_node_path.join)(_sessionDir, "api-error.json");
  return (0, import_node_path.join)(CONFIG_DIR, "api-error.json");
}
function setStoredError(error) {
  const errorFile = getErrorFilePath();
  try {
    if (error) {
      (0, import_node_fs.writeFileSync)(errorFile, JSON.stringify(error));
      debugLog(`[setStoredError] Wrote error to file: ${error.status} ${error.message}`);
    } else {
      try {
        (0, import_node_fs.unlinkSync)(errorFile);
      } catch {
      }
    }
  } catch (e) {
    debugLog(`[setStoredError] Failed to write: ${e}`);
  }
}
function getMetadataFilePath() {
  return _sessionDir ? (0, import_node_path.join)(_sessionDir, "tool-metadata.json") : null;
}
function readMetadataFileFromDir(dir) {
  try {
    const filePath = (0, import_node_path.join)(dir, "tool-metadata.json");
    const data = (0, import_node_fs.readFileSync)(filePath, "utf-8");
    return JSON.parse(data);
  } catch (error) {
    debugLog(`[toolMetadataStore.read] Failed for dir=${dir}: ${error instanceof Error ? error.message : String(error)}`);
    return {};
  }
}
var _metadataMap = /* @__PURE__ */ new Map();
function readMetadataFile() {
  if (!_sessionDir) return {};
  return readMetadataFileFromDir(_sessionDir);
}
function writeMetadataFile(allMetadata) {
  const filePath = getMetadataFilePath();
  if (!filePath) return;
  try {
    const tmpPath = filePath + ".tmp";
    (0, import_node_fs.writeFileSync)(tmpPath, JSON.stringify(allMetadata));
    (0, import_node_fs.renameSync)(tmpPath, filePath);
  } catch (error) {
    debugLog(`[toolMetadataStore.write] Failed for file=${filePath}: ${error instanceof Error ? error.message : String(error)}`);
  }
}
function mergeAndWriteMetadata(updater, retries = 1) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const all = readMetadataFile();
      updater(all);
      writeMetadataFile(all);
      return;
    } catch (error) {
      debugLog(`[toolMetadataStore.merge] Attempt ${attempt + 1}/${retries + 1} failed: ${error instanceof Error ? error.message : String(error)}`);
      if (attempt === retries) return;
    }
  }
}
var toolMetadataStore = {
  /**
   * Set session directory and pre-populate in-memory map from file.
   * Called by main process so subsequent get() calls are O(1) memory lookups.
   * Does NOT clear the map — entries from other sessions are preserved since
   * tool_use_ids are globally unique UUIDs and won't conflict.
   */
  setSessionDir(dir) {
    _sessionDir = dir;
    const all = readMetadataFile();
    for (const [id, meta] of Object.entries(all)) {
      _metadataMap.set(id, meta);
    }
  },
  /** Store metadata — writes to in-memory Map + cached file */
  set(toolUseId, metadata) {
    _metadataMap.set(toolUseId, metadata);
    mergeAndWriteMetadata((all) => {
      all[toolUseId] = metadata;
    });
  },
  /**
   * Read metadata — checks in-memory first, then session file.
   * Accepts an explicit sessionDir to read from the correct file even when
   * _sessionDir has been clobbered by a concurrent session's setSessionDir().
   */
  get(toolUseId, sessionDir) {
    const inMemory = _metadataMap.get(toolUseId);
    if (inMemory) return inMemory;
    const dir = sessionDir || _sessionDir;
    if (!dir) return void 0;
    const all = readMetadataFileFromDir(dir);
    const entry = all[toolUseId];
    if (entry) {
      _metadataMap.set(toolUseId, entry);
    }
    return entry;
  },
  delete(toolUseId) {
    _metadataMap.delete(toolUseId);
    mergeAndWriteMetadata((all) => {
      delete all[toolUseId];
    });
  },
  get size() {
    return _metadataMap.size;
  },
  /** Clear all in-memory entries. Used by tests to prevent cross-file state leaks. */
  _clearForTesting() {
    _metadataMap.clear();
  }
};
var displayNameSchema = {
  type: "string",
  description: 'REQUIRED: Human-friendly name for this action (2-4 words, e.g., "List Folders", "Search Documents", "Create Task")'
};
var intentSchema = {
  type: "string",
  description: "REQUIRED: Describe what you are trying to accomplish with this tool call (1-2 sentences)"
};

// ../../packages/shared/src/feature-flags.ts
function getEnv(key) {
  if (typeof process !== "undefined" && process.env) return process.env[key];
  return void 0;
}
function parseBooleanEnv(value) {
  if (value == null) return void 0;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return void 0;
}
function isDevRuntime() {
  const nodeEnv = (getEnv("NODE_ENV") || "").toLowerCase();
  return nodeEnv === "development" || nodeEnv === "dev" || getEnv("CRAFT_DEBUG") === "1";
}
function isDeveloperFeedbackEnabled() {
  const override = parseBooleanEnv(getEnv("CRAFT_FEATURE_DEVELOPER_FEEDBACK"));
  if (override !== void 0) return override;
  return isDevRuntime();
}
function isCraftAgentsCliEnabled() {
  const override = parseBooleanEnv(getEnv("CRAFT_FEATURE_CRAFT_AGENTS_CLI"));
  if (override !== void 0) return override;
  return false;
}
function isEmbeddedServerEnabled() {
  const override = parseBooleanEnv(getEnv("CRAFT_FEATURE_EMBEDDED_SERVER"));
  if (override !== void 0) return override;
  return false;
}
function isPagesSharingEnabled() {
  const override = parseBooleanEnv(getEnv("CRAFT_FEATURE_PAGES_SHARING"));
  if (override !== void 0) return override;
  return true;
}
var FEATURE_FLAGS = {
  /** Enable Opus 4.7 fast mode (speed:"fast" + beta header). 6x pricing. */
  fastMode: false,
  /**
   * Enable agent developer feedback tool.
   *
   * Defaults to enabled in explicit development runtimes; disabled otherwise.
   * Override with CRAFT_FEATURE_DEVELOPER_FEEDBACK=1|0.
   */
  get developerFeedback() {
    return isDeveloperFeedbackEnabled();
  },
  /**
   * Enable craft-agent CLI guidance and guardrails.
   *
   * Defaults to disabled. Override with CRAFT_FEATURE_CRAFT_AGENTS_CLI=1|0.
   */
  get craftAgentsCli() {
    return isCraftAgentsCliEnabled();
  },
  /**
   * Enable embedded server settings page.
   *
   * Defaults to disabled. Override with CRAFT_FEATURE_EMBEDDED_SERVER=1|0.
   */
  get embeddedServer() {
    return isEmbeddedServerEnabled();
  },
  /**
   * Enable Pages sharing (publish to Cloudflare).
   *
   * Defaults to ENABLED (Worker deployed 2026-08-27). Opt out with
   * CRAFT_FEATURE_PAGES_SHARING=0.
   */
  get pagesSharing() {
    return isPagesSharingEnabled();
  }
};

// ../../packages/shared/src/interceptor-request-utils.ts
async function resolveRequestContext(input, init) {
  if (typeof init?.body === "string") {
    return { bodyStr: init.body, normalizedInit: init };
  }
  if (input instanceof Request) {
    try {
      const bodyStr = await input.clone().text();
      const normalizedInit = {
        method: init?.method ?? input.method,
        headers: init?.headers ?? input.headers,
        body: init?.body ?? bodyStr
      };
      return { bodyStr, normalizedInit };
    } catch {
    }
  }
  return { bodyStr: void 0, normalizedInit: init ?? {} };
}

// ../../packages/shared/src/unified-network-interceptor.ts
var DEBUG_SSE_RAW = process.env.CRAFT_DEBUG_SSE_RAW === "1";
var PROXY_URL = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy || "";
var NO_PROXY = process.env.NO_PROXY || process.env.no_proxy || "";
function redactProxyUrl(proxyUrl) {
  try {
    const parsed = new URL(proxyUrl);
    parsed.username = "";
    parsed.password = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return "(invalid proxy URL)";
  }
}
var noProxyPatterns = NO_PROXY ? NO_PROXY.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean) : [];
function shouldBypassProxy(url) {
  if (noProxyPatterns.length === 0) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return noProxyPatterns.some((pattern) => {
      if (pattern === "*") return true;
      if (pattern.startsWith(".")) return hostname.endsWith(pattern);
      return hostname === pattern || hostname.endsWith("." + pattern);
    });
  } catch {
    return false;
  }
}
function getProxyForUrl(url) {
  if (!PROXY_URL || shouldBypassProxy(url)) return void 0;
  return PROXY_URL;
}
if (PROXY_URL) {
  debugLog(`[proxy] Configured: ${redactProxyUrl(PROXY_URL)}${NO_PROXY ? `, NO_PROXY: ${NO_PROXY}` : ""}`);
}
var MalformedBodyError = class extends Error {
  /** Stable error code for telemetry/UX */
  code;
  /** Human-readable detail to show in logs and surface to the user */
  detail;
  /** Adapter name (for diagnostics) */
  adapter;
  constructor(args) {
    super(`[${args.adapter}] Outgoing body rejected: ${args.code} \u2014 ${args.detail}`);
    this.name = "MalformedBodyError";
    this.code = args.code;
    this.detail = args.detail;
    this.adapter = args.adapter;
  }
};
function injectMetadataFields(properties, required) {
  const { _displayName, _intent, ...rest } = properties;
  const newProperties = {
    _displayName: _displayName || displayNameSchema,
    _intent: _intent || intentSchema,
    ...rest
  };
  const otherRequired = (required || []).filter((r) => r !== "_displayName" && r !== "_intent");
  return { properties: newProperties, required: ["_displayName", "_intent", ...otherRequired] };
}
function injectMetadataIntoToolSchema(schema) {
  const normalizedProperties = schema.properties && typeof schema.properties === "object" ? schema.properties : {};
  const normalizedRequired = Array.isArray(schema.required) ? schema.required : [];
  const result = injectMetadataFields(normalizedProperties, normalizedRequired);
  return {
    ...schema,
    properties: result.properties,
    required: result.required
  };
}
function captureMetadataFromInput(toolId, toolName, parsed) {
  const intent = typeof parsed._intent === "string" ? parsed._intent : void 0;
  const displayName = typeof parsed._displayName === "string" ? parsed._displayName : void 0;
  if (intent || displayName) {
    toolMetadataStore.set(toolId, { intent, displayName, timestamp: Date.now() });
    debugLog(`[SSE] Stored metadata for ${toolName} (${toolId}): intent=${!!intent}, displayName=${!!displayName}`);
    return true;
  }
  return false;
}
function stripMetadataFieldsFromRawJson(json) {
  return json.replace(/"_intent"\s*:\s*"(?:[^"\\]|\\.)*"\s*,?\s*/g, "").replace(/"_displayName"\s*:\s*"(?:[^"\\]|\\.)*"\s*,?\s*/g, "").replace(/,\s*}/g, "}");
}
function getConfiguredBaseUrl() {
  return process.env.ANTHROPIC_BASE_URL?.trim() || "https://api.anthropic.com";
}
var FAST_MODE_BETA = "fast-mode-2026-02-01";
function sanitizeEmptyTextCacheControl(body) {
  const messages = body.messages;
  if (!messages) return 0;
  let stripped = 0;
  for (const message of messages) {
    if (!Array.isArray(message.content)) continue;
    for (const block of message.content) {
      if (block.type === "text" && block.cache_control && (typeof block.text !== "string" || !block.text.trim())) {
        delete block.cache_control;
        stripped++;
      }
    }
  }
  if (stripped > 0) {
    debugLog(`[Anthropic] Stripped cache_control from ${stripped} empty text block(s)`);
  }
  return stripped;
}
function stripPromptCacheTtl(body) {
  let stripped = 0;
  const tools = body.tools;
  if (Array.isArray(tools)) {
    for (const tool of tools) {
      const cc = tool.cache_control;
      if (cc?.type === "ephemeral" && "ttl" in cc) {
        delete cc.ttl;
        stripped++;
      }
    }
  }
  const system = body.system;
  if (Array.isArray(system)) {
    for (const block of system) {
      const cc = block.cache_control;
      if (cc?.type === "ephemeral" && "ttl" in cc) {
        delete cc.ttl;
        stripped++;
      }
    }
  }
  const messages = body.messages;
  if (messages) {
    for (const message of messages) {
      if (!Array.isArray(message.content)) continue;
      for (const block of message.content) {
        const cc = block.cache_control;
        if (cc?.type === "ephemeral" && "ttl" in cc) {
          delete cc.ttl;
          stripped++;
        }
      }
    }
  }
  const topLevel = body.cache_control;
  if (topLevel?.type === "ephemeral" && "ttl" in topLevel) {
    delete topLevel.ttl;
    stripped++;
  }
  if (stripped > 0) {
    debugLog(`[Anthropic] Stripped TTL from ${stripped} cache_control block(s) (extendedPromptCache=false)`);
  }
  return stripped;
}
function upgradePromptCacheTtl(body) {
  if (!isExtendedPromptCacheEnabled()) return stripPromptCacheTtl(body);
  let upgraded = 0;
  const tools = body.tools;
  if (Array.isArray(tools)) {
    for (const tool of tools) {
      if (tool.cache_control && tool.cache_control.type === "ephemeral") {
        tool.cache_control.ttl = "1h";
        upgraded++;
      }
    }
  }
  const system = body.system;
  if (Array.isArray(system)) {
    for (const block of system) {
      if (block.cache_control && block.cache_control.type === "ephemeral") {
        block.cache_control.ttl = "1h";
        upgraded++;
      }
    }
  }
  const messages = body.messages;
  if (messages) {
    for (const message of messages) {
      if (!Array.isArray(message.content)) continue;
      for (const block of message.content) {
        if (block.cache_control && block.cache_control.type === "ephemeral") {
          block.cache_control.ttl = "1h";
          upgraded++;
        }
      }
    }
  }
  const topLevel = body.cache_control;
  if (topLevel?.type === "ephemeral") {
    topLevel.ttl = "1h";
    upgraded++;
  }
  if (upgraded > 0) {
    debugLog(`[Anthropic] Upgraded ${upgraded} cache_control block(s) to 1h TTL`);
  }
  return upgraded;
}
function shouldEnableFastMode(model) {
  if (!FEATURE_FLAGS.fastMode) return false;
  return typeof model === "string" && model === "claude-opus-4-7";
}
function appendBetaHeader(headers, beta) {
  let headerObj = {};
  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      headerObj[key] = value;
    });
  } else if (Array.isArray(headers)) {
    for (const [key, value] of headers) {
      headerObj[key] = value;
    }
  } else if (headers) {
    headerObj = { ...headers };
  }
  const existing = headerObj["anthropic-beta"];
  headerObj["anthropic-beta"] = existing ? `${existing},${beta}` : beta;
  return headerObj;
}
function stripBetaHeader(headers, beta) {
  let headerObj = {};
  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      headerObj[key] = value;
    });
  } else if (Array.isArray(headers)) {
    for (const [key, value] of headers) {
      headerObj[key] = value;
    }
  } else if (headers) {
    headerObj = { ...headers };
  }
  const existing = headerObj["anthropic-beta"];
  if (existing) {
    headerObj["anthropic-beta"] = existing.split(",").filter((b) => b.trim() !== beta).join(",");
  }
  return headerObj;
}
var SSE_EVENT_RE = /^event:\s*(.+)$/;
var SSE_DATA_RE = /^data:\s*(.+)$/;
function createAnthropicSseStrippingStream() {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const trackedBlocks = /* @__PURE__ */ new Map();
  let lineBuffer = "";
  let currentEventType = "";
  let currentData = "";
  let eventCount = 0;
  function processEvent(eventType, dataStr, controller) {
    eventCount++;
    let data;
    try {
      data = JSON.parse(dataStr);
    } catch {
      emitSseEvent(eventType, dataStr, controller);
      return;
    }
    if (eventType === "content_block_start") {
      const contentBlock = data.content_block;
      if (contentBlock?.type === "tool_use" && contentBlock.id && contentBlock.name != null) {
        const index = data.index;
        trackedBlocks.set(index, {
          id: contentBlock.id,
          name: contentBlock.name,
          index,
          bufferedJson: ""
        });
      }
      emitSseEvent(eventType, dataStr, controller);
      return;
    }
    if (eventType === "content_block_delta") {
      const index = data.index;
      const delta = data.delta;
      if (delta?.type === "input_json_delta" && trackedBlocks.has(index)) {
        const block = trackedBlocks.get(index);
        block.bufferedJson += delta.partial_json ?? "";
        return;
      }
      emitSseEvent(eventType, dataStr, controller);
      return;
    }
    if (eventType === "content_block_stop") {
      const index = data.index;
      const block = trackedBlocks.get(index);
      if (block) {
        trackedBlocks.delete(index);
        emitBufferedBlock(block, index, controller);
        emitSseEvent(eventType, dataStr, controller);
        return;
      }
      emitSseEvent(eventType, dataStr, controller);
      return;
    }
    emitSseEvent(eventType, dataStr, controller);
  }
  function emitBufferedBlock(block, index, controller) {
    if (!block.bufferedJson) {
      return;
    }
    try {
      const parsed = JSON.parse(block.bufferedJson);
      captureMetadataFromInput(block.id, block.name, parsed);
      delete parsed._intent;
      delete parsed._displayName;
      const cleanJson = JSON.stringify(parsed);
      const deltaEvent = {
        type: "content_block_delta",
        index,
        delta: {
          type: "input_json_delta",
          partial_json: cleanJson
        }
      };
      emitSseEvent("content_block_delta", JSON.stringify(deltaEvent), controller);
    } catch {
      debugLog(`[SSE Strip] Failed to parse buffered JSON for ${block.name} (${block.id}), stripping via regex`);
      const stripped = stripMetadataFieldsFromRawJson(block.bufferedJson);
      const deltaEvent = {
        type: "content_block_delta",
        index,
        delta: {
          type: "input_json_delta",
          partial_json: stripped
        }
      };
      emitSseEvent("content_block_delta", JSON.stringify(deltaEvent), controller);
    }
  }
  function emitSseEvent(eventType, dataStr, controller) {
    const sseText = `event: ${eventType}
data: ${dataStr}

`;
    controller.enqueue(encoder.encode(sseText));
  }
  return new TransformStream({
    transform(chunk, controller) {
      const text = lineBuffer + decoder.decode(chunk, { stream: true });
      const lines = text.split("\n");
      lineBuffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") {
          if (currentEventType && currentData) {
            processEvent(currentEventType, currentData, controller);
          }
          currentEventType = "";
          currentData = "";
          continue;
        }
        const eventMatch = trimmed.match(SSE_EVENT_RE);
        if (eventMatch) {
          currentEventType = eventMatch[1].trim();
          continue;
        }
        const dataMatch = trimmed.match(SSE_DATA_RE);
        if (dataMatch) {
          currentData = currentData ? `${currentData}
${dataMatch[1]}` : dataMatch[1];
          continue;
        }
      }
    },
    flush(controller) {
      if (lineBuffer.trim()) {
        const lines = lineBuffer.split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed === "") {
            if (currentEventType && currentData) {
              processEvent(currentEventType, currentData, controller);
            }
            currentEventType = "";
            currentData = "";
            continue;
          }
          const eventMatch = trimmed.match(SSE_EVENT_RE);
          if (eventMatch) {
            currentEventType = eventMatch[1].trim();
            continue;
          }
          const dataMatch = trimmed.match(SSE_DATA_RE);
          if (dataMatch) {
            currentData = currentData ? `${currentData}
${dataMatch[1]}` : dataMatch[1];
          }
        }
        if (currentEventType && currentData) {
          processEvent(currentEventType, currentData, controller);
        }
      }
      for (const [index, block] of trackedBlocks) {
        emitBufferedBlock(block, index, controller);
      }
      trackedBlocks.clear();
      lineBuffer = "";
      debugLog(`[SSE] Stream flush complete. Total events processed: ${eventCount}`);
    }
  });
}
var anthropicAdapter = {
  name: "anthropic",
  shouldIntercept(url) {
    const baseUrl = getConfiguredBaseUrl();
    return url.startsWith(baseUrl) && url.includes("/messages");
  },
  addMetadataToTools(body) {
    const tools = body.tools;
    if (!tools || !Array.isArray(tools)) {
      return body;
    }
    const richDescriptions = isRichToolDescriptionsEnabled();
    let modifiedCount = 0;
    for (const tool of tools) {
      const isMcpTool = tool.name?.startsWith("mcp__");
      if (!richDescriptions && !isMcpTool) {
        continue;
      }
      if (!tool.input_schema || typeof tool.input_schema !== "object") {
        continue;
      }
      const updatedSchema = injectMetadataIntoToolSchema(tool.input_schema);
      tool.input_schema.properties = updatedSchema.properties;
      tool.input_schema.required = updatedSchema.required;
      if (tool.input_schema.additionalProperties === false) {
        delete tool.input_schema.additionalProperties;
      }
      modifiedCount++;
    }
    if (modifiedCount > 0) {
      debugLog(`[Anthropic Schema] Added _intent and _displayName to ${modifiedCount} tools`);
    }
    return body;
  },
  injectMetadataIntoHistory(body) {
    const messages = body.messages;
    if (!messages) return body;
    let injectedCount = 0;
    for (const message of messages) {
      if (message.role !== "assistant" || !Array.isArray(message.content)) continue;
      for (const block of message.content) {
        if (block.type !== "tool_use" || !block.id || !block.input) continue;
        const hasIntent = "_intent" in block.input;
        const hasDisplayName = "_displayName" in block.input;
        if (hasIntent && hasDisplayName) continue;
        const stored = toolMetadataStore.get(block.id);
        if (stored) {
          const newInput = {};
          if (!hasDisplayName && stored.displayName) newInput._displayName = stored.displayName;
          if (!hasIntent && stored.intent) newInput._intent = stored.intent;
          if (Object.keys(newInput).length > 0) {
            Object.assign(newInput, block.input);
            block.input = newInput;
            injectedCount++;
          }
        }
      }
    }
    if (injectedCount > 0) {
      debugLog(`[Anthropic History] Re-injected metadata into ${injectedCount} tool_use blocks`);
    }
    return body;
  },
  createSseProcessor() {
    return createAnthropicSseStrippingStream();
  },
  stripsSseMetadata: true,
  modifyRequest(_url, init, body) {
    sanitizeEmptyTextCacheControl(body);
    upgradePromptCacheTtl(body);
    if (!is1MContextEnabled()) {
      debugLog("[Anthropic] Stripping context-1m beta header (enable1MContext=false)");
      init = {
        ...init,
        headers: stripBetaHeader(init?.headers, "context-1m-2025-08-07")
      };
    }
    const fastMode = shouldEnableFastMode(body.model);
    if (fastMode) {
      body.speed = "fast";
      debugLog(`[Fast Mode] Enabled for model=${body.model}`);
      return {
        init: {
          ...init,
          headers: appendBetaHeader(init?.headers, FAST_MODE_BETA)
        },
        body
      };
    }
    return { init, body };
  }
};
function createOpenAiSseStrippingStream() {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const trackedCalls = /* @__PURE__ */ new Map();
  const lastOpenedToolIndexByChoice = /* @__PURE__ */ new Map();
  let lineBuffer = "";
  let bufferingToolCalls = false;
  function emitSseLine(dataStr, controller) {
    if (DEBUG_SSE_RAW) debugLog(`[SSE RAW OUT openai] ${dataStr.slice(0, 4e3)}`);
    controller.enqueue(encoder.encode(`data: ${dataStr}

`));
  }
  function flushTrackedCalls(controller) {
    const sorted = Array.from(trackedCalls.values()).sort((a, b) => {
      if (a.choiceIndex !== b.choiceIndex) return a.choiceIndex - b.choiceIndex;
      return a.toolIndex - b.toolIndex;
    });
    for (const tc of sorted) {
      let merged = {};
      let parseFailed = false;
      if (tc.arguments) {
        try {
          const parsed = JSON.parse(tc.arguments);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            merged = { ...merged, ...parsed };
          }
        } catch {
          parseFailed = true;
          debugLog(`[OpenAI SSE] Failed to parse phase-1 arguments for ${tc.name} (${tc.id}), passing through raw`);
        }
      }
      for (const piece of tc.shiftedArgs) {
        try {
          const parsed = JSON.parse(piece);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
            merged = { ...merged, ...parsed };
          }
        } catch {
          parseFailed = true;
          debugLog(`[OpenAI SSE] Failed to parse phase-2 arguments for ${tc.name} (${tc.id}), passing through raw`);
        }
      }
      let outArgs;
      if (parseFailed && !tc.shiftedArgs.length) {
        outArgs = tc.arguments;
      } else {
        captureMetadataFromInput(tc.id, tc.name, merged);
        delete merged._intent;
        delete merged._displayName;
        outArgs = JSON.stringify(merged);
      }
      const consolidatedEvent = {
        choices: [{
          index: tc.choiceIndex,
          delta: {
            tool_calls: [{
              index: tc.toolIndex,
              id: tc.id,
              type: tc.type,
              function: { name: tc.name, arguments: outArgs }
            }]
          }
        }]
      };
      emitSseLine(JSON.stringify(consolidatedEvent), controller);
    }
    trackedCalls.clear();
    bufferingToolCalls = false;
  }
  function processDataLine(dataStr, controller) {
    if (DEBUG_SSE_RAW) debugLog(`[SSE RAW IN  openai] ${dataStr.slice(0, 4e3)}`);
    if (dataStr === "[DONE]") {
      flushTrackedCalls(controller);
      emitSseLine(dataStr, controller);
      return;
    }
    let data;
    try {
      data = JSON.parse(dataStr);
    } catch {
      emitSseLine(dataStr, controller);
      return;
    }
    const choices = data.choices;
    if (!choices || choices.length === 0) {
      emitSseLine(dataStr, controller);
      return;
    }
    let handledToolCalls = false;
    let strippedEmptyToolCalls = false;
    for (const choice of choices) {
      const toolCalls = choice?.delta?.tool_calls;
      if (!Array.isArray(toolCalls) || toolCalls.length === 0) {
        if (Array.isArray(toolCalls) && choice.delta) {
          delete choice.delta.tool_calls;
          strippedEmptyToolCalls = true;
        }
        continue;
      }
      handledToolCalls = true;
      const choiceIndex = choice.index ?? 0;
      for (const tc of toolCalls) {
        const fallbackIndex = lastOpenedToolIndexByChoice.get(choiceIndex);
        const toolIndex = tc.index ?? fallbackIndex ?? 0;
        const key = `${choiceIndex}:${toolIndex}`;
        if (tc.id) {
          const existing = trackedCalls.get(key);
          if (existing && existing.id === tc.id) {
            if (tc.function?.arguments) {
              existing.arguments += tc.function.arguments;
            }
            if (tc.function?.name && existing.name === "unknown") {
              existing.name = tc.function.name;
            }
            continue;
          }
          trackedCalls.set(key, {
            id: tc.id,
            name: tc.function?.name || "unknown",
            type: tc.type || "function",
            choiceIndex,
            toolIndex,
            arguments: tc.function?.arguments || "",
            shiftedArgs: []
          });
          lastOpenedToolIndexByChoice.set(choiceIndex, toolIndex);
          bufferingToolCalls = true;
        } else {
          const existingByKey = trackedCalls.get(key);
          if (existingByKey) {
            if (tc.function?.arguments) {
              existingByKey.arguments += tc.function.arguments;
            }
          } else {
            const phase1 = Array.from(trackedCalls.values()).filter((t) => t.choiceIndex === choiceIndex).sort((a, b) => a.toolIndex - b.toolIndex);
            const lastOpened = lastOpenedToolIndexByChoice.get(choiceIndex);
            if (typeof lastOpened === "number" && tc.index !== void 0 && tc.index > lastOpened && phase1.length > 0 && tc.function?.arguments) {
              const ord = tc.index - (lastOpened + 1);
              if (ord >= 0 && ord < phase1.length) {
                phase1[ord].shiftedArgs.push(tc.function.arguments);
              }
            }
          }
        }
      }
    }
    if (handledToolCalls) {
      return;
    }
    const forwardStr = strippedEmptyToolCalls ? JSON.stringify(data) : dataStr;
    const hasFinish = choices.some((choice) => choice?.finish_reason === "tool_calls" || choice?.finish_reason === "stop");
    if (hasFinish) {
      if (bufferingToolCalls) {
        flushTrackedCalls(controller);
      }
      emitSseLine(forwardStr, controller);
      return;
    }
    emitSseLine(forwardStr, controller);
  }
  return new TransformStream({
    transform(chunk, controller) {
      const text = lineBuffer + decoder.decode(chunk, { stream: true });
      const lines = text.split("\n");
      lineBuffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") continue;
        if (trimmed.startsWith("data: ")) {
          processDataLine(trimmed.slice(6), controller);
        } else {
          controller.enqueue(encoder.encode(trimmed + "\n"));
        }
      }
    },
    flush(controller) {
      if (lineBuffer.trim()) {
        const trimmed = lineBuffer.trim();
        if (trimmed.startsWith("data: ")) {
          processDataLine(trimmed.slice(6), controller);
        }
      }
      if (trackedCalls.size > 0) {
        flushTrackedCalls(controller);
      }
      lineBuffer = "";
    }
  });
}
var openAiAdapter = {
  name: "openai",
  shouldIntercept(url) {
    return url.includes("/chat/completions");
  },
  addMetadataToTools(body) {
    const tools = body.tools;
    if (!tools || !Array.isArray(tools)) {
      return body;
    }
    const richDescriptions = isRichToolDescriptionsEnabled();
    let modifiedCount = 0;
    for (const tool of tools) {
      if (tool.type !== "function" || !tool.function?.parameters) continue;
      const isMcpTool = tool.function.name?.startsWith("mcp__");
      if (!richDescriptions && !isMcpTool) {
        continue;
      }
      const params = tool.function.parameters;
      const updatedSchema = injectMetadataIntoToolSchema(params);
      params.properties = updatedSchema.properties;
      params.required = updatedSchema.required;
      if (params.additionalProperties === false) {
        delete params.additionalProperties;
      }
      modifiedCount++;
    }
    if (modifiedCount > 0) {
      debugLog(`[OpenAI Schema] Added _intent and _displayName to ${modifiedCount} tools`);
    }
    return body;
  },
  injectMetadataIntoHistory(body) {
    sanitizeOpenAiHistoryInPlace(body);
    const messages = body.messages;
    if (!messages) return body;
    let injectedCount = 0;
    for (const message of messages) {
      if (message.role !== "assistant" || !Array.isArray(message.tool_calls)) continue;
      for (const tc of message.tool_calls) {
        if (!tc.id || !tc.function?.arguments) continue;
        let args;
        try {
          args = JSON.parse(tc.function.arguments);
        } catch {
          continue;
        }
        const hasIntent = "_intent" in args;
        const hasDisplayName = "_displayName" in args;
        if (hasIntent && hasDisplayName) continue;
        const stored = toolMetadataStore.get(tc.id);
        if (stored) {
          const newArgs = {};
          if (!hasDisplayName && stored.displayName) newArgs._displayName = stored.displayName;
          if (!hasIntent && stored.intent) newArgs._intent = stored.intent;
          if (Object.keys(newArgs).length > 0) {
            Object.assign(newArgs, args);
            tc.function.arguments = JSON.stringify(newArgs);
            injectedCount++;
          }
        }
      }
    }
    if (injectedCount > 0) {
      debugLog(`[OpenAI History] Re-injected metadata into ${injectedCount} tool_calls`);
    }
    return body;
  },
  validateOutgoingBody(body) {
    validateOpenAiChatBody(body);
  },
  createSseProcessor() {
    return createOpenAiSseStrippingStream();
  },
  stripsSseMetadata: true
};
function createOpenAiResponsesSseStrippingStream() {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let lineBuffer = "";
  function emitSseLine(dataStr, controller) {
    if (DEBUG_SSE_RAW) debugLog(`[SSE RAW OUT openai-responses] ${dataStr.slice(0, 4e3)}`);
    controller.enqueue(encoder.encode(`data: ${dataStr}

`));
  }
  function processDataLine(dataStr, controller) {
    if (DEBUG_SSE_RAW) debugLog(`[SSE RAW IN  openai-responses] ${dataStr.slice(0, 4e3)}`);
    if (dataStr === "[DONE]") {
      emitSseLine(dataStr, controller);
      return;
    }
    let data;
    try {
      data = JSON.parse(dataStr);
    } catch {
      emitSseLine(dataStr, controller);
      return;
    }
    const eventType = data.type;
    if (eventType === "response.function_call_arguments.done") {
      const callId = typeof data.call_id === "string" ? data.call_id : void 0;
      const argsStr = typeof data.arguments === "string" ? data.arguments : void 0;
      if (callId && argsStr) {
        try {
          const parsed = JSON.parse(argsStr);
          captureMetadataFromInput(callId, "response:function_call", parsed);
          delete parsed._intent;
          delete parsed._displayName;
          data.arguments = JSON.stringify(parsed);
        } catch {
        }
      }
      emitSseLine(JSON.stringify(data), controller);
      return;
    }
    if (eventType === "response.output_item.done") {
      const item = data.item;
      if (item?.type === "function_call" && typeof item.arguments === "string") {
        const toolId = typeof item.call_id === "string" ? item.call_id : void 0;
        const toolName = typeof item.name === "string" ? item.name : "response:function_call";
        if (toolId) {
          try {
            const parsed = JSON.parse(item.arguments);
            captureMetadataFromInput(toolId, toolName, parsed);
            delete parsed._intent;
            delete parsed._displayName;
            item.arguments = JSON.stringify(parsed);
          } catch {
          }
        }
      }
      emitSseLine(JSON.stringify(data), controller);
      return;
    }
    emitSseLine(dataStr, controller);
  }
  return new TransformStream({
    transform(chunk, controller) {
      const text = lineBuffer + decoder.decode(chunk, { stream: true });
      const lines = text.split("\n");
      lineBuffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed === "") continue;
        if (trimmed.startsWith("data: ")) {
          processDataLine(trimmed.slice(6), controller);
        } else {
          controller.enqueue(encoder.encode(trimmed + "\n"));
        }
      }
    },
    flush(controller) {
      if (lineBuffer.trim()) {
        const trimmed = lineBuffer.trim();
        if (trimmed.startsWith("data: ")) {
          processDataLine(trimmed.slice(6), controller);
        }
      }
      lineBuffer = "";
    }
  });
}
var openAiResponsesAdapter = {
  name: "openai-responses",
  shouldIntercept(url) {
    return url.includes("/responses");
  },
  addMetadataToTools(body) {
    const tools = body.tools;
    if (!tools || !Array.isArray(tools)) return body;
    const richDescriptions = isRichToolDescriptionsEnabled();
    let modifiedCount = 0;
    for (const tool of tools) {
      if (tool.type !== "function" || !tool.parameters) continue;
      const isMcpTool = tool.name?.startsWith("mcp__");
      if (!richDescriptions && !isMcpTool) continue;
      const params = tool.parameters;
      const updatedSchema = injectMetadataIntoToolSchema(params);
      params.properties = updatedSchema.properties;
      params.required = updatedSchema.required;
      if (params.additionalProperties === false) {
        delete params.additionalProperties;
      }
      modifiedCount++;
    }
    if (modifiedCount > 0) {
      debugLog(`[OpenAI Responses Schema] Added _intent and _displayName to ${modifiedCount} tools`);
    }
    return body;
  },
  injectMetadataIntoHistory(body) {
    const input = body.input;
    if (!Array.isArray(input)) return body;
    repairResponsesHistoryInPlace(input);
    let injectedCount = 0;
    for (const entry of input) {
      if (entry.type !== "function_call" || typeof entry.call_id !== "string" || typeof entry.arguments !== "string") continue;
      let args;
      try {
        args = JSON.parse(entry.arguments);
      } catch {
        continue;
      }
      const hasIntent = "_intent" in args;
      const hasDisplayName = "_displayName" in args;
      if (hasIntent && hasDisplayName) continue;
      const stored = toolMetadataStore.get(entry.call_id);
      if (!stored) continue;
      const newArgs = {};
      if (!hasDisplayName && stored.displayName) newArgs._displayName = stored.displayName;
      if (!hasIntent && stored.intent) newArgs._intent = stored.intent;
      if (Object.keys(newArgs).length > 0) {
        Object.assign(newArgs, args);
        entry.arguments = JSON.stringify(newArgs);
        injectedCount++;
      }
    }
    if (injectedCount > 0) {
      debugLog(`[OpenAI Responses History] Re-injected metadata into ${injectedCount} function_call items`);
    }
    return body;
  },
  validateOutgoingBody(body) {
    validateOpenAiResponsesBody(body);
  },
  createSseProcessor() {
    return createOpenAiResponsesSseStrippingStream();
  },
  stripsSseMetadata: true
};
function sanitizeOpenAiHistoryInPlace(body) {
  const messages = body.messages;
  if (!Array.isArray(messages)) {
    return { droppedToolCalls: 0, droppedToolResults: 0 };
  }
  let droppedToolCalls = 0;
  const knownIds = /* @__PURE__ */ new Set();
  for (const message of messages) {
    if (message.role === "assistant" && Array.isArray(message.tool_calls)) {
      const cleaned = message.tool_calls.filter((tc) => {
        if (typeof tc.id !== "string" || tc.id === "") {
          droppedToolCalls++;
          return false;
        }
        knownIds.add(tc.id);
        return true;
      });
      if (cleaned.length !== message.tool_calls.length) {
        if (cleaned.length === 0) {
          delete message.tool_calls;
        } else {
          message.tool_calls = cleaned;
        }
      }
    }
  }
  let droppedToolResults = 0;
  if (droppedToolCalls > 0) {
    const filtered = messages.filter((message) => {
      if (message.role !== "tool") return true;
      const tcid = typeof message.tool_call_id === "string" ? message.tool_call_id : "";
      if (!tcid || !knownIds.has(tcid)) {
        droppedToolResults++;
        return false;
      }
      return true;
    });
    if (filtered.length !== messages.length) {
      body.messages = filtered;
    }
    debugLog(`[OpenAI History] Sanitized poisoned history: dropped ${droppedToolCalls} empty-id tool_call(s) and ${droppedToolResults} orphan tool result(s)`);
  }
  return { droppedToolCalls, droppedToolResults };
}
function validateOpenAiChatBody(body) {
  const messages = body.messages;
  if (!Array.isArray(messages)) return;
  const seenIds = /* @__PURE__ */ new Set();
  const knownIds = /* @__PURE__ */ new Set();
  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (!msg) continue;
    if (msg.role === "assistant" && Array.isArray(msg.tool_calls)) {
      for (const tc of msg.tool_calls) {
        const id = typeof tc.id === "string" ? tc.id : "";
        if (!id) {
          throw new MalformedBodyError({
            code: "missing_tool_call_id",
            detail: `messages[${i}].tool_calls[*] missing id`,
            adapter: "openai"
          });
        }
        if (seenIds.has(id)) {
          throw new MalformedBodyError({
            code: "duplicate_tool_call_id",
            detail: `messages[${i}].tool_calls[*] reuses id "${id}" already seen earlier`,
            adapter: "openai"
          });
        }
        seenIds.add(id);
        knownIds.add(id);
        const fnName = typeof tc.function?.name === "string" ? tc.function.name.trim() : "";
        if (!fnName) {
          throw new MalformedBodyError({
            code: "empty_tool_name",
            detail: `messages[${i}].tool_calls[*] (id="${id}") has empty function.name`,
            adapter: "openai"
          });
        }
      }
    }
    if (msg.role === "tool") {
      const tcid = typeof msg.tool_call_id === "string" ? msg.tool_call_id : "";
      if (!tcid) {
        throw new MalformedBodyError({
          code: "missing_tool_call_id",
          detail: `messages[${i}] (role=tool) missing tool_call_id`,
          adapter: "openai"
        });
      }
      if (!knownIds.has(tcid)) {
        throw new MalformedBodyError({
          code: "orphaned_function_call_output",
          detail: `messages[${i}] (role=tool) references unknown tool_call_id "${tcid}"`,
          adapter: "openai"
        });
      }
    }
  }
}
function validateOpenAiResponsesBody(body) {
  const input = body.input;
  if (!Array.isArray(input)) return;
  const seenCallIds = /* @__PURE__ */ new Set();
  const knownCallIds = /* @__PURE__ */ new Set();
  for (let i = 0; i < input.length; i++) {
    const entry = input[i];
    if (!entry) continue;
    if (entry.type === "function_call") {
      const callId = typeof entry.call_id === "string" ? entry.call_id : "";
      if (!callId) {
        throw new MalformedBodyError({
          code: "missing_call_id",
          detail: `input[${i}] (type=function_call) missing call_id`,
          adapter: "openai-responses"
        });
      }
      if (seenCallIds.has(callId)) {
        throw new MalformedBodyError({
          code: "duplicate_tool_call_id",
          detail: `input[${i}] (type=function_call) reuses call_id "${callId}"`,
          adapter: "openai-responses"
        });
      }
      seenCallIds.add(callId);
      knownCallIds.add(callId);
      const name = typeof entry.name === "string" ? entry.name.trim() : "";
      if (!name) {
        throw new MalformedBodyError({
          code: "empty_tool_name",
          detail: `input[${i}] (type=function_call, call_id="${callId}") has empty name`,
          adapter: "openai-responses"
        });
      }
    } else if (entry.type === "function_call_output") {
      const callId = typeof entry.call_id === "string" ? entry.call_id : "";
      if (!callId) {
        throw new MalformedBodyError({
          code: "missing_call_id",
          detail: `input[${i}] (type=function_call_output) missing call_id`,
          adapter: "openai-responses"
        });
      }
      if (!knownCallIds.has(callId)) {
        throw new MalformedBodyError({
          code: "orphaned_function_call_output",
          detail: `input[${i}] (type=function_call_output) references unknown call_id "${callId}"`,
          adapter: "openai-responses"
        });
      }
    }
  }
}
function repairResponsesHistoryInPlace(input) {
  let synthesizedCallIds = 0;
  let droppedOrphans = 0;
  const knownCallIds = /* @__PURE__ */ new Set();
  for (let i = 0; i < input.length; i++) {
    const entry = input[i];
    if (!entry) continue;
    if (entry.type !== "function_call") continue;
    if (typeof entry.call_id === "string" && entry.call_id.length > 0) {
      knownCallIds.add(entry.call_id);
      continue;
    }
    const name = typeof entry.name === "string" ? entry.name : "unknown";
    const argsHash = typeof entry.arguments === "string" ? hashShortString(entry.arguments) : "0";
    const synthetic = `repaired_${i}_${name}_${argsHash}`;
    entry.call_id = synthetic;
    knownCallIds.add(synthetic);
    synthesizedCallIds++;
    debugLog(`[OpenAI Responses Repair] Synthesized call_id "${synthetic}" for input[${i}] (name=${name})`);
  }
  if (synthesizedCallIds === 0 && input.every((e) => e.type !== "function_call_output")) {
    return { synthesizedCallIds, droppedOrphans };
  }
  for (let i = input.length - 1; i >= 0; i--) {
    const entry = input[i];
    if (!entry) continue;
    if (entry.type !== "function_call_output") continue;
    const callId = typeof entry.call_id === "string" ? entry.call_id : "";
    if (!callId || !knownCallIds.has(callId)) {
      input.splice(i, 1);
      droppedOrphans++;
      debugLog(`[OpenAI Responses Repair] Dropped orphan function_call_output at input[${i}] (call_id="${callId}")`);
    }
  }
  return { synthesizedCallIds, droppedOrphans };
}
function hashShortString(input) {
  let h = 5381;
  for (let i = 0; i < input.length; i++) {
    h = (h << 5) + h + input.charCodeAt(i) | 0;
  }
  return Math.abs(h).toString(36);
}
var adapters = [anthropicAdapter, openAiResponsesAdapter, openAiAdapter];
function getPiApiHint() {
  const hint = process.env.CRAFT_PI_MODEL_API?.trim();
  return hint || void 0;
}
function resolveAdapterNameFromPiApiHint(piApiHint) {
  if (!piApiHint) return void 0;
  if (piApiHint === "anthropic-messages") return "anthropic";
  if (piApiHint === "openai-completions") return "openai";
  if (piApiHint === "openai-responses" || piApiHint === "azure-openai-responses" || piApiHint === "openai-codex-responses") {
    return "openai-responses";
  }
  return void 0;
}
function findAdapter(url) {
  const piApiHint = getPiApiHint();
  const hintedAdapter = resolveAdapterNameFromPiApiHint(piApiHint);
  if (hintedAdapter === "anthropic") return anthropicAdapter;
  if (hintedAdapter === "openai") return openAiAdapter;
  if (hintedAdapter === "openai-responses") return openAiResponsesAdapter;
  return adapters.find((a) => a.shouldIntercept(url));
}
async function captureApiError(response, url) {
  if (response.status < 400) return;
  debugLog(`[Attempting to capture error for ${response.status} response]`);
  const errorClone = response.clone();
  try {
    const errorText = await errorClone.text();
    let errorMessage = response.statusText;
    let isHtmlResponse = false;
    try {
      const errorJson = JSON.parse(errorText);
      if (errorJson.error?.message) {
        errorMessage = errorJson.error.message;
      } else if (errorJson.message) {
        errorMessage = errorJson.message;
      }
    } catch {
      if (errorText) {
        isHtmlResponse = errorText.trimStart().startsWith("<");
        errorMessage = errorText;
      }
    }
    if (isHtmlResponse) {
      if (PROXY_URL) {
        errorMessage = `Received an unexpected HTML error page (HTTP ${response.status}) instead of a JSON API response. This may be caused by your network proxy (${redactProxyUrl(PROXY_URL)}). Check your proxy settings in Settings > Network.`;
      } else {
        errorMessage = `Received an unexpected HTML error page (HTTP ${response.status}) instead of a JSON API response. This could be caused by a firewall, captive portal, or network issue.`;
      }
      debugLog(`[Detected HTML error response \u2014 replaced raw HTML with clean message]`);
    }
    if (response.status === 400 && !errorText.trim()) {
      const summary = getLastOutgoingRequest(url);
      if (summary) {
        const emptyNames = summary.toolNames.filter((n) => n === "<empty>").length;
        const dupIds = summary.toolCallIds.length - new Set(summary.toolCallIds).size;
        const hints = [];
        if (emptyNames > 0) hints.push(`${emptyNames} tool call(s) with empty name`);
        if (dupIds > 0) hints.push(`${dupIds} duplicate tool_call_id(s)`);
        if (hints.length > 0) {
          errorMessage = `Endpoint rejected the request with no body. Likely cause: ${hints.join(", ")}. This usually means the upstream relay's tool-call streaming is broken \u2014 try a different model or endpoint. Last request had ${summary.toolCallIds.length} tool call(s) and ${summary.toolResults} tool result(s) over ${summary.historyLength} history entries.`;
        } else {
          errorMessage = `Endpoint rejected the request with no body (no obvious shape problem). Last request: ${summary.toolCallIds.length} tool call(s), ${summary.toolResults} tool result(s), ${summary.historyLength} history entries. Try a different endpoint.`;
        }
        debugLog(`[Empty-body 400 enriched: ${errorMessage}]`);
      }
    }
    setStoredError({
      status: response.status,
      statusText: response.statusText,
      message: errorMessage,
      timestamp: Date.now()
    });
    debugLog(`[Captured API error: ${response.status} ${errorMessage}]`);
  } catch (e) {
    setStoredError({
      status: response.status,
      statusText: response.statusText,
      message: response.statusText,
      timestamp: Date.now()
    });
    debugLog(`[Error reading body, capturing basic info: ${e}]`);
  }
}
function headersToCurl(headers) {
  if (!headers) return "";
  const headerObj = headers instanceof Headers ? Object.fromEntries(Array.from(headers)) : Array.isArray(headers) ? Object.fromEntries(headers) : headers;
  const sensitiveKeys = ["x-api-key", "authorization", "cookie"];
  return Object.entries(headerObj).map(([key, value]) => {
    const redacted = sensitiveKeys.includes(key.toLowerCase()) ? "[REDACTED]" : value;
    return `-H '${key}: ${redacted}'`;
  }).join(" \\\n  ");
}
function toCurl(url, init) {
  const method = init?.method?.toUpperCase() ?? "GET";
  const headers = headersToCurl(init?.headers);
  let curl = `curl -X ${method}`;
  if (headers) {
    curl += ` \\
  ${headers}`;
  }
  if (init?.body && typeof init.body === "string") {
    const escapedBody = init.body.replace(/'/g, "'\\''");
    curl += ` \\
  -d '${escapedBody}'`;
  }
  curl += ` \\
  '${url}'`;
  return curl;
}
async function logResponse(response, url, startTime, adapter) {
  const duration = Date.now() - startTime;
  if (adapter) {
    await captureApiError(response, url);
  }
  if (!DEBUG) return response;
  debugLog(`
\u2190 RESPONSE ${response.status} ${response.statusText} (${duration}ms)`);
  debugLog(`  URL: ${url}`);
  const respHeaders = {};
  response.headers.forEach((value, key) => {
    respHeaders[key] = value;
  });
  debugLog("  Headers:", respHeaders);
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("text/event-stream")) {
    debugLog("  Body: [SSE stream - not logged]");
    return response;
  }
  const clone = response.clone();
  try {
    const text = await clone.text();
    const maxLogSize = 5e3;
    if (text.length > maxLogSize) {
      debugLog(`  Body (truncated to ${maxLogSize} chars):
${text.substring(0, maxLogSize)}...`);
    } else {
      debugLog(`  Body:
${text}`);
    }
  } catch (e) {
    debugLog("  Body: [failed to read]", e);
  }
  return response;
}
var lastOutgoingRequest;
function rememberLastOutgoingRequest(url, body, adapter) {
  const summary = {
    url,
    adapter: adapter.name,
    preparedAt: Date.now(),
    toolCallIds: [],
    toolNames: [],
    toolResults: 0,
    historyLength: 0
  };
  if (adapter.name === "openai") {
    const messages = body.messages;
    if (Array.isArray(messages)) {
      summary.historyLength = messages.length;
      for (const msg of messages) {
        if (msg.role === "assistant" && Array.isArray(msg.tool_calls)) {
          for (const tc of msg.tool_calls) {
            if (typeof tc.id === "string") summary.toolCallIds.push(tc.id);
            const name = typeof tc.function?.name === "string" ? tc.function.name : "";
            summary.toolNames.push(name || "<empty>");
          }
        }
        if (msg.role === "tool") summary.toolResults++;
      }
    }
  } else if (adapter.name === "openai-responses") {
    const input = body.input;
    if (Array.isArray(input)) {
      summary.historyLength = input.length;
      for (const entry of input) {
        if (entry.type === "function_call") {
          if (typeof entry.call_id === "string") summary.toolCallIds.push(entry.call_id);
          const name = typeof entry.name === "string" ? entry.name : "";
          summary.toolNames.push(name || "<empty>");
        } else if (entry.type === "function_call_output") {
          summary.toolResults++;
        }
      }
    }
  }
  lastOutgoingRequest = summary;
}
function getLastOutgoingRequest(forUrl) {
  if (!lastOutgoingRequest) return void 0;
  if (Date.now() - lastOutgoingRequest.preparedAt > 3e4) return void 0;
  if (lastOutgoingRequest.url !== forUrl) return void 0;
  return lastOutgoingRequest;
}
function synthesizeMalformedBodyResponse(err, url, startTime, adapter) {
  const body = JSON.stringify({
    error: {
      type: "invalid_request_error",
      code: err.code,
      message: `ZenSkill blocked an outgoing request that the API would reject: ${err.detail}. This typically indicates a streaming-reassembly bug in the upstream endpoint or a stale tool history. Try starting a new session or switching to a different model/endpoint.`,
      param: "tool_calls"
    }
  });
  debugLog(`[${adapter.name}] Outgoing body validation failed (${err.code}); synthesizing 400 response`);
  setStoredError({
    status: 400,
    statusText: "Bad Request (blocked by ZenSkill)",
    message: err.detail,
    timestamp: Date.now()
  });
  return logResponse(
    new Response(body, {
      status: 400,
      statusText: "Bad Request",
      headers: { "content-type": "application/json" }
    }),
    url,
    startTime,
    adapter
  );
}
var originalFetch = globalThis.fetch.bind(globalThis);
async function interceptedFetch(input, init) {
  const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
  const startTime = Date.now();
  if (DEBUG) {
    debugLog("\n" + "=".repeat(80));
    debugLog("\u2192 REQUEST");
    debugLog(toCurl(url, init));
  }
  const adapter = findAdapter(url);
  if (adapter && (init?.method ?? (input instanceof Request ? input.method : void 0))?.toUpperCase() === "POST") {
    try {
      const { bodyStr, normalizedInit } = await resolveRequestContext(input, init);
      if (bodyStr) {
        let parsed = JSON.parse(bodyStr);
        parsed = adapter.addMetadataToTools(parsed);
        parsed = adapter.injectMetadataIntoHistory(parsed);
        if (adapter.validateOutgoingBody) {
          try {
            adapter.validateOutgoingBody(parsed);
          } catch (err) {
            if (err instanceof MalformedBodyError) {
              return synthesizeMalformedBodyResponse(err, url, startTime, adapter);
            }
            throw err;
          }
        }
        let modifiedInit = normalizedInit;
        if (adapter.modifyRequest) {
          const result = adapter.modifyRequest(url, normalizedInit, parsed);
          modifiedInit = result.init;
          parsed = result.body;
        }
        const proxy2 = getProxyForUrl(url);
        const finalBody = JSON.stringify(parsed);
        const finalInit = {
          ...modifiedInit,
          body: finalBody,
          ...proxy2 ? { proxy: proxy2 } : {}
        };
        rememberLastOutgoingRequest(url, parsed, adapter);
        debugLog(`[${adapter.name}] Intercepted request to ${url}`);
        const response2 = await originalFetch(url, finalInit);
        const contentType = response2.headers.get("content-type") ?? "";
        if (contentType.includes("text/event-stream") && response2.body) {
          debugLog(`[${adapter.name}] Creating SSE processor (${adapter.stripsSseMetadata ? "strip" : "capture"})`);
          const processor = adapter.createSseProcessor();
          const processedBody = response2.body.pipeThrough(processor);
          const processedResponse = new Response(processedBody, {
            status: response2.status,
            statusText: response2.statusText,
            headers: response2.headers
          });
          return logResponse(processedResponse, url, startTime, adapter);
        }
        if (contentType.includes("application/json") && response2.body) {
          const text = await response2.text();
          const stripped = stripMetadataFieldsFromRawJson(text);
          return logResponse(new Response(stripped, {
            status: response2.status,
            statusText: response2.statusText,
            headers: response2.headers
          }), url, startTime, adapter);
        }
        return logResponse(response2, url, startTime, adapter);
      }
    } catch (e) {
      debugLog(`[${adapter?.name}] FETCH modification failed:`, e);
    }
  }
  const proxy = getProxyForUrl(url);
  const proxyInit = proxy ? { ...init, proxy } : init;
  const response = await originalFetch(input, proxyInit);
  return logResponse(response, url, startTime);
}
var fetchProxy = new Proxy(interceptedFetch, {
  apply(target, thisArg, args) {
    return Reflect.apply(target, thisArg, args);
  },
  get(target, prop, receiver) {
    if (prop in originalFetch) {
      return originalFetch[prop];
    }
    return Reflect.get(target, prop, receiver);
  }
});
if (process.env.CRAFT_INTERCEPTOR_DISABLE_AUTO_INSTALL !== "1") {
  globalThis.fetch = fetchProxy;
  debugLog("Unified fetch interceptor installed");
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  MalformedBodyError,
  createAnthropicSseStrippingStream,
  createOpenAiResponsesSseStrippingStream,
  createOpenAiSseStrippingStream,
  injectMetadataIntoToolSchema,
  repairResponsesHistoryInPlace,
  resolveAdapterNameFromPiApiHint,
  sanitizeEmptyTextCacheControl,
  sanitizeOpenAiHistoryInPlace,
  stripMetadataFieldsFromRawJson,
  upgradePromptCacheTtl,
  validateOpenAiChatBody,
  validateOpenAiResponsesBody
});
