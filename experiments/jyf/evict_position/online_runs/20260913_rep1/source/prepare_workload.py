"""Select a workload independently of policy outcomes; audit source overlap."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

BASE=Path('/share/dai-sys/zhoulongsheng/agentkv')
EXP=BASE/'experiments/evict_position'
OLD=BASE/'experiments/nn_exp/cold_predictor_exp/workloads/agent050_decode32/workload.jsonl'
NEW=BASE/'workloads/ratio_train_v4flash/agent_050/workload.jsonl'
def read(p):return [json.loads(s) for s in p.read_text().split('\n') if s.strip()]
def anchor(r):
    m=next((x for x in r['prompt_body']['messages'] if x.get('role')=='user'),{})
    return hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()
def root(r):return re.sub(r':strict\d+$','',r['session_id'])
old,new=read(OLD),read(NEW)
old_ids={r['session_id'] for r in old}
old_roots={root(r) for r in old}
old_anchors={anchor(r) for r in old}
bad={r['session_id'] for r in new if r['session_id'] in old_ids or root(r) in old_roots or anchor(r) in old_anchors}
selected=[r for r in new if r['session_id'] not in bad]
assert selected
for r in selected:r['max_tokens']=min(32,r['max_tokens'])
out=EXP/'workload'
out.mkdir(exist_ok=False)
(out/'workload.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in selected))
meta=dict(name='evict_position_source_disjoint',source=str(NEW),training_trace_request_source=str(OLD),
          counts=dict(Counter(r['traffic_class'] for r in selected)),n_turns=len(selected),
          n_sessions=len({r['session_id'] for r in selected}),excluded_sessions=len(bad),
          overlap_checks=['session_id','source trajectory id before strict segment','first user message hash'],
          note='Dataset naming train/test predates this experiment. Here the seconds model was trained on the old unseen replay; this different source is serving test only. Common system prefixes may still overlap.',
          source_sha256=hashlib.sha256(NEW.read_bytes()).hexdigest(),
          workload_sha256=hashlib.sha256((out/'workload.jsonl').read_bytes()).hexdigest())
(out/'spec.json').write_text(json.dumps(meta,indent=2))
print(json.dumps(meta,indent=2))

