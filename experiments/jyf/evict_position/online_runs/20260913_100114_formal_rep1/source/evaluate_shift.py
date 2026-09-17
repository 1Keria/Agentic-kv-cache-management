"""Held-out frontier risk sets: unchanged CDF vs conditional log survival."""
import json
from pathlib import Path
import numpy as np
from predictor import Model,log_survival

root=Path(__file__).resolve().parent
d=np.load(root/'training/samples.npz')
model=Model(root/'training/model.pt')
h=model.predict(d['x'])
rows=[]
for age in (0,2,5,10,20,60):
    for horizon in (5,20,60):
        for subset in ('all','cold','warm'):
            mask=(d['split']==2)&(d['duration']>age)
            mask &= ((d['event']>.5)&(d['duration']<=age+horizon)) | (d['duration']>=age+horizon)
            if subset!='all':mask &= d['cold']==int(subset=='cold')
            if not mask.any():continue
            y=((d['event'][mask]>.5)&(d['duration'][mask]<=age+horizon)).astype(float)
            w=d['tokens'][mask]
            static=1-np.exp(log_survival(h[mask],horizon))
            shifted=1-np.exp(log_survival(h[mask],age+horizon)-log_survival(h[mask],age))
            r=dict(age_s=age,horizon_s=horizon,subset=subset,n=int(mask.sum()),positive_rate=float(y.mean()))
            for name,p in (('static',static),('shift',shifted)):
                p=np.clip(p,1e-8,1-1e-8)
                r[name]=dict(nll=float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),
                             brier=float(np.mean((y-p)**2)),token_brier=float(np.average((y-p)**2,weights=w)))
            rows.append(r)
(root/'shift_results.json').write_text(json.dumps(rows,indent=2))
lines=['# 新秒级 checkpoint 的条件更新时间评估','',
       '测试集 frontier exposure 中，仅选择直到 age 尚未复用且 horizon 标签可观测的样本。同一组风险集比较 static 和 log-survival 条件更新，未重新训练或按本结果调参。',
       '部分早删失样本排除，未做 IPCW；这是可观测子集诊断，重复 prefix exposure 也不能当作独立样本。不是 serving 命中率结论。','',
       '| age 秒 | 未来秒数 | n | Static NLL | Shift NLL | Static Token-Brier | Shift Token-Brier |',
       '|---:|---:|---:|---:|---:|---:|---:|']
for r in rows:
    if r['subset']=='all':lines.append(f"| {r['age_s']} | {r['horizon_s']} | {r['n']} | {r['static']['nll']:.5f} | {r['shift']['nll']:.5f} | {r['static']['token_brier']:.5f} | {r['shift']['token_brier']:.5f} |")
(root/'shift_report_zh.md').write_text('\n'.join(lines)+'\n')
print(root/'shift_report_zh.md')
