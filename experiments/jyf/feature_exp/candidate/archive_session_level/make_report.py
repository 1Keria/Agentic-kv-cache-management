"""Write feature catalog, correlation/ablation reports, and session bootstrap."""
import json
from pathlib import Path
import numpy as np
import run_candidate as exp

root=Path(__file__).resolve().parent;out=root/'runs/20260916_session_v3'
catalog=['# Session-only 候选特征清单','',
'候选共32维。长度基于规范化message内容字符数，不依赖服务模型tokenizer。以下所有prefix、turn、gap都限定在同一个session内。预测时点为请求到达。',
'','|特征|组|定义|处理|','|---|---|---|---|']
for n,(desc,g,t) in exp.FEATURES.items():catalog.append(f'|`{n}`|{g}|{desc}|{t}|')
catalog+=['','relative字段先除以当前τ再log1p；无历史填-1，真实0填0。其他log1p字段非负，context增长使用signed log1p。随后用训练集统计标准化。',
'','这里刻意没有has_tool（可从schema_count得到）、remaining_fraction、gap_trend、session_gap_count、多套阈值mask或物理radix结构。不同gap统计描述最近值、较早值、加权水平和波动，不存在人为添加的确定性公式重复；数据上的冗余由相关性与消融继续检查。']
(root/'feature_catalog.md').write_text('\n'.join(catalog)+'\n',encoding='utf-8')
if not (out/'results.json').exists():print('catalog written; training not complete');raise SystemExit
r=json.loads((out/'results.json').read_text());s=json.loads((out/'screening.json').read_text());c=json.loads((out/'correlations.json').read_text());meta=json.loads((out/'dataset_meta.json').read_text())
names=c['names'];corr=np.array(c['spearman']);high=[]
for i in range(len(names)):
 for j in range(i):
  if abs(corr[i,j])>=.8:high.append((abs(corr[i,j]),names[j],names[i],corr[i,j]))
high.sort(reverse=True)
lines=['# Session-only 特征探索结果','',
'本实验严格将输入限定为session上下文和该session的逻辑prefix历史。没有复用之前的cache frontier样本或serving特征。完整32维清单见 `feature_catalog.md`。',
'','## 标签及数据边界','',
'- 对象 `(推断session, logical message-boundary prefix)`；当前请求中出现的prefix，在后续同session请求中再次出现即为需求，无论缓存是否命中。',
'- 标签 `Z=(next_request_start-current_request_start)/tau_session`，τ为当前已知的最近最多8个session请求gap的median。尚未观测复用的prefix按日志全局结束时间右删失。',
'- session以 tenant + 首个user message内容推断，未获得权威session ID；相同首个user消息可能合并不同trajectory，属于数据限制。',
'- 只有request-start，没有response完成时间，因此原始gap含历史服务延迟；模型接口与serving状态无关，但数据不能证明理想时间标签已剥离服务延迟。',
'- 16,559请求、373,228原始样本；排除164,865个无session历史τ的样本后，正式使用208,363样本、3,448个session；训练/验证/测试session=2,415/526/507。',
'- τ完全来自当前session已有历史，未使用训练全局默认值；session首请求没有物理时间尺度，当前实验不替它制造相对时间标签。prefix首次出现但session已有历史的样本仍保留。',
'- 固定9个relative有限边界 `.125,.25,.5,1,2,4,8,16,64`；输出9个hazard加尾部概率。没有用测试数据选择bucket或特征。',
'- 相同32维输入宽度、两层64unit，消融列标准化后置零；所有组3 seeds；验证IPCW IBS(0–8τ)用于筛选。',
'- 所有报表阈值@1/@2/@4都指当前session的1/2/4个τ，不是秒。主指标IBS越低越好。',
'','## 相关性','',
'训练集抽取最多60,000个样本计算Spearman。没有训练集恒定列或完全相同列。下表列出绝对相关系数≥0.8的候选对；相关性只辅助解释，删除依据为消融。',
'','|特征A|特征B|Spearman|','|---|---|---:|']
for _,a,b,v in high:lines.append(f'|{a}|{b}|{v:.4f}|')
lines+=['','与未来复用的阈值关联见 `correlations.json/target_associations`。该分析在每个阈值只纳入可判定标签，存在删失选择限制；没有把只观察到复用的duration相关系数当作主筛选证据。',
'','## 组级消融（验证集）','',
'|方案|IBS|相对full变化|','|---|---:|---:|']
base=s['full']['validation']['ibs_0_8_relative']
for n,v in s.items():
 if n=='full' or n.startswith('without_group_'):
  b=v['validation']['ibs_0_8_relative'];lines.append(f'|{n}|{b:.6f}|{(b/base-1)*100:+.2f}%|')
