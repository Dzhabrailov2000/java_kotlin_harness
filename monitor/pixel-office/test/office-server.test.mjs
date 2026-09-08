/**
 * The routes the office exposes and the state it publishes over its socket.
 *
 * The journal behind the adapter is a FIXTURE HTTP server written by this test file: it answers the
 * two paging routes of run_progress.py with records this file made up. No CLI, no model and no real
 * pipeline run takes part, and nothing here may be presented as one.
 */

import assert from 'node:assert/strict';
import { createServer, request as httpRequest } from 'node:http';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, test } from 'node:test';

import { WebSocket } from 'ws';

import { createOfficeServer, parseArguments } from '../src/office-server.mjs';
import { IMPLEMENTER, MANAGER, USER } from '../src/projection.mjs';

/** A fixture journal API: the same page shape run_progress.py serves, over made-up records. */
function fixtureApi() {
  const feeds = { '/api/events': [], '/api/trace': [] };
  let fail = null;
  let hold = null;
  const server = createServer((incoming, response) => {
    const [path, query] = incoming.url.split('?');
    if (hold) {
      // Headers sent, body never finished: the adapter's own deadline has to end this.
      response.writeHead(200, { 'Content-Type': 'application/json' });
      response.write('{"journal": true, "events": [');
      return;
    }
    if (fail) {
      response.writeHead(fail, { 'Content-Type': 'text/plain' });
      response.end('fixture failure\n');
      return;
    }
    if (path === '/') {
      // run_progress.py serves the readable journal at its own root; /details is the office's
      // name for it, and the adapter rewrites the one into the other.
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end('<!doctype html><title>fixture journal</title>');
      return;
    }
    const records = feeds[path];
    if (!records) {
      response.writeHead(404);
      response.end();
      return;
    }
    const cursor = Number(new URLSearchParams(query).get('cursor') ?? 0);
    const page = { cursor: records.length, discard: false, events: records.slice(cursor),
                   invalid_lines: 0, more: false, journal: true, reset: false };
    response.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    response.end(JSON.stringify(page));
  });
  return {
    server,
    feeds,
    setFailure(status) { fail = status; },
    setHold(value) { hold = value; },
    async listen() {
      await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
      return 'http://127.0.0.1:' + server.address().port;
    },
    close() { return new Promise((resolve) => server.close(resolve)); },
  };
}

let sequence = 0;
function record(fields) {
  sequence += 1;
  return {
    schema: 1, event_id: 'fixture' + sequence, time: new Date().toISOString().slice(0, 23) + 'Z',
    run_id: 'fixture-run', attempt: 1, step_id: 'build-1', source: 'launcher', phase: 'build',
    event: 'run', status: 'started', ...fields,
  };
}

/** Collect messages from one socket until a predicate is satisfied, with a bounded wait. */
function collect(url, { send = [{ type: 'webviewReady' }], until, timeoutMs = 15000 }) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    const messages = [];
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error('timed out after ' + messages.map((item) => item.type).join(', ')));
    }, timeoutMs);
    socket.on('error', reject);
    socket.on('open', () => {
      for (const message of send) socket.send(JSON.stringify(message));
    });
    socket.on('message', (data) => {
      messages.push(JSON.parse(data.toString('utf8')));
      if (until(messages)) {
        clearTimeout(timer);
        socket.close();
        resolve(messages);
      }
    });
  });
}

/** One request with headers fetch is not allowed to set; returns the status code only. */
function rawStatus(origin, path, headers) {
  const url = new URL(path, origin);
  return new Promise((resolve, reject) => {
    const call = httpRequest({ hostname: url.hostname, port: url.port, path, method: 'GET', headers },
                             (response) => {
                               response.resume();
                               response.on('end', () => resolve(response.statusCode));
                             });
    call.on('error', reject);
    call.end();
  });
}

const snapshotDone = (messages) => messages.some((item) => item.type === 'pipelineSourceState');

