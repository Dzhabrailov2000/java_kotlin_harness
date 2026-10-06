#!/usr/bin/env node
// PostToolUse-хук (Write|Edit): ASCII-пунктуация в тексте, который пишет Claude.
// Проверяется только записанный фрагмент (content или new_string), а не весь файл: символ, который был
// в файле до правки, запись не блокирует.
let raw = '';
process.stdin.on('data', (d) => (raw += d));
process.stdin.on('end', () => {
  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0); // битый вход - не повод останавливать работу
  }
  const ti = (input && input.tool_input) || {};
  const text = ti.content != null ? ti.content : ti.new_string != null ? ti.new_string : '';
  // тире, кривые кавычки, точка-маркер, многоточие одним символом, елочки, стрелки, значки, флаги и эмодзи
  const bad = /[\u2010-\u2015\u2018\u2019\u201c-\u201e\u2022\u2026\u00ab\u00bb\u2190-\u21ff\u2300-\u23ff\u25a0-\u25ff\u2600-\u27bf\u2b00-\u2bff]|[\u{1f1e6}-\u{1f1ff}\u{1f300}-\u{1faff}]/u;
  if (typeof text !== 'string' || !bad.test(text)) process.exit(0);

  const hits = [];
  text.split('\n').forEach((line, i) => {
    if (bad.test(line)) hits.push(i + 1);
  });
  const file = ti.file_path || 'файл';
  console.log(
    JSON.stringify({
      decision: 'block',
      reason:
        'ASCII-пунктуация: в записанном тексте (' +
        file +
        ') есть тире, стрелка, кривые или елочные кавычки, многоточие одним символом или значок, строки фрагмента: ' +
        hits.join(', ') +
        '. Замени на дефис, "->", прямые кавычки или "..." и запиши снова. Если символ нужен по смыслу ' +
        '(данные, тест, чужая цитата), оставь его.',
    })
  );
  process.exit(0);
});
