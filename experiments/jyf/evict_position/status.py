import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
for run in sorted((ROOT/'online_runs').glob('*formal*')):
    print(run.name,(run/'status').read_text().strip() if (run/'status').exists() else '')
    for mode in ('precompute','on_demand','lru'):
        arm=run/mode
        if not arm.exists():continue
        api=arm/'replay/replay.jsonl'
        if api.exists():
            with api.open() as f:rs=[json.loads(s) for s in f if s.strip()]
            print(mode,'api_rows',len(rs),'summary', (arm/'replay/summary.json').exists())
        fs=list((arm/'metrics').glob('rank0_pid*.jsonl'))
        if fs:
            with fs[0].open() as f:rows=[json.loads(s) for s in f if s.strip()]
            es=[r for r in rows if r['kind']=='evict']
            ss=[r for r in rows if r['kind']=='submit']
            print(mode,'evictions',len(es),'max_frontier',max([r['max_frontier'] for r in es],default=0),
                  'fresh',sum(r['fresh_predictions'] for r in es),'pending_waits',sum(r['pending_waits'] for r in es),
                  'submissions',len(ss))
        log=arm/'server.log'
        if log.exists():
            lines=log.read_text(errors='replace').split('\n')
            failures=[s for s in lines if 'coverage violation' in s or 'Traceback' in s or 'TP frontier mismatch' in s]
            print('failures',failures[-3:])
