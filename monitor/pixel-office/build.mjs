/**
 * Reproducible build of the office bundle the monitor serves.
 *
 * 1. verify every vendored original file against vendor-manifest.json
 * 2. bundle and run the build-time asset decoder over the original PNG/JSON assets
 * 3. bundle the browser adapter together with the original engine modules
 * 4. check the real module graph (no React, server, transport or network module)
 * 5. record input and output digests in dist/build-manifest.json
 *
 * A clean rerun must produce identical dist bytes. The Python monitor never runs
 * this file: it serves the checked-in dist/ as it is.
 */

import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import * as esbuild from 'esbuild';

const root = dirname(fileURLToPath(import.meta.url));
const vendor = join(root, 'vendor');
const dist = join(root, 'dist');
const work = join(root, 'build');
const assetsDir = join(vendor, 'webview-ui/public/assets');

const sha256 = (data) => createHash('sha256').update(data).digest('hex');
const digestOf = (path) => sha256(readFileSync(path));

function fail(message) {
  process.stderr.write(message + '\n');
  process.exit(1);
}

// ── 1. vendored originals ────────────────────────────────────────────────────
const manifest = JSON.parse(readFileSync(join(root, 'vendor-manifest.json'), 'utf8'));
const present = [];
(function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path);
    else present.push(relative(vendor, path).split('\\').join('/'));
  }
})(vendor);
const expected = Object.keys(manifest.files).sort();
if (present.sort().join('\n') !== expected.join('\n')) {
  fail('vendor tree does not match vendor-manifest.json file list');
}
for (const [name, entry] of Object.entries(manifest.files)) {
  const path = join(vendor, name);
  if (digestOf(path) !== entry.sha256 || statSync(path).size !== entry.bytes) {
    fail('vendored file changed against the pinned upstream copy: ' + name);
  }
}

// ── 2. predecoded assets ─────────────────────────────────────────────────────
rmSync(work, { recursive: true, force: true });
mkdirSync(work, { recursive: true });
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

// ── 3. browser adapter ───────────────────────────────────────────────────────
const bundle = await esbuild.build({
  entryPoints: [join(root, 'src/office.ts')],
  bundle: true,
  platform: 'browser',
  format: 'iife',
  globalName: 'PixelOffice',
  target: ['chrome120', 'firefox120', 'safari17'],
  footer: { js: 'window.mountPixelOffice = PixelOffice.mountPixelOffice;' },
  banner: {
    js:
      '/* Pixel Agents office engine, MIT, Copyright (c) 2026 Pablo De Lucca.\n' +
      '   Original sources vendored from ' + manifest.repository + ' at ' + manifest.commit + '.\n' +
      '   Bundled with a local monitor adapter; see monitor/pixel-office/vendor/LICENSE. */',
  },
  legalComments: 'inline',
  metafile: true,
  outfile: join(dist, 'office.js'),
  logLevel: 'warning',
});

// ── 4. real module graph ─────────────────────────────────────────────────────
const built = Object.values(bundle.metafile.outputs).filter((output) => output.entryPoint);
if (built.length !== 1) fail('expected exactly one bundled output, got ' + built.length);
const inputs = Object.keys(built[0].inputs).sort();
const forbidden = inputs.filter((name) => /node_modules|react|fastify|\/transport\/|\/ws\/|OfficeCanvas|browserMock|main\.tsx|App\.tsx/i.test(name));
if (forbidden.length) fail('unexpected modules in the browser bundle: ' + forbidden.join(', '));
const required = [
  'vendor/webview-ui/src/office/engine/officeState.ts',
  'vendor/webview-ui/src/office/engine/renderer.ts',
  'vendor/webview-ui/src/office/engine/gameLoop.ts',
  'vendor/webview-ui/src/office/engine/characters.ts',
  'vendor/webview-ui/src/office/layout/furnitureCatalog.ts',
  'vendor/webview-ui/src/office/projection.ts',
];
for (const name of required) {
  if (!inputs.some((input) => input.endsWith(name))) fail('the bundle misses an original engine module: ' + name);
}

// ── 5. provenance of this build ──────────────────────────────────────────────
const officeDigest = digestOf(join(dist, 'office.js'));
const assetsDigest = digestOf(assetsPath);
const sources = ['src/office.ts', 'src/assets-build.ts', 'build.mjs', 'package.json', 'package-lock.json'];
const buildManifest = {
  upstream: { repository: manifest.repository, commit: manifest.commit, version: manifest.version },
  vendorManifestSha256: digestOf(join(root, 'vendor-manifest.json')),
  vendorFiles: expected.length,
  tools: {
    esbuild: JSON.parse(readFileSync(join(root, 'node_modules/esbuild/package.json'), 'utf8')).version,
    pngjs: JSON.parse(readFileSync(join(root, 'node_modules/pngjs/package.json'), 'utf8')).version,
  },
  adapterSources: Object.fromEntries(sources.map((name) => [name, digestOf(join(root, name))])),
  assets: counts,
  outputs: {
    'office.js': { sha256: officeDigest, bytes: statSync(join(dist, 'office.js')).size },
    'assets.json': { sha256: assetsDigest, bytes: statSync(assetsPath).size },
  },
  moduleGraph: { inputs: inputs.length },
};
writeFileSync(join(dist, 'build-manifest.json'), JSON.stringify(buildManifest, null, 2) + '\n', 'utf8');
rmSync(work, { recursive: true, force: true });

process.stdout.write(
  'office.js  sha256 ' + officeDigest + '  ' + buildManifest.outputs['office.js'].bytes + ' bytes\n' +
  'assets.json sha256 ' + assetsDigest + '  ' + buildManifest.outputs['assets.json'].bytes + ' bytes\n' +
  'integrity   sha256-' + Buffer.from(officeDigest, 'hex').toString('base64') + '\n' +
  'modules     ' + inputs.length + '\n',
);
