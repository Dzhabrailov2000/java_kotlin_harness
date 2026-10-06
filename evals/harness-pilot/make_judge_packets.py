#!/usr/bin/env python3
"""Build stable anonymous packets. Does not alter frozen solver inputs or results."""
import hashlib
import json
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    manifest=json.loads((ROOT/'experiment.json').read_text())
    ids=[row['id'] for row in manifest['order']]
    random.Random(739101).shuffle(ids)
    mapping={f'P{i+1:02d}':name for i,name in enumerate(ids)}
    out=ROOT/'blind';out.mkdir(exist_ok=True)
    (ROOT/'blind-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
    validation=ROOT/manifest['fixture_validation']
    proofs=json.loads((validation/'summary.json').read_text())
    for packet_id,run_id in mapping.items():
        folder=ROOT/'runs'/run_id
        if not (folder/'result.json').exists():continue
        result=json.loads((folder/'result.json').read_text());task=ROOT/'tasks'/result['task']
        spec=json.loads((task/'task.json').read_text())
        base=task/'workspace';submitted=folder/'artifacts'
        sources={str(p.relative_to(base)):p.read_text() for parent in ['src/main','migrations']
                 for p in sorted((base/parent).rglob('*')) if p.is_file()}
        code={str(p.relative_to(submitted)):p.read_text() for p in sorted((submitted/'src/main').rglob('*')) if p.is_file()}
        proof=[{k:v for k,v in p.items() if k not in ('workspace','seconds','command')} for p in proofs if p['task']==spec['id']]
        packet={'id':packet_id,'task':spec['id'],'kind':spec['kind'],
                'instruction':(task/'instruction.md').read_text(),'original':sources,'submitted':code,
                'review':result.get('review'),'rubric':spec['rubric'],'fixture_proof':proof,
                'grader_counts':result.get('grader',{}).get('counts'),
                'protected_file_changes':result['protected_file_changes']}
        if not result['valid_attempt']:
            packet['execution_status']={
                'protocol_valid':False,
                'client_completed':bool(result['evidence']['client_completed']),
                'client_exit_success':result['returncode']==0,
                'note':'Attempt did not complete as a valid protocol run. Files may be partial or unchanged; do not treat them as a completed submitted solution.'}
        contents=json.dumps(packet,ensure_ascii=False,indent=2)+'\n'
        path=out/(packet_id+'.json')
        if path.exists() and path.read_text()!=contents:raise RuntimeError('Anonymous packet changed: '+packet_id)
        path.write_text(contents)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('P*.json'))}
    (out/'manifest.json').write_text(json.dumps(files,indent=2)+'\n')
    print('Packets ready:',len(files))


if __name__=='__main__':main()
