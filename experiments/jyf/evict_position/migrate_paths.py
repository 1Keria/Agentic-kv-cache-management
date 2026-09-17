"""Repair current entrypoints/index after relocation; preserve historical logs."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
old='/share/dai-sys/zhoulongsheng/agentkv/experiments/evict_position'
assert root.name=='evict_position' and root.parent.name=='jyf',root
index=root/'completed_runs.json'
original=json.loads(index.read_text())
updated=[str(root/'online_runs'/Path(p).name) for p in original]
assert all(Path(p).is_dir() for p in updated)
audit=root/'migration.json'
if not audit.exists():
    audit.write_text(json.dumps(dict(previous_index=original,current_index=updated,
                                    historical_logs_and_source_snapshots_unchanged=True),indent=2))
index.write_text(json.dumps(updated,indent=2))
for name in ('README.md','conclusion_zh.md','training_report_zh.md'):
    p=root/name
    p.write_text(p.read_text().replace(old,str(root)))
print(json.dumps(dict(root=str(root),runs=updated),indent=2))
