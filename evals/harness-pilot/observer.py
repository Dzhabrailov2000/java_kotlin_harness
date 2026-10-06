"""A public SQL diagnostic backed by one disposable, network-isolated PostgreSQL."""
import http.server
import json
import subprocess
import threading
from pathlib import Path
from verify_fixtures import postgres

LAUNCHER = '''#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path
runtime=json.loads(Path('.pilot-runtime.json').read_text())
body=json.dumps({'sql':Path('migrations/V2__balance_check.sql').read_text()}).encode()
request=urllib.request.Request(runtime['sql_observer']+'/observe',data=body,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request) as response:
    result=json.load(response)
print(result['stdout'],end='')
print(result['stderr'],end='')
raise SystemExit(result['returncode'])
'''


def observe(container, sql):
    marker='ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;'
    diagnostic="SELECT 'LOCK:' || mode FROM pg_locks WHERE pid=pg_backend_pid() AND relation='accounts'::regclass ORDER BY mode;"
    if sql.count(marker)!=1:
        return {'returncode':2,'stdout':'','stderr':'Expected the declared VALIDATE statement once.\n'}
    setup='DROP TABLE IF EXISTS accounts;CREATE TABLE accounts(id BIGINT PRIMARY KEY,balance BIGINT NOT NULL);INSERT INTO accounts VALUES(1,10);\n'
    command=['docker','exec','-i',container,'psql','-U','postgres','-v','ON_ERROR_STOP=1','-At']
    result=subprocess.run(command,input=setup+sql.replace(marker,marker+'\n'+diagnostic),text=True,capture_output=True)
    return {'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}


class Observer:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.container=None
        self.calls=0

    def __enter__(self):
        self.container=postgres()
        owner=self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                if self.path!='/observe':
                    self.send_error(404);return
                size=int(self.headers.get('Content-Length',0))
                if size>65536:
                    self.send_error(413);return
                try:
                    data=json.loads(self.rfile.read(size))
                    result=observe(owner.container,data['sql'])
                except (ValueError,KeyError,TypeError):
                    self.send_error(400);return
                owner.calls+=1
                (owner.directory/f'{owner.calls:03d}.json').write_text(json.dumps({'input':data,'result':result},ensure_ascii=False,indent=2)+'\n')
                body=json.dumps(result).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        self.server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        return self

    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join()
        subprocess.run(['docker','stop',self.container],capture_output=True,check=True)
