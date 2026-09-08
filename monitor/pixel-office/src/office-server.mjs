/**
 * The monitor's office server: the built original frontend, its WebSocket, and the
 * existing Python journal API behind it.
 *
 * It serves exactly three kinds of route on 127.0.0.1 and nothing else: the built office
 * and the pinned original assets from a table built once at startup, the /ws socket the
 * original frontend connects to, and a proxy of /details and /api/* to the progress
 * server that owns the journal, the trace and the registered artifacts. There is no
 * directory handler, no request path is ever joined onto a directory, and no route can
 * launch a command or touch a CLI profile.
 *
 * The adapter observes. It polls the journal and the trace of one explicitly selected
 * run, projects them into office messages, and publishes what changed. Every poll has a
 * deadline that covers the body, and a response that arrives after its own deadline is
 * dropped: a stalled source becomes a visible unavailable feed, never a stale state that
 * still claims to be work.
 */

import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { createServer, request as httpRequest } from 'node:http';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { WebSocketServer } from 'ws';

import { OfficeStateStore } from './office-state.mjs';
import {
  ACTORS,
  emptyJournalFold,
  emptyTraceFold,
  foldJournal,
  foldTrace,
  projectOffice,
} from './projection.mjs';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, 'dist');
const office = join(dist, 'office');
const publicDir = join(root, 'vendor', 'webview-ui', 'public');

/** Upstream version of the vendored frontend; the office renders it in its own badge. */
const VERSION = JSON.parse(readFileSync(join(root, 'vendor-manifest.json'), 'utf8')).version.replace(/^v/, '');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ttf': 'font/ttf',
};

const POLL_INTERVAL_MS = 500;
const POLL_DEADLINE_MS = 10_000;
const PROXY_DEADLINE_MS = 30_000;
const PAGE_LIMIT = 2000;
const MAX_CLIENT_MESSAGE_BYTES = 4 * 1024 * 1024;
const PROXIED = new Set(['/details', '/api/events', '/api/trace', '/api/artifact']);

function contentType(name) {
  const dot = name.lastIndexOf('.');
  return TYPES[name.slice(dot)] ?? 'application/octet-stream';
}

/**
 * The complete table of files this server may return, built once from the two trees it
 * owns. A request path is looked up in this table; it is never turned into a file path.
 */
export function buildRouteTable() {
  const routes = new Map();
  const add = (base, name, prefix) => {
    const path = join(base, name);
    routes.set(prefix + name, { path, type: contentType(name), bytes: statSync(path).size });
  };
  const walk = (base, into = [], directory = base) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) walk(base, into, path);
      else into.push(relative(base, path).split('\\').join('/'));
    }
    return into;
  };
  // The pinned originals first, so a built file of the same name always wins.
  for (const name of walk(publicDir)) add(publicDir, name, '/');
  for (const name of walk(office)) add(office, name, '/');
  routes.set('/', routes.get('/index.html'));
  return routes;
}

/** Read the JSON body of a bounded request; a deadline covers headers and body alike. */
function fetchJson(origin, path, deadlineMs) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, origin);
    const call = httpRequest(
      { hostname: url.hostname, port: url.port, path: url.pathname + url.search, method: 'GET', headers: { Host: '127.0.0.1' } },
      (response) => {
        if (response.statusCode !== 200) {
          response.resume();
          reject(new Error('source answered ' + response.statusCode));
          return;
        }
        const chunks = [];
        let size = 0;
        response.on('data', (chunk) => {
          size += chunk.length;
          if (size > 64 * 1024 * 1024) {
            call.destroy(new Error('source page is too large'));
            return;
          }
          chunks.push(chunk);
        });
        response.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
          } catch (error) {
            reject(error);
          }
        });
        response.on('error', reject);
      },
    );
    // setTimeout on the request covers inactivity only, so the whole call is bounded
    // separately: a source that dribbles bytes forever still expires here.
    const timer = setTimeout(() => call.destroy(new Error('source did not answer within the deadline')), deadlineMs);
    call.on('error', reject);
    call.on('close', () => clearTimeout(timer));
    call.end();
  });
}

