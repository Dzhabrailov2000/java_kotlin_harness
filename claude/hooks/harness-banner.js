#!/usr/bin/env node
// Баннер личной обвязки Claude Code: скиллы и агенты с описаниями, команды,
// события хуков. Запускается вручную командой /harness; как hook не подключен -
// каталог выдается по запросу, а не подмешивается в каждый промпт.
// Описания читаются из frontmatter (поле description) каждого файла, поэтому
// всегда актуальны. Правило пользователя: только ASCII-пунктуация.

const fs = require('fs');
const path = require('path');
const os = require('os');

const root = path.join(os.homedir(), '.claude');

function readEntries(dir) {
  // Нечитаемый или отсутствующий каталог - пустой раздел, а не падение баннера.
  try {
    return fs.readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    return [];
  }
}

function readDescription(file) {
  // Отсутствующий, битый или бесфронтматтерный файл оставляет описание пустым.
  try {
    const text = fs.readFileSync(file, 'utf8');
    const fm = text.match(/^---\n([\s\S]*?)\n---/);
    if (!fm) return '';
    const dm = fm[1].match(/^description:\s*(.+)$/m);
    if (!dm) return '';
    return dm[1].trim().replace(/^["']|["']$/g, '');
  } catch (err) {
    return '';
  }
}

function listSkills() {
  const dir = path.join(root, 'skills');
  return readEntries(dir)
    // statSync, а не entry.isDirectory(): скиллы установлены симлинками на
    // java_kotlin_harness, для симлинка isDirectory() возвращает false и
    // такие скиллы молча выпадали из инвентаризации. Битая ссылка отсеивается.
    .filter((entry) => {
      try {
        return fs.statSync(path.join(dir, entry.name)).isDirectory();
      } catch (err) {
        return false;
      }
    })
    .map((entry) => ({
      name: entry.name,
      desc: readDescription(path.join(dir, entry.name, 'SKILL.md')),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function listMarkdown(subdir) {
  const dir = path.join(root, subdir);
  return readEntries(dir)
    .filter((entry) => entry.name.endsWith('.md'))
    .map((entry) => ({
      name: entry.name.replace(/\.md$/, ''),
      desc: readDescription(path.join(dir, entry.name)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function listHookEvents() {
  const file = path.join(root, 'settings.json');
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    return Object.keys(parsed.hooks || {})
      .sort()
      .map((name) => ({ name: name, desc: '' }));
  } catch (err) {
    return [];
  }
}

function section(title, items) {
  const lines = [`${title} (${items.length}):`];
  if (items.length === 0) {
    lines.push('  нет');
  } else {
    items.forEach((item) => lines.push(`  - ${item.name}${item.desc ? ': ' + item.desc : ''}`));
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
  'Это инвентарь установленного, а не поручение применять все подряд.',
];

console.log(out.join('\n'));
