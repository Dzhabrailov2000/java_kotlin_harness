/**
 * Same-page adapter around the vendored Pixel Agents office engine.
 *
 * The monitor page owns every fact: it reduces its own journal and trace feeds
 * and hands this adapter a bounded snapshot of three actors. The adapter only
 * projects that snapshot onto the original engine (OfficeState, renderer,
 * gameLoop) and reports pointer selection back. It never polls, never parses a
 * transcript and never invents a state of its own.
 *
 * Exposed as window.mountPixelOffice by the iife bundle.
 */

import { CHARACTER_HIT_HEIGHT } from '../vendor/webview-ui/src/constants.js';
import { buildDynamicCatalog, getCatalogEntry } from '../vendor/webview-ui/src/office/layout/furnitureCatalog.js';
import { startGameLoop } from '../vendor/webview-ui/src/office/engine/gameLoop.js';
import { OfficeState } from '../vendor/webview-ui/src/office/engine/officeState.js';
import { renderFrame } from '../vendor/webview-ui/src/office/engine/renderer.js';
import { setFloorSprites } from '../vendor/webview-ui/src/office/floorTiles.js';
import { overlayProjection } from '../vendor/webview-ui/src/office/projection.js';
import { setCarpetSprites } from '../vendor/webview-ui/src/office/sprites/carpetTiles.js';
import { setCharacterTemplates } from '../vendor/webview-ui/src/office/sprites/spriteData.js';
import { setProviderCapabilities } from '../vendor/webview-ui/src/office/toolUtils.js';
import type { Character, PlacedFurniture, Seat } from '../vendor/webview-ui/src/office/types.js';
import { CharacterState, Direction, TILE_SIZE } from '../vendor/webview-ui/src/office/types.js';
import { setWallSprites } from '../vendor/webview-ui/src/office/wallTiles.js';

/** One actor of the office as the monitor's reducers see it. */
export interface OfficeActorSnapshot {
  /** 1 Пользователь, 2 Codex, 3 Claude; other ids are ignored. */
  id: number;
  name: string;
  /** Short readable status line shown over the sprite. */
  short: string;
  /** True only for an actor the monitor observed working right now. */
  active: boolean;
  /** Observed tool name of a live invocation, or null. */
  tool: string | null;
}

export interface OfficeSnapshot {
  /** False freezes every work animation: an unreachable feed confirms nothing. */
  connected: boolean;
  /** False freezes the simulation (reduced motion or the page's own toggle). */
  motion: boolean;
  selectedActorId: number | null;
  actors: OfficeActorSnapshot[];
}

export interface OfficeView {
  update(snapshot: OfficeSnapshot): void;
  /** Fit, or a whole multiple of it; the view centres on the selected actor when zoomed in. */
  setZoomStep(step: number): void;
  zoomSteps(): number[];
  dispose(): void;
  /** Observable state for tests: no page code depends on it. */
  inspect(): OfficeInspection;
}

export interface OfficeInspection {
  frames: number;
  /** Lifecycle calls made into the engine so far; a repeated snapshot must not raise it. */
  lifecycleCalls: number;
  simulating: boolean;
  zoom: number;
  zoomStep: number;
  selectedActorId: number | null;
  actors: Array<{
    id: number;
    name: string;
    short: string;
    x: number;
    y: number;
    seatId: string | null;
    active: boolean;
    tool: string | null;
    state: number;
    labelLeft: number;
    labelTop: number;
    /** Centre of the character's hit box in CSS pixels of the canvas box. */
    hitX: number;
    hitY: number;
  }>;
}

export interface OfficeOptions {
  onSelect: (actorId: number) => void;
  /** Defaults to the route the monitor serves the predecoded payload on. */
  assetsUrl?: string;
}

const ACTOR_IDS = [1, 2, 3];
const PALETTES: Record<number, number> = { 1: 0, 2: 1, 3: 2 };
const ZOOM_STEPS = [1, 2, 3];
/** Sprites are 16x24 anchored bottom-centre; the label floats just above the head. */
const LABEL_LIFT_PX = 30;
/** Mirrors the padding the page gives the stage; the canvas is sized inside it. */
const CONTAINER_PADDING_PX = 8;
/** A finished frame may be stretched to fill the stage, but only this far. */
const MAX_DISPLAY_SCALE = 3;
/** Free space kept between two stacked labels, in CSS pixels. */
const LABEL_GAP_PX = 4;
const VOID_TILE = 255;

