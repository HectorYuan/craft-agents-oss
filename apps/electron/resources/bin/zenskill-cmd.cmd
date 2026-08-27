@echo off
rem ZenSkill CLI wrapper for Craft Agents Electron app
rem CRAFT_UV and CRAFT_ZENSKILL are set by the Electron main process
"%CRAFT_UV%" run --python 3.12 "%CRAFT_ZENSKILL%\zenskill\__main__.py" %*
