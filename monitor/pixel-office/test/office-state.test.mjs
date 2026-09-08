/**
 * What the office is allowed to store, and where.
 *
 * Every payload here is a FIXTURE of this test file. The storage is the monitor's own directory: no
 * Claude or Codex profile is read or written, and nothing the browser sends reaches a file before it
 * has been checked and bounded.
 */

import assert from 'node:assert/strict';
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { DEFAULT_SETTINGS, MAX_STATE_BYTES, OfficeStateStore } from '../src/office-state.mjs';

async function store() {
  return new OfficeStateStore(await mkdtemp(join(tmpdir(), 'pixel-office-state-')));
}

const LAYOUT = { version: 1, cols: 21, rows: 22, tiles: [[0]], furniture: [] };

test('an empty directory reads as the documented defaults', async () => {
  const state = await store();
  assert.deepEqual(state.read('settings'), DEFAULT_SETTINGS);
  assert.equal(state.read('layout'), null);
  assert.deepEqual(state.read('seats'), {});
  assert.deepEqual(state.read('areas'), {});
  assert.deepEqual(state.problems, []);
  assert.equal(DEFAULT_SETTINGS.alwaysShowLabels, true, 'the three role names are on screen by default');
});

test('a valid layout, seats and areas round-trip', async () => {
  const state = await store();
  assert.equal(state.write('layout', LAYOUT), null);
  assert.deepEqual(state.read('layout'), LAYOUT);
  assert.equal(state.write('seats', { 3: { palette: 2, hueShift: 0.5, seatId: 'seat-a' } }), null);
  assert.deepEqual(state.read('seats'), { 3: { palette: 2, hueShift: 0.5, seatId: 'seat-a' } });
  assert.equal(state.write('areas', { 'my-repo': ['Backend'] }), null);
  assert.deepEqual(state.read('areas'), { 'my-repo': ['Backend'] });
  assert.deepEqual(readdirSync(state.directory).sort(), ['areas.json', 'layout.json', 'seats.json']);
});

test('a payload of the wrong shape is refused and never written', async () => {
  const state = await store();
  for (const [kind, payload] of [
    ['layout', { version: 2, cols: 1, rows: 1, tiles: [], furniture: [] }],
    ['layout', { version: 1, cols: 100000, rows: 1, tiles: [], furniture: [] }],
    ['layout', { version: 1, cols: 1, rows: 1, tiles: 'not-a-grid', furniture: [] }],
    ['seats', { 3: { palette: 'red', hueShift: 0, seatId: null } }],
    ['seats', { '../escape': { palette: 1, hueShift: 0, seatId: null } }],
    ['areas', { repo: ['ok', 42] }],
    ['settings', { soundEnabled: 'yes' }],
    ['settings', { lastSeenVersion: 'x'.repeat(64) }],
  ]) {
    const problem = state.write(kind, payload);
    assert.match(String(problem), /^refused: /, kind + ' ' + JSON.stringify(payload));
  }
  assert.deepEqual(readdirSync(state.directory), []);
});

test('an oversized payload is refused', async () => {
  const state = await store();
  const huge = { version: 1, cols: 21, rows: 22, tiles: [], furniture: [{ uid: 'x'.repeat(MAX_STATE_BYTES) }] };
  assert.match(String(state.write('layout', huge)), /too large/);
  assert.equal(existsSync(join(state.directory, 'layout.json')), false);
});

test('a corrupt or oversized stored file is reported and ignored, not obeyed', async () => {
  const state = await store();
  writeFileSync(join(state.directory, 'settings.json'), '{ not json');
  assert.deepEqual(state.read('settings'), DEFAULT_SETTINGS);
  writeFileSync(join(state.directory, 'seats.json'), JSON.stringify({ 3: { palette: -1, hueShift: 0, seatId: null } }));
  assert.deepEqual(state.read('seats'), {});
  writeFileSync(join(state.directory, 'areas.json'), 'x'.repeat(MAX_STATE_BYTES + 1));
  assert.deepEqual(state.read('areas'), {});
  assert.equal(state.problems.length, 3, state.problems.join('; '));
});

test('a stored document is written whole, never as a half file', async () => {
  const state = await store();
  state.write('layout', LAYOUT);
  const path = join(state.directory, 'layout.json');
  const first = readFileSync(path, 'utf8');
  state.write('layout', { ...LAYOUT, cols: 30 });
  assert.notEqual(readFileSync(path, 'utf8'), first);
  assert.equal(JSON.parse(readFileSync(path, 'utf8')).cols, 30);
  assert.equal(existsSync(path + '.tmp'), false);
});