/** Floating name of one actor; its measured box drives the stacking of neighbouring labels. */
interface Label {
  box: HTMLElement;
  name: HTMLElement;
  short: HTMLElement;
  width: number;
  height: number;
}

interface AssetPayload {
  characters: Array<{ down: string[][][]; up: string[][][]; right: string[][][] }>;
  floors: string[][][];
  walls: string[][][][];
  carpets: string[][][][];
  furniture: { catalog: unknown[]; sprites: Record<string, string[][]> };
  layout: { cols: number; rows: number; furniture: unknown[] };
}

function fail(message: string): never {
  throw new Error(message);
}

function filled(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0;
}

function validatePayload(data: unknown): AssetPayload {
  const payload = data as AssetPayload;
  if (!payload || typeof payload !== 'object') fail('ассеты офиса: ответ не является объектом');
  if (!filled(payload.characters)) fail('ассеты офиса: спрайты персонажей отсутствуют');
  if (!filled(payload.floors)) fail('ассеты офиса: плитки пола отсутствуют');
  if (!filled(payload.walls)) fail('ассеты офиса: плитки стен отсутствуют');
  if (!filled(payload.carpets)) fail('ассеты офиса: ковры отсутствуют');
  if (!payload.furniture || !filled(payload.furniture.catalog) || !payload.furniture.sprites) {
    fail('ассеты офиса: каталог мебели отсутствует');
  }
  const layout = payload.layout;
  if (!layout || !(layout.cols > 0) || !(layout.rows > 0) || !Array.isArray(layout.furniture)) {
    fail('ассеты офиса: планировка комнаты повреждена');
  }
  for (const character of payload.characters) {
    if (!filled(character?.down) || !filled(character?.up) || !filled(character?.right)) {
      fail('ассеты офиса: у персонажа нет кадров движения');
    }
  }
  return payload;
}

/** Seats at a workstation first: a seat facing a computer, then one facing any desk, then the rest.
 *  The tie-break is the seat uid of the checked-in layout, so the three desks are the same every run.
 *  Colleagues at their computers read as an office; the same three on the sofa do not. */
function workstationsFirst(office: OfficeState, furniture: PlacedFurniture[]): string[] {
  const tiles = (test: (category: string, isDesk: boolean) => boolean): Set<string> => {
    const out = new Set<string>();
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry || !test(entry.category, entry.isDesk === true)) continue;
      for (let row = 0; row < entry.footprintH; row += 1) {
        for (let col = 0; col < entry.footprintW; col += 1) {
          out.add(item.col + col + ',' + (item.row + row));
        }
      }
    }
    return out;
  };
  const computers = tiles((category) => category === 'electronics');
  const desks = tiles((category, isDesk) => isDesk);
  const rank = (uid: string): number => {
    const seat = office.seats.get(uid);
    if (!seat) return 2;
    const step = seat.facingDir === Direction.RIGHT ? [1, 0]
      : seat.facingDir === Direction.LEFT ? [-1, 0]
      : seat.facingDir === Direction.DOWN ? [0, 1] : [0, -1];
    const facing = seat.seatCol + step[0] + ',' + (seat.seatRow + step[1]);
    return computers.has(facing) ? 0 : desks.has(facing) ? 1 : 2;
  };
  return Array.from(office.seats.keys()).sort((left, right) => {
    const difference = rank(left) - rank(right);
    return difference !== 0 ? difference : left < right ? -1 : left > right ? 1 : 0;
  });
}

/** The part of the grid that is actually a room: the shipped layout keeps whole void rows around it,
 *  and centring the whole grid would spend most of the canvas on nothing. */
