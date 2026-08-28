/**
 * Cross-platform asset copy script.
 *
 * Copies the resources/ directory to dist/resources/.
 * All bundled assets (docs, themes, permissions, tool-icons) now live in resources/
 * which electron-builder handles natively via directories.buildResources.
 *
 * At Electron startup, setBundledAssetsRoot(__dirname) is called, and then
 * getBundledAssetsDir('docs') resolves to <__dirname>/resources/docs/, etc.
 *
 * Run: bun scripts/copy-assets.ts
 */

import { cpSync, copyFileSync, readdirSync } from 'fs';
import { join } from 'path';

// Copy resources/ → dist/resources/, skipping subdirectories that are dead
// weight in every packaged layout: the ZenSkill engine pack (CRAFT_ZENSKILL /
// zenskill-seed) and bundled uv are resolved via <resourcesPath>/app/resources,
// never via the dist copy. docs/themes/permissions/tool-icons MUST keep being
// copied — packaged getBundledAssetsDir resolves them from <__dirname>/resources/.
const SKIP_COPY = new Set(['zenskill', 'bin']);

for (const entry of readdirSync('resources')) {
  if (SKIP_COPY.has(entry)) continue;
  cpSync(join('resources', entry), join('dist', 'resources', entry), { recursive: true });
}

console.log('✓ Copied resources/ → dist/resources/ (skipped: ' + [...SKIP_COPY].join(', ') + ')');

// Copy PowerShell parser script (for Windows command validation in Explore mode)
// Source: packages/shared/src/agent/powershell-parser.ps1
// Destination: dist/resources/powershell-parser.ps1
const psParserSrc = join('..', '..', 'packages', 'shared', 'src', 'agent', 'powershell-parser.ps1');
const psParserDest = join('dist', 'resources', 'powershell-parser.ps1');
try {
  copyFileSync(psParserSrc, psParserDest);
  console.log('✓ Copied powershell-parser.ps1 → dist/resources/');
} catch (err) {
  // Only warn - PowerShell validation is optional on non-Windows platforms
  console.log('⚠ powershell-parser.ps1 copy skipped (not critical on non-Windows)');
}
