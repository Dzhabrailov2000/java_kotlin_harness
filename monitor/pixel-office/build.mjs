/**
 * Reproducible build of the original Pixel Agents office the monitor serves.
 *
 * 1. verify every vendored original against vendor-manifest.json, byte for byte
 * 2. copy that tree into build/ and apply the reviewable patches of patches/ there
 * 3. decode the original PNG and manifest assets into dist/assets.json
 * 4. build the original React frontend from the patched tree into dist/office/
 * 5. check the real module graph: the original engine and UI are in it, the upstream
 *    server, its Claude provider and the dev mock are not
 * 6. record inputs, patches and outputs in dist/build-manifest.json
 *
 * The vendor tree is never edited; the patches carry every local change and are listed
 * with the hash of the file they apply to and of the file they produce. A clean rerun
 * produces identical dist bytes. The resulting JavaScript is built from the patched
 * originals with a local toolchain: it is not, and is never claimed to be, byte
 * identical to the published npm bundle.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import * as esbuild from 'esbuild';
import { build as viteBuild } from 'vite';

const root = dirname(fileURLToPath(import.meta.url));
const vendor = join(root, 'vendor');
const patches = join(root, 'patches');
const dist = join(root, 'dist');
const work = join(root, 'build');
const office = join(dist, 'office');
const assetsDir = join(vendor, 'webview-ui/public/assets');

const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const digestOf = (path) => sha256(readFileSync(path));

function fail(message) {
  process.stderr.write(message + '\n');
  process.exit(1);
}

function walk(directory, base = directory, into = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, base, into);
    else into.push(relative(base, path).split('\\').join('/'));
  }
  return into;
}

// ── 1. vendored originals ────────────────────────────────────────────────────
const manifest = JSON.parse(readFileSync(join(root, 'vendor-manifest.json'), 'utf8'));
const present = walk(vendor).sort();
const expected = Object.keys(manifest.files).sort();
if (present.join('\n') !== expected.join('\n')) {
  fail('vendor tree does not match vendor-manifest.json file list');
}
for (const [name, entry] of Object.entries(manifest.files)) {
  const path = join(vendor, name);
  if (digestOf(path) !== entry.sha256 || statSync(path).size !== entry.bytes) {
    fail('vendored file changed against the pinned upstream copy: ' + name);
  }
}

// ── 2. patched build tree ────────────────────────────────────────────────────
rmSync(work, { recursive: true, force: true });
mkdirSync(work, { recursive: true });
cpSync(vendor, work, { recursive: true });
const applied = [];
for (const name of readdirSync(patches).sort()) {
  if (!name.endsWith('.patch')) continue;
  const path = join(patches, name);
  const target = name.slice(0, -'.patch'.length).split('__').join('/');
  const before = digestOf(join(work, target));
  // GIT_CEILING_DIRECTORIES stops repository discovery at this package. Inside a
  // repository `git apply` resolves patch paths against the repository root and then
  // silently SKIPS everything outside the current subdirectory: it exits 0 and patches
  // nothing. Stopping the search makes it treat the build tree as the root, which is
  // what the patch paths mean. The digest comparison below is the second lock: a patch
  // that changed no byte fails this build instead of shipping an unpatched original.
  const result = spawnSync('git', ['apply', '--whitespace=nowarn', '-p1', path], {
    cwd: work,
    encoding: 'utf8',
    env: { ...process.env, GIT_CEILING_DIRECTORIES: root },
  });
  if (result.status !== 0) fail('patch does not apply to the pinned original: ' + name + '\n' + (result.stderr || ''));
  const after = digestOf(join(work, target));
  if (after === before) fail('patch applied without changing its target, so nothing was patched: ' + name);
  applied.push({
    patch: name,
    sha256: digestOf(path),
    target,
    original_sha256: before,
    patched_sha256: after,
  });
}
const patchedFiles = new Set(applied.map((entry) => entry.target));
for (const name of walk(work)) {
  if (patchedFiles.has(name)) continue;
  if (digestOf(join(work, name)) !== manifest.files[name].sha256) {
    fail('the build tree differs from the original outside the declared patches: ' + name);
  }
}

// ── 3. predecoded assets ─────────────────────────────────────────────────────
mkdirSync(dist, { recursive: true });
await esbuild.build({
  entryPoints: [join(root, 'src/assets-build.ts')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  external: ['pngjs'],
  outfile: join(work, 'assets-build.cjs'),
  logLevel: 'warning',
});
const assetsPath = join(dist, 'assets.json');
const decoded = spawnSync(process.execPath, [join(work, 'assets-build.cjs'), assetsDir, assetsPath], {
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'inherit'],
});
if (decoded.status !== 0) fail('asset decoding failed');
const counts = JSON.parse(decoded.stdout);

// ── 4. original frontend ─────────────────────────────────────────────────────
rmSync(office, { recursive: true, force: true });
const bundles = await viteBuild({ configFile: join(root, 'vite.config.mjs') });
const output = (Array.isArray(bundles) ? bundles[0] : bundles).output;

// ── 5. real module graph ─────────────────────────────────────────────────────
const chunks = output.filter((item) => item.type === 'chunk');
if (chunks.length !== 1) fail('expected exactly one JavaScript chunk, got ' + chunks.length);
const modules = Object.keys(chunks[0].modules).map((id) => relative(work, id).split('\\').join('/'));
const required = [
  'webview-ui/src/main.tsx',
  'webview-ui/src/App.tsx',
  'webview-ui/src/office/components/OfficeCanvas.tsx',
  'webview-ui/src/office/components/ToolOverlay.tsx',
  'webview-ui/src/office/editor/EditorToolbar.tsx',
  'webview-ui/src/office/engine/officeState.ts',
  'webview-ui/src/office/engine/renderer.ts',
  'webview-ui/src/office/engine/characters.ts',
  'webview-ui/src/office/layout/layoutSerializer.ts',
  'webview-ui/src/components/SettingsModal.tsx',
  'webview-ui/src/transport/webSocketTransport.ts',
];
for (const name of required) {
  if (!modules.includes(name)) fail('the office bundle misses an original module: ' + name);
}
const forbidden = modules.filter((name) => /browserMock|server\/src|fastify|\/hooks\/claude/i.test(name));
if (forbidden.length) fail('unexpected modules in the office bundle: ' + forbidden.join(', '));

// ── 6. provenance of this build ──────────────────────────────────────────────
const outputs = {};
for (const name of walk(office)) {
  outputs[name] = { sha256: digestOf(join(office, name)), bytes: statSync(join(office, name)).size };
}
outputs['../assets.json'] = { sha256: digestOf(assetsPath), bytes: statSync(assetsPath).size };
const version = (name) => JSON.parse(readFileSync(join(root, 'node_modules', name, 'package.json'), 'utf8')).version;
const sources = ['src/assets-build.ts', 'src/projection.mjs', 'src/office-server.mjs', 'src/office-state.mjs',
                 'build.mjs', 'vite.config.mjs', 'package.json', 'package-lock.json'];
const buildManifest = {
  upstream: { repository: manifest.repository, commit: manifest.commit, version: manifest.version },
  note: 'Built from the pinned originals with the patches below and a local toolchain. The output is not '
    + 'byte identical to the published npm bundle and is not presented as such.',
  vendorManifestSha256: digestOf(join(root, 'vendor-manifest.json')),
  vendorFiles: expected.length,
  patches: applied,
  tools: {
    node: process.version,
    vite: version('vite'),
    tailwindcss: version('tailwindcss'),
    react: version('react'),
    esbuild: version('esbuild'),
    pngjs: version('pngjs'),
  },
  adapterSources: Object.fromEntries(sources.map((name) => [name, digestOf(join(root, name))])),
  assets: counts,
  moduleGraph: { modules: modules.length },
  outputs,
};
writeFileSync(join(dist, 'build-manifest.json'), JSON.stringify(buildManifest, null, 2) + '\n', 'utf8');
rmSync(work, { recursive: true, force: true });

process.stdout.write(
  'upstream    ' + manifest.commit + ' (' + manifest.version + ')\n' +
  'patches     ' + applied.length + ' applied to ' + expected.length + ' vendored originals\n' +
  'modules     ' + modules.length + ' in the office bundle\n' +
  Object.entries(outputs)
    .map(([name, entry]) => 'output      ' + name + '  sha256 ' + entry.sha256 + '  ' + entry.bytes + ' bytes\n')
    .join(''),
);