function roomBounds(tileMap: number[][]): { x: number; y: number; width: number; height: number } {
  let minCol = Infinity, maxCol = -Infinity, minRow = Infinity, maxRow = -Infinity;
  for (let row = 0; row < tileMap.length; row += 1) {
    for (let col = 0; col < tileMap[row].length; col += 1) {
      if (tileMap[row][col] === VOID_TILE) continue;
      if (col < minCol) minCol = col;
      if (col > maxCol) maxCol = col;
      if (row < minRow) minRow = row;
      if (row > maxRow) maxRow = row;
    }
  }
  if (minCol > maxCol) {
    const cols = tileMap.length > 0 ? tileMap[0].length : 1;
    return { x: 0, y: 0, width: cols * TILE_SIZE, height: tileMap.length * TILE_SIZE };
  }
  // Wall pieces are 32 px tall on a 16 px tile and furniture stands taller than its footprint, so the
  // top row needs a tile of headroom or the far wall is cut in half.
  const top = Math.max(0, minRow * TILE_SIZE - TILE_SIZE);
  return {
    x: minCol * TILE_SIZE,
    y: top,
    width: (maxCol - minCol + 1) * TILE_SIZE,
    height: (maxRow + 1) * TILE_SIZE - top,
  };
}

export async function mountPixelOffice(
  canvas: HTMLCanvasElement,
  options: OfficeOptions,
): Promise<OfficeView> {
  const assetsUrl = options.assetsUrl || '/pixel-agents/assets.json';
  let response: Response;
  try {
    response = await fetch(assetsUrl, { cache: 'no-store' });
  } catch (error) {
    return fail('ассеты офиса не загружены: ' + String((error as Error)?.message || error));
  }
  if (!response.ok) fail('ассеты офиса не загружены: HTTP ' + response.status);
  const payload = validatePayload(await response.json());

  setCharacterTemplates(payload.characters);
  setFloorSprites(payload.floors);
  setWallSprites(payload.walls);
  setCarpetSprites(payload.carpets);
  if (!buildDynamicCatalog(payload.furniture as never)) fail('ассеты офиса: каталог мебели не собран');
  // Claude's read-only tools get the reading pose instead of the typing pose; the names are the
  // monitor's own observed tool names, not a provider discovery of any kind.
  setProviderCapabilities({
    readingTools: ['Read', 'Glob', 'Grep', 'NotebookRead', 'WebFetch', 'WebSearch'],
    subagentToolNames: ['Task', 'Agent'],
  });

  const office = new OfficeState(payload.layout as never);
  const layout = office.getLayout();
  const room = roomBounds(office.tileMap as unknown as number[][]);
  const seatIds = workstationsFirst(office, layout.furniture);
  const names = new Map<number, string>();
  const shorts = new Map<number, string>();
  const activeById = new Map<number, boolean>();
  const toolById = new Map<number, string | null>();
  let lifecycleCalls = 0;
  ACTOR_IDS.forEach((id, index) => {
    office.addAgent(id, PALETTES[id], 0, seatIds[index], true);
    // addAgent creates an active character: nothing is working until the monitor says so.
    office.setAgentActive(id, false);
    lifecycleCalls += 1;
    activeById.set(id, false);
    toolById.set(id, null);
    names.set(id, 'агент ' + id);
    shorts.set(id, 'состояние неизвестно');
  });

  const context = canvas.getContext('2d');
  if (!context) fail('офис: канвас не отдал 2d-контекст');
  const ctx = context;
  const container = canvas.parentElement;
  if (!container) fail('офис: у канваса нет контейнера для подписей');

  const overlay = document.createElement('div');
  overlay.className = 'office-labels';
  // The accessible controls live in the page; these labels are the visual layer of the same facts.
  overlay.setAttribute('aria-hidden', 'true');
  container.appendChild(overlay);
  const labels = new Map<number, Label>();
  for (const id of ACTOR_IDS) {
    const box = document.createElement('div');
    box.className = 'office-label';
    const name = document.createElement('span');
    name.className = 'office-label-name';
    const short = document.createElement('span');
    short.className = 'office-label-short';
    box.appendChild(name);
    box.appendChild(short);
    overlay.appendChild(box);
    labels.set(id, { box, name, short, width: 0, height: 0 });
  }

  let zoom = 1;
  let zoomStep = 1;
  let pan = { x: 0, y: 0 };
  const display = { width: 0, height: 0 };
  let stageWidth = -1;
  let frames = 0;
  let selectedActorId: number | null = null;
  let simulating = false;
  let stopLoop: (() => void) | null = null;
  let disposed = false;
  let wantMotion = true;
  let connected = true;

  const reduced = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const motionAllowed = () => wantMotion && !(reduced && reduced.matches);

  function seatOf(character: Character): Seat | null {
    return character.seatId ? office.seats.get(character.seatId) || null : null;
  }

  /** Frozen scenes show people at their desks: with the simulation stopped a mid-walk pose
   *  would freeze in a corridor and read as an interrupted action that never happened. */
  function settle(): void {
    for (const character of office.getCharacters()) {
      const seat = seatOf(character);
      if (!seat) continue;
      character.x = seat.seatCol * TILE_SIZE + TILE_SIZE / 2;
      character.y = seat.seatRow * TILE_SIZE + TILE_SIZE / 2;
      character.tileCol = seat.seatCol;
      character.tileRow = seat.seatRow;
      character.dir = seat.facingDir;
      character.path = [];
      character.moveProgress = 0;
      character.state = CharacterState.TYPE;
      character.frame = 0;
      character.frameTimer = 0;
    }
  }

  /** Device pixels of the backing store per CSS pixel of the box it is displayed in. The backing store is
   *  a whole multiple of the room, so this is not always the display's own ratio. */
  function pixelRatio(): number {
    return display.width > 0 ? canvas.width / display.width : window.devicePixelRatio || 1;
  }

  /** Pan that puts `target` in the middle of the canvas without showing anything outside the room. */
  function panFor(canvasSize: number, gridSize: number, boxStart: number, boxSize: number, target: number): number {
    const visible = canvasSize / zoom;
    const center = visible >= boxSize
      ? boxStart + boxSize / 2
      : Math.max(boxStart + visible / 2, Math.min(boxStart + boxSize - visible / 2, target));
    return canvasSize / 2 - center * zoom - Math.floor((canvasSize - gridSize * zoom) / 2);
  }

  /** Reads the page's layout and sizes the canvas; called on mount, resize and zoom, never per frame. */
  function layoutCanvas(): void {
    // The page decides how tall the stage may be; the inline height of the previous pass is dropped
    // first so that value is read, and set again below so no empty band is left under the frame.
    container.style.height = '';
    const available = {
      width: Math.max(64, container.clientWidth - CONTAINER_PADDING_PX * 2),
      height: Math.max(64, container.clientHeight - CONTAINER_PADDING_PX * 2),
    };
    stageWidth = container.clientWidth;
    const dpr = window.devicePixelRatio || 1;
    const fit = Math.min((available.width * dpr) / room.width, (available.height * dpr) / room.height);
    // Whole zoom keeps the original pixel art on its grid; the box is filled by scaling the finished
    // bitmap, so no fractional sprite sampling happens inside the renderer.
    zoom = Math.max(1, Math.floor(fit)) * zoomStep;
    const width = zoomStep > 1 ? Math.min(room.width * zoom, Math.round(available.width * dpr)) : room.width * zoom;
    const height = zoomStep > 1 ? Math.min(room.height * zoom, Math.round(available.height * dpr)) : room.height * zoom;
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    const scale = Math.min(available.width / (width / dpr), available.height / (height / dpr), MAX_DISPLAY_SCALE);
    display.width = Math.round((width / dpr) * scale);
    display.height = Math.round((height / dpr) * scale);
    canvas.style.width = display.width + 'px';
    canvas.style.height = display.height + 'px';
    container.style.height = display.height + CONTAINER_PADDING_PX * 2 + 'px';
  }

  function updatePan(): void {
    // Zoomed past the room, the person under discussion stays in view; otherwise the room is centred.
    const focus = selectedActorId === null ? null : findCharacter(selectedActorId);
    pan = {
      x: panFor(canvas.width, layout.cols * TILE_SIZE, room.x, room.width, focus ? focus.x : room.x + room.width / 2),
      y: panFor(canvas.height, layout.rows * TILE_SIZE, room.y, room.height, focus ? focus.y : room.y + room.height / 2),
    };
  }

  function findCharacter(id: number): Character | null {
    for (const character of office.getCharacters()) {
      if (character.id === id) return character;
    }
    return null;
  }

  function positionLabels(): void {
    if (display.width === 0 || display.height === 0) return;
    overlay.style.left = canvas.offsetLeft + 'px';
    overlay.style.top = canvas.offsetTop + 'px';
    overlay.style.width = display.width + 'px';
    overlay.style.height = display.height + 'px';
    const projection = overlayProjection(layout, display, zoom, pan, pixelRatio());
    // Каждая подпись сначала встает над своим персонажем, с клампом по собственному размеру:
    // она смещена на -50% по ширине и на -100% по высоте.
    const placed: Array<{ label: Label; left: number; half: number; top: number; height: number }> = [];
    for (const id of ACTOR_IDS) {
      const label = labels.get(id);
      const character = findCharacter(id);
      if (!label || !character) continue;
      const half = label.width / 2;
      placed.push({
        label,
        half,
        left: Math.max(half, Math.min(display.width - half, Math.round(projection.toScreenX(character.x)))),
        top: Math.max(label.height, Math.min(display.height, Math.round(projection.toScreenY(character.y - LABEL_LIFT_PX)))),
        height: label.height,
      });
    }
    // Neighbours are stacked against their measured boxes, not by a constant offset: a two line label
    // is taller than any fixed stagger, so at a narrow width the names would cover each other.
    // The label nearest the viewer keeps its place over its own sprite; the ones behind move up.
    placed.sort((first, second) => second.top - first.top);
    for (let index = 0; index < placed.length; index += 1) {
      const box = placed[index];
      for (let pass = 0; pass < index; pass += 1) {
        let moved = false;
        for (let other = 0; other < index; other += 1) {
          const above = placed[other];
          const apart = box.left + box.half <= above.left - above.half || above.left + above.half <= box.left - box.half
            || box.top - box.height >= above.top || box.top <= above.top - above.height;
          if (apart) continue;
          box.top = above.top - above.height - LABEL_GAP_PX;
          moved = true;
        }
        if (!moved) break;
      }
    }
    // Стопка выше сцены не помещается только в вырожденно низком канвасе; тогда она опускается
    // целиком, сохраняя расстояния между подписями.
    let overflow = 0;
    for (const box of placed) overflow = Math.max(overflow, box.height - box.top);
    for (const box of placed) {
      box.label.box.style.left = box.left + 'px';
      box.label.box.style.top = box.top + overflow + 'px';
    }
  }

  function paint(): void {
    updatePan();
    ctx.imageSmoothingEnabled = false;
    renderFrame(
      ctx,
      canvas.width,
      canvas.height,
      office.tileMap,
      office.furniture,
      office.getCharacters(),
      zoom,
      pan.x,
      pan.y,
      undefined,
      undefined,
      layout.tileColors,
      layout.cols,
      layout.rows,
      layout.carpetTiles,
      layout.areas,
      layout.areaTiles,
      false,
      null,
      office.getPets(),
    );
    frames += 1;
    positionLabels();
  }

  function startSimulation(): void {
    if (simulating || disposed) return;
    simulating = true;
    stopLoop = startGameLoop(canvas, {
      update: (dt) => office.update(dt),
      render: () => paint(),
    });
  }

  function stopSimulation(): void {
    if (stopLoop) stopLoop();
    stopLoop = null;
    simulating = false;
  }

  function applyMotion(): void {
    if (motionAllowed()) {
      startSimulation();
    } else if (simulating || frames === 0) {
      stopSimulation();
      settle();
      paint();
    }
  }

  function labelText(): void {
    for (const id of ACTOR_IDS) {
      const label = labels.get(id);
      if (!label) continue;
      label.name.textContent = names.get(id) || '';
      label.short.textContent = shorts.get(id) || '';
      label.box.className = 'office-label' + (selectedActorId === id ? ' selected' : '');
      // Measured here, where the text changes, and not on every frame of the loop.
      label.width = label.box.offsetWidth;
      label.height = label.box.offsetHeight;
    }
  }

  function update(snapshot: OfficeSnapshot): void {
    if (disposed || !snapshot || !Array.isArray(snapshot.actors)) return;
    connected = snapshot.connected !== false;
    selectedActorId = ACTOR_IDS.indexOf(Number(snapshot.selectedActorId)) >= 0
      ? Number(snapshot.selectedActorId)
      : null;
    for (const actor of snapshot.actors) {
      const id = Number(actor && actor.id);
      if (ACTOR_IDS.indexOf(id) < 0) continue;
      names.set(id, String(actor.name == null ? '' : actor.name));
      shorts.set(id, String(actor.short == null ? '' : actor.short));
      // A lost feed confirms nothing, so it can never leave a work animation running.
      const active = actor.active === true && connected;
      if (activeById.get(id) !== active) {
        // setAgentActive clears the path and resets the seat timer, so it is called on change only.
        office.setAgentActive(id, active);
        activeById.set(id, active);
        lifecycleCalls += 1;
      }
      const tool = active && typeof actor.tool === 'string' && actor.tool ? actor.tool : null;
      if (toolById.get(id) !== tool) {
        office.setAgentTool(id, tool);
        toolById.set(id, tool);
        lifecycleCalls += 1;
      }
    }
    wantMotion = snapshot.motion !== false;
    labelText();
    applyMotion();
    if (!simulating) paint();
  }

  function pick(event: MouseEvent): void {
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const ratio = pixelRatio();
    const deviceX = (event.clientX - rect.left) * ratio;
    const deviceY = (event.clientY - rect.top) * ratio;
    const offsetX = Math.floor((canvas.width - layout.cols * TILE_SIZE * zoom) / 2) + Math.round(pan.x);
    const offsetY = Math.floor((canvas.height - layout.rows * TILE_SIZE * zoom) / 2) + Math.round(pan.y);
    const hit = office.getCharacterAt((deviceX - offsetX) / zoom, (deviceY - offsetY) / zoom);
    if (hit !== null && ACTOR_IDS.indexOf(hit) >= 0) options.onSelect(hit);
  }

  const relayout = () => {
    if (disposed) return;
    layoutCanvas();
    paint();
  };
  // The container is observed, never the canvas, and only a real width change does work: layoutCanvas
  // sets the stage height itself and would otherwise keep waking its own observer.
  const onContainerResize = () => {
    if (disposed || container.clientWidth === stageWidth) return;
    relayout();
  };
  const onMotionChange = () => applyMotion();

  canvas.addEventListener('click', pick);
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(onContainerResize) : null;
  if (observer) observer.observe(container);
  window.addEventListener('resize', relayout);
  if (reduced && reduced.addEventListener) reduced.addEventListener('change', onMotionChange);

  labelText();
  layoutCanvas();
  settle();
  paint();
  applyMotion();

  const view: OfficeView = {
    update,
    setZoomStep(step: number): void {
      const next = ZOOM_STEPS.indexOf(step) >= 0 ? step : 1;
      if (next === zoomStep) return;
      zoomStep = next;
      layoutCanvas();
      paint();
    },
    zoomSteps: () => ZOOM_STEPS.slice(),
    dispose(): void {
      if (disposed) return;
      disposed = true;
      stopSimulation();
      canvas.removeEventListener('click', pick);
      if (observer) observer.disconnect();
      window.removeEventListener('resize', relayout);
      if (reduced && reduced.removeEventListener) reduced.removeEventListener('change', onMotionChange);
      overlay.remove();
    },
    inspect(): OfficeInspection {
      const rect = canvas.getBoundingClientRect();
      const projection = overlayProjection(layout, display, zoom, pan, pixelRatio());
      return {
        frames,
        lifecycleCalls,
        simulating,
        zoom,
        zoomStep,
        selectedActorId,
        actors: ACTOR_IDS.map((id) => {
          const character = findCharacter(id);
          const label = labels.get(id);
          const box = label ? label.box.getBoundingClientRect() : null;
          return {
            id,
            name: names.get(id) || '',
            short: shorts.get(id) || '',
            x: character ? character.x : -1,
            y: character ? character.y : -1,
            seatId: character ? character.seatId : null,
            active: activeById.get(id) === true,
            tool: toolById.get(id) || null,
            state: character ? character.state : -1,
            labelLeft: box ? box.left - rect.left : -1,
            labelTop: box ? box.top - rect.top : -1,
            hitX: character ? projection.toScreenX(character.x) : -1,
            hitY: character ? projection.toScreenY(character.y - CHARACTER_HIT_HEIGHT / 2) : -1,
          };
        }),
      };
    },
  };
  // Observation handle for the browser checks: the mounted view of this canvas. The page keeps its own
  // reference; nothing here gives a script anything it could not already do on the same origin.
  (canvas as unknown as { pixelOffice?: OfficeView }).pixelOffice = view;
  return view;
}
