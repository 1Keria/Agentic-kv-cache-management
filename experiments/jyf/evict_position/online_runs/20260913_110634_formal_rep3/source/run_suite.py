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
    gpus=os.environ.get('EP_GPUS','0,1,2,3,4,5,6,7')
    usage=subprocess.check_output(['nvidia-smi','--id='+gpus,'--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True)
    return len(usage.splitlines())==len(gpus.split(',')) and max(map(int,usage.splitlines()))<1024
orders=[['precompute','on_demand','lru'],['on_demand','lru','precompute'],['lru','precompute','on_demand']]
runs=[]
rep=1
while rep<=len(orders):
    order=orders[rep-1]
    stable=0
    while stable<3:
        stable=stable+1 if idle() else 0
        print(time.strftime('%Y-%m-%d %H:%M:%S'),f'rep {rep}: idle checks {stable}/3',flush=True)
        if stable<3:time.sleep(30)
    name=time.strftime('%Y%m%d_%H%M%S')+f'_formal_rep{rep}'
    env=dict(os.environ,ONLINE_MODES=' '.join(order))
    run=root/'online_runs'/name
    try:
        subprocess.run(['bash','run_online.sh',name],env=env,check=True)
        subprocess.run([sys.executable,'report.py',str(run),'--output',str(run/'report_zh.md')],check=True)
    except subprocess.CalledProcessError:
        logs='\n'.join(p.read_text(errors='replace') for p in run.glob('*/server.log'))
        orchestration=(run/'orchestrator.log').read_text(errors='replace')
        if 'The memory capacity is unbalanced' in logs or 'GPUs busy:' in orchestration or list(run.glob('*/RESOURCE_CONTAMINATED.json')):
            print('RESOURCE CONFLICT: retained failed run; waiting before retry',name,flush=True)
            (run/'RESOURCE_RETRY.txt').write_text('Excluded: shared-host GPU conflict. Retry uses a new directory.\n')
            continue
        raise
    runs.append(str(run))
    (root/'completed_runs.json').write_text(json.dumps(runs,indent=2))
    rep+=1
subprocess.run([sys.executable,'report.py',*runs,'--output',str(root/'report_zh.md')],check=True)
print('SUITE COMPLETE',flush=True)