async function startOffice(api, extra = {}) {
  const monitor = createOfficeServer({
    port: 0,
    apiOrigin: await api.listen(),
    stateDir: await mkdtemp(join(tmpdir(), 'pixel-office-server-')),
    pollIntervalMs: 100,
    ...extra,
  });
  await monitor.listen();
  return monitor;
}

test('the command line refuses an incomplete or unknown option', () => {
  assert.throws(() => parseArguments(['--state-dir', '/tmp/x']), /--api-origin is required/);
  assert.throws(() => parseArguments(['--api-origin', 'http://127.0.0.1:1']), /--state-dir is required/);
  assert.throws(() => parseArguments(['--api-origin', 'http://127.0.0.1:1', '--state-dir', '/tmp/x', '--exec', 'rm']), /unknown option/);
  const options = parseArguments(['--api-origin=http://127.0.0.1:1', '--state-dir=/tmp/x', '--port=0']);
  assert.equal(options.apiOrigin, 'http://127.0.0.1:1');
});

test('only the intended routes exist, and no request path becomes a file path', async () => {
  const api = fixtureApi();
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const get = async (path, headers = {}) => {
    const response = await fetch(new URL(path, monitor.url), { headers });
    return { status: response.status, type: response.headers.get('content-type'), body: await response.text() };
  };
  const index = await get('/');
  assert.equal(index.status, 200);
  assert.match(index.body, /<div id="root">/);
  assert.equal((await get('/fonts/FSPixelSansUnicode-Regular.ttf')).status, 200);
  assert.equal((await get('/assets/characters/char_0.png')).status, 200);
  const details = await get('/details');
  assert.equal(details.status, 200);
  assert.match(details.body, /fixture journal/);
  const events = await get('/api/events?cursor=0&limit=10');
  assert.equal(events.status, 200);
  assert.equal(JSON.parse(events.body).journal, true);
  for (const path of ['/nope', '/index.html/', '/vendor/LICENSE', '/src/office-server.mjs', '/dist/assets.json',
                      '/package.json', '/assets/index.html', '/api/', '/api/events/extra']) {
    assert.equal((await get(path)).status, 404, path);
  }
  // fetch refuses to set Host, so the foreign-origin probe goes through a raw request.
  assert.equal(await rawStatus(monitor.url, '/', { Host: 'example.com' }), 403);
  const post = await fetch(new URL('/', monitor.url), { method: 'POST' });
  assert.equal(post.status, 405);
  // A path that cannot be decoded is answered, not thrown: a throw here would end the office.
  assert.equal(await rawStatus(monitor.url, '/%zz', {}), 400);
  assert.equal((await get('/')).status, 200, 'the office is still serving after the malformed path');
  // The route table is the whole surface, built once; it holds no source or dependency file.
  for (const path of monitor.routes.keys()) {
    assert.doesNotMatch(path, /node_modules|\.mjs$|package|vendor-manifest/, path);
  }
});

