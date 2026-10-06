#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from evidence import files

ROOT=Path(__file__).resolve().parent


def postgres():
    name='jkh-pilot-pg-'+uuid.uuid4().hex[:12]
    subprocess.run(['docker','run','--pull=never','--rm','-d','--network','none','--name',name,
                    '-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:16'],check=True,capture_output=True,text=True)
    while True:
        # The image's temporary initialization server accepts Unix sockets before restarting.
        # TCP readiness observes only the final server and avoids a false startup success.
        p=subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','postgres'],capture_output=True)
        if p.returncode==0:return name
        state=subprocess.run(['docker','inspect','--format','{{.State.Running}}',name],capture_output=True,text=True)
        if state.returncode or state.stdout.strip()!='true':raise RuntimeError('PostgreSQL stopped before ready')
        time.sleep(.25)


def run_check(work,out,sql=False,pg=None,isolated=False):
    out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    if sql:env['PILOT_PG_CONTAINER']=pg
    argv=['python3','verify_sql.py'] if sql else ['./gradlew','test','--no-build-cache']
    if isolated:
        from clients import sandbox_profile
        profile=out/'sandbox.sb';profile.write_text(sandbox_profile(work))
        argv=['sandbox-exec','-f',str(profile),*argv]
    start=time.monotonic()
    with (out/'stdout.txt').open('w') as stdout,(out/'stderr.txt').open('w') as stderr:
        proc=subprocess.run(argv,cwd=work,env=env,stdout=stdout,stderr=stderr)
    result={'returncode':proc.returncode,'seconds':round(time.monotonic()-start,3),'command':argv}
    if sql:
        p=work/'lock-observation.json'
        result['observation']=json.loads(p.read_text()) if p.exists() else None
        result['executed']=bool(result['observation'] and result['observation']['applied']
                                and result['observation']['lock_modes_during_validation'])
    else:
        files=list(work.glob('build/test-results/test/TEST-*.xml'))
        counts={key:0 for key in ['tests','failures','errors','skipped']}
        for p in files:
            tree=ET.parse(p).getroot()
            for key in counts: counts[key]+=int(tree.attrib.get(key,0))
            shutil.copyfile(p,out/p.name)
        result['counts']=counts
        result['executed']=counts['tests']>1
    result['pass']=proc.returncode==0 and result['executed'] and (sql or not result['counts']['skipped'])
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--task',action='append');args=parser.parse_args()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    output=ROOT/'fixture-validation'/stamp
    output.mkdir(parents=True)
    inputs={}
    results=[]
    for task in sorted((ROOT/'tasks').iterdir()):
        if args.task and task.name not in args.task:continue
        spec=json.loads((task/'task.json').read_text())
        inputs[task.name]=files(task)
        base_pass=spec['kind']=='review' and not spec['rubric']['has_issue']
        variants=[('base',base_pass),('mutation',False)] if base_pass else [('base',False),('oracle',True)]
        for variant,expected in variants:
            work=Path(tempfile.mkdtemp(prefix='jkh-verifier-',dir='/private/tmp'))
            shutil.copytree(task/'workspace',work,dirs_exist_ok=True)
            if variant!='base':shutil.copytree(task/variant,work,dirs_exist_ok=True)
            shutil.copytree(task/'verifier',work,dirs_exist_ok=True)
            container=postgres() if spec['postgres'] else None
            try: result=run_check(work,output/task.name/variant,spec['postgres'],container)
            finally:
                if container:subprocess.run(['docker','stop',container],capture_output=True)
            result.update(task=task.name,variant=variant,expected=expected,workspace=str(work))
            result['valid']=result['executed'] and result['pass']==expected
            if not spec['postgres']:
                result['valid']=result['valid'] and result['counts']['tests']==spec['expected_test_count']
            results.append(result)
            print(task.name,variant,'VALID' if result['valid'] else 'INVALID',result,flush=True)
    output.mkdir(parents=True,exist_ok=True)
    (output/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    (output/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    print(output,flush=True)
    raise SystemExit(0 if all(r['valid'] for r in results) else 1)


if __name__=='__main__':main()