/** Everything the original frontend needs before it can show anything, in its own order. */
function snapshotMessages(assets, store, state) {
  const settings = store.read('settings');
  const seats = store.read('seats');
  const areas = store.read('areas');
  const layout = store.read('layout') ?? assets.layout;
  const agentMeta = {};
  for (const actor of ACTORS) {
    if (seats[String(actor.id)]) agentMeta[String(actor.id)] = seats[String(actor.id)];
  }
  const messages = [
    // No tool of this pipeline spawns a sub-agent character, and the reading pose is
    // chosen from the observed tool name, so both lists describe what is really there.
    { type: 'providerCapabilities', readingTools: ['Read', 'Grep', 'Glob'], subagentToolNames: [] },
    { type: 'characterSpritesLoaded', characters: assets.characters },
    { type: 'petSpritesLoaded', pets: assets.pets, petNames: assets.petNames },
    { type: 'floorTilesLoaded', sprites: assets.floors },
    { type: 'wallTilesLoaded', sets: assets.walls },
    { type: 'carpetTilesLoaded', sets: assets.carpets },
    { type: 'furnitureAssetsLoaded', catalog: assets.furniture.catalog, sprites: assets.furniture.sprites },
    {
      type: 'settingsLoaded',
      soundEnabled: settings.soundEnabled,
      lastSeenVersion: settings.lastSeenVersion,
      extensionVersion: VERSION,
      watchAllSessions: false,
      alwaysShowLabels: settings.alwaysShowLabels,
      ghostHeadlessAgents: settings.ghostHeadlessAgents,
      hooksEnabled: false,
      hooksInfoShown: true,
      externalAssetDirectories: [],
      showAreas: settings.showAreas,
    },
    { type: 'areaMappingsLoaded', mappings: areas },
    { type: 'workspaceFolders', folders: [] },
    {
      type: 'existingAgents',
      agents: ACTORS.map((actor) => actor.id),
      agentMeta,
      folderNames: {},
      externalAgents: {},
    },
    { type: 'layoutLoaded', layout },
  ];
  // Names and states come after the characters exist: existingAgents buffers them until
  // layoutLoaded, so anything sent earlier would address a character that is not there.
  for (const actor of ACTORS) {
    messages.push({ type: 'agentTeamInfo', id: actor.id, agentName: actor.name });
  }
  for (const actor of ACTORS) messages.push(state.actors[actor.id]);
  messages.push(state.source);
  return messages;
}

function equalActor(left, right) {
  if (!left || !right) return false;
  return (
    left.state === right.state &&
    left.caption === right.caption &&
    left.short === right.short &&
    left.role === right.role &&
    left.provenance === right.provenance &&
    (left.toolName ?? null) === (right.toolName ?? null)
  );
}

export function parseArguments(argv) {
  const options = {
    port: 0,
    apiOrigin: null,
    stateDir: null,
    pollIntervalMs: POLL_INTERVAL_MS,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const [name, inline] = argv[index].split(/=(.*)/s);
    const value = inline !== undefined ? inline : argv[++index];
    if (name === '--port') options.port = Number(value);
    else if (name === '--api-origin') options.apiOrigin = value;
    else if (name === '--state-dir') options.stateDir = value;
    else if (name === '--poll-interval-ms') options.pollIntervalMs = Number(value);
    else throw new Error('unknown option: ' + name);
  }
  if (!options.apiOrigin) throw new Error('--api-origin is required: the journal API this office reads');
  if (!options.stateDir) throw new Error('--state-dir is required: the local runtime storage of the office layout');
  if (!Number.isInteger(options.port) || options.port < 0 || options.port > 65535) throw new Error('invalid --port');
  if (!Number.isInteger(options.pollIntervalMs) || options.pollIntervalMs < 50) throw new Error('invalid --poll-interval-ms');
  return options;
}

