#!/usr/bin/env python3
import datetime
import hashlib
import json
import platform
import random
import subprocess
from pathlib import Path
from clients import ROOT,MODELS
from evidence import files


def capture(argv):
    p=subprocess.run(argv,text=True,capture_output=True,check=True)
    return (p.stdout+p.stderr).strip()


def main():
    if (ROOT/'experiment.json').exists():raise SystemExit('Experiment is already frozen')
    validation=sorted((ROOT/'fixture-validation').glob('*/inputs.json'))[-1].parent
    results=json.loads((validation/'summary.json').read_text())
    if len(results)!=16 or not all(r['valid'] for r in results):raise SystemExit('Final fixture validation is incomplete')
    inputs=json.loads((validation/'inputs.json').read_text())
    for name,digests in inputs.items():
        if files(ROOT/'tasks'/name)!=digests:raise SystemExit('Fixture changed after validation: '+name)
    probes=json.loads((ROOT/'preflight-summary.json').read_text())
    if len(probes)!=4 or not all(p['context_valid'] and p['client_completed'] for p in probes):
        raise SystemExit('Client preflight is incomplete')
    environment={'captured':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'platform':platform.platform(),'python':platform.python_version(),
        'claude':capture(['claude','--version']),'codex':capture(['codex','--version']),
        'java':capture(['java','-version']),
        'docker':capture(['docker','version','--format','{{.Server.Version}}']),
        'postgres_image':capture(['docker','image','inspect','--format','{{.Id}}','postgres:16']),
        'source_commit':capture(['git','-C',str(ROOT.parent.parent),'rev-parse','HEAD']),
        'models':MODELS,'auth':'Existing subscription authentication; no auth files copied.',
        'model_caps':None,'gradle':'9.5.1; see gradle_runtime for launcher and daemon JVM',
        'build':'Offline cached dependencies; compilation target/toolchain JDK 21',
        'sandbox':'One outer macOS sandbox-exec; no nested Codex sandbox; targeted read/write exclusions.'}
    environment['gradle_runtime']=capture(['gradle','--version'])
    (ROOT/'environment.json').write_text(json.dumps(environment,ensure_ascii=False,indent=2)+'\n')
    seed=20261006;rng=random.Random(seed)
    tasks=[f'T{i:02d}' for i in range(1,9)];rng.shuffle(tasks)
    firsts={engine:['A']*4+['B']*4 for engine in MODELS}
    for arms in firsts.values():rng.shuffle(arms)
    order=[]
    for i,task in enumerate(tasks):
        engines=list(MODELS);rng.shuffle(engines)
        for engine in engines:
            first=firsts[engine][i]
            for arm in [first,'B' if first=='A' else 'A']:
                order.append({'id':f'R{len(order)+1:02d}','task':task,'engine':engine,'arm':arm})
    names=[]
    for folder in ['tasks','snapshot']:
        names += [folder+'/'+name for name in files(ROOT/folder)]
    names += [p.name for p in ROOT.glob('*.py')]
    names += ['PROTOCOL.md','environment.json','snapshot-manifest.json','preflight-summary.json']
    frozen={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}
    manifest={'version':'pilot-v1','frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'seed':seed,'order':order,'fixture_validation':str(validation.relative_to(ROOT)),
        'models':MODELS,'frozen_files':frozen}
    manifest['input_digest']=hashlib.sha256(json.dumps(frozen,sort_keys=True).encode()).hexdigest()
    (ROOT/'experiment.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'frozen_files':len(frozen),'digest':manifest['input_digest'],'order':order},indent=2))


if __name__=='__main__':main()
