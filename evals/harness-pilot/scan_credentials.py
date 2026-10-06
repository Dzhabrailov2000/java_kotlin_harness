#!/usr/bin/env python3
"""Inspect saved captures without printing or recording matched credential values."""
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS = {'authorization', 'proxyauthorization', 'accesstoken', 'refreshtoken',
        'idtoken', 'sessiontoken', 'apikey', 'clientsecret', 'password'}
PATTERNS = {
    'anthropic_credential': re.compile(r'\bsk-ant-(?:api\d*|oat\d*)-[A-Za-z0-9_-]{20,}'),
    'openai_credential': re.compile(r'\bsk-(?:proj-|svcacct-)[A-Za-z0-9_-]{20,}'),
    'bearer_credential': re.compile(r'\bBearer\s+[A-Za-z0-9._~-]{30,}'),
}


def inspect_keys(value, filename, hits, location='$'):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r'[^a-z0-9]', '', key.lower())
            if normalized in KEYS and child not in (None, '', [], {}):
                hits.append({'file': filename, 'key_path': location + '.' + key,
                             'value_type': type(child).__name__})
            inspect_keys(child, filename, hits, location + '.' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            inspect_keys(child, filename, hits, location + '[' + str(index) + ']')


def main():
    files = sorted(set(list((ROOT / 'runs').glob('R*/http/*'))
                       + list((ROOT / 'runs').glob('R*/stdout.jsonl'))
                       + list((ROOT / 'runs').glob('R*/stderr.txt'))))
    hits = []
    records = 0
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(errors='replace')
        name = str(path.relative_to(ROOT))
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                hits.append({'file': name, 'pattern': label})
        try:
            record = json.loads(text)
        except ValueError:
            for line in text.splitlines():
                if line.startswith('data:'):
                    line = line[5:].strip()
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                records += 1
                inspect_keys(record, name, hits)
        else:
            records += 1
            inspect_keys(record, name, hits)
    result = {
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'Captured request/response bodies, metadata, stdout/stderr. '
                 'Key and prefix scan is not exhaustive secret detection. '
                 'Run after the main runner exits for a stable final snapshot.',
        'files': len(files), 'json_records': records, 'hits': hits,
    }
    (ROOT / 'credential-scan.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'files': len(files), 'json_records': records, 'hits': hits}, ensure_ascii=False))


if __name__ == '__main__':
    main()