lines+=['','## 单项消融（验证集）','',
'正变化表示删掉后变差。预设保留门槛为删除后IBS恶化超过1%；这是实用筛选门槛，不是显著性检验。','',
'|删除特征|IBS|相对full变化|进入精简集合|','|---|---:|---:|---|']
chosen_features=r['models']['selected']['features']
for n,v in s.items():
 if n.startswith('without_') and not n.startswith('without_group_'):
  name=n[len('without_'):];b=v['validation']['ibs_0_8_relative'];lines.append(f'|{name}|{b:.6f}|{(b/base-1)*100:+.2f}%|'+('是' if name in chosen_features else '否')+'|')
lines+=['','## 冻结候选与测试结果','',f"验证集选定方案：**{r['selected_by_validation']}**。单项门槛得到的精简集为：",'']
lines+=['- `'+n+'`：'+exp.FEATURES[n][0] for n in chosen_features]
lines+=['','|模型|维数|验证IBS|测试IBS|测试AUC@1/2/4τ|测试Brier@1/2/4τ|','|---|---:|---:|---:|---|---|']
for n,v in r['models'].items():
 t=v['test']['thresholds'];auc=' / '.join(f"{t[str(h)]['auc']:.4f}" for h in (1,2,4));br=' / '.join(f"{t[str(h)]['brier']:.4f}" for h in (1,2,4))
 lines.append('|%s|%s|%.6f|%.6f|%s|%s|'%(n,len(v['features']),v['validation']['ibs_0_8_relative'],v['test']['ibs_0_8_relative'],auc,br))
z=np.load(out/'samples.npz');ix=np.where(z['split']==2)[0];sessions,gi=np.unique(z['sid'][ix],return_inverse=True);count=np.bincount(gi)
a=np.load(out/'full_predictions.npz')['test_ibs'];b=np.load(out/'selected_predictions.npz')['test_ibs'];delta=b-a
rng=np.random.default_rng(94);boot=rng.multinomial(len(sessions),np.ones(len(sessions))/len(sessions),size=1000)
sums=np.bincount(gi,weights=delta);values=(boot@sums)/(boot@count);ci=np.quantile(values,[.025,.975]);macro=float(np.mean(sums/count))
audit={'delta_test_ibs_selected_minus_full':float(delta.mean()),'session_bootstrap_ci95':ci.tolist(),'session_macro_delta':macro,'n_test_sessions':len(sessions),
       'note':'bootstrap freezes IPCW estimates and ensemble; not training-seed or split uncertainty'}
(out/'bootstrap.json').write_text(json.dumps(audit,indent=2))
lines+=['',f"精简集−full 的测试 IBS 差值为 {delta.mean():+.6f}，按session重采样95% CI [{ci[0]:+.6f}, {ci[1]:+.6f}]；session等权平均差值 {macro:+.6f}。负数更好。",'',
'## 如何使用结论','',
'- 选择依据是验证集，不因测试指标回头调整。单组模型仅用于解释信息来源，不额外参与这轮预定义full/selected选择。',
'- 一次联合删除可能移除相互替代的信号，故必须检查selected整体结果；若验证不优于full，则保留full，不能强行宣布精简成功。',
'- 本轮是一个原始日志workload、一个session split；没有验证跨agent/workload泛化。不能将相关性、消融小差异表述成普遍因果规律。',
'- 字符长度输入虽不依赖serving tokenizer，仍会随任务内容变化；接口不含workload身份不等于跨workload精度已经成立。',
'- 按推断session隔离优于随机prefix曝光切分，但仍需真实session ID及response完成时间才能验证完全理想的session行为目标。',
]
(root/'screening_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(r['selected_by_validation'],chosen_features,audit)