test('a socket receives a complete snapshot in the order the original client needs', async () => {
  const api = fixtureApi();
  api.feeds['/api/events'].push(record({ event: 'run', status: 'started', model: 'claude-opus-5' }));
  api.feeds['/api/events'].push(record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' }));
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const messages = await collect(monitor.url.replace('http', 'ws') + 'ws', { until: snapshotDone });
  const order = messages.map((item) => item.type);
  assert.equal(order[0], 'providerCapabilities');
  assert.ok(order.indexOf('existingAgents') < order.indexOf('layoutLoaded'), 'agents are buffered until the layout arrives');
  assert.ok(order.indexOf('layoutLoaded') < order.indexOf('agentTeamInfo'), 'names address characters that exist');
  assert.ok(order.indexOf('agentTeamInfo') < order.indexOf('pipelineActorState'));
  for (const type of ['characterSpritesLoaded', 'petSpritesLoaded', 'floorTilesLoaded', 'wallTilesLoaded',
                      'carpetTilesLoaded', 'furnitureAssetsLoaded', 'settingsLoaded', 'areaMappingsLoaded']) {
    assert.ok(order.includes(type), type);
  }
  // Context occupancy is never observed here, so the gauge message is never sent.
  assert.ok(!order.includes('agentContextUsage'));
  assert.ok(!order.includes('agentStatus'), 'no neutral state is dressed up as a finished turn');
  const names = messages.filter((item) => item.type === 'agentTeamInfo');
  assert.deepEqual(names.map((item) => item.agentName), ['Пользователь', 'Codex', 'Claude']);
  assert.ok(names.every((item) => item.teamName === undefined && item.isTeamLead === undefined),
            'role representatives are not a native agent team');
  const actors = Object.fromEntries(messages.filter((item) => item.type === 'pipelineActorState').map((item) => [item.id, item]));
  assert.equal(actors[USER].state, 'human');
  assert.equal(actors[MANAGER].state, 'unknown');
  assert.equal(actors[IMPLEMENTER].state, 'working');
  assert.equal(actors[IMPLEMENTER].toolName, 'Bash');
  const layout = messages.find((item) => item.type === 'layoutLoaded');
  assert.equal(layout.layout.version, 1);
  assert.ok(layout.layout.furniture.length > 0, 'the shipped room is the default layout');
});

test('a later connection gets the current state, not the state of the first one', async () => {
  const api = fixtureApi();
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const ws = monitor.url.replace('http', 'ws') + 'ws';
  const first = await collect(ws, { until: snapshotDone });
  assert.equal(first.filter((item) => item.type === 'pipelineActorState').find((item) => item.id === IMPLEMENTER).state, 'unknown');

  api.feeds['/api/events'].push(record({ event: 'run', status: 'started' }));
  api.feeds['/api/events'].push(record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Edit', call_id: 'c2' }));
  // Wait for the adapter's own poll rather than assuming how fast it got there.
  const deadline = Date.now() + 15000;
  while (monitor.state.actors[IMPLEMENTER].state !== 'working') {
    if (Date.now() > deadline) throw new Error('the adapter never observed the appended records');
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  const second = await collect(ws, { until: snapshotDone });
  const actor = second.filter((item) => item.type === 'pipelineActorState').find((item) => item.id === IMPLEMENTER);
  assert.equal(actor.state, 'working');
  assert.equal(actor.caption, 'Edit');
  // The snapshot arrives once per connection: no actor is created twice.
  assert.equal(second.filter((item) => item.type === 'existingAgents').length, 1);
  assert.equal(second.filter((item) => item.type === 'pipelineActorState' && item.id === IMPLEMENTER).length, 1);
});

test('requestSnapshot answers a reconnected client with the whole current state', async () => {
  const api = fixtureApi();
  api.feeds['/api/events'].push(record({ event: 'run', status: 'started' }));
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const messages = await collect(monitor.url.replace('http', 'ws') + 'ws', {
    send: [{ type: 'requestSnapshot' }],
    until: snapshotDone,
  });
  assert.equal(messages[0].type, 'providerCapabilities');
  assert.equal(messages.filter((item) => item.type === 'pipelineActorState').length, 3);
});

test('a source that stops answering suppresses work instead of keeping a stale caption', async () => {
  const api = fixtureApi();
  api.feeds['/api/events'].push(record({ event: 'run', status: 'started' }));
  api.feeds['/api/events'].push(record({ source: 'native', event: 'tool_call', status: 'observed', tool: 'Bash', call_id: 'c1' }));
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  assert.equal(monitor.state.actors[IMPLEMENTER].state, 'working');
  api.setFailure(503);
  const deadline = Date.now() + 15000;
  while (monitor.state.source.available) {
    if (Date.now() > deadline) throw new Error('the adapter never noticed the failing source');
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.equal(monitor.state.actors[IMPLEMENTER].state, 'offline');
  assert.match(monitor.state.source.detail, /events:/);
  // Recovery restores activity only from a fresh observation.
  api.setFailure(null);
  while (!monitor.state.source.available) {
    if (Date.now() > deadline) throw new Error('the adapter never recovered');
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.equal(monitor.state.actors[IMPLEMENTER].state, 'working');
});

test('a record of another run is reported to the client and changes no actor', async () => {
  const api = fixtureApi();
  api.feeds['/api/events'].push(record({ run_id: 'run-a', event: 'run', status: 'started' }));
  api.feeds['/api/events'].push(record({ run_id: 'run-b', event: 'cli_exit', status: 'exited', exit_code: 7 }));
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const messages = await collect(monitor.url.replace('http', 'ws') + 'ws', { until: snapshotDone });
  const actor = messages.filter((item) => item.type === 'pipelineActorState').find((item) => item.id === IMPLEMENTER);
  assert.equal(actor.state, 'idle');
  assert.match(actor.caption, /запуск запрошен/, 'another run supplied this run with a state');
  const source = messages.find((item) => item.type === 'pipelineSourceState');
  // The feed itself works: the office keeps its states and says what else is in the directory.
  assert.equal(source.available, true);
  assert.match(source.note, /run-b/);
  assert.equal(monitor.state.runId, 'run-a');
});

test('a body that never finishes expires instead of hanging the office', async () => {
  const api = fixtureApi();
  api.setHold(true);
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  assert.equal(monitor.state.source.available, false, 'a request that never completed is not evidence');
  assert.match(monitor.state.source.detail, /deadline|JSON|Unexpected|источник/i);
  assert.equal(monitor.state.actors[IMPLEMENTER].state, 'offline');
});

test('office settings and layout sent by the client are stored, and a foreign payload is not', async () => {
  const api = fixtureApi();
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const url = monitor.url.replace('http', 'ws') + 'ws';
  await collect(url, {
    send: [{ type: 'webviewReady' },
           { type: 'setSoundEnabled', enabled: false },
           { type: 'saveLayout', layout: { version: 1, cols: 5, rows: 5, tiles: [[0]], furniture: [] } },
           { type: 'saveAgentSeats', seats: { 3: { palette: 1, hueShift: 0, seatId: null } } },
           { type: 'saveLayout', layout: { version: 9, evil: true } }],
    until: snapshotDone,
  });
  const deadline = Date.now() + 10000;
  while (monitor.store.read('layout') === null) {
    if (Date.now() > deadline) throw new Error('the layout was never stored');
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert.equal(monitor.store.read('settings').soundEnabled, false);
  assert.equal(monitor.store.read('layout').cols, 5, 'the refused payload did not overwrite the stored layout');
  assert.deepEqual(monitor.store.read('seats'), { 3: { palette: 1, hueShift: 0, seatId: null } });
  // The stored settings come back in the next snapshot.
  const again = await collect(url, { until: snapshotDone });
  assert.equal(again.find((item) => item.type === 'settingsLoaded').soundEnabled, false);
  assert.equal(again.find((item) => item.type === 'layoutLoaded').layout.cols, 5);
});

test('a message the adapter does not implement changes nothing at all', async () => {
  const api = fixtureApi();
  const monitor = await startOffice(api);
  after(async () => {
    await monitor.close();
    await api.close();
  });
  const url = monitor.url.replace('http', 'ws') + 'ws';
  const messages = await collect(url, {
    send: [{ type: 'webviewReady' },
           { type: 'launchAgent', folderPath: '/etc' },
           { type: 'setHooksEnabled', providerId: 'claude', enabled: true },
           { type: 'focusAgent', id: 3 },
           { type: 'closeAgent', id: 3 },
           { type: 'requestDiagnostics' }],
    until: (items) => items.some((item) => item.type === 'agentDiagnostics'),
  });
  const diagnostics = messages.find((item) => item.type === 'agentDiagnostics');
  assert.equal(diagnostics.agents.length, 3);
  assert.ok(!messages.some((item) => item.type === 'hooksStatus'), 'nothing answers a hook request');
  assert.equal(monitor.state.actors[IMPLEMENTER].state, 'unknown', 'closeAgent removed no role');
});
