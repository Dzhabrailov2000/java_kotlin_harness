#!/usr/bin/env node
// Баннер личной обвязки Claude Code: скиллы, агенты, команды, события хуков.
// Запускается из SessionStart-хука и из команды /harness.
// Правило пользователя: только ASCII-пунктуация, без тире, стрелок и галочек.

const fs = require('fs');
const path = require('path');
const os = require('os');

const root = path.join(os.homedir(), '.claude');

function listSkills() {
  const dir = path.join(root, 'skills');
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function listMarkdown(subdir) {
  const dir = path.join(root, subdir);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith('.md'))
    .map((name) => name.replace(/\.md$/, ''))
    .sort();
}

function listHookEvents() {
  const file = path.join(root, 'settings.json');
  if (!fs.existsSync(file)) return [];
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Object.keys(parsed.hooks || {}).sort();
  } catch (err) {
    return [];
  }
}

function section(title, items) {
  const lines = [`${title} (${items.length}):`];
  if (items.length === 0) {
    lines.push('  нет');
  } else {
    items.forEach((item) => lines.push(`  - ${item}`));
  }
  return lines.join('\n');
}

const out = [
  '========================================',
  '  Моя обвязка Claude Code',
  '========================================',
  section('Скиллы', listSkills()),
  section('Агенты', listMarkdown('agents')),
  section('Команды', listMarkdown('commands')),
  section('Хуки (события)', listHookEvents()),
  '========================================',
];

console.log(out.join('\n'));
