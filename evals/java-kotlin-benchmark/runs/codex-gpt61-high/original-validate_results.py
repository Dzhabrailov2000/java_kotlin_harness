#!/usr/bin/env python3
"""Check experiment accounting, frozen prompts and offline report integrity."""
import argparse
import json
from pathlib import Path
import re
import run_benchmark as runner
import build_report

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='codex-gpt61-high')
    parser.add_argument('--partial', action='store_true')
    args = parser.parse_args()
    manifest = runner.verify_frozen()
    for frozen_skill in (ROOT / 'frozen/skills').glob('*/SKILL.md'):
        relative = frozen_skill.relative_to(ROOT / 'frozen')
        assert (ROOT.parent.parent / relative).read_bytes() == frozen_skill.read_bytes()
        installed = Path.home() / '.claude/skills' / frozen_skill.parent.name / 'SKILL.md'
        assert installed.read_bytes() == frozen_skill.read_bytes(), 'Installed skill drift: ' + str(installed)
    cases = runner.read(ROOT / 'frozen/evals/java-kotlin-suite/cases.json')
    rubric = runner.read(ROOT / 'frozen/evals/java-kotlin-suite/rubrics.json')
    assert len(cases) == 60 and len({c['skill'] for c in cases}) == 30
    assert {r['id'] for r in rubric} == {c['id'] for c in cases}
    expected = {(c['id'], arm) for c in cases for arm in ['A', 'B']}
    assert len(manifest['order']) == 120
    assert {(r['id'], r['arm']) for r in manifest['order']} == expected
    root = ROOT / 'runs' / args.run
    metadata = runner.read(root / 'run.json')
    count = 0
    for case in cases:
        for arm in ['A', 'B']:
            folder = root / 'trials' / (case['id'] + '-' + arm)
            if not (folder / 'result.json').exists():
                assert args.partial, 'Missing trial: ' + folder.name
                continue
            result = runner.read(folder / 'result.json')
            assert result['status'] == 'completed', (folder.name, result['status'])
            assert result['runner_sha256'] == metadata['runner_sha256']
            prompt = runner.trial_prompt(case, arm)
            assert (folder / 'prompt.txt').read_text() == prompt
            assert runner.digest(prompt.encode()) == result['prompt_sha256']
            assert result['tool_events'] == 0
            answer = runner.read(folder / 'answer.json')
            assert set(answer) == {'verdict', 'findings', 'summary'}
            assert answer['verdict'] in ['issue', 'ok']
            assert isinstance(answer['summary'], str)
            for finding in answer['findings']:
                assert set(finding) == {'problem', 'evidence', 'fix'}
                assert all(isinstance(v, str) for v in finding.values())
            events = [json.loads(line) for line in (folder / 'stdout.txt').read_text().splitlines() if line.startswith('{')]
            item_types = {e.get('item', {}).get('type') for e in events if 'item' in e}
            assert item_types <= {'error', 'agent_message', 'reasoning'}, item_types
            usage = [e['usage'] for e in events if e.get('type') == 'turn.completed']
            assert len(usage) == 1 and usage[0] == result['usage']
            assert all(isinstance(v, int) and v >= 0 for v in usage[0].values())
            assert usage[0]['cached_input_tokens'] <= usage[0]['input_tokens']
            assert usage[0].get('reasoning_output_tokens', 0) <= usage[0]['output_tokens']
            assert json.loads((folder / 'answer.txt').read_text()) == answer
            count += 1
    data = build_report.summarize(args.run)
    assert sum(data['pairs'].values()) == 60
    assert data['metrics']['A']['completed'] + data['metrics']['B']['completed'] == count
    if not args.partial:
        assert count == 120 and data['judge_completed'] == 60
        assert data['pairs'].get('ungraded', 0) == 0
        for row in data['rows']:
            for arm in ['A', 'B']:
                grade = row['arms'][arm]['judge']
                assert grade is not None
                assert all(type(v) is bool for v in grade['must_met'] + grade['must_not_violated'])
                assert type(grade['false_positive']) is bool and type(grade['harmful_advice']) is bool
        checked = set(data['manual_audit']['checked'])
        differences = {r['id'] for r in data['rows'] if r['arms']['A']['pass'] != r['arms']['B']['pass']}
        assert differences <= checked, 'Author audit missing a discordant pair'
    report = ROOT / 'report.html'
    if report.exists():
        content = report.read_text()
        match = re.search(r'<script id="data" type="application/json">(.*?)</script>', content, re.S)
        embedded = json.loads(match.group(1))
        assert len(embedded['rows']) == 60 and len(embedded['skills']) == 30
        if not args.partial:
            assert embedded['metrics'] == data['metrics']
            assert embedded['pairs'] == data['pairs']
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', content)
        print('Offline report: 60 cases, 30 embedded skills; no external script/style dependencies')
    print(json.dumps({'validated_trials': count, 'judged_pairs': data['judge_completed'],
                      'pairs': data['pairs'], 'partial_mode': args.partial}, ensure_ascii=False))


if __name__ == '__main__':
    main()
