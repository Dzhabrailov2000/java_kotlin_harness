#!/usr/bin/env node
// PostToolUse hook (Write|Edit): ASCII punctuation control over the text Claude writes.
// Only the written fragment (content/new_string) is checked, not the whole file, so a dash that
// was already in the file before the edit does not block the write.
let raw = '';
process.stdin.on('data', (d) => (raw += d));
process.stdin.on('end', () => {
  let input;
  try {
    input = JSON.parse(raw);
  } catch {
    process.exit(0); // malformed input: never block the work over it
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
  const file = ti.file_path || 'the file';
  console.log(
    JSON.stringify({
      decision: 'block',
      reason:
        'ASCII punctuation: the written text (' +
        file +
        ') contains an em or en dash, at these lines of the fragment: ' +
        hits.join(', ') +
        '. Replace it with a hyphen, a colon or a comma as the sentence needs, then write again.',
    })
  );
  process.exit(0);
});
