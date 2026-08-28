/**
 * electron-builder afterPack hook
 *
 * Windows: prunes dead weight that the files-glob exclusions cannot reliably
 * remove (electron-builder negation ordering is unreliable) — the dist copy of
 * the ZenSkill engine pack / bundled bin (runtime reads
 * <resourcesPath>/app/resources via CRAFT_ZENSKILL), macOS-only assets copied
 * in by copy-assets, and the engine pack's browser-webui static files.
 *
 * macOS: nothing to do — icons come from resources/icon.icns, which is
 * generated from the Z-core master (see ../../.. Temp note in repo history;
 * compose via `python -m icnsutil compose` over icon_NxN.png set).
 */

const path = require('path');
const fs = require('fs');

/** Remove a path inside the packed app if present; returns true when removed. */
function pruneIfExists(appPath, relPath) {
  const target = path.join(appPath, relPath);
  if (!fs.existsSync(target)) return false;
  fs.rmSync(target, { recursive: true, force: true });
  console.log(`afterPack: pruned ${relPath}`);
  return true;
}

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== 'win32') {
    console.log('afterPack: no prune rules for this platform');
    return;
  }

  const appPath = path.join(context.appOutDir, 'resources', 'app');
  const pruned =
    pruneIfExists(appPath, path.join('dist', 'resources', 'zenskill')) |
    pruneIfExists(appPath, path.join('dist', 'resources', 'bin'));
  const deadAssets = [
    'dmg-background.png',
    'dmg-background.tiff',
    'dmg-background@2x.png',
    'source.png',
  ];
  for (const name of deadAssets) {
    pruneIfExists(appPath, path.join('dist', 'resources', name));
  }
  // Browser WebUI (Path B) static assets under the canonical engine pack copy:
  // need an undeclared aiohttp extra and are never served by Electron (~27MB).
  pruneIfExists(appPath, path.join('resources', 'zenskill', 'zenskill', 'webui'));
  if (!pruned) console.log('afterPack: win32 prune — nothing to remove');
};
