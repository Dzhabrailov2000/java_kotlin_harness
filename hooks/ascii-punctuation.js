#!/usr/bin/env node
// PostToolUse-хук (Write|Edit): контроль ASCII-пунктуации в тексте, который пишет Claude.
// Проверяется только записанный фрагмент (content/new_string), а не весь файл,
// чтобы не срабатывать на тире, уже лежавшие в файле до правки.
let raw = '';
process.stdin.on('data', (d) => (raw += d));
process.stdin.on('end', () => {
  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0); // битый вход - не блокируем работу
  }
  const ti = (input && input.tool_input) || {};
  const text = ti.content != null ? ti.content : ti.new_string != null ? ti.new_string : '';
  // U+2013 en dash, U+2014 em dash, U+2015 horizontal bar
  const bad = /[–—―]/;
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
        ') есть длинное/среднее тире, строки фрагмента: ' +
        hits.join(', ') +
        '. Замени на дефис, двоеточие или запятую по смыслу и перезапиши.',
    })
  );
  process.exit(0);
});
