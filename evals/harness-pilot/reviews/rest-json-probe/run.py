#!/usr/bin/env python3
"""Observe scalar coercion on copied sources; never change frozen tests or primary scores."""
import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from verify_fixtures import run_check


def main():
    task = ROOT / 'tasks/T01'
    cases = [(rid, ROOT / 'runs' / rid / 'artifacts/src/main') for rid in ('R26', 'R27', 'R28')]
    cases.append(('frozen-oracle', task / 'oracle/src/main'))
    observations = {}
    for name, source in cases:
        work = Path(tempfile.mkdtemp(prefix='jkh-rest-json-probe-', dir='/private/tmp'))
        shutil.copytree(task / 'workspace', work, dirs_exist_ok=True)
        shutil.copytree(source, work / 'src/main', dirs_exist_ok=True)
        shutil.copyfile(HERE / 'RestJsonProbeTest.kt', work / 'src/test/kotlin/pilot/RestJsonProbeTest.kt')
        result = run_check(work, HERE / name, isolated=True)
        result['workspace'] = str(work)
        assert result['returncode'] == 0 and result['counts'] == {
            'tests': 2, 'failures': 0, 'errors': 0, 'skipped': 0
        }, (name, result)
        record = ET.parse(HERE / name / 'TEST-pilot.RestJsonProbeTest.xml').getroot()
        samples = [json.loads(line.removeprefix('POSTHOC_JSON '))
                   for line in (record.findtext('system-out') or '').splitlines()
                   if line.startswith('POSTHOC_JSON ')]
        assert len(samples) == 3, (name, samples)
        observations[name] = {'samples': samples, 'execution': result}
        print(json.dumps({name: samples}), flush=True)
    (HERE / 'observations.json').write_text(json.dumps(observations, indent=2) + '\n')


if __name__ == '__main__':
    main()
