#!/usr/bin/env python3
"""Postprocessing only: confirm skill content in actual requests, beyond file listing."""
import json
import re
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def normalize(text):
    return ' '.join(text.replace('\\n','\n').replace('\\"','"').split())


def strings(value):
    if isinstance(value,str):
        yield value
        try:nested=json.loads(value)
        except ValueError:return
        if isinstance(nested,(dict,list)):yield from strings(nested)
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)


def main():
    lines={}
    for file in sorted((ROOT/'snapshot/skills').glob('java-kotlin-*/SKILL.md')):
        body=re.sub(r'\A---\n.*?\n---\n','',file.read_text(),flags=re.S)
        lines[file.parent.name]=[normalize(line) for line in body.splitlines() if len(line)>=70 and not line.startswith(('#','http','['))]
    frequency=Counter(line for group in lines.values() for line in set(group))
    anchors={name:[line for line in candidates if frequency[line]==1][:3] for name,candidates in lines.items()}
    assert all(len(group)>=2 for group in anchors.values()),'Insufficient unique skill anchors'
    result={}
    for directory in sorted((ROOT/'runs').glob('R*')):
        if not (directory/'result.json').exists():continue
        seen={};initial_names=None
        for path in sorted((directory/'http').glob('*-request.json')):
            obj=json.loads(path.read_text())
            if not obj.get('model'):continue
            if initial_names is None:
                initial_names=sorted(set(re.findall(r'java-kotlin-[a-z-]+',json.dumps(obj,ensure_ascii=False))))
            texts=[normalize(text) for text in strings(obj)]
            for name,phrases in anchors.items():
                if name in seen:continue
                matched=[phrase for phrase in phrases if any(phrase in text for text in texts)]
                if len(matched)>=2:seen[name]={'first_request':path.name,'matched_body_lines':matched}
        result[directory.name]={'skills':seen,'names_in_initial_request':initial_names or [],
            'method':'At least two distinct >=70-character body lines unique among 30 snapshot skills occur in actual request string values. Catalog and filename matches alone do not count.'}
    (ROOT/'skill-loading.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({name:list(value['skills']) for name,value in result.items()},ensure_ascii=False))


if __name__=='__main__':main()
