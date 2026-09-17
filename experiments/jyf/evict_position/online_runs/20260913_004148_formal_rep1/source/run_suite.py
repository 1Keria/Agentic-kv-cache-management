"""Wait for an idle host and run three counterbalanced repetitions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
os.chdir(root)
def idle():
    # This benchmark was observed taking the host after our pilot. Wait through
    # its between-stage GPU release as well, without touching its processes.
    ps=subprocess.check_output(['ps','-eo','args'],text=True)
    if any('run_plateau_extension.py' in s and not s.startswith('ps ') for s in ps.splitlines()):return False
    usage=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
    return len(usage.splitlines())==8 and max(map(int,usage.splitlines()))<1024
orders=[['precompute','on_demand','lru'],['on_demand','lru','precompute'],['lru','precompute','on_demand']]
runs=[]
for rep,order in enumerate(orders,1):
    stable=0
    while stable<3:
        stable=stable+1 if idle() else 0
        print(time.strftime('%Y-%m-%d %H:%M:%S'),f'rep {rep}: idle checks {stable}/3',flush=True)
        if stable<3:time.sleep(30)
    name=time.strftime('%Y%m%d_%H%M%S')+f'_formal_rep{rep}'
    env=dict(os.environ,ONLINE_MODES=' '.join(order))
    subprocess.run(['bash','run_online.sh',name],env=env,check=True)
    run=root/'online_runs'/name
    subprocess.run([sys.executable,'report.py',str(run),'--output',str(run/'report_zh.md')],check=True)
    runs.append(str(run))
    (root/'completed_runs.json').write_text(json.dumps(runs,indent=2))
subprocess.run([sys.executable,'report.py',*runs,'--output',str(root/'report_zh.md')],check=True)
print('SUITE COMPLETE',flush=True)
