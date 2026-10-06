#!/usr/bin/env python3
"""Validate report consistency and local links without executing browser content."""
import json
from html.parser import HTMLParser
from pathlib import Path
from run import verify_frozen

ROOT=Path(__file__).resolve().parent


class Document(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[];self.scripts=[];self.in_script=False
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values:self.ids.append(values['id'])
        if tag=='a' and 'href' in values:self.links.append(values['href'])
        if tag=='script':self.in_script=True
    def handle_endtag(self,tag):
        if tag=='script':self.in_script=False
    def handle_data(self,text):
        if self.in_script:self.scripts.append(text)


def main():
    manifest=verify_frozen();summary=json.loads((ROOT/'summary.json').read_text())
    document=Document();document.feed((ROOT/'report.html').read_text())
    assert len(document.ids)==len(set(document.ids)),'Duplicate HTML ids'
    assert set(s['id'] for s in manifest['order']).issubset(document.ids),'Missing attempts'
    missing=[]
    for link in document.links:
        if link.startswith(('https://','http://')):continue
        if link.startswith('#'):
            if link[1:] not in document.ids:missing.append(link)
        elif not (ROOT/link).exists():missing.append(link)
    assert not missing,missing
    rows=[json.loads(p.read_text()) for p in (ROOT/'runs').glob('R*/result.json')]
    assert summary['completed']==len(rows)
    assert len({r['evidence']['session_id'] for r in rows})==len(rows),'Session reused'
    assert len({r['workspace'] for r in rows})==len(rows),'Workspace reused'
    assert all(not r['evidence']['unexpected_context_markers'] for r in rows),'Unexpected personal context'
    fresh=[]
    for row in rows:
        directory=ROOT/'runs'/row['id']
        for path in sorted((directory/'http').glob('*-request.json')):
            request=json.loads(path.read_text())
            if not request.get('model'):continue
            messages=request.get('messages',request.get('input',[]))
            roles=[m.get('role') for m in messages if isinstance(m,dict)]
            assert 'assistant' not in roles,(row['id'],'Assistant history at start')
            assert not request.get('previous_response_id'),(row['id'],'Previous response at start')
            fresh.append(row['id']);break
    result={'html_ids_unique':True,'local_links_exist':True,'frozen_inputs_unchanged':True,
            'sessions_and_workspaces_unique':True,'completed':len(rows),
            'fresh_initial_requests':fresh,
            'valid_attempts':sum(r['valid_attempt'] for r in rows),
            'browser_visual_check':'Unavailable: browser tool rejected file URL; static HTML checked only.'}
    (ROOT/'report-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
