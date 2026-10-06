#!/usr/bin/env python3
"""One fresh CLI process per trial. No model workflow, auto-retries or model budgets."""
import argparse
import contextlib
import datetime
import difflib
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from clients import ROOT,MODELS,PROXY,child_env,command,install,sandbox_profile
from evidence import files,summarize,IGNORED
from observer import Observer
from transport import Recorder
from verify_fixtures import run_check

COMMON_PROMPT='''
Работай как один агент с инструментами в текущем самостоятельном проекте. Не делегируй, не запускай
другие модели, субагентов, многоагентный workflow или внешний review. Можно самостоятельно читать
файлы, менять код по заданию и запускать проверки. Не читай домашний каталог, другие проекты,
результаты других попыток и материалы оценивания. Не меняй сборку, существующие тесты и инструкции.
Для ответа используй текущие файлы и контракт задания. Не устанавливай инструменты и зависимости.
'''


def verify_frozen():
    manifest=json.loads((ROOT/'experiment.json').read_text())
    import hashlib
    for name,digest in manifest['frozen_files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen input changed: '+name)
    return manifest


def copy_artifacts(work,destination):
    destination.mkdir(parents=True)
    for path in sorted(work.rglob('*')):
        relative=path.relative_to(work)
        if any(part in IGNORED for part in relative.parts) or not path.is_file():continue
        if path.is_symlink():raise RuntimeError('Symlink in output: '+str(relative))
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)


def grade_code(task,work,out):
    scratch=Path(tempfile.mkdtemp(prefix='jkh-verifier-',dir='/private/tmp'))
    shutil.copytree(task/'workspace',scratch,dirs_exist_ok=True)
    # Only submitted production sources enter the trusted grader. Agent tests are preserved
    # in artifacts and transcripts, but cannot replace or configure independent checks.
    production=scratch/'src/main'
    if production.exists():shutil.rmtree(production)
    if (work/'src/main').exists():shutil.copytree(work/'src/main',production)
    shutil.copytree(task/'verifier',scratch,dirs_exist_ok=True)
    result=run_check(scratch,out,isolated=True)
    result['workspace']=str(scratch)
    required=json.loads((task/'task.json').read_text()).get('expected_test_count',2)
    result['required_test_count']=required
    result['pass']=result['pass'] and result['counts']['tests']>=required
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def trial(spec):
    run_id=spec['id'];task=ROOT/'tasks'/spec['task'];engine=spec['engine'];arm=spec['arm']
    output=ROOT/'runs'/run_id
    if output.exists():raise RuntimeError('Refusing to overwrite attempt '+run_id)
    output.mkdir(parents=True)
    work=Path('/private/tmp/jkh-agent-pilot')/('trial-'+uuid.uuid4().hex)/'workspace'
    shutil.copytree(task/'workspace',work)
    install(work,engine,arm)
    # Create hook configuration before hashing the initial workspace.
    command(engine,work,arm,'http://127.0.0.1:1')
    profile=output/'sandbox.sb';profile.write_text(sandbox_profile(work))
    prompt=(task/'instruction.md').read_text()+'\n'+COMMON_PROMPT
    (output/'prompt.txt').write_text(prompt)
    task_spec=json.loads((task/'task.json').read_text())
    observer_context=Observer(output/'sql-diagnostic') if task_spec['postgres'] else contextlib.nullcontext()
    result={**spec,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'workspace':str(work)}
    (output/'started.json').write_text(json.dumps(result,indent=2)+'\n')
    with observer_context as observer:
        if observer:(work/'.pilot-runtime.json').write_text(json.dumps({'sql_observer':observer.url})+'\n')
        initial=files(work);(output/'initial-files.json').write_text(json.dumps(initial,indent=2)+'\n')
        upstream='https://chatgpt.com' if engine=='codex' else 'https://api.anthropic.com'
        with Recorder(output/'http',upstream,PROXY) as recorder:
            argv=command(engine,work,arm,recorder.url)
            (output/'command.json').write_text(json.dumps(argv,ensure_ascii=False,indent=2)+'\n')
            started=time.monotonic()
            with (output/'stdout.jsonl').open('w') as stdout,(output/'stderr.txt').open('w') as stderr:
                proc=subprocess.Popen(['sandbox-exec','-f',str(profile),*argv],cwd=work,stdin=subprocess.PIPE,
                                      stdout=stdout,stderr=stderr,text=True,env=child_env(engine,recorder.url))
                proc.communicate(prompt)
            result.update(returncode=proc.returncode,seconds=round(time.monotonic()-started,3),http_requests=recorder.sequence)
        if observer:result['sql_diagnostic_calls']=observer.calls
    copy_artifacts(work,output/'artifacts')
    final_files=files(work);result['changed_files']=[name for name in sorted(initial.keys()|final_files.keys()) if initial.get(name)!=final_files.get(name)]
    protected=[]
    for name in result['changed_files']:
        if name.startswith(('src/test/','.claude/','.agents/')) and name in initial:protected.append(name)
        elif name in ['build.gradle.kts','settings.gradle.kts','gradle.properties','gradlew','AGENTS.md','CLAUDE.md','observe-locks','.pilot-runtime.json']:protected.append(name)
        elif task_spec['kind']=='review' and name.startswith(('src/main/','migrations/')):protected.append(name)
    result['protected_file_changes']=sorted(set(protected))
    diffs=[]
    for name in result['changed_files']:
        if name.startswith(('src/','migrations/')):
            old=task/'workspace'/name;new=work/name
            diffs.extend(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],
                         new.read_text().splitlines(True) if new.exists() else [],fromfile='before/'+name,tofile='after/'+name))
    (output/'change.diff').write_text(''.join(diffs))
    evidence=summarize(output,engine,arm);result['evidence']=evidence
    (output/'final.txt').write_text(evidence['final'])
    if task_spec['kind']!='review':
        result['grader']=grade_code(task,output/'artifacts',output/'grader')
        result['task_pass']=result['grader']['pass'] and not protected
    else:
        review=work/'review.json'
        try:
            value=json.loads(review.read_text())
            assert isinstance(value,dict) and isinstance(value['findings'],list)
            for finding in value['findings']:
                assert all(key in finding for key in ['file','line','severity','problem','scenario','fix'])
                assert finding['severity'] in ('critical','major') and isinstance(finding['line'],int) and finding['line']>0
            result['review']=value;result['review_schema_valid']=True
        except (OSError,ValueError,KeyError,AssertionError,TypeError):
            result['review_schema_valid']=False
        result['task_pass']=None # Independently judged, not keyword-matched.
    result['valid_attempt']=evidence['context_valid'] and proc.returncode==0 and evidence['client_completed']
    expected_model,effort=MODELS[engine]
    result['valid_attempt']=result['valid_attempt'] and evidence['requested_models']==[expected_model]
    result['valid_attempt']=result['valid_attempt'] and all(isinstance(e,dict) and e.get('effort')==effort for e in evidence['requested_efforts'])
    result['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['id','task','engine','arm','seconds','valid_attempt','task_pass']},ensure_ascii=False),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append');args=parser.parse_args()
    manifest=verify_frozen()
    for spec in manifest['order']:
        if args.run and spec['id'] not in args.run:continue
        if (ROOT/'runs'/spec['id']/'result.json').exists():continue
        if (ROOT/'runs'/spec['id']).exists():raise RuntimeError('Interrupted attempt requires explicit disposition: '+spec['id'])
        trial(spec)


if __name__=='__main__':main()
