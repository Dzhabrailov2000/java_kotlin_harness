#!/usr/bin/env python3
"""Preserve client transport fallbacks separately from task outcome and primary usage."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def inspect_response(path):
    if not path.exists():
        return {'format': 'missing', 'completed': False, 'terminal_events': []}
    text = path.read_text(errors='replace')
    try:
        body = json.loads(text)
    except ValueError:
        events = []
        has_stream_data = False
        for line in text.splitlines():
            if not line.startswith('data:'):
                continue
            has_stream_data = True
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            if event.get('type') in ('message_stop', 'response.completed',
                                    'response.failed', 'response.incomplete', 'error'):
                events.append(event['type'])
        return {'format': 'stream' if has_stream_data else 'unparsed', 'completed': any(e in ('message_stop', 'response.completed')
                                                    for e in events), 'terminal_events': events}
    complete = ((body.get('type') == 'message' and body.get('stop_reason') is not None)
                or body.get('status') == 'completed')
    return {'format': 'json', 'completed': complete,
            'terminal_events': [body.get('type', body.get('object', 'unknown'))],
            'stop_reason': body.get('stop_reason')}


def main():
    output = {}
    for directory in sorted((ROOT / 'runs').glob('R*')):
        if not (directory / 'result.json').exists():
            continue
        requests = []
        contexts = {}
        for path in sorted((directory / 'http').glob('*-request.json')):
            body = json.loads(path.read_text())
            if not body.get('model'):
                continue
            key = path.name.removesuffix('-request.json')
            response = inspect_response(path.with_name(key + '-response.bin'))
            meta_path = path.with_name(key + '-response-meta.json')
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            # Same prompt/tools; a changed output limit or streaming mode remains visible below.
            context = {k: v for k, v in body.items() if k not in ('stream', 'max_tokens')}
            digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
            requests.append({'request': path.name, 'http_status': meta.get('status'),
                             'stream_requested': body.get('stream'), 'max_tokens': body.get('max_tokens'),
                             'same_context_as': contexts.get(digest), **response})
            contexts[digest] = path.name
        output[directory.name] = {
            'requests': requests,
            'responses_without_completion': sum(not r['completed'] for r in requests),
            'same_context_resubmissions': sum(r['same_context_as'] is not None for r in requests),
            'method': 'Only model requests; SSE terminal events or non-stream JSON stop_reason. '
                      'Same context comparison excludes stream and max_tokens only. '
                      'Client wall time and reported usage stay unchanged.'}
    (ROOT / 'transport-observations.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({rid: {'responses_without_completion': r['responses_without_completion'],
                           'same_context_resubmissions': r['same_context_resubmissions']}
                      for rid, r in output.items()
                      if r['responses_without_completion'] or r['same_context_resubmissions']}))


if __name__ == '__main__':
    main()
