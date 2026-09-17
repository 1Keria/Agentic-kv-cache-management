"""Read-only host GPU ownership audit during a serving arm."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
server=int(sys.argv[1])
out=Path(sys.argv[2])
with (out/'gpu_ownership.jsonl').open('a',buffering=1) as f:
    while True:
        try:os.kill(server,0)
        except ProcessLookupError:break
        result=subprocess.check_output(['nvidia-smi','--id='+os.environ.get('CUDA_VISIBLE_DEVICES','0,1,2,3,4,5,6,7'),'--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True)
        pids={int(s.strip()) for s in result.splitlines() if s.strip().isdigit()}
        ppids={int(p):int(pp) for p,pp in (s.split() for s in subprocess.check_output(['ps','-eo','pid=,ppid='],text=True).splitlines())}
        def ours(pid):
            seen=set()
            while pid in ppids and pid not in seen:
                if pid==server:return True
                seen.add(pid)
                pid=ppids[pid]
            return False
        foreign=sorted(p for p in pids if p in ppids and not ours(p))
        r=dict(wall_s=time.time(),server_pid=server,gpu_pids=sorted(pids),foreign_pids=foreign)
        f.write(json.dumps(r)+'\n')
        if foreign:(out/'RESOURCE_CONTAMINATED.json').write_text(json.dumps(r,indent=2))
        time.sleep(5)
