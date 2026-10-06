import json, os, subprocess
from pathlib import Path
text=Path('migrations/V2__balance_check.sql').read_text()
marker="ALTER TABLE accounts VALIDATE CONSTRAINT balance_nonnegative;"
observation="""SELECT 'LOCK:' || mode FROM pg_locks WHERE pid=pg_backend_pid()
AND relation='accounts'::regclass ORDER BY mode;"""
if text.count(marker)!=1: raise SystemExit('fixture verifier expects its declared SQL statement')
sql="DROP TABLE IF EXISTS accounts;CREATE TABLE accounts(id BIGINT PRIMARY KEY,balance BIGINT NOT NULL);INSERT INTO accounts VALUES(1,10);\n"+text.replace(marker,marker+'\n'+observation)
p=subprocess.run(['docker','exec','-i',os.environ['PILOT_PG_CONTAINER'],'psql','-U','postgres','-v','ON_ERROR_STOP=1','-At'],input=sql,text=True,capture_output=True)
print(p.stdout);print(p.stderr)
modes=[line[5:] for line in p.stdout.splitlines() if line.startswith('LOCK:')]
result={'applied':p.returncode==0,'lock_modes_during_validation':modes,'blocks_regular_writes':'AccessExclusiveLock' in modes or 'ShareLock' in modes or 'ShareRowExclusiveLock' in modes}
Path('lock-observation.json').write_text(json.dumps(result,indent=2))
assert result['applied'],p.stderr
assert modes,'No lock observation'
assert not result['blocks_regular_writes'],modes
