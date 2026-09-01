#!/usr/bin/env node
// UserPromptSubmit hook: перед каждым ответом подмешивает в контекст модели
// список доступной обвязки с КРАТКИМИ ОПИСАНИЯМИ и просит применить
// релевантные компоненты, а не все подряд.
// Описания читаются из frontmatter (поле description) каждого файла, поэтому
// всегда актуальны. Правило пользователя: только ASCII-пунктуация.

const fs = require('fs');
const path = require('path');
const os = require('os');

const root = path.join(os.homedir(), '.claude');

function readDescription(file) {
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

function collectSkills() {
  const dir = path.join(root, 'skills');
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir, { withFileTypes: true })
    // statSync, а не entry.isDirectory(): скиллы установлены симлинками на
    // java_kotlin_harness, для симлинка isDirectory() возвращает false и
    // такие скиллы молча выпадали из напоминания.
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

function collectAgents() {
  const dir = path.join(root, 'agents');
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith('.md'))
    .map((name) => ({
      name: name.replace(/\.md$/, ''),
      desc: readDescription(path.join(dir, name)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function formatList(items) {
  return items
    .map((it) => '- ' + it.name + (it.desc ? ': ' + it.desc : ''))
    .join('\n');
}

const skills = collectSkills();
const agents = collectAgents();

const out = [
  '[Обвязка] Перед ответом сверься со списком ниже и примени РЕЛЕВАНТНЫЕ компоненты.',
  'Не применяй всё подряд: только то, что подходит запросу. Если ничего не подходит, отвечай как обычно.',
  '',
  'Скиллы (знание, применяю сам):',
  skills.length ? formatList(skills) : '- нет',
  '',
  'Агенты (субподрядчики, запускаю по необходимости):',
  agents.length ? formatList(agents) : '- нет',
];

console.log(out.join('\n'));
