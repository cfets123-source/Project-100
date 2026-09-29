import subprocess,json
from datetime import datetime,timezone

def run(args):
    return subprocess.check_output(args,text=True).strip()
previous=run(['docker','inspect','--format','{{.Image}}','project-100-api-1'])
backup='/data/backups/pre-binance-connection-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.db'
code='import sqlite3; s=sqlite3.connect("/data/paper.db"); d=sqlite3.connect('+repr(backup)+'); s.backup(d); print(d.execute("PRAGMA integrity_check").fetchone()[0]); d.close(); s.close()'
integrity=run(['docker','exec','project-100-api-1','python','-c',code])
assert integrity=='ok',integrity
subprocess.run(['docker','compose','--project-name','project-100','-f','/opt/veloikos-releases/20260924-binance-connection/release/compose.api.yml','up','--no-deps','-d','api','account-observer'],check=True)
print(json.dumps({'previous_image':previous,'backup':backup,'backup_integrity':integrity,'image':run(['docker','image','inspect','--format','{{.Id}}','veloikos-binance-connection:20260924'])}))
