#!/usr/bin/env python3
"""Local, header-free request evidence for authorized CLI calls.

Credentials pass directly to the fixed upstream in memory and are never logged.
This is transport instrumentation, not an agent tool or an extra model workflow.
"""
import hashlib
import http.server
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path


class Recorder:
    def __init__(self, directory, upstream, proxy=None):
        if upstream not in ('https://chatgpt.com', 'https://api.anthropic.com'):
            raise ValueError('unsupported upstream')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.upstream = upstream
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https':proxy} if proxy else {}))
        self.lock = threading.Lock()
        self.sequence = 0
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def log_message(self, *_):
                pass

            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def forward(self):
                body = self.rfile.read(int(self.headers.get('Content-Length',0)))
                with owner.lock:
                    number = owner.sequence
                    owner.sequence += 1
                key = f'{number:04d}'
                request_meta = {'method':self.command,'path':self.path,
                                'body_sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
                try:
                    obj = json.loads(body)
                except (ValueError,UnicodeDecodeError):
                    obj = None
                if obj is not None:
                    rendered=json.dumps(obj,ensure_ascii=False)
                    markers=[s for s in ['Reactive UEM','Магнит','uem-task','uem-report','OPERCNT-'] if s in rendered]
                    request_meta['unexpected_context_markers']=markers
                    if not markers:
                        (owner.directory/f'{key}-request.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
                (owner.directory/f'{key}-meta.json').write_text(json.dumps(request_meta,indent=2)+'\n')
                if request_meta.get('unexpected_context_markers'):
                    self.send_error(400,'unexpected external context detected')
                    return
                headers={k:v for k,v in self.headers.items() if k.lower() not in
                         ('host','connection','content-length','accept-encoding','transfer-encoding')}
                headers['Accept-Encoding']='identity'
                req=urllib.request.Request(owner.upstream+self.path,data=body if self.command=='POST' else None,
                                           headers=headers,method=self.command)
                try:
                    response=owner.opener.open(req)
                except urllib.error.HTTPError as error:
                    response=error
                except Exception as error:
                    (owner.directory/f'{key}-error.json').write_text(json.dumps({'type':type(error).__name__})+'\n')
                    self.send_error(502,'upstream transport failed')
                    return
                with response:
                    self.send_response(response.status)
                    for k,v in response.headers.items():
                        if k.lower() in ('content-type','content-encoding','cache-control'):
                            self.send_header(k,v)
                    self.end_headers()
                    (owner.directory/f'{key}-response-meta.json').write_text(json.dumps({'status':response.status})+'\n')
                    with (owner.directory/f'{key}-response.bin').open('wb') as log:
                        while True:
                            chunk=response.read1(65536)
                            if not chunk: break
                            log.write(chunk);log.flush()
                            try:
                                self.wfile.write(chunk);self.wfile.flush()
                            except (BrokenPipeError,ConnectionResetError):
                                break

        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    @property
    def url(self): return f'http://127.0.0.1:{self.server.server_port}'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join()
