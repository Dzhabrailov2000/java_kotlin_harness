#!/usr/bin/env python3
"""Verify frozen inputs, both CLI log formats, accounting and the offline report."""
import argparse
import json
from pathlib import Path
import re
import run_benchmark as runner
import build_report

ROOT = Path(__file__).resolve().parent


def validate_call(folder, metadata, sessions, workdirs):
    result = runner.read(folder / 'result.json')
    assert result['status'] == 'completed', (str(folder), result['status'])
    assert result['runner_sha256'] == metadata['runner_sha256']
    assert result['model_requested'] == metadata['model']
    assert result['engine'] == metadata['engine'] and result['effort'] == metadata['effort']
    assert runner.digest((folder / 'prompt.txt').read_bytes()) == result['prompt_sha256']
    assert result['tool_events'] == 0
    answer = runner.read(folder / 'answer.json')
    assert json.loads((folder / 'answer.txt').read_text()) == answer
    events = [json.loads(line) for line in (folder / 'stdout.txt').read_text().splitlines() if line.startswith('{')]
    if metadata['engine'] == 'codex':
        item_types = {e.get('item', {}).get('type') for e in events if 'item' in e}
        assert item_types <= {'error', 'agent_message', 'reasoning'}, item_types
        messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed' and
                    e.get('item', {}).get('type') == 'agent_message']
        assert len(messages) == 1 and json.loads(messages[0]) == answer, 'Codex answer differs from raw CLI output'
        usages = [e['usage'] for e in events if e.get('type') == 'turn.completed']
        assert len(usages) == 1 and usages[0] == result['usage']
        starts = [e for e in events if e.get('type') == 'thread.started']
        assert len(starts) == 1
        sid = starts[0]['thread_id']
        cmd = result['command']
        cwd = cmd[cmd.index('-C') + 1]
        assert all(f in cmd for f in ['--no-daemon', '--ephemeral', '--ignore-user-config', '--ignore-rules'])
    else:
        assert metadata['engine'] == 'claude'
        initial = [e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init']
        finals = [e for e in events if e.get('type') == 'result']
        assert len(initial) == len(finals) == 1
        init, final = initial[0], finals[0]
        assert init['tools'] == ['StructuredOutput']
        assert all(init[k] == [] for k in ['mcp_servers', 'skills', 'plugins', 'slash_commands'])
        assert init['model'] == metadata['model']
        assert final.get('is_error') is False
        assert not final.get('permission_denials')
        assert final['structured_output'] == answer and result['answer_source'] == 'structured_output'
        blocks = [b for e in events if e.get('type') == 'assistant'
                  for b in e.get('message', {}).get('content', [])
                  if b.get('type') in ['tool_use', 'server_tool_use']]
        assert blocks and all(b['type'] == 'tool_use' and b['name'] == 'StructuredOutput' for b in blocks)
        assert len(blocks) == result['structured_output_events']
        assert all(b['input'] == answer for b in blocks), 'Formatter differs from final answer'
        raw = final['usage']
        assert raw == result['raw_usage']
        usage = result['usage']
        assert usage['input_tokens'] == sum(raw.get(k, 0) for k in ['input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'])
        assert usage['cached_input_tokens'] == raw.get('cache_read_input_tokens', 0)
        assert usage['cache_creation_input_tokens'] == raw.get('cache_creation_input_tokens', 0)
        assert usage['uncached_input_tokens'] == raw['input_tokens']
        assert usage['output_tokens'] == raw['output_tokens']
        assert usage['reasoning_output_tokens'] == raw.get('output_tokens_details', {}).get('thinking_tokens', 0)
        assert all(v == 0 for v in raw.get('server_tool_use', {}).values())
        assert final['modelUsage'] == result['model_usage']
        assert set(final['modelUsage']) == {metadata['model']}
        assert result['cost_usd'] is None
        sid, cwd = init['session_id'], init['cwd']
        assert sid == final['session_id'] == result['session_id']
        cmd = result['command']
        assert all(f in cmd for f in ['--safe-mode', '--no-session-persistence', '--disable-slash-commands', '--strict-mcp-config', '--json-schema'])
        assert cmd[cmd.index('--tools') + 1] == ''
        assert cmd[cmd.index('--setting-sources') + 1] == ''
        assert json.loads(cmd[cmd.index('--json-schema') + 1]) == runner.read(folder / 'schema.json')
    usage = result['usage']
    assert all(type(v) is int and v >= 0 for v in usage.values())
    assert usage['cached_input_tokens'] <= usage['input_tokens']
    assert usage.get('reasoning_output_tokens', 0) <= usage['output_tokens']
    assert sid not in sessions and cwd not in workdirs, 'Session or workdir reused'
    sessions.add(sid)
    workdirs.add(cwd)
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='codex-gpt61-high')
    parser.add_argument('--partial', action='store_true')
    parser.add_argument('--data-only', action='store_true', help='Validate preserved results before rendering report')
    parser.add_argument('--snapshot-only', action='store_true', help='Validate the evaluated frozen snapshot; report live source/install drift separately, without certifying current skills')
    args = parser.parse_args()
    manifest = runner.verify_frozen()
    drift = build_report.live_skill_drift()
    for frozen_skill in (ROOT / 'frozen/skills').glob('*/SKILL.md'):
        relative = frozen_skill.relative_to(ROOT / 'frozen')
        if not args.snapshot_only:
            assert (ROOT.parent.parent / relative).read_bytes() == frozen_skill.read_bytes()
        for directory in ['.claude/skills', '.agents/skills']:
            installed = Path.home() / directory / frozen_skill.parent.name / 'SKILL.md'
            if not args.snapshot_only:
                assert installed.read_bytes() == frozen_skill.read_bytes(), 'Installed skill drift: ' + str(installed)
    cases = runner.read(ROOT / 'frozen/evals/java-kotlin-suite/cases.json')
    rubrics = runner.read(ROOT / 'frozen/evals/java-kotlin-suite/rubrics.json')
    assert len(cases) == 60 and len({c['skill'] for c in cases}) == 30
    assert {r['id'] for r in rubrics} == {c['id'] for c in cases}
    expected = {(c['id'], arm) for c in cases for arm in ['A', 'B']}
    assert len(manifest['order']) == 120
    assert {(r['id'], r['arm']) for r in manifest['order']} == expected
    root = ROOT / 'runs' / args.run
    metadata = runner.read(root / 'run.json')
    assert runner.digest((root / 'runner-snapshot.py').read_bytes()) == metadata['runner_sha256']
    assert runner.digest((ROOT / 'frozen/manifest.json').read_bytes()) == metadata['manifest_sha256']
    assert runner.digest(runner.BASE.encode()) == metadata['base_prompt_sha256']
    count, sessions, workdirs = 0, set(), set()
    for case in cases:
        for arm in ['A', 'B']:
            folder = root / 'trials' / (case['id'] + '-' + arm)
            if not (folder / 'result.json').exists():
                assert args.partial, 'Missing trial: ' + folder.name
                continue
            answer = validate_call(folder, metadata, sessions, workdirs)
            assert (folder / 'prompt.txt').read_text() == runner.trial_prompt(case, arm)
            assert set(answer) == {'verdict', 'findings', 'summary'}
            assert answer['verdict'] in ['issue', 'ok']
            assert isinstance(answer['summary'], str) and isinstance(answer['findings'], list)
            for finding in answer['findings']:
                assert set(finding) == {'problem', 'evidence', 'fix'}
                assert all(isinstance(v, str) for v in finding.values())
            count += 1
    labels_path = root / 'judge-label-key.json'
    labels = runner.read(labels_path) if labels_path.exists() else {}
    rubric_map = {r['id']: r for r in rubrics}
    for case in cases:
        folder = root / 'judges' / case['id']
        if not (folder / 'result.json').exists():
            assert args.partial, 'Missing judge: ' + case['id']
            continue
        grade = validate_call(folder, metadata, sessions, workdirs)
        assert set(labels[case['id']]) == {'X', 'Y'} and set(labels[case['id']].values()) == {'A', 'B'}
        answers = {label: (root / 'trials' / (case['id'] + '-' + arm) / 'answer.txt').read_text()
                   for label, arm in labels[case['id']].items()}
        assert (folder / 'prompt.txt').read_text() == runner.judge_prompt(case, rubric_map[case['id']], answers)
        assert {j['label'] for j in grade['judgments']} == {'X', 'Y'} and len(grade['judgments']) == 2
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
        required = {r['id'] for r in data['rows'] if r['arms']['A']['pass'] is False or r['arms']['B']['pass'] is False}
        plan = runner.read(root / 'audit-plan.json')
        required.update(plan['random_cases'])
        assert required <= checked, 'Author audit missing preselected or failing/discordant pairs'
        assert len(sessions) == len(workdirs) == 180
    report = ROOT / 'report.html'
    if report.exists() and not args.data_only:
        content = report.read_text()
        match = re.search(r'<script id="data" type="application/json">(.*?)</script>', content, re.S)
        embedded_all = json.loads(match.group(1))
        candidates = embedded_all.get('series', [embedded_all])
        embedded = next(s for s in candidates if s['run'] == args.run)
        assert len(embedded['rows']) == 60 and len(embedded['skills']) == 30
        if not args.partial:
            for key in ['run', 'run_config', 'display', 'observed_model_ids', 'metrics', 'pairs',
                        'rows', 'skills', 'manual_audit', 'judge_usage', 'judge_completed',
                        'manifest', 'protocol', 'claude_protocol', 'analysis_notes', 'selection', 'audit_response', 'live_skill_drift']:
                assert embedded[key] == data[key], 'Stale report: ' + key
            if 'series' in embedded_all:
                assert embedded_all['preflights'] == build_report.preflight_summary()
        assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\']https?://', content)
        print('Offline report: 60 cases, 30 embedded skills per series; no external script/style dependencies')
    print(json.dumps({'run': args.run, 'validated_trials': count, 'judged_pairs': data['judge_completed'],
                      'distinct_sessions': len(sessions), 'pairs': data['pairs'], 'partial_mode': args.partial,
                      'snapshot_only': args.snapshot_only, 'live_skill_drift': drift}, ensure_ascii=False))


if __name__ == '__main__':
    main()
