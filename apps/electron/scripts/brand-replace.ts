/**
 * Brand replacement for built renderer bundles (ZenSkill rebrand).
 *
 * The renderer ships upstream Craft Agents JS bundles; per the fork trademark
 * terms the "Craft" branding must not ship. Rather than chasing strings
 * through app source, we rewrite them post-build — same approach as
 * scripts/build_webui.py (browser WebUI), applied to the Electron renderer.
 *
 * Keep this list explicit and minimal: blanket "Craft" replacement would
 * corrupt identifiers (e.g. craft-logos paths, CSS class fragments).
 */

import { existsSync, readdirSync, readFileSync, writeFileSync, statSync } from 'fs';
import { join } from 'path';

const RENDERER_DIR = join(__dirname, '..', 'dist', 'renderer');
const MAIN_CJS = join(__dirname, '..', 'dist', 'main.cjs');

const REPLACEMENTS: Array<[string, string]> = [
  ['Craft Agents', 'ZenSkill'],
  ['Craft Agent', 'ZenSkill'],
];

// dist/main.cjs carries embedded i18n strings and the deeplink scheme; the
// same human-readable rules apply there. Bare "craft-agent" (import
// specifiers) and thecraftagents.com (upstream auth URLs, functional until a
// ZenSkill account service exists) are intentionally left alone.
const MAIN_REPLACEMENTS: Array<[string, string]> = [
  ...REPLACEMENTS,
  ['craftagents://', 'zenskill://'],
];

const TEXT_EXTS = new Set(['.js', '.html', '.css', '.svg', '.txt']);

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (TEXT_EXTS.has(name.slice(name.lastIndexOf('.')))) out.push(p);
  }
  return out;
}

function applyReplacements(
  file: string,
  pairs: Array<[string, string]>,
  counts: Map<string, number>
): boolean {
  let content = readFileSync(file, 'utf-8');
  let touched = false;
  for (const [from, to] of pairs) {
    const parts = content.split(from);
    if (parts.length > 1) {
      counts.set(from, (counts.get(from) ?? 0) + parts.length - 1);
      content = parts.join(to);
      touched = true;
    }
  }
  if (touched) writeFileSync(file, content);
  return touched;
}

function main(): void {
  let filesChanged = 0;
  const counts = new Map<string, number>();

  for (const file of walk(RENDERER_DIR)) {
    if (applyReplacements(file, REPLACEMENTS, counts)) filesChanged++;
  }
  if (existsSync(MAIN_CJS)) {
    if (applyReplacements(MAIN_CJS, MAIN_REPLACEMENTS, counts)) filesChanged++;
  }

  for (const [from, n] of counts) console.log(`  "${from}" -> replaced ${n} occurrence(s)`);
  console.log(`brand-replace: ${filesChanged} file(s) updated`);
}

main();
