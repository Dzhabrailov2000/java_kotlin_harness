/* Pixel Agents office engine, MIT, Copyright (c) 2026 Pablo De Lucca.
   Original sources vendored from https://github.com/pixel-agents-hq/pixel-agents at 3537e140c2094761beae748592aeb92ece8edfdd.
   Bundled with a local monitor adapter; see monitor/pixel-office/vendor/LICENSE. */
var PixelOffice = (() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __export = (target, all) => {
    for (var name in all)
      __defProp(target, name, { get: all[name], enumerable: true });
  };
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

  // src/office.ts
  var office_exports = {};
  __export(office_exports, {
    mountPixelOffice: () => mountPixelOffice
  });

  // vendor/webview-ui/src/constants.ts
  var TILE_SIZE = 16;
  var DEFAULT_COLS = 20;
  var DEFAULT_ROWS = 11;
  var WALK_SPEED_PX_PER_SEC = 48;
  var WALK_FRAME_DURATION_SEC = 0.15;
  var TYPE_FRAME_DURATION_SEC = 0.3;
  var WANDER_PAUSE_MIN_SEC = 2;
  var WANDER_PAUSE_MAX_SEC = 20;
  var WANDER_MOVES_BEFORE_REST_MIN = 3;
  var WANDER_MOVES_BEFORE_REST_MAX = 6;
  var SEAT_REST_MIN_SEC = 120;
  var SEAT_REST_MAX_SEC = 240;
  var MATRIX_EFFECT_DURATION_SEC = 0.3;
  var MATRIX_TRAIL_LENGTH = 6;
  var MATRIX_SPRITE_COLS = 16;
  var MATRIX_SPRITE_ROWS = 24;
  var MATRIX_FLICKER_FPS = 30;
  var MATRIX_FLICKER_VISIBILITY_THRESHOLD = 180;
  var MATRIX_COLUMN_STAGGER_RANGE = 0.3;
  var MATRIX_HEAD_COLOR = "#ccffcc";
  var matrixGreenBright = (a) => `rgba(0, 255, 65, ${a})`;
  var matrixGreenMid = (a) => `rgba(0, 170, 40, ${a})`;
  var matrixGreenDim = (a) => `rgba(0, 85, 20, ${a})`;
  var MATRIX_TRAIL_OVERLAY_ALPHA = 0.6;
  var MATRIX_TRAIL_EMPTY_ALPHA = 0.5;
  var MATRIX_TRAIL_MID_THRESHOLD = 0.33;
  var MATRIX_TRAIL_DIM_THRESHOLD = 0.66;
  var CHARACTER_SITTING_OFFSET_PX = 6;
  var CHARACTER_Z_SORT_OFFSET = 0.5;
  var OUTLINE_Z_SORT_OFFSET = 1e-3;
  var SELECTED_OUTLINE_ALPHA = 1;
  var HOVERED_OUTLINE_ALPHA = 0.5;
  var HEADLESS_CHARACTER_ALPHA = 0.5;
  var GHOST_PREVIEW_SPRITE_ALPHA = 0.5;
  var GHOST_PREVIEW_TINT_ALPHA = 0.25;
  var SELECTION_DASH_PATTERN = [4, 3];
  var BUTTON_MIN_RADIUS = 6;
  var BUTTON_RADIUS_ZOOM_FACTOR = 3;
  var BUTTON_ICON_SIZE_FACTOR = 0.45;
  var BUTTON_LINE_WIDTH_MIN = 1.5;
  var BUTTON_LINE_WIDTH_ZOOM_FACTOR = 0.5;
  var BUBBLE_FADE_DURATION_SEC = 0.5;
  var BUBBLE_SITTING_OFFSET_PX = 10;
  var BUBBLE_VERTICAL_OFFSET_PX = 24;
  var FALLBACK_FLOOR_COLOR = "#808080";
  var SEAT_OWN_COLOR = "rgba(0, 127, 212, 0.35)";
  var SEAT_AVAILABLE_COLOR = "rgba(0, 200, 80, 0.35)";
  var SEAT_BUSY_COLOR = "rgba(220, 50, 50, 0.35)";
  var GRID_LINE_COLOR = "rgba(255,255,255,0.12)";
  var VOID_TILE_OUTLINE_COLOR = "rgba(255,255,255,0.08)";
  var VOID_TILE_DASH_PATTERN = [2, 2];
  var GHOST_BORDER_HOVER_FILL = "rgba(60, 130, 220, 0.25)";
  var GHOST_BORDER_HOVER_STROKE = "rgba(60, 130, 220, 0.5)";
  var GHOST_BORDER_STROKE = "rgba(255, 255, 255, 0.06)";
  var GHOST_VALID_TINT = "#00ff00";
  var GHOST_INVALID_TINT = "#ff0000";
  var SELECTION_HIGHLIGHT_COLOR = "#007fd4";
  var DELETE_BUTTON_BG = "rgba(200, 50, 50, 0.85)";
  var ROTATE_BUTTON_BG = "rgba(50, 120, 200, 0.85)";
  var BUTTON_ICON_COLOR = "#fff";
  var CANVAS_ERROR_TILE_COLOR = "#FF00FF";
  var WALL_COLOR = "#3A3A5C";
  var CARPET_DEFAULT_COLOR = { h: 0, s: 71, b: -32, c: 0, colorize: true };
  var CARPET_DEFAULT_ACCENT_COLOR = {
    h: 34,
    s: 64,
    b: 21,
    c: 0,
    colorize: true
  };
  var AREA_OVERLAY_ALPHA = 0.25;
  var AREA_ACTIVE_ALPHA_MULTIPLIER = 1.6;
  var AREA_LABEL_FONT_SIZE_PX = 14;
  var AREA_LABEL_MIN_FONT_SIZE_PX = 12;
  var AREA_LABEL_ALPHA = 1;
  var AREA_LABEL_FALLBACK_COLOR = "#ffffff";
  var AREA_LABEL_SHADOW_COLOR = "#000000";
  var AREA_LABEL_SHADOW_ALPHA = 0.6;
  var FURNITURE_ANIM_INTERVAL_SEC = 0.2;
  var MAX_DELTA_TIME_SEC = 0.1;
  var WAITING_BUBBLE_DURATION_SEC = 2;
  var DISMISS_BUBBLE_FAST_FADE_SEC = 0.3;
  var INACTIVE_SEAT_TIMER_MIN_SEC = 3;
  var INACTIVE_SEAT_TIMER_RANGE_SEC = 2;
  var PALETTE_COUNT = 6;
  var AUTO_ON_FACING_DEPTH = 3;
  var AUTO_ON_SIDE_DEPTH = 2;
  var CHARACTER_HIT_HALF_WIDTH = 8;
  var CHARACTER_HIT_HEIGHT = 24;
  var GREETER_ID = -1e9;
  var GREETER_TILE_MARGIN = 3;
  var DEFAULT_MAX_CONTEXT_TOKENS = 2e5;
  var PET_WALK_SPEED_PX_PER_SEC = 32;
  var PET_WALK_FRAME_DURATION_SEC = 0.15;
  var PET_IDLE_FRAME_DURATION_SEC = 0.3;
  var PET_WALK_SEQUENCE = [0, 1, 0, 2];
  var PET_IDLE_SEQUENCE = [0, 1, 2, 1];
  var PET_WANDER_PAUSE_MIN_SEC = 3;
  var PET_WANDER_PAUSE_MAX_SEC = 15;
  var PET_FOLLOW_RECALC_INTERVAL_SEC = 1;
  var PET_FOLLOW_CHANCE = 0.3;
  var PET_FOLLOW_RADIUS_TILES = 3;
  var PET_FOLLOW_DURATION_MIN_SEC = 5;
  var PET_FOLLOW_DURATION_MAX_SEC = 15;
  var PET_HIT_HALF_WIDTH = 8;
  var PET_HIT_HEIGHT = 16;
  var MAX_PET_ID_LENGTH = 128;

  // vendor/webview-ui/src/office/layout/furnitureCatalog.ts
  var rotationGroups = /* @__PURE__ */ new Map();
  var stateGroups = /* @__PURE__ */ new Map();
  var offToOn = /* @__PURE__ */ new Map();
  var onToOff = /* @__PURE__ */ new Map();
  var animationGroups = /* @__PURE__ */ new Map();
  var internalCatalog = null;
  var dynamicCatalog = null;
  var dynamicCategories = null;
  function buildDynamicCatalog(assets) {
    if (!assets?.catalog || !assets?.sprites) return false;
    const allEntries = assets.catalog.map((asset) => {
      const sprite = assets.sprites[asset.id];
      if (!sprite) {
        console.warn(`No sprite data for asset ${asset.id}`);
        return null;
      }
      return {
        type: asset.id,
        label: asset.label,
        footprintW: asset.footprintW,
        footprintH: asset.footprintH,
        sprite,
        isDesk: asset.isDesk,
        category: asset.category,
        ...asset.orientation ? { orientation: asset.orientation } : {},
        ...asset.canPlaceOnSurfaces ? { canPlaceOnSurfaces: true } : {},
        ...asset.backgroundTiles ? { backgroundTiles: asset.backgroundTiles } : {},
        ...asset.canPlaceOnWalls ? { canPlaceOnWalls: true } : {},
        ...asset.mirrorSide ? { mirrorSide: true } : {}
      };
    }).filter((e) => e !== null);
    for (const asset of assets.catalog) {
      if (asset.mirrorSide && asset.orientation === "side") {
        const sideEntry = allEntries.find((e) => e.type === asset.id);
        if (sideEntry) {
          allEntries.push({
            ...sideEntry,
            type: `${asset.id}:left`,
            orientation: "left",
            mirrorSide: true
          });
        }
      }
    }
    if (allEntries.length === 0) return false;
    rotationGroups.clear();
    stateGroups.clear();
    offToOn.clear();
    onToOff.clear();
    animationGroups.clear();
    const groupMap = /* @__PURE__ */ new Map();
    for (const asset of assets.catalog) {
      if (asset.groupId && asset.orientation) {
        if (asset.state && asset.state !== "off") continue;
        let orientMap = groupMap.get(asset.groupId);
        if (!orientMap) {
          orientMap = /* @__PURE__ */ new Map();
          groupMap.set(asset.groupId, orientMap);
        }
        if (asset.orientation === "side") {
          orientMap.set("right", asset.id);
          if (asset.mirrorSide) {
            orientMap.set("left", `${asset.id}:left`);
          }
        } else {
          orientMap.set(asset.orientation, asset.id);
        }
      }
    }
    const rotationSchemes = /* @__PURE__ */ new Map();
    for (const asset of assets.catalog) {
      if (asset.groupId && asset.rotationScheme) {
        rotationSchemes.set(asset.groupId, asset.rotationScheme);
      }
    }
    const nonFrontIds = /* @__PURE__ */ new Set();
    const orientationOrder = ["front", "right", "back", "left"];
    for (const [groupId, orientMap] of groupMap) {
      if (orientMap.size < 2) continue;
      const scheme = rotationSchemes.get(groupId);
      let allowedOrients = orientationOrder;
      if (scheme === "2-way") {
        allowedOrients = ["front", "right"];
      }
      const orderedOrients = allowedOrients.filter((o) => orientMap.has(o));
      if (orderedOrients.length < 2) continue;
      const members = {};
      for (const o of orderedOrients) {
        members[o] = orientMap.get(o);
      }
      const rg = { orientations: orderedOrients, members };
      const registeredIds = /* @__PURE__ */ new Set();
      for (const id of Object.values(members)) {
        if (!registeredIds.has(id)) {
          rotationGroups.set(id, rg);
          registeredIds.add(id);
        }
      }
      for (const [orient, id] of Object.entries(members)) {
        if (orient !== "front") nonFrontIds.add(id);
      }
    }
    const stateMap = /* @__PURE__ */ new Map();
    for (const asset of assets.catalog) {
      if (asset.groupId && asset.state) {
        const key = `${asset.groupId}|${asset.orientation || ""}`;
        let sm = stateMap.get(key);
        if (!sm) {
          sm = /* @__PURE__ */ new Map();
          stateMap.set(key, sm);
        }
        if (asset.animationGroup && asset.frame !== void 0 && asset.frame > 0) continue;
        sm.set(asset.state, asset.id);
      }
    }
    for (const sm of stateMap.values()) {
      const onId = sm.get("on");
      const offId = sm.get("off");
      if (onId && offId) {
        stateGroups.set(onId, offId);
        stateGroups.set(offId, onId);
        offToOn.set(offId, onId);
        onToOff.set(onId, offId);
      }
    }
    for (const asset of assets.catalog) {
      if (asset.groupId && asset.orientation && asset.state === "on") {
        if (asset.animationGroup && asset.frame !== void 0 && asset.frame > 0) continue;
        const offCounterpart = stateGroups.get(asset.id);
        if (offCounterpart) {
          const offGroup = rotationGroups.get(offCounterpart);
          if (offGroup) {
            const onMembers = {};
            for (const orient of offGroup.orientations) {
              const offId = offGroup.members[orient];
              const onId = stateGroups.get(offId);
              onMembers[orient] = onId ?? offId;
            }
            const onGroup = {
              orientations: offGroup.orientations,
              members: onMembers
            };
            for (const id of Object.values(onMembers)) {
              if (!rotationGroups.has(id)) {
                rotationGroups.set(id, onGroup);
              }
            }
          }
        }
      }
    }
    const animGroupCollector = /* @__PURE__ */ new Map();
    for (const asset of assets.catalog) {
      if (asset.animationGroup && asset.frame !== void 0) {
        let frames = animGroupCollector.get(asset.animationGroup);
        if (!frames) {
          frames = [];
          animGroupCollector.set(asset.animationGroup, frames);
        }
        frames.push({ id: asset.id, frame: asset.frame });
      }
    }
    for (const [groupId, frames] of animGroupCollector) {
      frames.sort((a, b) => a.frame - b.frame);
      animationGroups.set(
        groupId,
        frames.map((f) => f.id)
      );
    }
    const onStateIds = /* @__PURE__ */ new Set();
    for (const asset of assets.catalog) {
      if (asset.state === "on") onStateIds.add(asset.id);
    }
    internalCatalog = allEntries;
    const visibleEntries = allEntries.filter(
      (e) => !nonFrontIds.has(e.type) && !onStateIds.has(e.type)
    );
    for (const entry of visibleEntries) {
      if (rotationGroups.has(entry.type) || stateGroups.has(entry.type)) {
        entry.label = entry.label.replace(/ - Front - Off$/, "").replace(/ - Front$/, "").replace(/ - Off$/, "");
      }
    }
    dynamicCatalog = visibleEntries;
    dynamicCategories = Array.from(new Set(visibleEntries.map((e) => e.category))).filter((c) => !!c).sort();
    const rotGroupCount = new Set(Array.from(rotationGroups.values())).size;
    const animGroupCount = animationGroups.size;
    console.log(
      `\u2713 Built dynamic catalog with ${allEntries.length} assets (${visibleEntries.length} visible, ${rotGroupCount} rotation groups, ${stateGroups.size / 2} state pairs, ${animGroupCount} animation groups)`
    );
    return true;
  }
  function getCatalogEntry(type) {
    if (internalCatalog) {
      return internalCatalog.find((e) => e.type === type);
    }
    return dynamicCatalog?.find((e) => e.type === type);
  }
  function getOnStateType(currentType) {
    return offToOn.get(currentType) ?? currentType;
  }
  function getAnimationFrames(type) {
    for (const [, frames] of animationGroups) {
      if (frames.includes(type)) return frames;
    }
    return null;
  }
  function getOrientationInGroup(type) {
    const group = rotationGroups.get(type);
    if (!group) return void 0;
    for (const [orient, id] of Object.entries(group.members)) {
      if (id === type) return orient;
    }
    return void 0;
  }

  // vendor/webview-ui/src/office/engine/gameLoop.ts
  function startGameLoop(canvas, callbacks) {
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    let lastTime = 0;
    let rafId = 0;
    let stopped = false;
    const frame = (time) => {
      if (stopped) return;
      const dt = lastTime === 0 ? 0 : Math.min((time - lastTime) / 1e3, MAX_DELTA_TIME_SEC);
      lastTime = time;
      callbacks.update(dt);
      ctx.imageSmoothingEnabled = false;
      callbacks.render(ctx);
      rafId = requestAnimationFrame(frame);
    };
    rafId = requestAnimationFrame(frame);
    return () => {
      stopped = true;
      cancelAnimationFrame(rafId);
    };
  }

  // vendor/core/src/paletteUtils.ts
  var HUE_SHIFT_MIN_DEG = 45;
  var HUE_SHIFT_RANGE_DEG = 271;
  function pickDiversePalette(paletteCount, paletteCounts) {
    if (paletteCounts.length !== paletteCount) {
      throw new Error(
        `paletteCounts length (${paletteCounts.length}) must equal paletteCount (${paletteCount})`
      );
    }
    const minCount = Math.min(...paletteCounts);
    const available = [];
    for (let i = 0; i < paletteCount; i++) {
      if (paletteCounts[i] === minCount) available.push(i);
    }
    const palette = available[Math.floor(Math.random() * available.length)];
    let hueShift = 0;
    if (minCount > 0) {
      hueShift = HUE_SHIFT_MIN_DEG + Math.floor(Math.random() * HUE_SHIFT_RANGE_DEG);
    }
    return { palette, hueShift };
  }

  // vendor/webview-ui/src/office/colorize.ts
  var colorizeCache = /* @__PURE__ */ new Map();
  function getColorizedSprite(cacheKey, sprite, color) {
    const cached = colorizeCache.get(cacheKey);
    if (cached) return cached;
    const result = color.colorize ? colorizeSprite(sprite, color) : adjustSprite(sprite, color);
    colorizeCache.set(cacheKey, result);
    return result;
  }
  function clearColorizeCache() {
    colorizeCache.clear();
  }
  function colorizeSprite(sprite, color) {
    const { h, s, b, c } = color;
    const result = [];
    for (const row of sprite) {
      const newRow = [];
      for (const pixel of row) {
        if (pixel === "") {
          newRow.push("");
          continue;
        }
        const r = parseInt(pixel.slice(1, 3), 16);
        const g = parseInt(pixel.slice(3, 5), 16);
        const bv = parseInt(pixel.slice(5, 7), 16);
        let lightness = (0.299 * r + 0.587 * g + 0.114 * bv) / 255;
        if (c !== 0) {
          const factor = (100 + c) / 100;
          lightness = 0.5 + (lightness - 0.5) * factor;
        }
        if (b !== 0) {
          lightness = lightness + b / 200;
        }
        lightness = Math.max(0, Math.min(1, lightness));
        const alpha = extractAlpha(pixel);
        const satFrac = s / 100;
        const hex = hslToHex(h, satFrac, lightness);
        newRow.push(appendAlpha(hex, alpha));
      }
      result.push(newRow);
    }
    return result;
  }
  function extractAlpha(pixel) {
    return pixel.length > 7 ? parseInt(pixel.slice(7, 9), 16) : 255;
  }
  function appendAlpha(hex, alpha) {
    if (alpha >= 255) return hex;
    return `${hex}${alpha.toString(16).padStart(2, "0").toUpperCase()}`;
  }
  function hslToHex(h, s, l) {
    const c = (1 - Math.abs(2 * l - 1)) * s;
    const hp = h / 60;
    const x = c * (1 - Math.abs(hp % 2 - 1));
    let r1;
    let g1;
    let b1;
    if (hp < 1) {
      r1 = c;
      g1 = x;
      b1 = 0;
    } else if (hp < 2) {
      r1 = x;
      g1 = c;
      b1 = 0;
    } else if (hp < 3) {
      r1 = 0;
      g1 = c;
      b1 = x;
    } else if (hp < 4) {
      r1 = 0;
      g1 = x;
      b1 = c;
    } else if (hp < 5) {
      r1 = x;
      g1 = 0;
      b1 = c;
    } else {
      r1 = c;
      g1 = 0;
      b1 = x;
    }
    const m = l - c / 2;
    const r = Math.round((r1 + m) * 255);
    const g = Math.round((g1 + m) * 255);
    const bOut = Math.round((b1 + m) * 255);
    return `#${clamp255(r).toString(16).padStart(2, "0")}${clamp255(g).toString(16).padStart(2, "0")}${clamp255(bOut).toString(16).padStart(2, "0")}`.toUpperCase();
  }
  function clamp255(v) {
    return Math.max(0, Math.min(255, v));
  }
  function rgbToHsl(r, g, b) {
    const rf = r / 255, gf = g / 255, bf = b / 255;
    const max = Math.max(rf, gf, bf), min = Math.min(rf, gf, bf);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === rf) h = ((gf - bf) / d + (gf < bf ? 6 : 0)) * 60;
    else if (max === gf) h = ((bf - rf) / d + 2) * 60;
    else h = ((rf - gf) / d + 4) * 60;
    return [h, s, l];
  }
  function flatColorizeSprite(sprite, color) {
    const { h, s, b, c } = color;
    let lightness = 0.5;
    if (c !== 0) {
      lightness = 0.5 + (lightness - 0.5) * ((100 + c) / 100);
    }
    if (b !== 0) {
      lightness = lightness + b / 200;
    }
    lightness = Math.max(0, Math.min(1, lightness));
    const hex = hslToHex(h, s / 100, lightness);
    return sprite.map(
      (row) => row.map((pixel) => {
        if (pixel === "") return "";
        const alpha = extractAlpha(pixel);
        return appendAlpha(hex, alpha);
      })
    );
  }
  function adjustSprite(sprite, color) {
    const { h: hShift, s: sShift, b, c } = color;
    const result = [];
    for (const row of sprite) {
      const newRow = [];
      for (const pixel of row) {
        if (pixel === "") {
          newRow.push("");
          continue;
        }
        const r = parseInt(pixel.slice(1, 3), 16);
        const g = parseInt(pixel.slice(3, 5), 16);
        const bv = parseInt(pixel.slice(5, 7), 16);
        const alpha = extractAlpha(pixel);
        const [origH, origS, origL] = rgbToHsl(r, g, bv);
        const newH = ((origH + hShift) % 360 + 360) % 360;
        const newS = Math.max(0, Math.min(1, origS + sShift / 100));
        let lightness = origL;
        if (c !== 0) {
          const factor = (100 + c) / 100;
          lightness = 0.5 + (lightness - 0.5) * factor;
        }
        if (b !== 0) {
          lightness = lightness + b / 200;
        }
        lightness = Math.max(0, Math.min(1, lightness));
        const hex = hslToHex(newH, newS, lightness);
        newRow.push(appendAlpha(hex, alpha));
      }
      result.push(newRow);
    }
    return result;
  }

  // vendor/webview-ui/src/office/types.ts
  var TileType = {
    WALL: 0,
    FLOOR_1: 1,
    FLOOR_2: 2,
    FLOOR_3: 3,
    FLOOR_4: 4,
    FLOOR_5: 5,
    FLOOR_6: 6,
    FLOOR_7: 7,
    FLOOR_8: 8,
    FLOOR_9: 9,
    VOID: 255
  };
  var CharacterState = {
    IDLE: "idle",
    WALK: "walk",
    TYPE: "type"
  };
  var Direction = {
    DOWN: 0,
    LEFT: 1,
    RIGHT: 2,
    UP: 3
  };
  var PetState = { IDLE: "idle", WALK: "walk", FOLLOW: "follow" };

  // vendor/webview-ui/src/office/layout/layoutSerializer.ts
  function layoutToTileMap(layout) {
    const map = [];
    for (let r = 0; r < layout.rows; r++) {
      const row = [];
      for (let c = 0; c < layout.cols; c++) {
        row.push(layout.tiles[r * layout.cols + c]);
      }
      map.push(row);
    }
    return map;
  }
  function layoutToFurnitureInstances(furniture) {
    const deskZByTile = /* @__PURE__ */ new Map();
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry || !entry.isDesk) continue;
      const deskZY = item.row * TILE_SIZE + entry.sprite.length;
      for (let dr = 0; dr < entry.footprintH; dr++) {
        for (let dc = 0; dc < entry.footprintW; dc++) {
          const key = `${item.col + dc},${item.row + dr}`;
          const prev = deskZByTile.get(key);
          if (prev === void 0 || deskZY > prev) deskZByTile.set(key, deskZY);
        }
      }
    }
    const instances = [];
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry) continue;
      const x = item.col * TILE_SIZE;
      const y = item.row * TILE_SIZE;
      const spriteH = entry.sprite.length;
      let zY = y + spriteH;
      if (entry.category === "chairs") {
        if (entry.orientation === "back") {
          zY = (item.row + entry.footprintH) * TILE_SIZE + 1;
        } else {
          zY = (item.row + 1) * TILE_SIZE;
        }
      }
      if (entry.canPlaceOnSurfaces) {
        for (let dr = 0; dr < entry.footprintH; dr++) {
          for (let dc = 0; dc < entry.footprintW; dc++) {
            const deskZ = deskZByTile.get(`${item.col + dc},${item.row + dr}`);
            if (deskZ !== void 0 && deskZ + 0.5 > zY) zY = deskZ + 0.5;
          }
        }
      }
      let sprite = entry.sprite;
      if (item.color) {
        const { h, s, b: bv, c: cv } = item.color;
        sprite = getColorizedSprite(
          `furn-${item.type}-${h}-${s}-${bv}-${cv}-${item.color.colorize ? 1 : 0}`,
          entry.sprite,
          item.color
        );
      }
      let mirrored = false;
      if (entry.mirrorSide) {
        const orientInGroup = getOrientationInGroup(item.type);
        if (orientInGroup === "left") {
          mirrored = true;
        }
      }
      instances.push({ sprite, x, y, zY, ...mirrored ? { mirrored: true } : {} });
    }
    return instances;
  }
  function getBlockedTiles(furniture, excludeTiles) {
    const tiles = /* @__PURE__ */ new Set();
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry) continue;
      const bgRows = entry.backgroundTiles || 0;
      for (let dr = 0; dr < entry.footprintH; dr++) {
        if (dr < bgRows) continue;
        for (let dc = 0; dc < entry.footprintW; dc++) {
          const key = `${item.col + dc},${item.row + dr}`;
          if (excludeTiles && excludeTiles.has(key)) continue;
          tiles.add(key);
        }
      }
    }
    return tiles;
  }
  function orientationToFacing(orientation) {
    switch (orientation) {
      case "front":
        return Direction.DOWN;
      case "back":
        return Direction.UP;
      case "left":
        return Direction.LEFT;
      case "right":
      case "side":
        return Direction.RIGHT;
      default:
        return Direction.DOWN;
    }
  }
  function layoutToSeats(furniture) {
    const seats = /* @__PURE__ */ new Map();
    const deskTiles = /* @__PURE__ */ new Set();
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry || !entry.isDesk) continue;
      for (let dr = 0; dr < entry.footprintH; dr++) {
        for (let dc = 0; dc < entry.footprintW; dc++) {
          deskTiles.add(`${item.col + dc},${item.row + dr}`);
        }
      }
    }
    const dirs = [
      { dc: 0, dr: -1, facing: Direction.UP },
      // desk is above chair → face UP
      { dc: 0, dr: 1, facing: Direction.DOWN },
      // desk is below chair → face DOWN
      { dc: -1, dr: 0, facing: Direction.LEFT },
      // desk is left of chair → face LEFT
      { dc: 1, dr: 0, facing: Direction.RIGHT }
      // desk is right of chair → face RIGHT
    ];
    for (const item of furniture) {
      const entry = getCatalogEntry(item.type);
      if (!entry || entry.category !== "chairs") continue;
      let seatCount = 0;
      const bgRows = entry.backgroundTiles ?? 0;
      for (let dr = bgRows; dr < entry.footprintH; dr++) {
        for (let dc = 0; dc < entry.footprintW; dc++) {
          const tileCol = item.col + dc;
          const tileRow = item.row + dr;
          let facingDir = Direction.DOWN;
          if (entry.orientation) {
            facingDir = orientationToFacing(entry.orientation);
          } else {
            for (const d of dirs) {
              if (deskTiles.has(`${tileCol + d.dc},${tileRow + d.dr}`)) {
                facingDir = d.facing;
                break;
              }
            }
          }
          const seatUid = seatCount === 0 ? item.uid : `${item.uid}:${seatCount}`;
          seats.set(seatUid, {
            uid: seatUid,
            seatCol: tileCol,
            seatRow: tileRow,
            facingDir,
            assigned: false
          });
          seatCount++;
        }
      }
    }
    return seats;
  }
  var DEFAULT_LEFT_ROOM_COLOR = { h: 35, s: 30, b: 15, c: 0 };
  var DEFAULT_RIGHT_ROOM_COLOR = { h: 25, s: 45, b: 5, c: 10 };
  function createDefaultLayout() {
    const W = TileType.WALL;
    const F1 = TileType.FLOOR_1;
    const F2 = TileType.FLOOR_2;
    const tiles = [];
    const tileColors = [];
    for (let r = 0; r < DEFAULT_ROWS; r++) {
      for (let c = 0; c < DEFAULT_COLS; c++) {
        if (r === 0 || r === DEFAULT_ROWS - 1 || c === 0 || c === DEFAULT_COLS - 1) {
          tiles.push(W);
          tileColors.push(null);
        } else if (c < 10) {
          tiles.push(F1);
          tileColors.push(DEFAULT_LEFT_ROOM_COLOR);
        } else {
          tiles.push(F2);
          tileColors.push(DEFAULT_RIGHT_ROOM_COLOR);
        }
      }
    }
    return { version: 1, cols: DEFAULT_COLS, rows: DEFAULT_ROWS, tiles, tileColors, furniture: [] };
  }

  // vendor/webview-ui/src/office/layout/tileMap.ts
  function isWalkable(col, row, tileMap, blockedTiles) {
    const rows = tileMap.length;
    const cols = rows > 0 ? tileMap[0].length : 0;
    if (row < 0 || row >= rows || col < 0 || col >= cols) return false;
    const t = tileMap[row][col];
    if (t === TileType.WALL || t === TileType.VOID) return false;
    if (blockedTiles.has(`${col},${row}`)) return false;
    return true;
  }
  function getWalkableTiles(tileMap, blockedTiles) {
    const rows = tileMap.length;
    const cols = rows > 0 ? tileMap[0].length : 0;
    const tiles = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (isWalkable(c, r, tileMap, blockedTiles)) {
          tiles.push({ col: c, row: r });
        }
      }
    }
    return tiles;
  }
  function findPath(startCol, startRow, endCol, endRow, tileMap, blockedTiles) {
    if (startCol === endCol && startRow === endRow) return [];
    const key = (c, r) => `${c},${r}`;
    const startKey = key(startCol, startRow);
    const endKey = key(endCol, endRow);
    const endWalkable = isWalkable(endCol, endRow, tileMap, blockedTiles);
    if (!endWalkable) {
      return [];
    }
    const visited = /* @__PURE__ */ new Set();
    visited.add(startKey);
    const parent = /* @__PURE__ */ new Map();
    const queue = [{ col: startCol, row: startRow }];
    const dirs = [
      { dc: 0, dr: -1 },
      // up
      { dc: 0, dr: 1 },
      // down
      { dc: -1, dr: 0 },
      // left
      { dc: 1, dr: 0 }
      // right
    ];
    while (queue.length > 0) {
      const curr = queue.shift();
      const currKey = key(curr.col, curr.row);
      if (currKey === endKey) {
        const path = [];
        let k = endKey;
        while (k !== startKey) {
          const [c, r] = k.split(",").map(Number);
          path.unshift({ col: c, row: r });
          k = parent.get(k);
        }
        return path;
      }
      for (const d of dirs) {
        const nc = curr.col + d.dc;
        const nr = curr.row + d.dr;
        const nk = key(nc, nr);
        if (visited.has(nk)) continue;
        if (!isWalkable(nc, nr, tileMap, blockedTiles)) continue;
        visited.add(nk);
        parent.set(nk, currKey);
        queue.push({ col: nc, row: nr });
      }
    }
    return [];
  }

  // vendor/webview-ui/src/office/sprites/petSpriteData.ts
  var loadedPets = null;
  var loadedPetNames = [];
  function getPetSprites(petIndex) {
    if (!loadedPets) return null;
    if (petIndex < 0 || petIndex >= loadedPets.length) return null;
    return loadedPets[petIndex];
  }
  function getPetCount() {
    return loadedPets?.length ?? 0;
  }
  function getPetName(petIndex) {
    return loadedPetNames[petIndex] ?? `Pet ${petIndex + 1}`;
  }

  // vendor/webview-ui/src/office/sprites/bubble-permission.json
  var bubble_permission_default = {
    name: "bubble-permission",
    description: "Permission bubble: white square with '...' in amber, and a tail pointer (11x13)",
    width: 11,
    height: 13,
    palette: {
      _: "",
      B: "#555566",
      F: "#EEEEFF",
      A: "#CCA700"
    },
    pixels: [
      ["B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "A", "F", "A", "F", "A", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "B", "B", "B", "B", "B", "B", "B", "B", "B", "B"],
      ["_", "_", "_", "_", "B", "B", "B", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "B", "_", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "_", "_", "_", "_", "_", "_"]
    ]
  };

  // vendor/webview-ui/src/office/sprites/bubble-pet.json
  var bubble_pet_default = {
    name: "bubble-pet",
    description: "Heart bubble: shown when a pet is petted (11x13)",
    width: 11,
    height: 13,
    palette: {
      _: "",
      B: "#555566",
      F: "#EEEEFF",
      H: "#E64566"
    },
    pixels: [
      ["_", "B", "B", "B", "B", "B", "B", "B", "B", "B", "_"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "H", "H", "F", "H", "H", "F", "F", "B"],
      ["B", "F", "H", "H", "H", "H", "H", "H", "H", "F", "B"],
      ["B", "F", "H", "H", "H", "H", "H", "H", "H", "F", "B"],
      ["B", "F", "H", "H", "H", "H", "H", "H", "H", "F", "B"],
      ["B", "F", "F", "H", "H", "H", "H", "H", "F", "F", "B"],
      ["B", "F", "F", "F", "H", "H", "H", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "H", "F", "F", "F", "F", "B"],
      ["_", "B", "B", "B", "B", "B", "B", "B", "B", "B", "_"],
      ["_", "_", "_", "_", "B", "B", "B", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "B", "_", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "_", "_", "_", "_", "_", "_"]
    ]
  };

  // vendor/webview-ui/src/office/sprites/bubble-waiting.json
  var bubble_waiting_default = {
    name: "bubble-waiting",
    description: "Waiting bubble: white square with green checkmark, and a tail pointer (11x13)",
    width: 11,
    height: 13,
    palette: {
      _: "",
      B: "#555566",
      F: "#EEEEFF",
      G: "#44BB66"
    },
    pixels: [
      ["_", "B", "B", "B", "B", "B", "B", "B", "B", "B", "_"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "G", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "G", "F", "F", "B"],
      ["B", "F", "F", "G", "F", "F", "G", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "G", "G", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["B", "F", "F", "F", "F", "F", "F", "F", "F", "F", "B"],
      ["_", "B", "B", "B", "B", "B", "B", "B", "B", "B", "_"],
      ["_", "_", "_", "_", "B", "B", "B", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "B", "_", "_", "_", "_", "_"],
      ["_", "_", "_", "_", "_", "_", "_", "_", "_", "_", "_"]
    ]
  };

  // vendor/webview-ui/src/office/sprites/spriteData.ts
  function resolveBubbleSprite(data) {
    return data.pixels.map((row) => row.map((key) => data.palette[key] ?? key));
  }
  var BUBBLE_PERMISSION_SPRITE = resolveBubbleSprite(bubble_permission_default);
  var BUBBLE_WAITING_SPRITE = resolveBubbleSprite(bubble_waiting_default);
  var BUBBLE_HEART_SPRITE = resolveBubbleSprite(bubble_pet_default);
  var loadedCharacters = null;
  function setCharacterTemplates(data) {
    loadedCharacters = data;
    spriteCache.clear();
  }
  function getLoadedCharacterCount() {
    return loadedCharacters ? loadedCharacters.length : PALETTE_COUNT;
  }
  function flipSpriteHorizontal(sprite) {
    return sprite.map((row) => [...row].reverse());
  }
  var spriteCache = /* @__PURE__ */ new Map();
  function hueShiftSprites(sprites, hueShift) {
    const color = { h: hueShift, s: 0, b: 0, c: 0 };
    const shift = (s) => adjustSprite(s, color);
    const shiftWalk = (arr) => [
      shift(arr[0]),
      shift(arr[1]),
      shift(arr[2]),
      shift(arr[3])
    ];
    const shiftPair = (arr) => [
      shift(arr[0]),
      shift(arr[1])
    ];
    return {
      walk: {
        [Direction.DOWN]: shiftWalk(sprites.walk[Direction.DOWN]),
        [Direction.UP]: shiftWalk(sprites.walk[Direction.UP]),
        [Direction.RIGHT]: shiftWalk(sprites.walk[Direction.RIGHT]),
        [Direction.LEFT]: shiftWalk(sprites.walk[Direction.LEFT])
      },
      typing: {
        [Direction.DOWN]: shiftPair(sprites.typing[Direction.DOWN]),
        [Direction.UP]: shiftPair(sprites.typing[Direction.UP]),
        [Direction.RIGHT]: shiftPair(sprites.typing[Direction.RIGHT]),
        [Direction.LEFT]: shiftPair(sprites.typing[Direction.LEFT])
      },
      reading: {
        [Direction.DOWN]: shiftPair(sprites.reading[Direction.DOWN]),
        [Direction.UP]: shiftPair(sprites.reading[Direction.UP]),
        [Direction.RIGHT]: shiftPair(sprites.reading[Direction.RIGHT]),
        [Direction.LEFT]: shiftPair(sprites.reading[Direction.LEFT])
      }
    };
  }
  function emptySprite(w, h) {
    const rows = [];
    for (let y = 0; y < h; y++) {
      rows.push(new Array(w).fill(""));
    }
    return rows;
  }
  function getCharacterSprites(paletteIndex, hueShift = 0) {
    const cacheKey = `${paletteIndex}:${hueShift}`;
    const cached = spriteCache.get(cacheKey);
    if (cached) return cached;
    let sprites;
    if (loadedCharacters) {
      const char = loadedCharacters[paletteIndex % loadedCharacters.length];
      const d = char.down;
      const u = char.up;
      const rt = char.right;
      const flip = flipSpriteHorizontal;
      sprites = {
        walk: {
          [Direction.DOWN]: [d[0], d[1], d[2], d[1]],
          [Direction.UP]: [u[0], u[1], u[2], u[1]],
          [Direction.RIGHT]: [rt[0], rt[1], rt[2], rt[1]],
          [Direction.LEFT]: [flip(rt[0]), flip(rt[1]), flip(rt[2]), flip(rt[1])]
        },
        typing: {
          [Direction.DOWN]: [d[3], d[4]],
          [Direction.UP]: [u[3], u[4]],
          [Direction.RIGHT]: [rt[3], rt[4]],
          [Direction.LEFT]: [flip(rt[3]), flip(rt[4])]
        },
        reading: {
          [Direction.DOWN]: [d[5], d[6]],
          [Direction.UP]: [u[5], u[6]],
          [Direction.RIGHT]: [rt[5], rt[6]],
          [Direction.LEFT]: [flip(rt[5]), flip(rt[6])]
        }
      };
    } else {
      const e = emptySprite(16, 32);
      const walkSet = [e, e, e, e];
      const pairSet = [e, e];
      sprites = {
        walk: {
          [Direction.DOWN]: walkSet,
          [Direction.UP]: walkSet,
          [Direction.RIGHT]: walkSet,
          [Direction.LEFT]: walkSet
        },
        typing: {
          [Direction.DOWN]: pairSet,
          [Direction.UP]: pairSet,
          [Direction.RIGHT]: pairSet,
          [Direction.LEFT]: pairSet
        },
        reading: {
          [Direction.DOWN]: pairSet,
          [Direction.UP]: pairSet,
          [Direction.RIGHT]: pairSet,
          [Direction.LEFT]: pairSet
        }
      };
    }
    if (hueShift !== 0) {
      sprites = hueShiftSprites(sprites, hueShift);
    }
    spriteCache.set(cacheKey, sprites);
    return sprites;
  }

  // vendor/webview-ui/src/office/toolUtils.ts
  var providerCaps = {
    readingTools: /* @__PURE__ */ new Set(),
    subagentToolNames: /* @__PURE__ */ new Set()
  };
  function setProviderCapabilities(caps) {
    providerCaps.readingTools = new Set(caps.readingTools);
    providerCaps.subagentToolNames = new Set(caps.subagentToolNames);
  }
  function isReadingToolName(name) {
    return typeof name === "string" && providerCaps.readingTools.has(name);
  }

  // vendor/webview-ui/src/office/engine/characters.ts
  function isReadingTool(tool) {
    if (!tool) return false;
    return isReadingToolName(tool);
  }
  function tileCenter(col, row) {
    return {
      x: col * TILE_SIZE + TILE_SIZE / 2,
      y: row * TILE_SIZE + TILE_SIZE / 2
    };
  }
  function directionBetween(fromCol, fromRow, toCol, toRow) {
    const dc = toCol - fromCol;
    const dr = toRow - fromRow;
    if (dc > 0) return Direction.RIGHT;
    if (dc < 0) return Direction.LEFT;
    if (dr > 0) return Direction.DOWN;
    return Direction.UP;
  }
  function createCharacter(id, palette, seatId, seat, hueShift = 0) {
    const col = seat ? seat.seatCol : 1;
    const row = seat ? seat.seatRow : 1;
    const center = tileCenter(col, row);
    return {
      id,
      state: CharacterState.TYPE,
      dir: seat ? seat.facingDir : Direction.DOWN,
      x: center.x,
      y: center.y,
      tileCol: col,
      tileRow: row,
      path: [],
      moveProgress: 0,
      currentTool: null,
      palette,
      hueShift,
      frame: 0,
      frameTimer: 0,
      wanderTimer: 0,
      wanderCount: 0,
      wanderLimit: randomInt(WANDER_MOVES_BEFORE_REST_MIN, WANDER_MOVES_BEFORE_REST_MAX),
      isActive: true,
      seatId,
      bubbleType: null,
      bubbleTimer: 0,
      seatTimer: 0,
      isSubagent: false,
      parentAgentId: null,
      matrixEffect: null,
      matrixEffectTimer: 0,
      matrixEffectSeeds: [],
      contextTokens: 0,
      maxContextTokens: DEFAULT_MAX_CONTEXT_TOKENS
    };
  }
  function updateCharacter(ch, dt, walkableTiles, seats, tileMap, blockedTiles) {
    ch.frameTimer += dt;
    switch (ch.state) {
      case CharacterState.TYPE: {
        if (ch.frameTimer >= TYPE_FRAME_DURATION_SEC) {
          ch.frameTimer -= TYPE_FRAME_DURATION_SEC;
          ch.frame = (ch.frame + 1) % 2;
        }
        if (!ch.isActive) {
          if (ch.seatTimer > 0) {
            ch.seatTimer -= dt;
            break;
          }
          ch.seatTimer = 0;
          ch.state = CharacterState.IDLE;
          ch.frame = 0;
          ch.frameTimer = 0;
          ch.wanderTimer = randomRange(WANDER_PAUSE_MIN_SEC, WANDER_PAUSE_MAX_SEC);
          ch.wanderCount = 0;
          ch.wanderLimit = randomInt(WANDER_MOVES_BEFORE_REST_MIN, WANDER_MOVES_BEFORE_REST_MAX);
        }
        break;
      }
      case CharacterState.IDLE: {
        ch.frame = 0;
        if (ch.seatTimer < 0) ch.seatTimer = 0;
        if (ch.isActive) {
          if (!ch.seatId) {
            ch.state = CharacterState.TYPE;
            ch.frame = 0;
            ch.frameTimer = 0;
            break;
          }
          const seat = seats.get(ch.seatId);
          if (seat) {
            const path = findPath(
              ch.tileCol,
              ch.tileRow,
              seat.seatCol,
              seat.seatRow,
              tileMap,
              blockedTiles
            );
            if (path.length > 0) {
              ch.path = path;
              ch.moveProgress = 0;
              ch.state = CharacterState.WALK;
              ch.frame = 0;
              ch.frameTimer = 0;
            } else {
              ch.state = CharacterState.TYPE;
              ch.dir = seat.facingDir;
              ch.frame = 0;
              ch.frameTimer = 0;
            }
          }
          break;
        }
        ch.wanderTimer -= dt;
        if (ch.wanderTimer <= 0) {
          if (ch.wanderCount >= ch.wanderLimit && ch.seatId) {
            const seat = seats.get(ch.seatId);
            if (seat) {
              const path = findPath(
                ch.tileCol,
                ch.tileRow,
                seat.seatCol,
                seat.seatRow,
                tileMap,
                blockedTiles
              );
              if (path.length > 0) {
                ch.path = path;
                ch.moveProgress = 0;
                ch.state = CharacterState.WALK;
                ch.frame = 0;
                ch.frameTimer = 0;
                break;
              }
            }
          }
          if (walkableTiles.length > 0) {
            const target = walkableTiles[Math.floor(Math.random() * walkableTiles.length)];
            const path = findPath(
              ch.tileCol,
              ch.tileRow,
              target.col,
              target.row,
              tileMap,
              blockedTiles
            );
            if (path.length > 0) {
              ch.path = path;
              ch.moveProgress = 0;
              ch.state = CharacterState.WALK;
              ch.frame = 0;
              ch.frameTimer = 0;
              ch.wanderCount++;
            }
          }
          ch.wanderTimer = randomRange(WANDER_PAUSE_MIN_SEC, WANDER_PAUSE_MAX_SEC);
        }
        break;
      }
      case CharacterState.WALK: {
        if (ch.frameTimer >= WALK_FRAME_DURATION_SEC) {
          ch.frameTimer -= WALK_FRAME_DURATION_SEC;
          ch.frame = (ch.frame + 1) % 4;
        }
        if (ch.path.length === 0) {
          const center = tileCenter(ch.tileCol, ch.tileRow);
          ch.x = center.x;
          ch.y = center.y;
          if (ch.isActive) {
            if (!ch.seatId) {
              ch.state = CharacterState.TYPE;
            } else {
              const seat = seats.get(ch.seatId);
              if (seat && ch.tileCol === seat.seatCol && ch.tileRow === seat.seatRow) {
                ch.state = CharacterState.TYPE;
                ch.dir = seat.facingDir;
              } else {
                ch.state = CharacterState.IDLE;
              }
            }
          } else {
            if (ch.seatId) {
              const seat = seats.get(ch.seatId);
              if (seat && ch.tileCol === seat.seatCol && ch.tileRow === seat.seatRow) {
                ch.state = CharacterState.TYPE;
                ch.dir = seat.facingDir;
                if (ch.seatTimer < 0) {
                  ch.seatTimer = 0;
                } else {
                  ch.seatTimer = randomRange(SEAT_REST_MIN_SEC, SEAT_REST_MAX_SEC);
                }
                ch.wanderCount = 0;
                ch.wanderLimit = randomInt(
                  WANDER_MOVES_BEFORE_REST_MIN,
                  WANDER_MOVES_BEFORE_REST_MAX
                );
                ch.frame = 0;
                ch.frameTimer = 0;
                break;
              }
            }
            ch.state = CharacterState.IDLE;
            ch.wanderTimer = randomRange(WANDER_PAUSE_MIN_SEC, WANDER_PAUSE_MAX_SEC);
          }
          ch.frame = 0;
          ch.frameTimer = 0;
          break;
        }
        const nextTile = ch.path[0];
        ch.dir = directionBetween(ch.tileCol, ch.tileRow, nextTile.col, nextTile.row);
        ch.moveProgress += WALK_SPEED_PX_PER_SEC / TILE_SIZE * dt;
        const fromCenter = tileCenter(ch.tileCol, ch.tileRow);
        const toCenter = tileCenter(nextTile.col, nextTile.row);
        const t = Math.min(ch.moveProgress, 1);
        ch.x = fromCenter.x + (toCenter.x - fromCenter.x) * t;
        ch.y = fromCenter.y + (toCenter.y - fromCenter.y) * t;
        if (ch.moveProgress >= 1) {
          ch.tileCol = nextTile.col;
          ch.tileRow = nextTile.row;
          ch.x = toCenter.x;
          ch.y = toCenter.y;
          ch.path.shift();
          ch.moveProgress = 0;
        }
        if (ch.isActive && ch.seatId) {
          const seat = seats.get(ch.seatId);
          if (seat) {
            const lastStep = ch.path[ch.path.length - 1];
            if (!lastStep || lastStep.col !== seat.seatCol || lastStep.row !== seat.seatRow) {
              const newPath = findPath(
                ch.tileCol,
                ch.tileRow,
                seat.seatCol,
                seat.seatRow,
                tileMap,
                blockedTiles
              );
              if (newPath.length > 0) {
                ch.path = newPath;
                ch.moveProgress = 0;
              }
            }
          }
        }
        break;
      }
    }
  }
  function getCharacterSprite(ch, sprites) {
    switch (ch.state) {
      case CharacterState.TYPE:
        if (isReadingTool(ch.currentTool)) {
          return sprites.reading[ch.dir][ch.frame % 2];
        }
        return sprites.typing[ch.dir][ch.frame % 2];
      case CharacterState.WALK:
        return sprites.walk[ch.dir][ch.frame % 4];
      case CharacterState.IDLE:
        return sprites.walk[ch.dir][1];
      default:
        return sprites.walk[ch.dir][1];
    }
  }
  function randomRange(min, max) {
    return min + Math.random() * (max - min);
  }
  function randomInt(min, max) {
    return min + Math.floor(Math.random() * (max - min + 1));
  }

  // vendor/webview-ui/src/office/engine/matrixEffectState.ts
  function matrixEffectSeeds() {
    const seeds = [];
    for (let i = 0; i < MATRIX_SPRITE_COLS; i++) {
      seeds.push(Math.random());
    }
    return seeds;
  }
  function startMatrixEffect(ch, kind) {
    ch.matrixEffect = kind;
    ch.matrixEffectTimer = 0;
    ch.matrixEffectSeeds = matrixEffectSeeds();
  }
  function advanceMatrixEffect(ch, dt) {
    if (!ch.matrixEffect) return "none";
    ch.matrixEffectTimer += dt;
    if (ch.matrixEffectTimer < MATRIX_EFFECT_DURATION_SEC) return "running";
    if (ch.matrixEffect === "despawn") return "despawned";
    ch.matrixEffect = null;
    ch.matrixEffectTimer = 0;
    ch.matrixEffectSeeds = [];
    return "spawned";
  }

  // vendor/webview-ui/src/office/engine/petEntity.ts
  function randomRange2(min, max) {
    return min + Math.random() * (max - min);
  }
  function tileCenter2(col, row) {
    return {
      x: col * TILE_SIZE + TILE_SIZE / 2,
      y: row * TILE_SIZE + TILE_SIZE / 2
    };
  }
  function directionBetween2(fromCol, fromRow, toCol, toRow) {
    const dc = toCol - fromCol;
    const dr = toRow - fromRow;
    if (dc > 0) return Direction.RIGHT;
    if (dc < 0) return Direction.LEFT;
    if (dr > 0) return Direction.DOWN;
    return Direction.UP;
  }
  function manhattanDistance(c1, r1, c2, r2) {
    return Math.abs(c1 - c2) + Math.abs(r1 - r2);
  }
  function findNearbyCharacter(pet, characters) {
    let closest = null;
    let closestDist = Number.POSITIVE_INFINITY;
    for (const ch of characters.values()) {
      if (ch.matrixEffect === "despawn") continue;
      const d = manhattanDistance(pet.tileCol, pet.tileRow, ch.tileCol, ch.tileRow);
      if (d > PET_FOLLOW_RADIUS_TILES) continue;
      if (d < closestDist) {
        closest = ch;
        closestDist = d;
      }
    }
    return closest;
  }
  function findAdjacentTile(ch, tileMap, blockedTiles) {
    const candidates = [
      { col: ch.tileCol, row: ch.tileRow - 1 },
      { col: ch.tileCol, row: ch.tileRow + 1 },
      { col: ch.tileCol - 1, row: ch.tileRow },
      { col: ch.tileCol + 1, row: ch.tileRow }
    ];
    for (const t of candidates) {
      if (isWalkable(t.col, t.row, tileMap, blockedTiles)) return t;
    }
    return null;
  }
  function updateWalkAnimation(pet, dt) {
    pet.frameTimer += dt;
    if (pet.frameTimer >= PET_WALK_FRAME_DURATION_SEC) {
      pet.frameTimer -= PET_WALK_FRAME_DURATION_SEC;
      pet.frame = (pet.frame + 1) % 4;
    }
  }
  function updateIdleAnimation(pet, dt) {
    pet.frameTimer += dt;
    if (pet.frameTimer >= PET_IDLE_FRAME_DURATION_SEC) {
      pet.frameTimer -= PET_IDLE_FRAME_DURATION_SEC;
      pet.frame = (pet.frame + 1) % 4;
    }
  }
  function movePetAlongPath(pet, dt) {
    if (pet.path.length === 0) return;
    const nextTile = pet.path[0];
    pet.dir = directionBetween2(pet.tileCol, pet.tileRow, nextTile.col, nextTile.row);
    pet.moveProgress += PET_WALK_SPEED_PX_PER_SEC / TILE_SIZE * dt;
    const fromCenter = tileCenter2(pet.tileCol, pet.tileRow);
    const toCenter = tileCenter2(nextTile.col, nextTile.row);
    const t = Math.min(pet.moveProgress, 1);
    pet.x = fromCenter.x + (toCenter.x - fromCenter.x) * t;
    pet.y = fromCenter.y + (toCenter.y - fromCenter.y) * t;
    if (pet.moveProgress >= 1) {
      pet.tileCol = nextTile.col;
      pet.tileRow = nextTile.row;
      pet.x = toCenter.x;
      pet.y = toCenter.y;
      pet.path.shift();
      pet.moveProgress = 0;
    }
  }
  function createPet(id, petType, col, row) {
    const center = tileCenter2(col, row);
    return {
      id,
      name: "",
      // Filled by OfficeState.addPet() via getPetName(petType)
      petType,
      state: PetState.IDLE,
      dir: Direction.DOWN,
      x: center.x,
      y: center.y,
      tileCol: col,
      tileRow: row,
      path: [],
      moveProgress: 0,
      frame: 0,
      frameTimer: 0,
      wanderTimer: randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC),
      followTargetId: null,
      followRecalcTimer: 0,
      followDuration: 0,
      followDurationLimit: 0,
      bubbleType: null,
      bubbleTimer: 0
    };
  }
  function updatePet(pet, dt, walkableTiles, characters, tileMap, blockedTiles) {
    switch (pet.state) {
      case PetState.IDLE: {
        updateIdleAnimation(pet, dt);
        pet.wanderTimer -= dt;
        if (pet.wanderTimer > 0) break;
        if (Math.random() < PET_FOLLOW_CHANCE) {
          const target = findNearbyCharacter(pet, characters);
          if (target) {
            pet.state = PetState.FOLLOW;
            pet.followTargetId = target.id;
            pet.followDuration = 0;
            pet.followRecalcTimer = 0;
            pet.followDurationLimit = randomRange2(
              PET_FOLLOW_DURATION_MIN_SEC,
              PET_FOLLOW_DURATION_MAX_SEC
            );
            pet.frame = 0;
            pet.frameTimer = 0;
            break;
          }
        }
        if (walkableTiles.length > 0) {
          const candidates = walkableTiles.filter(
            (t) => t.col !== pet.tileCol || t.row !== pet.tileRow
          );
          if (candidates.length > 0) {
            const target = candidates[Math.floor(Math.random() * candidates.length)];
            const path = findPath(
              pet.tileCol,
              pet.tileRow,
              target.col,
              target.row,
              tileMap,
              blockedTiles
            );
            if (path.length > 0) {
              pet.state = PetState.WALK;
              pet.path = path;
              pet.moveProgress = 0;
              pet.frame = 0;
              pet.frameTimer = 0;
            }
          }
        }
        pet.wanderTimer = randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC);
        break;
      }
      case PetState.WALK: {
        updateWalkAnimation(pet, dt);
        movePetAlongPath(pet, dt);
        if (pet.path.length === 0 && pet.moveProgress === 0) {
          pet.state = PetState.IDLE;
          pet.wanderTimer = randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC);
          pet.frame = 0;
          pet.frameTimer = 0;
        }
        break;
      }
      case PetState.FOLLOW: {
        pet.followDuration += dt;
        const target = pet.followTargetId !== null ? characters.get(pet.followTargetId) : void 0;
        if (!target) {
          pet.state = PetState.IDLE;
          pet.followTargetId = null;
          pet.path = [];
          pet.moveProgress = 0;
          pet.frame = 0;
          pet.frameTimer = 0;
          pet.wanderTimer = randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC);
          break;
        }
        if (pet.followDuration >= pet.followDurationLimit) {
          pet.state = PetState.IDLE;
          pet.followTargetId = null;
          pet.path = [];
          pet.moveProgress = 0;
          pet.frame = 0;
          pet.frameTimer = 0;
          pet.wanderTimer = randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC);
          break;
        }
        const dist = manhattanDistance(pet.tileCol, pet.tileRow, target.tileCol, target.tileRow);
        if (dist <= 1) {
          if (dist === 1) {
            pet.dir = directionBetween2(pet.tileCol, pet.tileRow, target.tileCol, target.tileRow);
          }
          pet.state = PetState.IDLE;
          pet.followTargetId = null;
          pet.path = [];
          pet.moveProgress = 0;
          pet.frame = 0;
          pet.frameTimer = 0;
          pet.wanderTimer = randomRange2(PET_WANDER_PAUSE_MIN_SEC, PET_WANDER_PAUSE_MAX_SEC);
          break;
        }
        pet.followRecalcTimer -= dt;
        if (pet.followRecalcTimer <= 0) {
          const adj = findAdjacentTile(target, tileMap, blockedTiles);
          if (adj) {
            const path = findPath(pet.tileCol, pet.tileRow, adj.col, adj.row, tileMap, blockedTiles);
            if (path.length > 0) {
              pet.path = path;
              pet.moveProgress = 0;
            }
          }
          pet.followRecalcTimer = PET_FOLLOW_RECALC_INTERVAL_SEC;
        }
        updateWalkAnimation(pet, dt);
        movePetAlongPath(pet, dt);
        break;
      }
    }
  }
  function getPetSpriteData(pet, petSprites) {
    if (!petSprites) return null;
    if (pet.state === PetState.IDLE) {
      const frameIdx2 = PET_IDLE_SEQUENCE[pet.frame % PET_IDLE_SEQUENCE.length];
      switch (pet.dir) {
        case Direction.DOWN:
          return petSprites.idleDown[frameIdx2];
        case Direction.UP:
          return petSprites.idleUp[frameIdx2];
        case Direction.RIGHT:
          return petSprites.idleRight[frameIdx2];
        case Direction.LEFT:
          return petSprites.idleLeft[frameIdx2];
      }
    }
    const frameIdx = PET_WALK_SEQUENCE[pet.frame % PET_WALK_SEQUENCE.length];
    switch (pet.dir) {
      case Direction.DOWN:
        return petSprites.walkDown[frameIdx];
      case Direction.UP:
        return petSprites.walkUp[frameIdx];
      case Direction.RIGHT:
        return petSprites.walkRight[frameIdx];
      case Direction.LEFT:
        return petSprites.walkLeft[frameIdx];
    }
  }

  // vendor/webview-ui/src/office/engine/seatPlacement.ts
  function anchorTile(anchor, seats) {
    if (!anchor) return void 0;
    const seat = anchor.seatId ? seats.get(anchor.seatId) : void 0;
    return seat ? { col: seat.seatCol, row: seat.seatRow } : { col: anchor.tileCol, row: anchor.tileRow };
  }
  function closestFreeSeat(seats, col, row) {
    let best = null;
    let bestDist = Infinity;
    for (const [uid, seat] of seats) {
      if (seat.assigned) continue;
      const d = Math.abs(seat.seatCol - col) + Math.abs(seat.seatRow - row);
      if (d < bestDist) {
        best = uid;
        bestDist = d;
      }
    }
    return best;
  }

  // vendor/webview-ui/src/office/engine/officeState.ts
  function seatFacingOffset(direction) {
    if (direction === Direction.RIGHT) return { dCol: 1, dRow: 0 };
    if (direction === Direction.LEFT) return { dCol: -1, dRow: 0 };
    if (direction === Direction.DOWN) return { dCol: 0, dRow: 1 };
    return { dCol: 0, dRow: -1 };
  }
  var OfficeState = class {
    layout;
    tileMap;
    seats;
    blockedTiles;
    furniture;
    walkableTiles;
    characters = /* @__PURE__ */ new Map();
    pets = [];
    /** Accumulated time for furniture animation frame cycling */
    furnitureAnimTimer = 0;
    selectedAgentId = null;
    cameraFollowId = null;
    hoveredAgentId = null;
    hoveredTile = null;
    /** Maps "parentId:toolId" → sub-agent character ID (negative) */
    subagentIdMap = /* @__PURE__ */ new Map();
    /** Reverse lookup: sub-agent character ID → parent info */
    subagentMeta = /* @__PURE__ */ new Map();
    nextSubagentId = -1;
    /**
     * folderName → list of Area labels that workspace folder belongs to.
     * Populated by useExtensionMessages on `areaMappingsLoaded`. Consulted by
     * `findFreeSeat()` to bias new agents toward seats inside their folder's Area.
     */
    areaMappings = {};
    /**
     * The first-run consent greeter, deliberately NOT in `characters`.
     *
     * `characters` means "agents": everything that iterates it — seat
     * assignment, palette diversity, the wander FSM, hit-testing, the seat
     * payload the webview persists — is asking an agent question the greeter has
     * no answer to. Holding it here instead of tagging it with a flag makes
     * every one of those loops correct by default, rather than correct as long
     * as each remembers an `isGreeter` guard. It is drawn because
     * `getCharacters()` appends it, and that is the only place it joins the
     * others.
     */
    greeter = null;
    /** World-space point the camera drifts to while the greeter is up
     *  (the bubble overlay recomputes it every frame: the combined center of the
     *  character and its speech bubble). An explicit cameraFollowId outranks it. */
    greeterCameraTarget = null;
    /** Latched by a manual pan during the ask: the user took the camera, so the
     *  overlay's per-frame updates stop re-centering. Reset on spawn/despawn. */
    greeterCameraCancelled = false;
    setAreaMappings(mappings) {
      this.areaMappings = mappings;
    }
    constructor(layout) {
      this.layout = layout || createDefaultLayout();
      this.tileMap = layoutToTileMap(this.layout);
      this.seats = layoutToSeats(this.layout.furniture);
      this.blockedTiles = getBlockedTiles(this.layout.furniture);
      this.furniture = layoutToFurnitureInstances(this.layout.furniture);
      this.walkableTiles = getWalkableTiles(this.tileMap, this.blockedTiles);
      this.rebuildPetsFromLayout(this.layout);
    }
    /** Rebuild all derived state from a new layout. Reassigns existing characters.
     *  @param shift Optional pixel shift to apply when grid expands left/up */
    rebuildFromLayout(layout, shift) {
      this.layout = layout;
      this.tileMap = layoutToTileMap(layout);
      this.seats = layoutToSeats(layout.furniture);
      this.blockedTiles = getBlockedTiles(layout.furniture);
      this.rebuildFurnitureInstances();
      this.walkableTiles = getWalkableTiles(this.tileMap, this.blockedTiles);
      if (shift && (shift.col !== 0 || shift.row !== 0)) {
        for (const ch of this.characters.values()) {
          ch.tileCol += shift.col;
          ch.tileRow += shift.row;
          ch.x += shift.col * TILE_SIZE;
          ch.y += shift.row * TILE_SIZE;
          ch.path = [];
          ch.moveProgress = 0;
        }
      }
      if (shift && (shift.col !== 0 || shift.row !== 0)) {
        for (const pet of this.pets) {
          pet.tileCol += shift.col;
          pet.tileRow += shift.row;
          pet.x += shift.col * TILE_SIZE;
          pet.y += shift.row * TILE_SIZE;
          pet.path = [];
          pet.moveProgress = 0;
        }
      }
      for (const seat of this.seats.values()) {
        seat.assigned = false;
      }
      for (const ch of this.characters.values()) {
        if (ch.seatId && this.seats.has(ch.seatId)) {
          const seat = this.seats.get(ch.seatId);
          if (!seat.assigned) {
            seat.assigned = true;
            ch.tileCol = seat.seatCol;
            ch.tileRow = seat.seatRow;
            const cx = seat.seatCol * TILE_SIZE + TILE_SIZE / 2;
            const cy = seat.seatRow * TILE_SIZE + TILE_SIZE / 2;
            ch.x = cx;
            ch.y = cy;
            ch.dir = seat.facingDir;
            continue;
          }
        }
        ch.seatId = null;
      }
      for (const ch of this.characters.values()) {
        if (ch.seatId) continue;
        const seatId = this.findFreeSeat(ch.folderName);
        if (seatId) {
          this.seats.get(seatId).assigned = true;
          ch.seatId = seatId;
          const seat = this.seats.get(seatId);
          ch.tileCol = seat.seatCol;
          ch.tileRow = seat.seatRow;
          ch.x = seat.seatCol * TILE_SIZE + TILE_SIZE / 2;
          ch.y = seat.seatRow * TILE_SIZE + TILE_SIZE / 2;
          ch.dir = seat.facingDir;
        }
      }
      for (const ch of this.characters.values()) {
        if (ch.seatId) continue;
        if (ch.tileCol < 0 || ch.tileCol >= layout.cols || ch.tileRow < 0 || ch.tileRow >= layout.rows) {
          this.relocateCharacterToWalkable(ch);
        }
      }
      for (const pet of this.pets) {
        if (pet.tileCol < 0 || pet.tileCol >= layout.cols || pet.tileRow < 0 || pet.tileRow >= layout.rows || !isWalkable(pet.tileCol, pet.tileRow, this.tileMap, this.blockedTiles)) {
          if (this.walkableTiles.length > 0) {
            const spawn = this.walkableTiles[Math.floor(Math.random() * this.walkableTiles.length)];
            pet.tileCol = spawn.col;
            pet.tileRow = spawn.row;
            pet.x = spawn.col * TILE_SIZE + TILE_SIZE / 2;
            pet.y = spawn.row * TILE_SIZE + TILE_SIZE / 2;
            pet.path = [];
            pet.moveProgress = 0;
            pet.state = PetState.IDLE;
            pet.frame = 0;
            pet.frameTimer = 0;
            pet.followTargetId = null;
          }
        }
      }
      this.rebuildPetsFromLayout(layout);
    }
    /** Move a character to a random walkable tile */
    relocateCharacterToWalkable(ch) {
      if (this.walkableTiles.length === 0) return;
      const spawn = this.walkableTiles[Math.floor(Math.random() * this.walkableTiles.length)];
      ch.tileCol = spawn.col;
      ch.tileRow = spawn.row;
      ch.x = spawn.col * TILE_SIZE + TILE_SIZE / 2;
      ch.y = spawn.row * TILE_SIZE + TILE_SIZE / 2;
      ch.path = [];
      ch.moveProgress = 0;
    }
    getLayout() {
      return this.layout;
    }
    /** Get the blocked-tile key for a character's own seat, or null */
    ownSeatKey(ch) {
      if (!ch.seatId) return null;
      const seat = this.seats.get(ch.seatId);
      if (!seat) return null;
      return `${seat.seatCol},${seat.seatRow}`;
    }
    /** Temporarily unblock a character's own seat, run fn, then re-block */
    withOwnSeatUnblocked(ch, fn) {
      const key = this.ownSeatKey(ch);
      if (key) this.blockedTiles.delete(key);
      const result = fn();
      if (key) this.blockedTiles.add(key);
      return result;
    }
    /** Collect every tile occupied by electronics furniture (PCs, monitors, etc.). */
    buildElectronicsTileSet() {
      const out = /* @__PURE__ */ new Set();
      for (const item of this.layout.furniture) {
        const entry = getCatalogEntry(item.type);
        if (!entry || entry.category !== "electronics") continue;
        for (let dr = 0; dr < entry.footprintH; dr++) {
          for (let dc = 0; dc < entry.footprintW; dc++) {
            out.add(`${item.col + dc},${item.row + dr}`);
          }
        }
      }
      return out;
    }
    /** Find the area label assigned to a seat's tile, or null. Public for e2e
     *  observability (getAgentSeats hook reads a seated agent's area). */
    seatZone(uid) {
      const seat = this.seats.get(uid);
      if (!seat) return null;
      const tiles = this.layout.areaTiles;
      if (!tiles || tiles.length === 0) return null;
      const idx = seat.seatRow * this.layout.cols + seat.seatCol;
      if (idx < 0 || idx >= tiles.length) return null;
      return tiles[idx] ?? null;
    }
    /**
     * Does this seat face an electronics tile (PC, monitor)? Mirrors the
     * forward-and-flanking scan used by furniture auto-state.
     */
    isSeatFacingElectronics(seat, electronicsTiles) {
      const { dCol, dRow } = seatFacingOffset(seat.facingDir);
      for (let d = 1; d <= AUTO_ON_FACING_DEPTH; d++) {
        const tileCol = seat.seatCol + dCol * d;
        const tileRow = seat.seatRow + dRow * d;
        if (electronicsTiles.has(`${tileCol},${tileRow}`)) return true;
        if (dCol !== 0) {
          if (electronicsTiles.has(`${tileCol},${tileRow - 1}`) || electronicsTiles.has(`${tileCol},${tileRow + 1}`)) {
            return true;
          }
        } else if (electronicsTiles.has(`${tileCol - 1},${tileRow}`) || electronicsTiles.has(`${tileCol + 1},${tileRow}`)) {
          return true;
        }
      }
      return false;
    }
    /**
     * Random-pick a seat from a candidate list, biased toward seats that face an
     * electronics tile. Returns null when the candidate list is empty.
     */
    pickFromSeats(seatUids, electronicsTiles) {
      if (seatUids.length === 0) return null;
      const pcSeats = [];
      const otherSeats = [];
      for (const uid of seatUids) {
        const seat = this.seats.get(uid);
        if (!seat) continue;
        if (this.isSeatFacingElectronics(seat, electronicsTiles)) {
          pcSeats.push(uid);
        } else {
          otherSeats.push(uid);
        }
      }
      if (pcSeats.length > 0) return pcSeats[Math.floor(Math.random() * pcSeats.length)];
      if (otherSeats.length > 0) return otherSeats[Math.floor(Math.random() * otherSeats.length)];
      return null;
    }
    /**
     * 3-stage seat picker for top-level agents.
     *
     *   Stage 1: If `folderName` is given and `areaMappings[folderName]` lists
     *            Area labels, prefer free seats whose tile is labeled with one
     *            of those areas.
     *   Stage 2: Prefer free seats whose tile has NO area label (unzoned).
     *   Stage 3: Any free seat.
     *
     * Each stage routes through `pickFromSeats` for the PC-bias rule. Returns
     * null only when every seat is already occupied. Passing `undefined`
     * preserves pre-Areas single-stage behavior (skips Stage 1; Stage 2 picks
     * unzoned seats from a layout without `areaTiles`, which is every seat).
     */
    findFreeSeat(folderName) {
      const electronicsTiles = this.buildElectronicsTileSet();
      const freeSeats = [];
      for (const [uid, seat] of this.seats) {
        if (!seat.assigned) freeSeats.push(uid);
      }
      if (freeSeats.length === 0) return null;
      const areaLabels = folderName ? this.areaMappings[folderName] : void 0;
      if (areaLabels && areaLabels.length > 0) {
        const wanted = new Set(areaLabels);
        const inArea = freeSeats.filter((uid) => {
          const label = this.seatZone(uid);
          return label !== null && wanted.has(label);
        });
        const pick = this.pickFromSeats(inArea, electronicsTiles);
        if (pick) return pick;
      }
      const unzoned = freeSeats.filter((uid) => this.seatZone(uid) === null);
      const pick2 = this.pickFromSeats(unzoned, electronicsTiles);
      if (pick2) return pick2;
      return this.pickFromSeats(freeSeats, electronicsTiles);
    }
    /** Closest walkable tile to (col,row) not occupied by another character, or null. */
    closestFreeWalkableTile(col, row) {
      const occupied = /* @__PURE__ */ new Set();
      for (const ch of this.characters.values()) {
        occupied.add(`${ch.tileCol},${ch.tileRow}`);
      }
      let best = null;
      let bestDist = Infinity;
      for (const tile of this.walkableTiles) {
        if (occupied.has(`${tile.col},${tile.row}`)) continue;
        const d = Math.abs(tile.col - col) + Math.abs(tile.row - row);
        if (d < bestDist) {
          best = tile;
          bestDist = d;
        }
      }
      return best;
    }
    /**
     * Pick a diverse palette for a new agent based on currently active agents.
     * First 6 agents each get a unique skin (random order). Beyond 6, skins
     * repeat in balanced rounds with a random hue shift (≥45°).
     */
    pickDiversePalette() {
      const paletteCount = getLoadedCharacterCount();
      const counts = new Array(paletteCount).fill(0);
      for (const ch of this.characters.values()) {
        if (ch.isSubagent) continue;
        if (ch.palette < paletteCount) counts[ch.palette]++;
      }
      return pickDiversePalette(paletteCount, counts);
    }
    addAgent(id, preferredPalette, preferredHueShift, preferredSeatId, skipSpawnEffect, folderName, nearAgentId) {
      if (this.characters.has(id)) return;
      let palette;
      let hueShift;
      if (preferredPalette !== void 0) {
        palette = preferredPalette;
        hueShift = preferredHueShift ?? 0;
      } else {
        const pick = this.pickDiversePalette();
        palette = pick.palette;
        hueShift = pick.hueShift;
      }
      const anchor = nearAgentId !== void 0 ? this.characters.get(nearAgentId) : void 0;
      const anchorAt = anchorTile(anchor, this.seats);
      let seatId = null;
      if (preferredSeatId && this.seats.has(preferredSeatId)) {
        const seat = this.seats.get(preferredSeatId);
        if (!seat.assigned) {
          seatId = preferredSeatId;
        }
      }
      if (!seatId && anchorAt) {
        seatId = closestFreeSeat(this.seats, anchorAt.col, anchorAt.row);
      }
      if (!seatId) {
        seatId = this.findFreeSeat(folderName);
      }
      let ch;
      if (seatId) {
        const seat = this.seats.get(seatId);
        seat.assigned = true;
        ch = createCharacter(id, palette, seatId, seat, hueShift);
      } else {
        let spawn = anchorAt ? this.closestFreeWalkableTile(anchorAt.col, anchorAt.row) : null;
        if (!spawn) {
          spawn = this.walkableTiles.length > 0 ? this.walkableTiles[Math.floor(Math.random() * this.walkableTiles.length)] : { col: 1, row: 1 };
        }
        ch = createCharacter(id, palette, null, null, hueShift);
        ch.x = spawn.col * TILE_SIZE + TILE_SIZE / 2;
        ch.y = spawn.row * TILE_SIZE + TILE_SIZE / 2;
        ch.tileCol = spawn.col;
        ch.tileRow = spawn.row;
      }
      if (folderName) {
        ch.folderName = folderName;
      }
      if (!skipSpawnEffect) {
        startMatrixEffect(ch, "spawn");
      }
      this.characters.set(id, ch);
    }
    // ── Greeter ───────────────────────────────────────────────────
    // The Intro is diegetic: a char_0 character stands near the office's
    // bottom-left corner and "speaks" the tour through a DOM bubble
    // (IntroBubble). It is not an agent — see the `greeter` field.
    /** Spawn the greeter near the office's bottom-left corner: target tile
     *  GREETER_TILE_MARGIN in from the left and bottom edges, falling
     *  back to the closest walkable tile when the target is a seat, furniture,
     *  a wall, or VOID (seat tiles are in blockedTiles, so closestFreeWalkableTile
     *  covers every one of those). Idempotent; a remount mid-despawn (StrictMode)
     *  revives it. */
    spawnGreeter() {
      this.greeterCameraCancelled = false;
      if (this.greeter) {
        if (this.greeter.matrixEffect === "despawn") startMatrixEffect(this.greeter, "spawn");
        return;
      }
      const spawn = this.closestFreeWalkableTile(
        GREETER_TILE_MARGIN,
        this.layout.rows - 1 - GREETER_TILE_MARGIN
      );
      if (!spawn) return;
      const ch = createCharacter(GREETER_ID, 0, null, null, 0);
      ch.isGreeter = true;
      ch.state = CharacterState.IDLE;
      ch.isActive = false;
      ch.dir = Direction.DOWN;
      ch.x = spawn.col * TILE_SIZE + TILE_SIZE / 2;
      ch.y = spawn.row * TILE_SIZE + TILE_SIZE / 2;
      ch.tileCol = spawn.col;
      ch.tileRow = spawn.row;
      startMatrixEffect(ch, "spawn");
      this.greeter = ch;
    }
    /** Start the greeter's despawn effect and release the greeter camera. The
     *  character is dropped once the effect finishes (see update()).
     *  Idempotent — every close path (answer, Escape, hooksStatus) funnels here. */
    despawnGreeter() {
      this.greeterCameraTarget = null;
      this.greeterCameraCancelled = false;
      if (!this.greeter || this.greeter.matrixEffect === "despawn") return;
      startMatrixEffect(this.greeter, "despawn");
    }
    /** Per-frame update from the bubble overlay; ignored once the user panned. */
    setGreeterCameraTarget(p) {
      if (!this.greeterCameraCancelled) this.greeterCameraTarget = p;
    }
    /** Manual pan during the ask: stop re-centering until the next spawn. */
    cancelGreeterCamera() {
      this.greeterCameraTarget = null;
      this.greeterCameraCancelled = true;
    }
    removeAgent(id) {
      const ch = this.characters.get(id);
      if (!ch) return;
      if (ch.matrixEffect === "despawn") return;
      if (ch.seatId) {
        const seat = this.seats.get(ch.seatId);
        if (seat) seat.assigned = false;
      }
      if (this.selectedAgentId === id) this.selectedAgentId = null;
      if (this.cameraFollowId === id) this.cameraFollowId = null;
      startMatrixEffect(ch, "despawn");
      ch.bubbleType = null;
    }
    /** Find seat uid at a given tile position, or null */
    getSeatAtTile(col, row) {
      for (const [uid, seat] of this.seats) {
        if (seat.seatCol === col && seat.seatRow === row) return uid;
      }
      return null;
    }
    /** Reassign an agent from their current seat to a new seat */
    reassignSeat(agentId, seatId) {
      const ch = this.characters.get(agentId);
      if (!ch) return;
      if (ch.seatId) {
        const old = this.seats.get(ch.seatId);
        if (old) old.assigned = false;
      }
      const seat = this.seats.get(seatId);
      if (!seat || seat.assigned) return;
      seat.assigned = true;
      ch.seatId = seatId;
      const path = this.withOwnSeatUnblocked(
        ch,
        () => findPath(ch.tileCol, ch.tileRow, seat.seatCol, seat.seatRow, this.tileMap, this.blockedTiles)
      );
      if (path.length > 0) {
        ch.path = path;
        ch.moveProgress = 0;
        ch.state = CharacterState.WALK;
        ch.frame = 0;
        ch.frameTimer = 0;
      } else {
        ch.state = CharacterState.TYPE;
        ch.dir = seat.facingDir;
        ch.frame = 0;
        ch.frameTimer = 0;
        if (!ch.isActive) {
          ch.seatTimer = INACTIVE_SEAT_TIMER_MIN_SEC + Math.random() * INACTIVE_SEAT_TIMER_RANGE_SEC;
        }
      }
    }
    /**
     * Move a just-linked teammate to the free seat closest to its lead, so teams
     * cluster. Only moves when that seat is strictly closer than the teammate's
     * current one — a teammate created as a plain external agent (seated by an
     * arbitrary findFreeSeat) and tagged as a teammate only after tag discovery
     * would otherwise keep its arbitrary seat, unlike an inline teammate seated
     * next to the lead at creation.
     */
    reseatNextToLead(teammateId, leadId) {
      const teammate = this.characters.get(teammateId);
      const lead = this.characters.get(leadId);
      if (!teammate || !lead) return;
      const anchorAt = anchorTile(lead, this.seats);
      if (!anchorAt) return;
      const target = closestFreeSeat(this.seats, anchorAt.col, anchorAt.row);
      if (!target || target === teammate.seatId) return;
      const targetSeat = this.seats.get(target);
      const targetDist = Math.abs(targetSeat.seatCol - anchorAt.col) + Math.abs(targetSeat.seatRow - anchorAt.row);
      const currentSeat = teammate.seatId ? this.seats.get(teammate.seatId) : void 0;
      const currentDist = currentSeat ? Math.abs(currentSeat.seatCol - anchorAt.col) + Math.abs(currentSeat.seatRow - anchorAt.row) : Infinity;
      if (targetDist < currentDist) {
        this.reassignSeat(teammateId, target);
      }
    }
    /** Send an agent back to their currently assigned seat */
    sendToSeat(agentId) {
      const ch = this.characters.get(agentId);
      if (!ch || !ch.seatId) return;
      const seat = this.seats.get(ch.seatId);
      if (!seat) return;
      const path = this.withOwnSeatUnblocked(
        ch,
        () => findPath(ch.tileCol, ch.tileRow, seat.seatCol, seat.seatRow, this.tileMap, this.blockedTiles)
      );
      if (path.length > 0) {
        ch.path = path;
        ch.moveProgress = 0;
        ch.state = CharacterState.WALK;
        ch.frame = 0;
        ch.frameTimer = 0;
      } else {
        ch.state = CharacterState.TYPE;
        ch.dir = seat.facingDir;
        ch.frame = 0;
        ch.frameTimer = 0;
        if (!ch.isActive) {
          ch.seatTimer = INACTIVE_SEAT_TIMER_MIN_SEC + Math.random() * INACTIVE_SEAT_TIMER_RANGE_SEC;
        }
      }
    }
    /** Walk an agent to an arbitrary walkable tile (right-click command) */
    walkToTile(agentId, col, row) {
      const ch = this.characters.get(agentId);
      if (!ch || ch.isSubagent) return false;
      if (!isWalkable(col, row, this.tileMap, this.blockedTiles)) {
        const key = this.ownSeatKey(ch);
        if (!key || key !== `${col},${row}`) return false;
      }
      const path = this.withOwnSeatUnblocked(
        ch,
        () => findPath(ch.tileCol, ch.tileRow, col, row, this.tileMap, this.blockedTiles)
      );
      if (path.length === 0) return false;
      ch.path = path;
      ch.moveProgress = 0;
      ch.state = CharacterState.WALK;
      ch.frame = 0;
      ch.frameTimer = 0;
      return true;
    }
    /** Create a sub-agent character with the parent's palette. Returns the sub-agent ID. */
    addSubagent(parentAgentId, parentToolId) {
      const key = `${parentAgentId}:${parentToolId}`;
      if (this.subagentIdMap.has(key)) return this.subagentIdMap.get(key);
      const id = this.nextSubagentId--;
      const parentCh = this.characters.get(parentAgentId);
      const palette = parentCh ? parentCh.palette : 0;
      const hueShift = parentCh ? parentCh.hueShift : 0;
      const parentCol = parentCh ? parentCh.tileCol : 0;
      const parentRow = parentCh ? parentCh.tileRow : 0;
      let spawn = { col: parentCol, row: parentRow };
      if (this.walkableTiles.length > 0) {
        spawn = this.closestFreeWalkableTile(parentCol, parentRow) ?? this.walkableTiles[0];
      }
      const ch = createCharacter(id, palette, null, null, hueShift);
      ch.x = spawn.col * TILE_SIZE + TILE_SIZE / 2;
      ch.y = spawn.row * TILE_SIZE + TILE_SIZE / 2;
      ch.tileCol = spawn.col;
      ch.tileRow = spawn.row;
      if (parentCh) ch.dir = parentCh.dir;
      ch.isSubagent = true;
      ch.parentAgentId = parentAgentId;
      startMatrixEffect(ch, "spawn");
      this.characters.set(id, ch);
      this.subagentIdMap.set(key, id);
      this.subagentMeta.set(id, { parentAgentId, parentToolId });
      return id;
    }
    /** Remove a specific sub-agent character and free its seat */
    removeSubagent(parentAgentId, parentToolId) {
      const key = `${parentAgentId}:${parentToolId}`;
      const id = this.subagentIdMap.get(key);
      if (id === void 0) return;
      const ch = this.characters.get(id);
      if (ch) {
        if (ch.matrixEffect === "despawn") {
          this.subagentIdMap.delete(key);
          this.subagentMeta.delete(id);
          return;
        }
        if (ch.seatId) {
          const seat = this.seats.get(ch.seatId);
          if (seat) seat.assigned = false;
        }
        startMatrixEffect(ch, "despawn");
        ch.bubbleType = null;
      }
      this.subagentIdMap.delete(key);
      this.subagentMeta.delete(id);
      if (this.selectedAgentId === id) this.selectedAgentId = null;
      if (this.cameraFollowId === id) this.cameraFollowId = null;
    }
    /** Remove all sub-agents belonging to a parent agent */
    removeAllSubagents(parentAgentId) {
      const toRemove = [];
      for (const [key, id] of this.subagentIdMap) {
        const meta = this.subagentMeta.get(id);
        if (meta && meta.parentAgentId === parentAgentId) {
          const ch = this.characters.get(id);
          if (ch) {
            if (ch.matrixEffect === "despawn") {
              this.subagentMeta.delete(id);
              toRemove.push(key);
              continue;
            }
            if (ch.seatId) {
              const seat = this.seats.get(ch.seatId);
              if (seat) seat.assigned = false;
            }
            startMatrixEffect(ch, "despawn");
            ch.bubbleType = null;
          }
          this.subagentMeta.delete(id);
          if (this.selectedAgentId === id) this.selectedAgentId = null;
          if (this.cameraFollowId === id) this.cameraFollowId = null;
          toRemove.push(key);
        }
      }
      for (const key of toRemove) {
        this.subagentIdMap.delete(key);
      }
    }
    /** Look up the sub-agent character ID for a given parent+toolId, or null */
    getSubagentId(parentAgentId, parentToolId) {
      return this.subagentIdMap.get(`${parentAgentId}:${parentToolId}`) ?? null;
    }
    setAgentActive(id, active) {
      const ch = this.characters.get(id);
      if (ch) {
        ch.isActive = active;
        if (!active) {
          ch.seatTimer = -1;
          ch.path = [];
          ch.moveProgress = 0;
        }
        this.rebuildFurnitureInstances();
      }
    }
    /** Rebuild furniture instances with auto-state applied (active agents turn electronics ON) */
    rebuildFurnitureInstances() {
      const autoOnTiles = /* @__PURE__ */ new Set();
      for (const ch of this.characters.values()) {
        if (!ch.isActive || !ch.seatId) continue;
        const seat = this.seats.get(ch.seatId);
        if (!seat) continue;
        const dCol = seat.facingDir === Direction.RIGHT ? 1 : seat.facingDir === Direction.LEFT ? -1 : 0;
        const dRow = seat.facingDir === Direction.DOWN ? 1 : seat.facingDir === Direction.UP ? -1 : 0;
        for (let d = 1; d <= AUTO_ON_FACING_DEPTH; d++) {
          const tileCol = seat.seatCol + dCol * d;
          const tileRow = seat.seatRow + dRow * d;
          autoOnTiles.add(`${tileCol},${tileRow}`);
        }
        for (let d = 1; d <= AUTO_ON_SIDE_DEPTH; d++) {
          const baseCol = seat.seatCol + dCol * d;
          const baseRow = seat.seatRow + dRow * d;
          if (dCol !== 0) {
            autoOnTiles.add(`${baseCol},${baseRow - 1}`);
            autoOnTiles.add(`${baseCol},${baseRow + 1}`);
          } else {
            autoOnTiles.add(`${baseCol - 1},${baseRow}`);
            autoOnTiles.add(`${baseCol + 1},${baseRow}`);
          }
        }
      }
      if (autoOnTiles.size === 0) {
        this.furniture = layoutToFurnitureInstances(this.layout.furniture);
        return;
      }
      const animFrame = Math.floor(this.furnitureAnimTimer / FURNITURE_ANIM_INTERVAL_SEC);
      const modifiedFurniture = this.layout.furniture.map((item) => {
        const entry = getCatalogEntry(item.type);
        if (!entry) return item;
        for (let dr = 0; dr < entry.footprintH; dr++) {
          for (let dc = 0; dc < entry.footprintW; dc++) {
            if (autoOnTiles.has(`${item.col + dc},${item.row + dr}`)) {
              let onType = getOnStateType(item.type);
              if (onType !== item.type) {
                const frames = getAnimationFrames(onType);
                if (frames && frames.length > 1) {
                  const frameIdx = animFrame % frames.length;
                  onType = frames[frameIdx];
                }
                return { ...item, type: onType };
              }
              return item;
            }
          }
        }
        return item;
      });
      this.furniture = layoutToFurnitureInstances(modifiedFurniture);
    }
    setAgentTool(id, tool) {
      const ch = this.characters.get(id);
      if (ch) {
        ch.currentTool = tool;
      }
    }
    showPermissionBubble(id) {
      const ch = this.characters.get(id);
      if (ch) {
        ch.bubbleType = "permission";
        ch.bubbleTimer = 0;
      }
    }
    clearPermissionBubble(id) {
      const ch = this.characters.get(id);
      if (ch && ch.bubbleType === "permission") {
        ch.bubbleType = null;
        ch.bubbleTimer = 0;
      }
    }
    showWaitingBubble(id, awaitingInput = false) {
      const ch = this.characters.get(id);
      if (ch) {
        ch.bubbleType = "waiting";
        ch.waitingAwaitingInput = awaitingInput;
        ch.bubbleTimer = WAITING_BUBBLE_DURATION_SEC;
      }
    }
    /** Dismiss bubble on click — permission: instant, waiting: quick fade */
    dismissBubble(id) {
      const ch = this.characters.get(id);
      if (!ch || !ch.bubbleType) return;
      if (ch.bubbleType === "permission") {
        ch.bubbleType = null;
        ch.bubbleTimer = 0;
      } else if (ch.bubbleType === "waiting") {
        ch.bubbleTimer = Math.min(ch.bubbleTimer, DISMISS_BUBBLE_FAST_FADE_SEC);
      }
    }
    // ── Pets ──────────────────────────────────────────────────────
    /**
     * Add a pet to the live runtime. Spawns at a uniformly-random walkable tile.
     * Mirror in `this.layout.pets` so debounced saveLayout serialises the roster.
     * Bounds-checks petType against the loaded sprite count to defend against stale layouts.
     */
    addPet(placedPet) {
      if (typeof placedPet.id !== "string" || placedPet.id.length === 0 || placedPet.id.length > MAX_PET_ID_LENGTH) {
        return;
      }
      if (!Number.isInteger(placedPet.petType) || placedPet.petType < 0 || placedPet.petType >= getPetCount()) {
        return;
      }
      if (this.pets.some((p) => p.id === placedPet.id)) return;
      if (this.walkableTiles.length === 0) return;
      const spawn = this.walkableTiles[Math.floor(Math.random() * this.walkableTiles.length)];
      const pet = createPet(placedPet.id, placedPet.petType, spawn.col, spawn.row);
      pet.name = getPetName(placedPet.petType);
      this.pets.push(pet);
      this.syncLayoutPets();
    }
    /** Remove a pet by id. Idempotent. */
    removePet(id) {
      const before = this.pets.length;
      this.pets = this.pets.filter((p) => p.id !== id);
      if (this.pets.length !== before) {
        this.syncLayoutPets();
      }
    }
    /** Shallow snapshot for external consumers (renderer, hooks). */
    getPets() {
      return this.pets.slice();
    }
    /** Unique petType values currently placed. Used by the Pets toolbar to mark active rows. */
    getActivePetTypes() {
      const seen = /* @__PURE__ */ new Set();
      for (const p of this.pets) seen.add(p.petType);
      return Array.from(seen);
    }
    /**
     * Hit-test pets at a pixel world position. Sorts back-to-front (largest y wins on tie)
     * so the visually-frontmost pet receives the click.
     * Returns the pet id or null.
     */
    getPetAt(worldX, worldY) {
      const ordered = this.pets.slice().sort((a, b) => b.y - a.y);
      for (const pet of ordered) {
        const left = pet.x - PET_HIT_HALF_WIDTH;
        const right = pet.x + PET_HIT_HALF_WIDTH;
        const top = pet.y - PET_HIT_HEIGHT;
        const bottom = pet.y;
        if (worldX >= left && worldX <= right && worldY >= top && worldY <= bottom) {
          return pet.id;
        }
      }
      return null;
    }
    /** Show the heart bubble on a pet for WAITING_BUBBLE_DURATION_SEC. */
    showPetBubble(petId) {
      const pet = this.pets.find((p) => p.id === petId);
      if (!pet) return;
      pet.bubbleType = "heart";
      pet.bubbleTimer = WAITING_BUBBLE_DURATION_SEC;
    }
    /** Dismiss the heart bubble on click; collapses timer to a fast fade. */
    dismissPetBubble(petId) {
      const pet = this.pets.find((p) => p.id === petId);
      if (!pet || !pet.bubbleType) return;
      pet.bubbleTimer = Math.min(pet.bubbleTimer, DISMISS_BUBBLE_FAST_FADE_SEC);
    }
    /**
     * Reconcile `this.pets` to match the layout's placed-pet roster.
     * - Pets in layout but not in runtime → spawn via addPet().
     * - Pets in runtime but not in layout → remove.
     * - Pets in both → keep existing runtime state (position, FSM).
     *
     * Called from constructor and rebuildFromLayout. Always runs AFTER walkableTiles
     * is populated.
     */
    rebuildPetsFromLayout(layout) {
      const placed = layout.pets ?? [];
      const placedIds = new Set(placed.map((p) => p.id));
      this.pets = this.pets.filter((p) => placedIds.has(p.id));
      const existingIds = new Set(this.pets.map((p) => p.id));
      for (const p of placed) {
        if (existingIds.has(p.id)) continue;
        this.addPet(p);
      }
      this.syncLayoutPets();
    }
    /**
     * Re-export the current pet roster into `this.layout.pets`. Called only from
     * mutating methods (addPet / removePet / rebuildPetsFromLayout) — NEVER from
     * getLayout(), which runs on every render frame.
     */
    syncLayoutPets() {
      this.layout.pets = this.pets.map((p) => ({ id: p.id, petType: p.petType }));
    }
    setTeamInfo(id, teamName, agentName, isTeamLead, leadAgentId, teamUsesTmux) {
      const ch = this.characters.get(id);
      if (!ch) return;
      const wasUnlinked = ch.leadAgentId === void 0;
      ch.teamName = teamName;
      ch.agentName = agentName;
      ch.isTeamLead = isTeamLead;
      ch.leadAgentId = leadAgentId;
      if (teamUsesTmux !== void 0) {
        ch.teamUsesTmux = teamUsesTmux;
      }
      if (leadAgentId !== void 0) {
        ch.isHeadless = false;
      }
      if (wasUnlinked && leadAgentId !== void 0 && !isTeamLead) {
        this.reseatNextToLead(id, leadAgentId);
      }
    }
    /** Mark an agent as headless (adopted, no terminal to focus). */
    setHeadless(id, headless) {
      const ch = this.characters.get(id);
      if (!ch) return;
      ch.isHeadless = headless;
    }
    setAgentContext(id, contextTokens, maxContextTokens) {
      const ch = this.characters.get(id);
      if (!ch) return;
      ch.contextTokens = contextTokens;
      ch.maxContextTokens = maxContextTokens;
    }
    update(dt) {
      const prevFrame = Math.floor(this.furnitureAnimTimer / FURNITURE_ANIM_INTERVAL_SEC);
      this.furnitureAnimTimer += dt;
      const newFrame = Math.floor(this.furnitureAnimTimer / FURNITURE_ANIM_INTERVAL_SEC);
      if (newFrame !== prevFrame) {
        this.rebuildFurnitureInstances();
      }
      if (this.greeter && advanceMatrixEffect(this.greeter, dt) === "despawned") {
        this.greeter = null;
      }
      const toDelete = [];
      for (const ch of this.characters.values()) {
        const effect = advanceMatrixEffect(ch, dt);
        if (effect !== "none") {
          if (effect === "despawned") toDelete.push(ch.id);
          continue;
        }
        this.withOwnSeatUnblocked(
          ch,
          () => updateCharacter(ch, dt, this.walkableTiles, this.seats, this.tileMap, this.blockedTiles)
        );
        if (ch.bubbleType === "waiting") {
          ch.bubbleTimer -= dt;
          if (ch.bubbleTimer <= 0) {
            ch.bubbleType = null;
            ch.bubbleTimer = 0;
          }
        }
      }
      for (const id of toDelete) {
        this.characters.delete(id);
      }
      for (const pet of this.pets) {
        updatePet(pet, dt, this.walkableTiles, this.characters, this.tileMap, this.blockedTiles);
        if (pet.bubbleType) {
          pet.bubbleTimer -= dt;
          if (pet.bubbleTimer <= 0) {
            pet.bubbleType = null;
            pet.bubbleTimer = 0;
          }
        }
      }
    }
    /** The `saveAgentSeats` payload: palette, hue and seat for every agent worth
     *  restoring. Sub-agents are excluded because they are derived state the
     *  runtime re-materializes, and the greeter never reaches here at all —
     *  it is not in `characters`. */
    getPersistableSeats() {
      const seats = {};
      for (const ch of this.characters.values()) {
        if (ch.isSubagent) continue;
        seats[ch.id] = { palette: ch.palette, hueShift: ch.hueShift, seatId: ch.seatId };
      }
      return seats;
    }
    /** Everything the renderer draws: the agents plus, while the first-run ask
     *  is up, the consent greeter. This is the ONE place the greeter joins the
     *  agents — every other consumer reads `characters` and gets agents only. */
    getCharacters() {
      const chars = Array.from(this.characters.values());
      if (this.greeter) chars.push(this.greeter);
      return chars;
    }
    /** Get character at pixel position (for hit testing). Returns id or null.
     *  Agents only: clicks pass straight through the consent greeter, which is
     *  a prop, not something to select or follow. */
    getCharacterAt(worldX, worldY) {
      const chars = Array.from(this.characters.values()).sort((a, b) => b.y - a.y);
      for (const ch of chars) {
        if (ch.matrixEffect === "despawn") continue;
        const sittingOffset = ch.state === CharacterState.TYPE ? CHARACTER_SITTING_OFFSET_PX : 0;
        const anchorY = ch.y + sittingOffset;
        const left = ch.x - CHARACTER_HIT_HALF_WIDTH;
        const right = ch.x + CHARACTER_HIT_HALF_WIDTH;
        const top = anchorY - CHARACTER_HIT_HEIGHT;
        const bottom = anchorY;
        if (worldX >= left && worldX <= right && worldY >= top && worldY <= bottom) {
          return ch.id;
        }
      }
      return null;
    }
  };

  // vendor/webview-ui/src/office/floorTiles.ts
  var DEFAULT_FLOOR_SPRITE = Array.from(
    { length: TILE_SIZE },
    () => Array(TILE_SIZE).fill(FALLBACK_FLOOR_COLOR)
  );
  var floorSprites = [];
  function setFloorSprites(sprites) {
    floorSprites = sprites;
    clearColorizeCache();
  }
  function getFloorSprite(patternIndex) {
    const idx = patternIndex - 1;
    if (idx < 0) return null;
    if (idx < floorSprites.length) return floorSprites[idx];
    if (floorSprites.length === 0 && patternIndex >= 1) return DEFAULT_FLOOR_SPRITE;
    return null;
  }
  function hasFloorSprites() {
    return true;
  }
  function getColorizedFloorSprite(patternIndex, color) {
    const key = `floor-${patternIndex}-${color.h}-${color.s}-${color.b}-${color.c}`;
    const base = getFloorSprite(patternIndex);
    if (!base) {
      const err = Array.from(
        { length: 16 },
        () => Array(16).fill(CANVAS_ERROR_TILE_COLOR)
      );
      return err;
    }
    return getColorizedSprite(key, base, { ...color, colorize: true });
  }

  // vendor/webview-ui/src/office/projection.ts
  function mapOffset(canvasWidth, canvasHeight, cols, rows, zoom, panX, panY) {
    const mapW = cols * TILE_SIZE * zoom;
    const mapH = rows * TILE_SIZE * zoom;
    return {
      offsetX: Math.floor((canvasWidth - mapW) / 2) + Math.round(panX),
      offsetY: Math.floor((canvasHeight - mapH) / 2) + Math.round(panY)
    };
  }
  function overlayProjection(layout, containerRect, zoom, pan, dpr) {
    const canvasW = Math.round(containerRect.width * dpr);
    const canvasH = Math.round(containerRect.height * dpr);
    const { offsetX, offsetY } = mapOffset(
      canvasW,
      canvasH,
      layout.cols,
      layout.rows,
      zoom,
      pan.x,
      pan.y
    );
    return {
      toScreenX: (worldX) => (offsetX + worldX * zoom) / dpr,
      toScreenY: (worldY) => (offsetY + worldY * zoom) / dpr,
      viewportWorldWidth: canvasW / zoom,
      viewportWorldHeight: canvasH / zoom,
      toWorldLength: (cssPx) => cssPx * dpr / zoom
    };
  }

  // vendor/webview-ui/src/office/sprites/carpetTiles.ts
  var carpetSets = [];
  var carpetVariantPalettes = [];
  var carpetCache = /* @__PURE__ */ new Map();
  function setCarpetSprites(sets) {
    carpetSets = sets;
    carpetCache.clear();
    carpetVariantPalettes = sets.map((variantSprites) => classifyCarpetPalette(variantSprites));
  }
  function hasCarpetSprites() {
    return carpetSets.length > 0;
  }
  function getCarpetColorKey(color) {
    return `${color.h}|${color.s}|${color.b}|${color.c}|${color.colorize ? 1 : 0}`;
  }
  function getCarpetPaletteKey(color, accentColor) {
    return `${getCarpetColorKey(color)}#${getCarpetColorKey(accentColor)}`;
  }
  function getCarpetJunctionSprite(jx, jy, variant, carpetTiles, cols, rows, color = CARPET_DEFAULT_COLOR, accentColor = CARPET_DEFAULT_ACCENT_COLOR, paletteKey = getCarpetPaletteKey(color, accentColor)) {
    if (variant < 0 || variant >= carpetSets.length) return null;
    const msCase = carpetJunctionCase(jx, jy, variant, carpetTiles, cols, rows, paletteKey);
    if (msCase === 0) return null;
    const variantSet = carpetSets[variant];
    const baseSprite = variantSet?.[msCase];
    if (!baseSprite) return null;
    const palette = carpetVariantPalettes[variant];
    if (!palette || !palette.mainRgb) return null;
    const cacheKey = `${variant}:${msCase}:${paletteKey}`;
    return getDualColorizedCarpetSprite(cacheKey, baseSprite, palette, color, accentColor);
  }
  function carpetJunctionCase(jx, jy, variant, carpetTiles, cols, rows, paletteKey) {
    let msCase = 0;
    if (tileHasVariant(jx - 1, jy - 1, variant, carpetTiles, cols, rows, paletteKey)) msCase |= 1;
    if (tileHasVariant(jx, jy - 1, variant, carpetTiles, cols, rows, paletteKey)) msCase |= 2;
    if (tileHasVariant(jx, jy, variant, carpetTiles, cols, rows, paletteKey)) msCase |= 4;
    if (tileHasVariant(jx - 1, jy, variant, carpetTiles, cols, rows, paletteKey)) msCase |= 8;
    return msCase;
  }
  function tileHasVariant(col, row, variant, carpetTiles, cols, rows, paletteKey) {
    if (col < 0 || row < 0 || col >= cols || row >= rows) return false;
    const tile = carpetTiles[row * cols + col];
    if (!tile || tile.variant !== variant) return false;
    if (paletteKey !== void 0) {
      const tileColor = tile.color ?? CARPET_DEFAULT_COLOR;
      const tileAccent = tile.accentColor ?? CARPET_DEFAULT_ACCENT_COLOR;
      if (getCarpetPaletteKey(tileColor, tileAccent) !== paletteKey) return false;
    }
    return true;
  }
  function classifyCarpetPalette(variantSprites) {
    const unique = /* @__PURE__ */ new Set();
    for (const sprite of variantSprites) {
      if (!sprite) continue;
      for (const row of sprite) {
        for (const pixel of row) {
          if (pixel === "") continue;
          const rgb = pixel.length === 9 ? pixel.slice(0, 7) : pixel;
          unique.add(rgb);
        }
      }
    }
    if (unique.size === 0) {
      return { mainRgb: null, accentRgb: null };
    }
    const sorted = [...unique].sort((a, b) => luminanceFromRgb(a) - luminanceFromRgb(b));
    if (sorted.length === 1) {
      return { mainRgb: sorted[0], accentRgb: sorted[0] };
    }
    return {
      mainRgb: sorted[0],
      accentRgb: sorted[sorted.length - 1]
    };
  }
  function luminanceFromRgb(rgb) {
    const r = parseInt(rgb.slice(1, 3), 16);
    const g = parseInt(rgb.slice(3, 5), 16);
    const b = parseInt(rgb.slice(5, 7), 16);
    return 0.299 * r + 0.587 * g + 0.114 * b;
  }
  function getDualColorizedCarpetSprite(cacheKey, baseSprite, palette, color, accentColor) {
    const cached = carpetCache.get(cacheKey);
    if (cached) return cached;
    if (!palette.mainRgb) return null;
    const accentRgb = palette.accentRgb ?? palette.mainRgb;
    const mainMask = maskCarpetSprite(baseSprite, palette.mainRgb);
    const accentMask = maskCarpetSprite(baseSprite, accentRgb);
    const mainLayer = flatColorizeSprite(mainMask, color);
    const accentLayer = flatColorizeSprite(accentMask, accentColor);
    const merged = mergeCarpetLayers(mainLayer, accentLayer);
    carpetCache.set(cacheKey, merged);
    return merged;
  }
  function maskCarpetSprite(sprite, rgb) {
    return sprite.map(
      (row) => row.map((pixel) => {
        if (pixel === "") return "";
        const pixelRgb = pixel.length === 9 ? pixel.slice(0, 7) : pixel;
        return pixelRgb === rgb ? pixel : "";
      })
    );
  }
  function mergeCarpetLayers(base, accent) {
    const rows = base.length;
    const result = new Array(rows);
    for (let r = 0; r < rows; r++) {
      const baseRow = base[r];
      const accentRow = accent[r];
      const cols = baseRow.length;
      const out = new Array(cols);
      for (let c = 0; c < cols; c++) {
        const accentPixel = accentRow[c];
        out[c] = accentPixel !== "" ? accentPixel : baseRow[c];
      }
      result[r] = out;
    }
    return result;
  }

  // vendor/webview-ui/src/office/sprites/spriteCache.ts
  var zoomCaches = /* @__PURE__ */ new Map();
  var outlineCache = /* @__PURE__ */ new WeakMap();
  function getOutlineSprite(sprite) {
    const cached = outlineCache.get(sprite);
    if (cached) return cached;
    const rows = sprite.length;
    const cols = sprite[0].length;
    const outline = [];
    for (let r = 0; r < rows + 2; r++) {
      outline.push(new Array(cols + 2).fill(""));
    }
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (sprite[r][c] === "") continue;
        const er = r + 1;
        const ec = c + 1;
        if (outline[er - 1][ec] === "") outline[er - 1][ec] = "#FFFFFF";
        if (outline[er + 1][ec] === "") outline[er + 1][ec] = "#FFFFFF";
        if (outline[er][ec - 1] === "") outline[er][ec - 1] = "#FFFFFF";
        if (outline[er][ec + 1] === "") outline[er][ec + 1] = "#FFFFFF";
      }
    }
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (sprite[r][c] !== "") {
          outline[r + 1][c + 1] = "";
        }
      }
    }
    outlineCache.set(sprite, outline);
    return outline;
  }
  function getCachedSprite(sprite, zoom) {
    let cache = zoomCaches.get(zoom);
    if (!cache) {
      cache = /* @__PURE__ */ new WeakMap();
      zoomCaches.set(zoom, cache);
    }
    const cached = cache.get(sprite);
    if (cached) return cached;
    const rows = sprite.length;
    const cols = sprite[0].length;
    const canvas = document.createElement("canvas");
    canvas.width = cols * zoom;
    canvas.height = rows * zoom;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const color = sprite[r][c];
        if (color === "") continue;
        ctx.fillStyle = color;
        ctx.fillRect(c * zoom, r * zoom, zoom, zoom);
      }
    }
    cache.set(sprite, canvas);
    return canvas;
  }

  // vendor/webview-ui/src/office/wallTiles.ts
  var wallSets = [];
  function setWallSprites(sets) {
    wallSets = sets;
  }
  function hasWallSprites() {
    return wallSets.length > 0;
  }
  function buildWallMask(col, row, tileMap) {
    const tmRows = tileMap.length;
    const tmCols = tmRows > 0 ? tileMap[0].length : 0;
    let mask = 0;
    if (row > 0 && tileMap[row - 1][col] === TileType.WALL) mask |= 1;
    if (col < tmCols - 1 && tileMap[row][col + 1] === TileType.WALL) mask |= 2;
    if (row < tmRows - 1 && tileMap[row + 1][col] === TileType.WALL) mask |= 4;
    if (col > 0 && tileMap[row][col - 1] === TileType.WALL) mask |= 8;
    return mask;
  }
  function getWallSprite(col, row, tileMap, setIndex = 0) {
    if (wallSets.length === 0) return null;
    const sprites = wallSets[setIndex] ?? wallSets[0];
    const mask = buildWallMask(col, row, tileMap);
    const sprite = sprites[mask];
    if (!sprite) return null;
    return { sprite, offsetY: TILE_SIZE - sprite.length };
  }
  function getColorizedWallSprite(col, row, tileMap, color, setIndex = 0) {
    if (wallSets.length === 0) return null;
    const sprites = wallSets[setIndex] ?? wallSets[0];
    const mask = buildWallMask(col, row, tileMap);
    const sprite = sprites[mask];
    if (!sprite) return null;
    const cacheKey = `wall-${setIndex}-${mask}-${color.h}-${color.s}-${color.b}-${color.c}`;
    const colorized = getColorizedSprite(cacheKey, sprite, { ...color, colorize: true });
    return { sprite: colorized, offsetY: TILE_SIZE - sprite.length };
  }
  function getWallInstances(tileMap, tileColors, cols) {
    if (wallSets.length === 0) return [];
    const tmRows = tileMap.length;
    const tmCols = tmRows > 0 ? tileMap[0].length : 0;
    const layoutCols = cols ?? tmCols;
    const instances = [];
    for (let r = 0; r < tmRows; r++) {
      for (let c = 0; c < tmCols; c++) {
        if (tileMap[r][c] !== TileType.WALL) continue;
        const colorIdx = r * layoutCols + c;
        const wallColor = tileColors?.[colorIdx];
        const wallInfo = wallColor ? getColorizedWallSprite(c, r, tileMap, wallColor) : getWallSprite(c, r, tileMap);
        if (!wallInfo) continue;
        instances.push({
          sprite: wallInfo.sprite,
          x: c * TILE_SIZE,
          y: r * TILE_SIZE + wallInfo.offsetY,
          zY: (r + 1) * TILE_SIZE
        });
      }
    }
    return instances;
  }
  function wallColorToHex(color) {
    const { h, s, b, c } = color;
    let lightness = 0.5;
    if (c !== 0) {
      const factor = (100 + c) / 100;
      lightness = 0.5 + (lightness - 0.5) * factor;
    }
    if (b !== 0) {
      lightness = lightness + b / 200;
    }
    lightness = Math.max(0, Math.min(1, lightness));
    const satFrac = s / 100;
    const ch = (1 - Math.abs(2 * lightness - 1)) * satFrac;
    const hp = h / 60;
    const x = ch * (1 - Math.abs(hp % 2 - 1));
    let r1;
    let g1;
    let b1;
    if (hp < 1) {
      r1 = ch;
      g1 = x;
      b1 = 0;
    } else if (hp < 2) {
      r1 = x;
      g1 = ch;
      b1 = 0;
    } else if (hp < 3) {
      r1 = 0;
      g1 = ch;
      b1 = x;
    } else if (hp < 4) {
      r1 = 0;
      g1 = x;
      b1 = ch;
    } else if (hp < 5) {
      r1 = x;
      g1 = 0;
      b1 = ch;
    } else {
      r1 = ch;
      g1 = 0;
      b1 = x;
    }
    const m = lightness - ch / 2;
    const clamp = (v) => Math.max(0, Math.min(255, Math.round((v + m) * 255)));
    return `#${clamp(r1).toString(16).padStart(2, "0")}${clamp(g1).toString(16).padStart(2, "0")}${clamp(b1).toString(16).padStart(2, "0")}`;
  }

  // vendor/webview-ui/src/office/engine/matrixEffect.ts
  function flickerVisible(col, row, time) {
    const t = Math.floor(time * MATRIX_FLICKER_FPS);
    const hash = col * 7 + row * 13 + t * 31 & 255;
    return hash < MATRIX_FLICKER_VISIBILITY_THRESHOLD;
  }
  function renderMatrixEffect(ctx, ch, spriteData, drawX, drawY, zoom) {
    const progress = ch.matrixEffectTimer / MATRIX_EFFECT_DURATION_SEC;
    const isSpawn = ch.matrixEffect === "spawn";
    const time = ch.matrixEffectTimer;
    const totalSweep = MATRIX_SPRITE_ROWS + MATRIX_TRAIL_LENGTH;
    for (let col = 0; col < MATRIX_SPRITE_COLS; col++) {
      const stagger = (ch.matrixEffectSeeds[col] ?? 0) * MATRIX_COLUMN_STAGGER_RANGE;
      const colProgress = Math.max(
        0,
        Math.min(1, (progress - stagger) / (1 - MATRIX_COLUMN_STAGGER_RANGE))
      );
      const headRow = colProgress * totalSweep;
      for (let row = 0; row < MATRIX_SPRITE_ROWS; row++) {
        const pixel = spriteData[row]?.[col];
        const hasPixel = pixel && pixel !== "";
        const distFromHead = headRow - row;
        const px = drawX + col * zoom;
        const py = drawY + row * zoom;
        if (isSpawn) {
          if (distFromHead < 0) {
            continue;
          } else if (distFromHead < 1) {
            ctx.fillStyle = MATRIX_HEAD_COLOR;
            ctx.fillRect(px, py, zoom, zoom);
          } else if (distFromHead < MATRIX_TRAIL_LENGTH) {
            const trailPos = distFromHead / MATRIX_TRAIL_LENGTH;
            if (hasPixel) {
              ctx.fillStyle = pixel;
              ctx.fillRect(px, py, zoom, zoom);
              const greenAlpha = (1 - trailPos) * MATRIX_TRAIL_OVERLAY_ALPHA;
              if (flickerVisible(col, row, time)) {
                ctx.fillStyle = matrixGreenBright(greenAlpha);
                ctx.fillRect(px, py, zoom, zoom);
              }
            } else {
              if (flickerVisible(col, row, time)) {
                const alpha = (1 - trailPos) * MATRIX_TRAIL_EMPTY_ALPHA;
                ctx.fillStyle = trailPos < MATRIX_TRAIL_MID_THRESHOLD ? matrixGreenBright(alpha) : trailPos < MATRIX_TRAIL_DIM_THRESHOLD ? matrixGreenMid(alpha) : matrixGreenDim(alpha);
                ctx.fillRect(px, py, zoom, zoom);
              }
            }
          } else {
            if (hasPixel) {
              ctx.fillStyle = pixel;
              ctx.fillRect(px, py, zoom, zoom);
            }
          }
        } else {
          if (distFromHead < 0) {
            if (hasPixel) {
              ctx.fillStyle = pixel;
              ctx.fillRect(px, py, zoom, zoom);
            }
          } else if (distFromHead < 1) {
            ctx.fillStyle = MATRIX_HEAD_COLOR;
            ctx.fillRect(px, py, zoom, zoom);
          } else if (distFromHead < MATRIX_TRAIL_LENGTH) {
            if (flickerVisible(col, row, time)) {
              const trailPos = distFromHead / MATRIX_TRAIL_LENGTH;
              const alpha = (1 - trailPos) * MATRIX_TRAIL_EMPTY_ALPHA;
              ctx.fillStyle = trailPos < MATRIX_TRAIL_MID_THRESHOLD ? matrixGreenBright(alpha) : trailPos < MATRIX_TRAIL_DIM_THRESHOLD ? matrixGreenMid(alpha) : matrixGreenDim(alpha);
              ctx.fillRect(px, py, zoom, zoom);
            }
          }
        }
      }
    }
  }

  // vendor/webview-ui/src/office/engine/renderer.ts
  var ghostHeadlessAgents = false;
  function renderCarpetLayer(ctx, carpetTiles, cols, rows, offsetX, offsetY, zoom) {
    if (!hasCarpetSprites()) return;
    if (!carpetTiles || carpetTiles.length === 0) return;
    const s = TILE_SIZE * zoom;
    const halfS = s / 2;
    for (let jy = 0; jy <= rows; jy++) {
      for (let jx = 0; jx <= cols; jx++) {
        const localGroups = /* @__PURE__ */ new Map();
        const adjacent = [
          { col: jx - 1, row: jy - 1 },
          // NW
          { col: jx, row: jy - 1 },
          // NE
          { col: jx, row: jy },
          // SE
          { col: jx - 1, row: jy }
          // SW
        ];
        for (const pos of adjacent) {
          if (pos.col < 0 || pos.row < 0 || pos.col >= cols || pos.row >= rows) continue;
          const tile = carpetTiles[pos.row * cols + pos.col];
          if (!tile) continue;
          const color = tile.color ?? CARPET_DEFAULT_COLOR;
          const accentColor = tile.accentColor ?? CARPET_DEFAULT_ACCENT_COLOR;
          const paletteKey = getCarpetPaletteKey(color, accentColor);
          const key = `${tile.variant}:${paletteKey}`;
          const order = tile.order ?? 0;
          const existing = localGroups.get(key);
          if (!existing || order > existing.order) {
            localGroups.set(key, { variant: tile.variant, color, accentColor, paletteKey, order });
          }
        }
        if (localGroups.size === 0) continue;
        const ordered = [...localGroups.values()].sort((a, b) => a.order - b.order);
        for (const { variant, color, accentColor, paletteKey } of ordered) {
          const sprite = getCarpetJunctionSprite(
            jx,
            jy,
            variant,
            carpetTiles,
            cols,
            rows,
            color,
            accentColor,
            paletteKey
          );
          if (!sprite) continue;
          const cached = getCachedSprite(sprite, zoom);
          ctx.drawImage(cached, offsetX + jx * s - halfS, offsetY + jy * s - halfS);
        }
      }
    }
  }
  function renderAreaOverlay(ctx, areaTiles, areas, cols, rows, offsetX, offsetY, zoom, activeAreaLabel) {
    if (!areaTiles || areaTiles.length === 0) return;
    if (!areas || areas.length === 0) return;
    const s = TILE_SIZE * zoom;
    const colorMap = /* @__PURE__ */ new Map();
    for (const a of areas) colorMap.set(a.label, a.color);
    ctx.save();
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const label = areaTiles[r * cols + c];
        if (!label) continue;
        const color = colorMap.get(label);
        if (!color) continue;
        ctx.globalAlpha = activeAreaLabel === label ? AREA_OVERLAY_ALPHA * AREA_ACTIVE_ALPHA_MULTIPLIER : AREA_OVERLAY_ALPHA;
        ctx.fillStyle = color;
        ctx.fillRect(offsetX + c * s, offsetY + r * s, s, s);
      }
    }
    ctx.restore();
  }
  function renderAreaLabels(ctx, areaTiles, areas, cols, rows, offsetX, offsetY, zoom) {
    if (!areaTiles || areaTiles.length === 0) return;
    if (!areas || areas.length === 0) return;
    const s = TILE_SIZE * zoom;
    const colorMap = /* @__PURE__ */ new Map();
    for (const a of areas) colorMap.set(a.label, a.color);
    const centroids = /* @__PURE__ */ new Map();
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const label = areaTiles[r * cols + c];
        if (!label) continue;
        const acc = centroids.get(label);
        if (acc) {
          acc.sumX += c;
          acc.sumY += r;
          acc.count += 1;
        } else {
          centroids.set(label, { sumX: c, sumY: r, count: 1 });
        }
      }
    }
    if (centroids.size === 0) return;
    const fontSize = Math.max(AREA_LABEL_FONT_SIZE_PX * zoom, AREA_LABEL_MIN_FONT_SIZE_PX);
    ctx.save();
    ctx.font = `bold ${fontSize}px 'FS Pixel Sans'`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const [label, acc] of centroids) {
      const cx = offsetX + (acc.sumX / acc.count + 0.5) * s;
      const cy = offsetY + (acc.sumY / acc.count + 0.5) * s;
      ctx.globalAlpha = AREA_LABEL_SHADOW_ALPHA;
      ctx.fillStyle = AREA_LABEL_SHADOW_COLOR;
      ctx.fillText(label, cx + 1, cy + 1);
      ctx.globalAlpha = AREA_LABEL_ALPHA;
      ctx.fillStyle = colorMap.get(label) ?? AREA_LABEL_FALLBACK_COLOR;
      ctx.fillText(label, cx, cy);
    }
    ctx.restore();
  }
  function renderTileGrid(ctx, tileMap, offsetX, offsetY, zoom, tileColors, cols) {
    const s = TILE_SIZE * zoom;
    const useSpriteFloors = hasFloorSprites();
    const tmRows = tileMap.length;
    const tmCols = tmRows > 0 ? tileMap[0].length : 0;
    const layoutCols = cols ?? tmCols;
    for (let r = 0; r < tmRows; r++) {
      for (let c = 0; c < tmCols; c++) {
        const tile = tileMap[r][c];
        if (tile === TileType.VOID) continue;
        if (tile === TileType.WALL || !useSpriteFloors) {
          if (tile === TileType.WALL) {
            const colorIdx2 = r * layoutCols + c;
            const wallColor = tileColors?.[colorIdx2];
            ctx.fillStyle = wallColor ? wallColorToHex(wallColor) : WALL_COLOR;
          } else {
            ctx.fillStyle = FALLBACK_FLOOR_COLOR;
          }
          ctx.fillRect(offsetX + c * s, offsetY + r * s, s, s);
          continue;
        }
        const colorIdx = r * layoutCols + c;
        const color = tileColors?.[colorIdx] ?? { h: 0, s: 0, b: 0, c: 0 };
        const sprite = getColorizedFloorSprite(tile, color);
        const cached = getCachedSprite(sprite, zoom);
        ctx.drawImage(cached, offsetX + c * s, offsetY + r * s);
      }
    }
  }
  function renderScene(ctx, furniture, characters, offsetX, offsetY, zoom, selectedAgentId, hoveredAgentId, pets = []) {
    const drawables = [];
    for (const f of furniture) {
      const cached = getCachedSprite(f.sprite, zoom);
      const fx = offsetX + f.x * zoom;
      const fy = offsetY + f.y * zoom;
      if (f.mirrored) {
        drawables.push({
          zY: f.zY,
          draw: (c) => {
            c.save();
            c.translate(fx + cached.width, fy);
            c.scale(-1, 1);
            c.drawImage(cached, 0, 0);
            c.restore();
          }
        });
      } else {
        drawables.push({
          zY: f.zY,
          draw: (c) => {
            c.drawImage(cached, fx, fy);
          }
        });
      }
    }
    for (const ch of characters) {
      const sprites = getCharacterSprites(ch.palette, ch.hueShift);
      const spriteData = getCharacterSprite(ch, sprites);
      const cached = getCachedSprite(spriteData, zoom);
      const sittingOffset = ch.state === CharacterState.TYPE ? CHARACTER_SITTING_OFFSET_PX : 0;
      const drawX = Math.round(offsetX + ch.x * zoom - cached.width / 2);
      const drawY = Math.round(offsetY + (ch.y + sittingOffset) * zoom - cached.height);
      const charZY = ch.y + TILE_SIZE / 2 + CHARACTER_Z_SORT_OFFSET;
      const alpha = ch.isHeadless && ghostHeadlessAgents ? HEADLESS_CHARACTER_ALPHA : 1;
      if (ch.matrixEffect) {
        const mDrawX = drawX;
        const mDrawY = drawY;
        const mSpriteData = spriteData;
        const mCh = ch;
        drawables.push({
          zY: charZY,
          draw: (c) => {
            c.save();
            c.globalAlpha = alpha;
            renderMatrixEffect(c, mCh, mSpriteData, mDrawX, mDrawY, zoom);
            c.restore();
          }
        });
        continue;
      }
      const isSelected = selectedAgentId !== null && ch.id === selectedAgentId;
      const isHovered = hoveredAgentId !== null && ch.id === hoveredAgentId;
      if (isSelected || isHovered) {
        const outlineAlpha = isSelected ? SELECTED_OUTLINE_ALPHA : HOVERED_OUTLINE_ALPHA;
        const outlineData = getOutlineSprite(spriteData);
        const outlineCached = getCachedSprite(outlineData, zoom);
        const olDrawX = drawX - zoom;
        const olDrawY = drawY - zoom;
        drawables.push({
          zY: charZY - OUTLINE_Z_SORT_OFFSET,
          // sort just before character
          draw: (c) => {
            c.save();
            c.globalAlpha = outlineAlpha;
            c.drawImage(outlineCached, olDrawX, olDrawY);
            c.restore();
          }
        });
      }
      drawables.push({
        zY: charZY,
        draw: (c) => {
          if (alpha === 1) {
            c.drawImage(cached, drawX, drawY);
            return;
          }
          c.save();
          c.globalAlpha = alpha;
          c.drawImage(cached, drawX, drawY);
          c.restore();
        }
      });
    }
    for (const pet of pets) {
      const petSprites = getPetSprites(pet.petType);
      const spriteData = getPetSpriteData(pet, petSprites);
      if (!spriteData) continue;
      const cached = getCachedSprite(spriteData, zoom);
      const drawX = Math.round(offsetX + pet.x * zoom - cached.width / 2);
      const drawY = Math.round(offsetY + pet.y * zoom - cached.height);
      const petZY = pet.y + TILE_SIZE / 2;
      drawables.push({
        zY: petZY,
        draw: (c) => {
          c.drawImage(cached, drawX, drawY);
        }
      });
    }
    drawables.sort((a, b) => a.zY - b.zY);
    for (const d of drawables) {
      d.draw(ctx);
    }
  }
  function renderSeatIndicators(ctx, seats, characters, selectedAgentId, hoveredTile, offsetX, offsetY, zoom) {
    if (selectedAgentId === null || !hoveredTile) return;
    const selectedChar = characters.get(selectedAgentId);
    if (!selectedChar) return;
    for (const [uid, seat] of seats) {
      if (seat.seatCol !== hoveredTile.col || seat.seatRow !== hoveredTile.row) continue;
      const s = TILE_SIZE * zoom;
      const x = offsetX + seat.seatCol * s;
      const y = offsetY + seat.seatRow * s;
      if (selectedChar.seatId === uid) {
        ctx.fillStyle = SEAT_OWN_COLOR;
      } else if (!seat.assigned) {
        ctx.fillStyle = SEAT_AVAILABLE_COLOR;
      } else {
        ctx.fillStyle = SEAT_BUSY_COLOR;
      }
      ctx.fillRect(x, y, s, s);
      break;
    }
  }
  function renderGridOverlay(ctx, offsetX, offsetY, zoom, cols, rows, tileMap) {
    const s = TILE_SIZE * zoom;
    ctx.strokeStyle = GRID_LINE_COLOR;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 0; c <= cols; c++) {
      const x = offsetX + c * s + 0.5;
      ctx.moveTo(x, offsetY);
      ctx.lineTo(x, offsetY + rows * s);
    }
    for (let r = 0; r <= rows; r++) {
      const y = offsetY + r * s + 0.5;
      ctx.moveTo(offsetX, y);
      ctx.lineTo(offsetX + cols * s, y);
    }
    ctx.stroke();
    if (tileMap) {
      ctx.save();
      ctx.strokeStyle = VOID_TILE_OUTLINE_COLOR;
      ctx.lineWidth = 1;
      ctx.setLineDash(VOID_TILE_DASH_PATTERN);
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (tileMap[r]?.[c] === TileType.VOID) {
            ctx.strokeRect(offsetX + c * s + 0.5, offsetY + r * s + 0.5, s - 1, s - 1);
          }
        }
      }
      ctx.restore();
    }
  }
  function renderGhostBorder(ctx, offsetX, offsetY, zoom, cols, rows, ghostHoverCol, ghostHoverRow) {
    const s = TILE_SIZE * zoom;
    ctx.save();
    const ghostTiles = [];
    for (let c = -1; c <= cols; c++) {
      ghostTiles.push({ c, r: -1 });
      ghostTiles.push({ c, r: rows });
    }
    for (let r = 0; r < rows; r++) {
      ghostTiles.push({ c: -1, r });
      ghostTiles.push({ c: cols, r });
    }
    for (const { c, r } of ghostTiles) {
      const x = offsetX + c * s;
      const y = offsetY + r * s;
      const isHovered = c === ghostHoverCol && r === ghostHoverRow;
      if (isHovered) {
        ctx.fillStyle = GHOST_BORDER_HOVER_FILL;
        ctx.fillRect(x, y, s, s);
      }
      ctx.strokeStyle = isHovered ? GHOST_BORDER_HOVER_STROKE : GHOST_BORDER_STROKE;
      ctx.lineWidth = 1;
      ctx.setLineDash(VOID_TILE_DASH_PATTERN);
      ctx.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1);
    }
    ctx.restore();
  }
  function renderGhostPreview(ctx, sprite, col, row, valid, offsetX, offsetY, zoom, mirrored = false) {
    const cached = getCachedSprite(sprite, zoom);
    const x = offsetX + col * TILE_SIZE * zoom;
    const y = offsetY + row * TILE_SIZE * zoom;
    ctx.save();
    ctx.globalAlpha = GHOST_PREVIEW_SPRITE_ALPHA;
    if (mirrored) {
      ctx.translate(x + cached.width, y);
      ctx.scale(-1, 1);
      ctx.drawImage(cached, 0, 0);
    } else {
      ctx.drawImage(cached, x, y);
    }
    ctx.restore();
    ctx.save();
    ctx.globalAlpha = GHOST_PREVIEW_TINT_ALPHA;
    ctx.fillStyle = valid ? GHOST_VALID_TINT : GHOST_INVALID_TINT;
    ctx.fillRect(x, y, cached.width, cached.height);
    ctx.restore();
  }
  function renderSelectionHighlight(ctx, col, row, w, h, offsetX, offsetY, zoom) {
    const s = TILE_SIZE * zoom;
    const x = offsetX + col * s;
    const y = offsetY + row * s;
    ctx.save();
    ctx.strokeStyle = SELECTION_HIGHLIGHT_COLOR;
    ctx.lineWidth = 2;
    ctx.setLineDash(SELECTION_DASH_PATTERN);
    ctx.strokeRect(x + 1, y + 1, w * s - 2, h * s - 2);
    ctx.restore();
  }
  function renderDeleteButton(ctx, col, row, w, _h, offsetX, offsetY, zoom) {
    const s = TILE_SIZE * zoom;
    const cx = offsetX + (col + w) * s + 1;
    const cy = offsetY + row * s - 1;
    const radius = Math.max(BUTTON_MIN_RADIUS, zoom * BUTTON_RADIUS_ZOOM_FACTOR);
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = DELETE_BUTTON_BG;
    ctx.fill();
    ctx.strokeStyle = BUTTON_ICON_COLOR;
    ctx.lineWidth = Math.max(BUTTON_LINE_WIDTH_MIN, zoom * BUTTON_LINE_WIDTH_ZOOM_FACTOR);
    ctx.lineCap = "round";
    const xSize = radius * BUTTON_ICON_SIZE_FACTOR;
    ctx.beginPath();
    ctx.moveTo(cx - xSize, cy - xSize);
    ctx.lineTo(cx + xSize, cy + xSize);
    ctx.moveTo(cx + xSize, cy - xSize);
    ctx.lineTo(cx - xSize, cy + xSize);
    ctx.stroke();
    ctx.restore();
    return { cx, cy, radius };
  }
  function renderRotateButton(ctx, col, row, _w, _h, offsetX, offsetY, zoom) {
    const s = TILE_SIZE * zoom;
    const radius = Math.max(BUTTON_MIN_RADIUS, zoom * BUTTON_RADIUS_ZOOM_FACTOR);
    const cx = offsetX + col * s - 1;
    const cy = offsetY + row * s - 1;
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fillStyle = ROTATE_BUTTON_BG;
    ctx.fill();
    ctx.strokeStyle = BUTTON_ICON_COLOR;
    ctx.lineWidth = Math.max(BUTTON_LINE_WIDTH_MIN, zoom * BUTTON_LINE_WIDTH_ZOOM_FACTOR);
    ctx.lineCap = "round";
    const arcR = radius * BUTTON_ICON_SIZE_FACTOR;
    ctx.beginPath();
    ctx.arc(cx, cy, arcR, -Math.PI * 0.8, Math.PI * 0.7);
    ctx.stroke();
    const endAngle = Math.PI * 0.7;
    const endX = cx + arcR * Math.cos(endAngle);
    const endY = cy + arcR * Math.sin(endAngle);
    const arrowSize = radius * 0.35;
    ctx.beginPath();
    ctx.moveTo(endX + arrowSize * 0.6, endY - arrowSize * 0.3);
    ctx.lineTo(endX, endY);
    ctx.lineTo(endX + arrowSize * 0.7, endY + arrowSize * 0.5);
    ctx.stroke();
    ctx.restore();
    return { cx, cy, radius };
  }
  function renderBubbles(ctx, characters, offsetX, offsetY, zoom) {
    for (const ch of characters) {
      if (!ch.bubbleType) continue;
      if (ch.bubbleType === "waiting" && ch.waitingAwaitingInput) continue;
      const sprite = ch.bubbleType === "permission" ? BUBBLE_PERMISSION_SPRITE : BUBBLE_WAITING_SPRITE;
      let alpha = 1;
      if (ch.bubbleType === "waiting" && ch.bubbleTimer < BUBBLE_FADE_DURATION_SEC) {
        alpha = ch.bubbleTimer / BUBBLE_FADE_DURATION_SEC;
      }
      const cached = getCachedSprite(sprite, zoom);
      const sittingOff = ch.state === CharacterState.TYPE ? BUBBLE_SITTING_OFFSET_PX : 0;
      const bubbleX = Math.round(offsetX + ch.x * zoom - cached.width / 2);
      const bubbleY = Math.round(
        offsetY + (ch.y + sittingOff - BUBBLE_VERTICAL_OFFSET_PX) * zoom - cached.height - 1 * zoom
      );
      ctx.save();
      if (alpha < 1) ctx.globalAlpha = alpha;
      ctx.drawImage(cached, bubbleX, bubbleY);
      ctx.restore();
    }
  }
  function renderPetBubbles(ctx, pets, offsetX, offsetY, zoom) {
    for (const pet of pets) {
      if (!pet.bubbleType) continue;
      const sprite = BUBBLE_HEART_SPRITE;
      let alpha = 1;
      if (pet.bubbleTimer < BUBBLE_FADE_DURATION_SEC) {
        alpha = Math.max(0, pet.bubbleTimer / BUBBLE_FADE_DURATION_SEC);
      }
      const cached = getCachedSprite(sprite, zoom);
      const bubbleX = Math.round(offsetX + pet.x * zoom - cached.width / 2);
      const bubbleY = Math.round(offsetY + (pet.y - TILE_SIZE) * zoom - cached.height - 1 * zoom);
      ctx.save();
      if (alpha < 1) ctx.globalAlpha = alpha;
      ctx.drawImage(cached, bubbleX, bubbleY);
      ctx.restore();
    }
  }
  function renderFrame(ctx, canvasWidth, canvasHeight, tileMap, furniture, characters, zoom, panX, panY, selection, editor, tileColors, layoutCols, layoutRows, carpetTiles, areas, areaTiles, showAreas, activeAreaLabel, pets) {
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    const cols = layoutCols ?? (tileMap.length > 0 ? tileMap[0].length : 0);
    const rows = layoutRows ?? tileMap.length;
    const { offsetX, offsetY } = mapOffset(canvasWidth, canvasHeight, cols, rows, zoom, panX, panY);
    renderTileGrid(ctx, tileMap, offsetX, offsetY, zoom, tileColors, layoutCols);
    if (carpetTiles && carpetTiles.length > 0) {
      renderCarpetLayer(ctx, carpetTiles, cols, rows, offsetX, offsetY, zoom);
    }
    if (showAreas) {
      renderAreaOverlay(ctx, areaTiles, areas, cols, rows, offsetX, offsetY, zoom, activeAreaLabel);
    }
    if (selection) {
      renderSeatIndicators(
        ctx,
        selection.seats,
        selection.characters,
        selection.selectedAgentId,
        selection.hoveredTile,
        offsetX,
        offsetY,
        zoom
      );
    }
    const wallInstances = hasWallSprites() ? getWallInstances(tileMap, tileColors, layoutCols) : [];
    const allFurniture = wallInstances.length > 0 ? [...wallInstances, ...furniture] : furniture;
    const selectedId = selection?.selectedAgentId ?? null;
    const hoveredId = selection?.hoveredAgentId ?? null;
    renderScene(
      ctx,
      allFurniture,
      characters,
      offsetX,
      offsetY,
      zoom,
      selectedId,
      hoveredId,
      pets ?? []
    );
    renderBubbles(ctx, characters, offsetX, offsetY, zoom);
    if (pets && pets.length > 0) {
      renderPetBubbles(ctx, pets, offsetX, offsetY, zoom);
    }
    if (showAreas) {
      renderAreaLabels(ctx, areaTiles, areas, cols, rows, offsetX, offsetY, zoom);
    }
    if (editor) {
      if (editor.showGrid) {
        renderGridOverlay(ctx, offsetX, offsetY, zoom, cols, rows, tileMap);
      }
      if (editor.showGhostBorder) {
        renderGhostBorder(
          ctx,
          offsetX,
          offsetY,
          zoom,
          cols,
          rows,
          editor.ghostBorderHoverCol,
          editor.ghostBorderHoverRow
        );
      }
      if (editor.ghostSprite && editor.ghostCol >= 0) {
        renderGhostPreview(
          ctx,
          editor.ghostSprite,
          editor.ghostCol,
          editor.ghostRow,
          editor.ghostValid,
          offsetX,
          offsetY,
          zoom,
          editor.ghostMirrored
        );
      }
      if (editor.hasSelection) {
        renderSelectionHighlight(
          ctx,
          editor.selectedCol,
          editor.selectedRow,
          editor.selectedW,
          editor.selectedH,
          offsetX,
          offsetY,
          zoom
        );
        editor.deleteButtonBounds = renderDeleteButton(
          ctx,
          editor.selectedCol,
          editor.selectedRow,
          editor.selectedW,
          editor.selectedH,
          offsetX,
          offsetY,
          zoom
        );
        if (editor.isRotatable) {
          editor.rotateButtonBounds = renderRotateButton(
            ctx,
            editor.selectedCol,
            editor.selectedRow,
            editor.selectedW,
            editor.selectedH,
            offsetX,
            offsetY,
            zoom
          );
        } else {
          editor.rotateButtonBounds = null;
        }
      } else {
        editor.deleteButtonBounds = null;
        editor.rotateButtonBounds = null;
      }
    }
    return { offsetX, offsetY };
  }

  // src/office.ts
  var ACTOR_IDS = [1, 2, 3];
  var PALETTES = { 1: 0, 2: 1, 3: 2 };
  var ZOOM_STEPS = [1, 2, 3];
  var LABEL_LIFT_PX = 30;
  var CONTAINER_PADDING_PX = 8;
  var MAX_DISPLAY_SCALE = 3;
  var LABEL_GAP_PX = 4;
  var VOID_TILE = 255;
  function fail(message) {
    throw new Error(message);
  }
  function filled(value) {
    return Array.isArray(value) && value.length > 0;
  }
  function validatePayload(data) {
    const payload = data;
    if (!payload || typeof payload !== "object") fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043E\u0442\u0432\u0435\u0442 \u043D\u0435 \u044F\u0432\u043B\u044F\u0435\u0442\u0441\u044F \u043E\u0431\u044A\u0435\u043A\u0442\u043E\u043C");
    if (!filled(payload.characters)) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u0441\u043F\u0440\u0430\u0439\u0442\u044B \u043F\u0435\u0440\u0441\u043E\u043D\u0430\u0436\u0435\u0439 \u043E\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044E\u0442");
    if (!filled(payload.floors)) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043F\u043B\u0438\u0442\u043A\u0438 \u043F\u043E\u043B\u0430 \u043E\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044E\u0442");
    if (!filled(payload.walls)) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043F\u043B\u0438\u0442\u043A\u0438 \u0441\u0442\u0435\u043D \u043E\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044E\u0442");
    if (!filled(payload.carpets)) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043A\u043E\u0432\u0440\u044B \u043E\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044E\u0442");
    if (!payload.furniture || !filled(payload.furniture.catalog) || !payload.furniture.sprites) {
      fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043A\u0430\u0442\u0430\u043B\u043E\u0433 \u043C\u0435\u0431\u0435\u043B\u0438 \u043E\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442");
    }
    const layout = payload.layout;
    if (!layout || !(layout.cols > 0) || !(layout.rows > 0) || !Array.isArray(layout.furniture)) {
      fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043F\u043B\u0430\u043D\u0438\u0440\u043E\u0432\u043A\u0430 \u043A\u043E\u043C\u043D\u0430\u0442\u044B \u043F\u043E\u0432\u0440\u0435\u0436\u0434\u0435\u043D\u0430");
    }
    for (const character of payload.characters) {
      if (!filled(character?.down) || !filled(character?.up) || !filled(character?.right)) {
        fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u0443 \u043F\u0435\u0440\u0441\u043E\u043D\u0430\u0436\u0430 \u043D\u0435\u0442 \u043A\u0430\u0434\u0440\u043E\u0432 \u0434\u0432\u0438\u0436\u0435\u043D\u0438\u044F");
      }
    }
    return payload;
  }
  function workstationsFirst(office, furniture) {
    const tiles = (test) => {
      const out = /* @__PURE__ */ new Set();
      for (const item of furniture) {
        const entry = getCatalogEntry(item.type);
        if (!entry || !test(entry.category, entry.isDesk === true)) continue;
        for (let row = 0; row < entry.footprintH; row += 1) {
          for (let col = 0; col < entry.footprintW; col += 1) {
            out.add(item.col + col + "," + (item.row + row));
          }
        }
      }
      return out;
    };
    const computers = tiles((category) => category === "electronics");
    const desks = tiles((category, isDesk) => isDesk);
    const rank = (uid) => {
      const seat = office.seats.get(uid);
      if (!seat) return 2;
      const step = seat.facingDir === Direction.RIGHT ? [1, 0] : seat.facingDir === Direction.LEFT ? [-1, 0] : seat.facingDir === Direction.DOWN ? [0, 1] : [0, -1];
      const facing = seat.seatCol + step[0] + "," + (seat.seatRow + step[1]);
      return computers.has(facing) ? 0 : desks.has(facing) ? 1 : 2;
    };
    return Array.from(office.seats.keys()).sort((left, right) => {
      const difference = rank(left) - rank(right);
      return difference !== 0 ? difference : left < right ? -1 : left > right ? 1 : 0;
    });
  }
  function roomBounds(tileMap) {
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
    const top = Math.max(0, minRow * TILE_SIZE - TILE_SIZE);
    return {
      x: minCol * TILE_SIZE,
      y: top,
      width: (maxCol - minCol + 1) * TILE_SIZE,
      height: (maxRow + 1) * TILE_SIZE - top
    };
  }
  async function mountPixelOffice(canvas, options) {
    const assetsUrl = options.assetsUrl || "/pixel-agents/assets.json";
    let response;
    try {
      response = await fetch(assetsUrl, { cache: "no-store" });
    } catch (error) {
      return fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430 \u043D\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043D\u044B: " + String(error?.message || error));
    }
    if (!response.ok) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430 \u043D\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043D\u044B: HTTP " + response.status);
    const payload = validatePayload(await response.json());
    setCharacterTemplates(payload.characters);
    setFloorSprites(payload.floors);
    setWallSprites(payload.walls);
    setCarpetSprites(payload.carpets);
    if (!buildDynamicCatalog(payload.furniture)) fail("\u0430\u0441\u0441\u0435\u0442\u044B \u043E\u0444\u0438\u0441\u0430: \u043A\u0430\u0442\u0430\u043B\u043E\u0433 \u043C\u0435\u0431\u0435\u043B\u0438 \u043D\u0435 \u0441\u043E\u0431\u0440\u0430\u043D");
    setProviderCapabilities({
      readingTools: ["Read", "Glob", "Grep", "NotebookRead", "WebFetch", "WebSearch"],
      subagentToolNames: ["Task", "Agent"]
    });
    const office = new OfficeState(payload.layout);
    const layout = office.getLayout();
    const room = roomBounds(office.tileMap);
    const seatIds = workstationsFirst(office, layout.furniture);
    const names = /* @__PURE__ */ new Map();
    const shorts = /* @__PURE__ */ new Map();
    const activeById = /* @__PURE__ */ new Map();
    const toolById = /* @__PURE__ */ new Map();
    let lifecycleCalls = 0;
    ACTOR_IDS.forEach((id, index) => {
      office.addAgent(id, PALETTES[id], 0, seatIds[index], true);
      office.setAgentActive(id, false);
      lifecycleCalls += 1;
      activeById.set(id, false);
      toolById.set(id, null);
      names.set(id, "\u0430\u0433\u0435\u043D\u0442 " + id);
      shorts.set(id, "\u0441\u043E\u0441\u0442\u043E\u044F\u043D\u0438\u0435 \u043D\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043D\u043E");
    });
    const context = canvas.getContext("2d");
    if (!context) fail("\u043E\u0444\u0438\u0441: \u043A\u0430\u043D\u0432\u0430\u0441 \u043D\u0435 \u043E\u0442\u0434\u0430\u043B 2d-\u043A\u043E\u043D\u0442\u0435\u043A\u0441\u0442");
    const ctx = context;
    const container = canvas.parentElement;
    if (!container) fail("\u043E\u0444\u0438\u0441: \u0443 \u043A\u0430\u043D\u0432\u0430\u0441\u0430 \u043D\u0435\u0442 \u043A\u043E\u043D\u0442\u0435\u0439\u043D\u0435\u0440\u0430 \u0434\u043B\u044F \u043F\u043E\u0434\u043F\u0438\u0441\u0435\u0439");
    const overlay = document.createElement("div");
    overlay.className = "office-labels";
    overlay.setAttribute("aria-hidden", "true");
    container.appendChild(overlay);
    const labels = /* @__PURE__ */ new Map();
    for (const id of ACTOR_IDS) {
      const box = document.createElement("div");
      box.className = "office-label";
      const name = document.createElement("span");
      name.className = "office-label-name";
      const short = document.createElement("span");
      short.className = "office-label-short";
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
    let selectedActorId = null;
    let simulating = false;
    let stopLoop = null;
    let disposed = false;
    let wantMotion = true;
    let connected = true;
    const reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    const motionAllowed = () => wantMotion && !(reduced && reduced.matches);
    function seatOf(character) {
      return character.seatId ? office.seats.get(character.seatId) || null : null;
    }
    function settle() {
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
    function pixelRatio() {
      return display.width > 0 ? canvas.width / display.width : window.devicePixelRatio || 1;
    }
    function panFor(canvasSize, gridSize, boxStart, boxSize, target) {
      const visible = canvasSize / zoom;
      const center = visible >= boxSize ? boxStart + boxSize / 2 : Math.max(boxStart + visible / 2, Math.min(boxStart + boxSize - visible / 2, target));
      return canvasSize / 2 - center * zoom - Math.floor((canvasSize - gridSize * zoom) / 2);
    }
    function layoutCanvas() {
      container.style.height = "";
      const available = {
        width: Math.max(64, container.clientWidth - CONTAINER_PADDING_PX * 2),
        height: Math.max(64, container.clientHeight - CONTAINER_PADDING_PX * 2)
      };
      stageWidth = container.clientWidth;
      const dpr = window.devicePixelRatio || 1;
      const fit = Math.min(available.width * dpr / room.width, available.height * dpr / room.height);
      zoom = Math.max(1, Math.floor(fit)) * zoomStep;
      const width = zoomStep > 1 ? Math.min(room.width * zoom, Math.round(available.width * dpr)) : room.width * zoom;
      const height = zoomStep > 1 ? Math.min(room.height * zoom, Math.round(available.height * dpr)) : room.height * zoom;
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
      const scale = Math.min(available.width / (width / dpr), available.height / (height / dpr), MAX_DISPLAY_SCALE);
      display.width = Math.round(width / dpr * scale);
      display.height = Math.round(height / dpr * scale);
      canvas.style.width = display.width + "px";
      canvas.style.height = display.height + "px";
      container.style.height = display.height + CONTAINER_PADDING_PX * 2 + "px";
    }
    function updatePan() {
      const focus = selectedActorId === null ? null : findCharacter(selectedActorId);
      pan = {
        x: panFor(canvas.width, layout.cols * TILE_SIZE, room.x, room.width, focus ? focus.x : room.x + room.width / 2),
        y: panFor(canvas.height, layout.rows * TILE_SIZE, room.y, room.height, focus ? focus.y : room.y + room.height / 2)
      };
    }
    function findCharacter(id) {
      for (const character of office.getCharacters()) {
        if (character.id === id) return character;
      }
      return null;
    }
    function positionLabels() {
      if (display.width === 0 || display.height === 0) return;
      overlay.style.left = canvas.offsetLeft + "px";
      overlay.style.top = canvas.offsetTop + "px";
      overlay.style.width = display.width + "px";
      overlay.style.height = display.height + "px";
      const projection = overlayProjection(layout, display, zoom, pan, pixelRatio());
      const placed = [];
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
          height: label.height
        });
      }
      placed.sort((first, second) => second.top - first.top);
      for (let index = 0; index < placed.length; index += 1) {
        const box = placed[index];
        for (let pass = 0; pass < index; pass += 1) {
          let moved = false;
          for (let other = 0; other < index; other += 1) {
            const above = placed[other];
            const apart = box.left + box.half <= above.left - above.half || above.left + above.half <= box.left - box.half || box.top - box.height >= above.top || box.top <= above.top - above.height;
            if (apart) continue;
            box.top = above.top - above.height - LABEL_GAP_PX;
            moved = true;
          }
          if (!moved) break;
        }
      }
      let overflow = 0;
      for (const box of placed) overflow = Math.max(overflow, box.height - box.top);
      for (const box of placed) {
        box.label.box.style.left = box.left + "px";
        box.label.box.style.top = box.top + overflow + "px";
      }
    }
    function paint() {
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
        void 0,
        void 0,
        layout.tileColors,
        layout.cols,
        layout.rows,
        layout.carpetTiles,
        layout.areas,
        layout.areaTiles,
        false,
        null,
        office.getPets()
      );
      frames += 1;
      positionLabels();
    }
    function startSimulation() {
      if (simulating || disposed) return;
      simulating = true;
      stopLoop = startGameLoop(canvas, {
        update: (dt) => office.update(dt),
        render: () => paint()
      });
    }
    function stopSimulation() {
      if (stopLoop) stopLoop();
      stopLoop = null;
      simulating = false;
    }
    function applyMotion() {
      if (motionAllowed()) {
        startSimulation();
      } else if (simulating || frames === 0) {
        stopSimulation();
        settle();
        paint();
      }
    }
    function labelText() {
      for (const id of ACTOR_IDS) {
        const label = labels.get(id);
        if (!label) continue;
        label.name.textContent = names.get(id) || "";
        label.short.textContent = shorts.get(id) || "";
        label.box.className = "office-label" + (selectedActorId === id ? " selected" : "");
        label.width = label.box.offsetWidth;
        label.height = label.box.offsetHeight;
      }
    }
    function update(snapshot) {
      if (disposed || !snapshot || !Array.isArray(snapshot.actors)) return;
      connected = snapshot.connected !== false;
      selectedActorId = ACTOR_IDS.indexOf(Number(snapshot.selectedActorId)) >= 0 ? Number(snapshot.selectedActorId) : null;
      for (const actor of snapshot.actors) {
        const id = Number(actor && actor.id);
        if (ACTOR_IDS.indexOf(id) < 0) continue;
        names.set(id, String(actor.name == null ? "" : actor.name));
        shorts.set(id, String(actor.short == null ? "" : actor.short));
        const active = actor.active === true && connected;
        if (activeById.get(id) !== active) {
          office.setAgentActive(id, active);
          activeById.set(id, active);
          lifecycleCalls += 1;
        }
        const tool = active && typeof actor.tool === "string" && actor.tool ? actor.tool : null;
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
    function pick(event) {
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
    const onContainerResize = () => {
      if (disposed || container.clientWidth === stageWidth) return;
      relayout();
    };
    const onMotionChange = () => applyMotion();
    canvas.addEventListener("click", pick);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(onContainerResize) : null;
    if (observer) observer.observe(container);
    window.addEventListener("resize", relayout);
    if (reduced && reduced.addEventListener) reduced.addEventListener("change", onMotionChange);
    labelText();
    layoutCanvas();
    settle();
    paint();
    applyMotion();
    const view = {
      update,
      setZoomStep(step) {
        const next = ZOOM_STEPS.indexOf(step) >= 0 ? step : 1;
        if (next === zoomStep) return;
        zoomStep = next;
        layoutCanvas();
        paint();
      },
      zoomSteps: () => ZOOM_STEPS.slice(),
      dispose() {
        if (disposed) return;
        disposed = true;
        stopSimulation();
        canvas.removeEventListener("click", pick);
        if (observer) observer.disconnect();
        window.removeEventListener("resize", relayout);
        if (reduced && reduced.removeEventListener) reduced.removeEventListener("change", onMotionChange);
        overlay.remove();
      },
      inspect() {
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
              name: names.get(id) || "",
              short: shorts.get(id) || "",
              x: character ? character.x : -1,
              y: character ? character.y : -1,
              seatId: character ? character.seatId : null,
              active: activeById.get(id) === true,
              tool: toolById.get(id) || null,
              state: character ? character.state : -1,
              labelLeft: box ? box.left - rect.left : -1,
              labelTop: box ? box.top - rect.top : -1,
              hitX: character ? projection.toScreenX(character.x) : -1,
              hitY: character ? projection.toScreenY(character.y - CHARACTER_HIT_HEIGHT / 2) : -1
            };
          })
        };
      }
    };
    canvas.pixelOffice = view;
    return view;
  }
  return __toCommonJS(office_exports);
})();
window.mountPixelOffice = PixelOffice.mountPixelOffice;
