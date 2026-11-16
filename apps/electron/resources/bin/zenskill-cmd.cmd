@echo off
rem ZenSkill CLI wrapper for Craft Agents Electron app
rem CRAFT_UV and CRAFT_ZENSKILL are set by the Electron main process
if "%UV_PROJECT_ENVIRONMENT%"=="" set "UV_PROJECT_ENVIRONMENT=%USERPROFILE%\.zenskill\electron-venv"
set "UV_PYTHON_INSTALL_DIR=%CRAFT_ZENSKILL%\python"
cd /d "%CRAFT_ZENSKILL%" || exit /b 1
rem 打包后 zenskill/ 目录只读，`uv run` 写不了 .tmp 临时文件就直接退出，
rem 桌面端表现为 `MCP error -32000: Connection closed`。venv 已建好时直连解释器。
if exist "%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" (
  "%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" -m zenskill %*
) else (
  "%CRAFT_UV%" run --python 3.12 --project "%CRAFT_ZENSKILL%" python -m zenskill %*
)
