#!/usr/bin/env python3
import argparse
import datetime
import json
import subprocess
from pathlib import Path
from clients import ROOT, PROXY, child_env, command, install, sandbox_profile
from transport import Recorder


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('engine',choices=['codex','claude'])
    parser.add_argument('arm',choices=['A','B'])
    args=parser.parse_args()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
    output=ROOT/'preflight'/f'{stamp}-{args.engine}-{args.arm}'
    output.mkdir(parents=True)
    work=Path('/private/tmp/jkh-agent-pilot')/output.name/'workspace'
    work.mkdir(parents=True)
    (work/'Probe.kt').write_text('val fixture = \"FIXTURE_INPUT_17\"\n')
    install(work,args.engine,args.arm)
    profile=output/'sandbox.sb';profile.write_text(sandbox_profile(work))
    prompt=('Прочитай Probe.kt инструментом, затем через терминал выполни python3 -c "print(17+25)". '
            'Запиши обычным инструментом редактирования в probe-output.txt значение из файла и результат вычисления. '
            'Это техническая проверка инструментов; ничего другого делать не нужно. Работай только в текущем каталоге, '
            'не делегируй задачу. В конце сообщи, что получилось.')
    (output/'prompt.txt').write_text(prompt)
    upstream='https://chatgpt.com' if args.engine=='codex' else 'https://api.anthropic.com'
    with Recorder(output/'http',upstream,PROXY) as recorder:
        argv=command(args.engine,work,args.arm,recorder.url)
        (output/'command.json').write_text(json.dumps(argv,ensure_ascii=False,indent=2)+'\n')
        with (output/'stdout.jsonl').open('w') as stdout,(output/'stderr.txt').open('w') as stderr:
            proc=subprocess.Popen(['sandbox-exec','-f',str(profile),*argv],cwd=work,stdin=subprocess.PIPE,
                                  stdout=stdout,stderr=stderr,text=True,env=child_env(args.engine,recorder.url))
            proc.communicate(prompt)
        result={'returncode':proc.returncode,'workspace':str(work),'engine':args.engine,'arm':args.arm,
                'requests':recorder.sequence,'output':(work/'probe-output.txt').read_text() if (work/'probe-output.txt').exists() else None}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(output,flush=True);print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
