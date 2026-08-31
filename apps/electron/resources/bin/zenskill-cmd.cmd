@echo off
rem ZenSkill CLI wrapper for Craft Agents Electron app
rem CRAFT_UV and CRAFT_ZENSKILL are set by the Electron main process
if "%UV_PROJECT_ENVIRONMENT%"=="" set "UV_PROJECT_ENVIRONMENT=%USERPROFILE%\.zenskill\electron-venv"
cd /d "%CRAFT_ZENSKILL%" || exit /b 1
"%CRAFT_UV%" run --python 3.12 --project "%CRAFT_ZENSKILL%" python -m zenskill %*
