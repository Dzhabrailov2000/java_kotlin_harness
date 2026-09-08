/**
 * Build-time decoder for the vendored Pixel Agents assets.
 *
 * Runs under node during the build only. It calls the original upstream
 * decoders (core/src/assets) over the original PNG/JSON inputs and writes one
 * predecoded JSON payload, so the browser adapter needs no PNG decoder, no
 * image source and no network beyond the two local routes.
 *
 * The upstream furniture decoder catches per-asset failures and warns instead
 * of throwing, so a partially decoded set would otherwise look like a success:
 * every console warning during decoding fails this build.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import { buildAssetIndex, buildFurnitureCatalog } from '../vendor/core/src/assets/build.js';
import {
  decodeAllCarpets,
  decodeAllCharacters,
  decodeAllFloors,
  decodeAllFurniture,
  decodeAllWalls,
} from '../vendor/core/src/assets/loader.js';
import type { CatalogEntry } from '../vendor/core/src/assets/types.js';

type SpriteData = string[][];

const [assetsDir, outputPath] = process.argv.slice(2);
if (!assetsDir || !outputPath) {
  throw new Error('usage: assets-build <assetsDir> <outputPath>');
}

const warnings: string[] = [];
const originalWarn = console.warn;
const originalError = console.error;
console.warn = (...args: unknown[]) => {
  warnings.push(args.map(String).join(' '));
};
console.error = (...args: unknown[]) => {
  warnings.push(args.map(String).join(' '));
};

function spriteFilled(sprite: SpriteData | undefined): boolean {
  return (
    Array.isArray(sprite) &&
    sprite.length > 0 &&
    sprite.some((row) => Array.isArray(row) && row.some((pixel) => pixel !== ''))
  );
}

const catalog: CatalogEntry[] = buildFurnitureCatalog(assetsDir);
const index = buildAssetIndex(assetsDir);
const characters = decodeAllCharacters(assetsDir);
const floors = decodeAllFloors(assetsDir);
const walls = decodeAllWalls(assetsDir);
const carpets = decodeAllCarpets(assetsDir);
const sprites = decodeAllFurniture(assetsDir, catalog);

console.warn = originalWarn;
console.error = originalError;

if (!index.defaultLayout) {
  throw new Error('no default layout in ' + assetsDir);
}
const layout = JSON.parse(readFileSync(join(assetsDir, index.defaultLayout), 'utf8')) as {
  cols: number;
  rows: number;
  furniture: Array<{ type: string }>;
};

const problems: string[] = warnings.map((line) => 'decoder warning: ' + line);
if (characters.length === 0) problems.push('no character sprites decoded');
if (floors.length === 0) problems.push('no floor sprites decoded');
if (walls.length === 0) problems.push('no wall sprite sets decoded');
if (carpets.length === 0) problems.push('no carpet sprite sets decoded');
if (catalog.length === 0) problems.push('empty furniture catalog');
for (const entry of catalog) {
  if (!spriteFilled(sprites[entry.id])) problems.push('furniture sprite missing or blank: ' + entry.id);
}
for (const [position, character] of characters.entries()) {
  for (const direction of ['down', 'up', 'right'] as const) {
    const frames = character[direction];
    if (!Array.isArray(frames) || frames.length === 0 || !frames.every(spriteFilled)) {
      problems.push('character ' + position + ' has no usable ' + direction + ' frames');
    }
  }
}
if (!floors.every(spriteFilled)) problems.push('a floor sprite is blank');
// Every furniture type the shipped room places must resolve, including the mirrored ":left"
// variants that buildDynamicCatalog synthesises from mirrorSide members.
const known = new Set(catalog.map((entry) => entry.id));
for (const item of layout.furniture) {
  const base = item.type.endsWith(':left') ? item.type.slice(0, -':left'.length) : item.type;
  if (!known.has(base)) problems.push('layout places unknown furniture type: ' + item.type);
}
if (problems.length > 0) {
  throw new Error('asset build is incomplete:\n  ' + problems.join('\n  '));
}

const payload = {
  characters,
  floors,
  walls,
  carpets,
  furniture: { catalog, sprites },
  layout,
};
mkdirSync(dirname(outputPath), { recursive: true });
writeFileSync(outputPath, JSON.stringify(payload), 'utf8');
process.stdout.write(
  JSON.stringify({
    characters: characters.length,
    floors: floors.length,
    walls: walls.length,
    carpets: carpets.length,
    catalog: catalog.length,
    sprites: Object.keys(sprites).length,
    layout: { cols: layout.cols, rows: layout.rows, furniture: layout.furniture.length },
  }) + '\n',
);
