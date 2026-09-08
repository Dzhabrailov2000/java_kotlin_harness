/**
 * What the original engine really does with a neutral actor, over minutes of its own time.
 *
 * This is not a fixture of the projection: it builds the actual patched engine the office
 * ships (the pinned originals plus the patches of patches/, applied here exactly as
 * build.mjs applies them), drives the actual OfficeState through the shipped default room,
 * and reads the state, the frame and the sprite of the characters it holds. No browser and
 * no model take part; time is simulated in fixed steps and Math.random is seeded, so the
 * run is the same on every machine.
 *
 * The defect it exists for: setAgentActive(id, false) only skips the rest of the transition
 * that follows it. The original engine seats an inactive character again at the end of
 * every wander and rests it there for two to four minutes, and while it rests the TYPE
 * branch keeps cycling the typing frames. A human, an idle, a failed, a stale or a
 * disconnected actor was therefore typing for minutes, a hundred seconds after the last
 * observation. The check below reaches that transition and looks at what the actor renders.
 */

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

import * as esbuild from 'esbuild';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const work = mkdtempSync(join(tmpdir(), 'office-engine-'));
after(() => rmSync(work, { recursive: true, force: true }));

/** The engine of the shipped office: pinned originals plus the declared patches, nothing else. */
async function patchedEngine() {
  const tree = join(work, 'tree');
  cpSync(join(root, 'vendor'), tree, { recursive: true });
  for (const name of readdirSync(join(root, 'patches')).sort()) {
    if (!name.endsWith('.patch')) continue;
    execFileSync('git', ['apply', '--whitespace=nowarn', '-p1', join(root, 'patches', name)],
      { cwd: tree, env: { ...process.env, GIT_CEILING_DIRECTORIES: work } });
  }
  const entry = join(tree, 'engine-entry.ts');
  await esbuild.build({
    stdin: {
      contents: [
        "export { OfficeState } from './webview-ui/src/office/engine/officeState.js';",
        "export { getCharacterSprite } from './webview-ui/src/office/engine/characters.js';",
        "export { buildDynamicCatalog } from './webview-ui/src/office/layout/furnitureCatalog.js';",
        "export { CharacterState } from './webview-ui/src/office/types.js';",
      ].join('\n'),
      resolveDir: tree,
      sourcefile: entry,
      loader: 'ts',
    },
    bundle: true,
    format: 'esm',
    platform: 'neutral',
    outfile: join(work, 'engine.mjs'),
    logLevel: 'silent',
  });
  return import(pathToFileURL(join(work, 'engine.mjs')).href);
}

/** Distinguishable sprites: what the renderer would draw is compared, not only a counter. */
const SPRITES = {
  typing: [0, 1, 2, 3].map((dir) => ['typing-' + dir + '-0', 'typing-' + dir + '-1']),
  reading: [0, 1, 2, 3].map((dir) => ['reading-' + dir + '-0', 'reading-' + dir + '-1']),
  walk: [0, 1, 2, 3].map((dir) => [0, 1, 2, 3].map((frame) => 'walk-' + dir + '-' + frame)),
};

/** A seeded generator in place of Math.random, so every run takes the same decisions. */
function seeded(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

const engine = await patchedEngine();
const { OfficeState, getCharacterSprite, buildDynamicCatalog, CharacterState } = engine;

const STEP = 1 / 30;
const MINUTES = 20;
// The room and the furniture the office actually serves. The engine reads its seats through
// the catalog the server sends, so both arrive here the same way: an empty default grid has
// no seat to be rested at, and that rest is where the defect lived.
const ASSETS = JSON.parse(readFileSync(join(root, 'dist', 'assets.json'), 'utf8'));
const ROOM = ASSETS.layout;
assert.equal(buildDynamicCatalog({ catalog: ASSETS.furniture.catalog, sprites: ASSETS.furniture.sprites }), true);

test('a neutral actor never plays the typing animation, however long it sits', () => {
  const random = Math.random;
  Math.random = seeded(20260908);
  try {
    const office = new OfficeState(ROOM);
    // Two actors of the shipped room: one the adapter took out of its working state, one
    // left active. The neutral one is what this check is about; the active one is the
    // control that the animation itself still works.
    office.addAgent(2, 0, 0, undefined, true);
    office.addAgent(3, 1, 0, undefined, true);
    office.setAgentTool(2, null);
    office.setAgentActive(2, false);
    office.setAgentTool(3, 'Edit');
    office.setAgentActive(3, true);

    const neutral = office.characters.get(2);
    const working = office.characters.get(3);
    assert.ok(neutral && working, 'the default room seats both actors');

    const seen = { typeVisits: 0, seatedAfterWander: 0, wandered: false, typingFrames: 0, sprites: new Set() };
    let previous = neutral.state;
    let workingAnimated = false;
    for (let tick = 0; tick * STEP < MINUTES * 60; tick += 1) {
      office.update(STEP);
      if (neutral.state !== previous) {
        if (neutral.state === CharacterState.TYPE) {
          seen.typeVisits += 1;
          if (seen.wandered) seen.seatedAfterWander += 1;
        }
        if (neutral.state === CharacterState.WALK) seen.wandered = true;
        previous = neutral.state;
      }
      if (neutral.state === CharacterState.TYPE) {
        seen.sprites.add(getCharacterSprite(neutral, SPRITES));
        if (neutral.frame !== 0) seen.typingFrames += 1;
      }
      if (working.state === CharacterState.TYPE && working.frame !== 0) workingAnimated = true;
    }

    // The scenario really reached the transition the defect lived in: the neutral actor
    // stood up, wandered and was seated again by the original engine.
    assert.ok(seen.wandered, 'the neutral actor never left its seat, so the case was not reached');
    assert.ok(seen.seatedAfterWander > 0,
      'the neutral actor was never seated again after wandering, so the case was not reached');
    assert.equal(neutral.isActive, false, 'nothing in the simulation may make a neutral actor active');
    assert.equal(seen.typingFrames, 0,
      'a neutral actor advanced the typing frames ' + seen.typingFrames + ' times');
    assert.deepEqual([...seen.sprites].sort(), ['typing-' + neutral.dir + '-0'],
      'a neutral actor rendered more than the still seated pose: ' + [...seen.sprites].join(', '));
    assert.ok(workingAnimated, 'the observed working actor stopped animating, which is not the fix asked for');
  } finally {
    Math.random = random;
  }
});

test('an actor that becomes observed work again types, and stops when it stops being observed', () => {
  const random = Math.random;
  Math.random = seeded(4242);
  try {
    const office = new OfficeState(ROOM);
    office.addAgent(3, 0, 0, undefined, true);
    const actor = office.characters.get(3);

    // Working: the character returns to its seat and plays the typing frames.
    office.setAgentTool(3, 'Edit');
    office.setAgentActive(3, true);
    let animated = 0;
    for (let tick = 0; tick * STEP < 120; tick += 1) {
      office.update(STEP);
      if (actor.state === CharacterState.TYPE && actor.frame !== 0) animated += 1;
    }
    assert.ok(animated > 0, 'an observed working actor must animate');

    // The observation ends: the frames stop, in the same seat, at once.
    office.setAgentTool(3, null);
    office.setAgentActive(3, false);
    let frames = 0;
    for (let tick = 0; tick * STEP < 10 * 60; tick += 1) {
      office.update(STEP);
      if (actor.state === CharacterState.TYPE && actor.frame !== 0) frames += 1;
    }
    assert.equal(frames, 0, 'the actor kept typing ' + frames + ' frames after its observation ended');
  } finally {
    Math.random = random;
  }
});
