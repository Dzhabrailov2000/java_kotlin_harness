import hashlib
import json
import re
from pathlib import Path

IGNORED={'.git','.gradle','build','__pycache__'}


def files(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob('*')) if p.is_file() and not p.is_symlink()
            and not any(part in IGNORED for part in p.relative_to(root).parts)}


def jsonlines(path):
    result=[]
    for line in path.read_text().splitlines():
        try:result.append(json.loads(line))
        except ValueError:pass
    return result


def summarize(directory,engine,arm):
    events=jsonlines(directory/'stdout.jsonl')
    requests=[]
    for path in sorted((directory/'http').glob('*-request.json')):
        obj=json.loads(path.read_text())
        if obj.get('model'):requests.append(obj)
    request_text=[json.dumps(obj,ensure_ascii=False) for obj in requests]
    contamination=[]
    for path in (directory/'http').glob('*-meta.json'):
        contamination.extend(json.loads(path.read_text()).get('unexpected_context_markers',[]))
    tools=[];final='';session=None;usage={};complete=False;hooks=[];denials=[]
    if engine=='claude':
        for event in events:
            if event.get('subtype')=='init':session=event.get('session_id')
            if event.get('type')=='assistant':
                for block in event.get('message',{}).get('content',[]):
                    if block.get('type')=='tool_use':tools.append({'name':block['name'],'input':block.get('input',{})})
            if event.get('subtype')=='hook_response':hooks.append(event)
            if event.get('type')=='result':
                final=event.get('result','');complete=not event.get('is_error',True)
                raw=event.get('usage',{})
                usage={'input_total':sum(raw.get(k,0) for k in ['input_tokens','cache_creation_input_tokens','cache_read_input_tokens']),
                       'input_uncached':raw.get('input_tokens',0),'cache_write':raw.get('cache_creation_input_tokens',0),
                       'cache_read':raw.get('cache_read_input_tokens',0),'output':raw.get('output_tokens',0),
                       'list_price_estimate_usd':event.get('total_cost_usd'),'raw':raw}
                denials=event.get('permission_denials',[])
    else:
        for event in events:
            if event.get('type')=='thread.started':session=event.get('thread_id')
            if event.get('type')=='item.completed':
                item=event.get('item',{})
                if item.get('type')=='agent_message':final=item.get('text','')
            if event.get('type')=='turn.completed':
                raw=event.get('usage',{});complete=True
                usage={'input_total':raw.get('input_tokens',0),'cache_read':raw.get('cached_input_tokens',0),
                       'cache_write':raw.get('cache_write_input_tokens',0),'output':raw.get('output_tokens',0),
                       'list_price_estimate_usd':None,'raw':raw}
        # Function calls are captured at the wire because nested code-mode tools may not
        # appear individually in the CLI JSON stream.
        for path in sorted((directory/'http').glob('*-response.bin')):
            for line in path.read_text(errors='replace').splitlines():
                if not line.startswith('data: '):continue
                try:event=json.loads(line[6:])
                except ValueError:continue
                if event.get('type')=='response.output_item.done':
                    item=event.get('item',{})
                    if item.get('type') in ('function_call','custom_tool_call'):
                        tools.append({'name':item.get('name'),'namespace':item.get('namespace'),
                                      'input':item.get('arguments',item.get('input',''))})
    tool_text=json.dumps(tools,ensure_ascii=False)
    forbidden=[name for name in ['spawn_agent','followup_task','send_message_to_thread','create_thread',
                                 'collaboration.send_message','collaboration.list_agents',
                                 'collaboration.interrupt_agent','collaboration.wait_agent'] if name in tool_text]
    forbidden += [t['name'] for t in tools if t['name'] in ('Agent','Task')]
    forbidden += [t['name'] for t in tools if t['name'] in ('send_message','list_agents','interrupt_agent','wait_agent')]
    if re.search(r'\b(?:codex\s+(?:exec|--no-daemon)|claude\s+(?:-p\b|--print\b|--model\b))',tool_text):
        forbidden.append('nested_model_cli')
    skill_calls=[t for t in tools if t['name']=='Skill']
    skill_reads=[t for t in tools if 'SKILL.md' in json.dumps(t,ensure_ascii=False)]
    result={'session_id':session,'client_completed':complete,'model_requests':len(requests),
            'requested_models':sorted(set(r.get('model','') for r in requests)),
            'requested_efforts':[r.get('reasoning',r.get('output_config')) for r in requests],
            'core_present':any('Личные правила работы' in s for s in request_text),
            'kotlin_rule_present':any('ktlintFormat' in s and 'Без `!!`' in s for s in request_text),
            'skill_catalog_present':any('java-kotlin-naming' in s for s in request_text),
            'unexpected_context_markers':sorted(set(contamination)),
            'tool_calls':len(tools),'forbidden_delegation':forbidden,'skill_calls':skill_calls,
            'skill_file_accesses':skill_reads,'hook_responses':hooks,'permission_denials':denials,
            'usage':usage,'final':final}
    result['context_valid']=bool(requests) and not contamination and not forbidden and result['core_present']==(arm=='B')
    if arm=='A' and (result['kotlin_rule_present'] or result['skill_catalog_present']):result['context_valid']=False
    return result
