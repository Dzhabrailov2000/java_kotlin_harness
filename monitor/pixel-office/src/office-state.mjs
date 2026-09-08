/**
 * Local runtime storage of the office's own appearance: layout, seats, settings, areas.
 *
 * This is the monitor's state directory and nothing else. The Claude and Codex CLI
 * profiles are never read or written here, and no value from the browser reaches a file
 * before it has been validated and bounded: an oversized, malformed or foreign payload
 * is refused and the previous file is left as it was.
 */

import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

/** One stored document may not exceed this; a layout of the shipped room is ~30 kB. */
export const MAX_STATE_BYTES = 2 * 1024 * 1024;

export const DEFAULT_SETTINGS = {
  soundEnabled: true,
  // The three role names are the point of this office, so they are always on screen
  // rather than only on hover.
  alwaysShowLabels: true,
  ghostHeadlessAgents: false,
  showAreas: false,
  lastSeenVersion: '',
};

const BOOLEAN_SETTINGS = ['soundEnabled', 'alwaysShowLabels', 'ghostHeadlessAgents', 'showAreas'];

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** A layout the office engine can rebuild from, or null. Shape only, never trust size. */
export function validateLayout(value) {
  if (!isPlainObject(value)) return null;
  if (value.version !== 1) return null;
  if (!Array.isArray(value.tiles) || !Array.isArray(value.furniture)) return null;
  if (!Number.isInteger(value.cols) || !Number.isInteger(value.rows)) return null;
  if (value.cols < 1 || value.rows < 1 || value.cols > 512 || value.rows > 512) return null;
  if (value.areas !== undefined && !Array.isArray(value.areas)) return null;
  return value;
}

/** Seat assignments as the office sends them: palette, hue shift and an optional seat id. */
export function validateSeats(value) {
  if (!isPlainObject(value)) return null;
  const seats = {};
  for (const [key, seat] of Object.entries(value)) {
    if (!/^\d{1,9}$/.test(key) || !isPlainObject(seat)) return null;
    if (!Number.isInteger(seat.palette) || seat.palette < 0 || seat.palette > 64) return null;
    if (typeof seat.hueShift !== 'number' || !Number.isFinite(seat.hueShift)) return null;
    if (seat.seatId !== null && (typeof seat.seatId !== 'string' || seat.seatId.length > 64)) return null;
    seats[key] = { palette: seat.palette, hueShift: seat.hueShift, seatId: seat.seatId ?? null };
  }
  return seats;
}

/** folderName -> area labels; both sides are short display strings, not paths to open. */
export function validateAreas(value) {
  if (!isPlainObject(value)) return null;
  const mappings = {};
  for (const [folder, labels] of Object.entries(value)) {
    if (typeof folder !== 'string' || folder.length > 200) return null;
    if (!Array.isArray(labels) || labels.length > 64) return null;
    if (!labels.every((label) => typeof label === 'string' && label.length > 0 && label.length <= 200)) return null;
    mappings[folder] = [...labels];
  }
  return mappings;
}

export function validateSettings(value) {
  if (!isPlainObject(value)) return null;
  const settings = { ...DEFAULT_SETTINGS };
  for (const name of BOOLEAN_SETTINGS) {
    if (name in value) {
      if (typeof value[name] !== 'boolean') return null;
      settings[name] = value[name];
    }
  }
  if ('lastSeenVersion' in value) {
    if (typeof value.lastSeenVersion !== 'string' || value.lastSeenVersion.length > 32) return null;
    settings.lastSeenVersion = value.lastSeenVersion;
  }
  return settings;
}

const DOCUMENTS = {
  settings: { file: 'settings.json', validate: validateSettings, fallback: () => ({ ...DEFAULT_SETTINGS }) },
  layout: { file: 'layout.json', validate: validateLayout, fallback: () => null },
  seats: { file: 'seats.json', validate: validateSeats, fallback: () => ({}) },
  areas: { file: 'areas.json', validate: validateAreas, fallback: () => ({}) },
};

export class OfficeStateStore {
  /**
   * @param {string} directory explicit local runtime storage of this monitor
   */
  constructor(directory) {
    this.directory = directory;
    this.problems = [];
    mkdirSync(directory, { recursive: true });
  }

  read(kind) {
    const document = DOCUMENTS[kind];
    if (!document) throw new Error('unknown office state document: ' + kind);
    const path = join(this.directory, document.file);
    let raw;
    try {
      raw = readFileSync(path);
    } catch (error) {
      if (error.code !== 'ENOENT') this.problems.push(document.file + ' is unreadable: ' + error.code);
      return document.fallback();
    }
    if (raw.length > MAX_STATE_BYTES) {
      this.problems.push(document.file + ' exceeds the stored-document bound and was ignored');
      return document.fallback();
    }
    let parsed;
    try {
      parsed = JSON.parse(raw.toString('utf8'));
    } catch {
      this.problems.push(document.file + ' is not JSON and was ignored');
      return document.fallback();
    }
    const valid = document.validate(parsed);
    if (valid === null && kind !== 'layout') {
      this.problems.push(document.file + ' does not match its shape and was ignored');
      return document.fallback();
    }
    return valid;
  }

  /** Store a validated document; an invalid or oversized one is refused, not written. */
  write(kind, value) {
    const document = DOCUMENTS[kind];
    if (!document) return 'unknown document';
    const valid = document.validate(value);
    if (valid === null) return 'refused: ' + document.file + ' payload does not match its shape';
    const data = JSON.stringify(valid);
    if (Buffer.byteLength(data) > MAX_STATE_BYTES) return 'refused: ' + document.file + ' payload is too large';
    const path = join(this.directory, document.file);
    const temporary = path + '.tmp';
    try {
      writeFileSync(temporary, data + '\n', { encoding: 'utf8', mode: 0o600 });
      renameSync(temporary, path);
    } catch (error) {
      return 'refused: ' + document.file + ' could not be stored: ' + error.code;
    }
    return null;
  }
}
