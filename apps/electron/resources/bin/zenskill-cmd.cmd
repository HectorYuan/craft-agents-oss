@echo off
rem ZenSkill CLI wrapper for Craft Agents Electron app
rem CRAFT_UV and CRAFT_ZENSKILL are set by the Electron main process.
rem --project is required: __main__.py uses package-relative imports and cannot
rem be executed as a bare script path.
"%CRAFT_UV%" run --project "%CRAFT_ZENSKILL%" --python 3.12 zenskill %*