export function createOfficeServer(options) {
  const assets = JSON.parse(readFileSync(join(dist, 'assets.json'), 'utf8'));
  const routes = buildRouteTable();
  const store = new OfficeStateStore(options.stateDir);

  let journalFold = emptyJournalFold();
  let traceFold = emptyTraceFold();
  let cursors = { events: { cursor: 0, discard: false }, trace: { cursor: 0, discard: false } };
  let source = { available: true, detail: 'источник еще не прочитан' };
  let state = projectOffice({ journal: journalFold, trace: traceFold, source });
  let published = {};
  let generation = 0;
  let timer = null;
  let stopped = false;

  const server = createServer((incoming, response) => handle(incoming, response));
  const sockets = new WebSocketServer({ noServer: true });

  function send(socket, message) {
    if (socket.readyState === socket.OPEN) socket.send(JSON.stringify(message));
  }

  function broadcast(messages) {
    for (const socket of sockets.clients) {
      for (const message of messages) send(socket, message);
    }
  }

  function republish() {
    const changed = [];
    for (const actor of ACTORS) {
      const next = state.actors[actor.id];
      if (!equalActor(published[actor.id], next)) {
        published[actor.id] = next;
        changed.push(next);
      }
    }
    if (published.source === undefined || published.source.available !== state.source.available
        || published.source.detail !== state.source.detail || published.source.note !== state.source.note) {
      published.source = state.source;
      changed.push(state.source);
    }
    if (changed.length > 0) broadcast(changed);
  }

  async function poll() {
    const mine = ++generation;
    const problems = [];
    for (const [name, path] of [['events', '/api/events'], ['trace', '/api/trace']]) {
      let guard = 0;
      for (;;) {
        const position = cursors[name];
        let page;
        try {
          page = await fetchJson(
            options.apiOrigin,
            path + '?cursor=' + position.cursor + '&limit=' + PAGE_LIMIT + '&discard=' + (position.discard ? 1 : 0),
            POLL_DEADLINE_MS,
          );
        } catch (error) {
          problems.push(name + ': ' + error.message);
          break;
        }
        // A response that outlived its own poll belongs to a state nobody is showing any
        // more; applying it would resurrect an observation the next poll already replaced.
        if (mine !== generation || stopped) return;
        if (!page.journal) {
          problems.push(name + ': ' + (page.error ? 'источник недоступен (' + page.error + ')' : 'журнала еще нет'));
          break;
        }
        if (page.reset) {
          // The file was replaced or truncated: everything derived from it is history.
          cursors[name] = { cursor: 0, discard: false };
          if (name === 'events') journalFold = emptyJournalFold();
          else traceFold = emptyTraceFold();
          if (++guard > 4) break;
          continue;
        }
        if (page.invalid_lines > 0) problems.push(name + ': ' + page.invalid_lines + ' нечитаемых записей пропущено');
        // The journal is polled first, so the run it selected seeds the trace: both folds
        // isolate the same run instead of each choosing one from whatever it read first.
        if (name === 'events') journalFold = foldJournal(page.events, journalFold);
        else traceFold = foldTrace(page.events, traceFold, journalFold.runId);
        cursors[name] = { cursor: page.cursor, discard: page.discard };
        if (!page.more) break;
        if (++guard > 512) break;
      }
    }
    source = problems.length > 0
      ? { available: false, detail: problems.join('; ') }
      : { available: true, detail: '' };
    state = projectOffice({ journal: journalFold, trace: traceFold, source });
    republish();
  }

  function schedule() {
    if (stopped) return;
    timer = setTimeout(() => {
      poll()
        .catch(() => {
          source = { available: false, detail: 'наблюдатель монитора отказал' };
          state = projectOffice({ journal: journalFold, trace: traceFold, source });
          republish();
        })
        .finally(schedule);
    }, options.pollIntervalMs);
    timer.unref?.();
  }

  function proxy(incoming, response, path) {
    const url = new URL(options.apiOrigin);
    const target = path === '/details' ? '/' : path;
    const call = httpRequest(
      {
        hostname: url.hostname,
        port: url.port,
        path: target + (incoming.url.includes('?') ? '?' + incoming.url.split('?')[1] : ''),
        method: 'GET',
        headers: { Host: '127.0.0.1' },
      },
      (upstream) => {
        const headers = {};
        for (const name of ['content-type', 'content-length', 'content-security-policy', 'content-disposition',
                            'x-artifact-sha256', 'cache-control', 'x-content-type-options', 'referrer-policy']) {
          if (upstream.headers[name]) headers[name] = upstream.headers[name];
        }
        response.writeHead(upstream.statusCode, headers);
        upstream.pipe(response);
      },
    );
    const timer = setTimeout(() => call.destroy(new Error('deadline')), PROXY_DEADLINE_MS);
    call.on('error', () => {
      clearTimeout(timer);
      if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('journal API is unavailable\n');
    });
    call.on('close', () => clearTimeout(timer));
    call.end();
  }

  function handle(incoming, response) {
    const host = (incoming.headers.host ?? '').replace(/:\d+$/, '');
    if (host !== '127.0.0.1' && host !== 'localhost') {
      response.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('only local hosts are served\n');
      return;
    }
    if (incoming.method !== 'GET' && incoming.method !== 'HEAD') {
      response.writeHead(405, { 'Content-Type': 'text/plain; charset=utf-8', Allow: 'GET, HEAD' });
      response.end('method not allowed\n');
      return;
    }
    // A malformed escape makes decodeURI throw, and a throw in this listener would take the whole
    // office down with it. A path that cannot be decoded names no route.
    let path;
    try {
      path = decodeURI(incoming.url.split('?')[0]);
    } catch {
      response.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('malformed request path\n');
      return;
    }
    if (PROXIED.has(path)) {
      proxy(incoming, response, path);
      return;
    }
    const route = routes.get(path);
    if (!route) {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('not found\n');
      return;
    }
    let body;
    try {
      body = readFileSync(route.path);
    } catch {
      response.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('the office bundle is not built\n');
      return;
    }
    response.writeHead(200, {
      'Content-Type': route.type,
      'Content-Length': body.length,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      ETag: '"' + createHash('sha256').update(body).digest('hex').slice(0, 32) + '"',
    });
    response.end(incoming.method === 'HEAD' ? undefined : body);
  }

  server.on('upgrade', (incoming, socket, head) => {
    const host = (incoming.headers.host ?? '').replace(/:\d+$/, '');
    if (incoming.url.split('?')[0] !== '/ws' || (host !== '127.0.0.1' && host !== 'localhost')) {
      socket.destroy();
      return;
    }
    sockets.handleUpgrade(incoming, socket, head, (client) => sockets.emit('connection', client, incoming));
  });

  sockets.on('connection', (socket) => {
    socket.on('message', (data) => {
      if (data.length > MAX_CLIENT_MESSAGE_BYTES) return;
      let message;
      try {
        message = JSON.parse(data.toString('utf8'));
      } catch {
        return;
      }
      if (!message || typeof message.type !== 'string') return;
      onClientMessage(socket, message);
    });
    // The snapshot is not sent before webviewReady: the original client registers its
    // handler and then announces itself, and a reconnect asks again with requestSnapshot.
  });

  function onClientMessage(socket, message) {
    switch (message.type) {
      case 'webviewReady':
      case 'requestSnapshot':
        for (const item of snapshotMessages(assets, store, state)) send(socket, item);
        for (const actor of ACTORS) published[actor.id] = state.actors[actor.id];
        published.source = state.source;
        return;
      case 'saveLayout':
        store.write('layout', message.layout);
        return;
      case 'saveAgentSeats':
        store.write('seats', message.seats);
        return;
      case 'saveAreaMappings':
        store.write('areas', message.mappings);
        return;
      case 'setSoundEnabled':
      case 'setAlwaysShowLabels':
      case 'setGhostHeadlessAgents':
      case 'setShowAreas': {
        const field = { setSoundEnabled: 'soundEnabled', setAlwaysShowLabels: 'alwaysShowLabels',
                        setGhostHeadlessAgents: 'ghostHeadlessAgents', setShowAreas: 'showAreas' }[message.type];
        store.write('settings', { ...store.read('settings'), [field]: message.enabled });
        return;
      }
      case 'setLastSeenVersion':
        store.write('settings', { ...store.read('settings'), lastSeenVersion: message.version });
        return;
      case 'requestDiagnostics':
        send(socket, {
          type: 'agentDiagnostics',
          agents: ACTORS.map((actor) => ({
            id: actor.id,
            name: actor.name,
            state: state.actors[actor.id]?.state ?? 'unknown',
            caption: state.actors[actor.id]?.caption ?? '',
            provenance: state.actors[actor.id]?.provenance ?? '',
            sourceAvailable: state.source.available,
            sourceDetail: state.source.detail,
          })),
        });
        return;
      default:
        // focusAgent, closeAgent, launchAgent and the hook messages have no meaning for a
        // role representative of this pipeline. They are ignored rather than answered
        // with an effect the sender did not ask for.
        return;
    }
  }

  return {
    server,
    get url() {
      const address = server.address();
      return 'http://127.0.0.1:' + address.port + '/';
    },
    get state() {
      return state;
    },
    routes,
    store,
    async listen() {
      await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(options.port, '127.0.0.1', resolve);
      });
      await poll();
      schedule();
      return this.url;
    },
    async close() {
      stopped = true;
      if (timer) clearTimeout(timer);
      for (const socket of sockets.clients) socket.terminate();
      await new Promise((resolve) => sockets.close(resolve));
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

if (process.argv[1] && import.meta.url === new URL(process.argv[1], 'file:').href) {
  const options = parseArguments(process.argv.slice(2));
  const monitor = createOfficeServer(options);
  const url = await monitor.listen();
  process.stdout.write(JSON.stringify({ url, state_dir: options.stateDir, api: options.apiOrigin }) + '\n');
  const stop = () => {
    monitor.close().then(() => process.exit(0), () => process.exit(1));
  };
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
}
