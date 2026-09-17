"""Consolidate final session-only exploration, including negative test evidence."""
import json,hashlib
from pathlib import Path
import numpy as np
import torch
import run_candidate as e
root=Path(__file__).resolve().parent;out=root/'runs/20260916_session_v3'
initial=json.loads((out/'results.json').read_text());groups=json.loads((out/'group_confirmation.json').read_text());ref=json.loads((out/'final_selection.json').read_text());rec=json.loads((out/'recommended.json').read_text());screen=json.loads((out/'screening.json').read_text())
final=rec['models'][rec['chosen']];z=np.load(out/'samples.npz');test=np.where(z['split']==2)[0]
assert len(e.NAMES)==32 and z['x'].shape[1]==32 and np.all(np.isfinite(z['x'])) and np.all(z['turn']>1) and np.all(z['tau']>0)
assert all(not(set(z['sid'][z['split']==i])&set(z['sid'][z['split']==j])) for i in range(3) for j in range(i))
assert np.all(z['duration']>0)
models={'no_features':groups['no_features'],'full32':initial['models']['full'],'screened24':initial['models']['selected'],'refined12':ref['models']['strict'],'refined8':ref['models']['compact']}
paths={'no_features':'no_features','full32':'full','screened24':'selected','refined12':'refined_strict','refined8':'refined_compact'}
_,gi=np.unique(z['sid'][test],return_inverse=True);counts=np.bincount(gi);rng=np.random.default_rng(64);boot=rng.multinomial(len(counts),np.ones(len(counts))/len(counts),size=1000)
preds={name:np.load(out/(p+'_predictions.npz')) for name,p in paths.items()}
comparisons={}
for name in ('no_features','full32','screened24'):
 diff=preds['refined8']['test_ibs']-preds[name]['test_ibs'];sums=np.bincount(gi,weights=diff);bs=(boot@sums)/(boot@counts)
 comparisons[name]={'delta_ibs':float(diff.mean()),'ci95':np.quantile(bs,[.025,.975]).tolist(),'session_macro_delta':float((sums/counts).mean())}
(out/'final_bootstrap.json').write_text(json.dumps(comparisons,indent=2))
lines=['# Session-only候选特征：最终探索结论','',
'**结论：已完成32维候选池、训练集相关性、组级/逐项消融和压缩验证。验证集选出的8维只能作为研究候选，测试集排序能力接近随机，不能认定已找到可部署的最优输入。**',
'','## 模型接口与理想目标','',
'- 对象是session自己的逻辑prefix，以message边界和内容身份定义；不依赖tokenizer或物理radix树切分。',
'- 输入只读取当前请求已知的context与本session历史，不读取当前response、缓存hit/LRU、全局事件计数、压力、并发、模型/agent/workload身份。',
'- τ只取本session最近最多8个已完成request gap的median。不使用训练集全局τ；无历史τ的session首请求从本轮相对时间实验排除。',
'- 输出9个固定relative区间的条件hazard，加剩余尾部质量，对应10个桶。目标Z=本session下一次需求该prefix的距离/τ。',
'- relative finite edges为[.125,.25,.5,1,2,4,8,16,64]，需要秒级查询时使用S_seconds(t)=S_relative(t/τ)。',
'- **观测限制**：日志只有request-start，没有response完成时间。实验输入不含serving环境，目标却仍是历史request-start间隔的代理标签，不能证明已经剥离历史推理/排队延迟。session也由tenant+首个user消息推断，并非权威session ID。',
'','## 候选池与不重复原则','',
'完整定义、变换和分组见 `feature_catalog.md`：position 5维、context 9维、evolution 5维、session 5维、prefix_history 8维，共32维。',
'已排除remaining=1-prefix、trend=last-prev、session_gap_count=turn-1、has_tool与tool_count重复、全局event/物理node年龄/深度/children。idle在本实验请求到达预测时点恒为0，不加入。',
'`last_message_is_tool`与`last_message_is_user`是同一个三分类角色(tool/user/other)的两个编码位，不应理解为两项独立语义信号。在当前数据中它们近乎互补，所以专门做了删一位的实验。',
'','## 数据和方法','',
'正式run为 `runs/20260916_session_v3`。16,559请求形成373,228原始prefix样本，排除164,865无session历史τ样本后，使用208,363条、3,448个推断session。',
'训练/验证/测试：132,351 / 52,074 / 23,938 条，session数量2,415 / 526 / 507。同一session完全隔离。仍保留session已有τ但prefix新出现的cold-prefix样本。',
'每组3个seed（41–43），固定32维网络宽度、2×64 hidden，删除输入列置零保持初始化可比；session等总训练权重，censor-aware hazard loss，60 epoch上限。',
'相关性在训练集计算，消融与压缩只据验证集选择；测试不参与挑选。但这是多阶段自适应探索，仍需新的独立测试集确认最终候选。',
'指标：IPCW IBS(0–8τ)越低越好；AUC@1/2/4τ评价对应相对时间窗口内复用的排序，不是秒，也不是精确bucket命中率。',
'','## 组级消融','',
'|删除组|验证IBS|相对32维变化|','|---|---:|---:|']
b=screen['full']['validation']['ibs_0_8_relative']
for g in ('full','without_group_context','without_group_evolution','without_group_position','without_group_prefix_history','without_group_session'):
 v=screen[g]['validation']['ibs_0_8_relative'];lines.append(f'|{g}|{v:.6f}|{100*(v/b-1):+.2f}%|')
lines+=['','本数据里prefix历史组和context有增量，session节奏组整组删除反而改善。不能因此声称所有session历史无效：输出归一化仍然显式使用session历史τ。',
'','## 验证选择过程','',
'1. 从32维做单项消融，保留删除后验证IBS恶化超过1%的维度，得到24维，并验证联合效果。',
'2. 检查无特征基线以及context与其余组的组合。按“验证IBS距离最优不超过1%时选更小模型”，得到22维context+position+prefix_history作为进一步压缩基线。',
'3. 对22维逐项删除，再联合验证12维与8维精简集合，验证选择8维。',
'4. 对8维中末尾role两个标志分别删一位，得到两个7维方案；验证IBS分别0.162256、0.162800，8维为0.160093。按已定1%容忍规则，未用7维替换8维。',
'','## 8维研究候选（7项语义信息）','',
'|维度|定义|类别|','|---|---|---|']
for n in final['features']:desc,g,_=e.FEATURES[n];lines.append(f'|`{n}`|{desc}|{g}|')
lines+=['','这不是“已证明跨workload有效”的清单，只是在当前验证集和训练协议下选出的精简方案。',
'','## 测试结果','',
'|方案|维数|验证IBS|测试IBS|测试AUC@1τ|@2τ|@4τ|','|---|---:|---:|---:|---:|---:|---:|']
for n,v in models.items():
 t=v['test'];lines.append('|%s|%d|%.6f|%.6f|%.4f|%.4f|%.4f|'%(n,len(v['features']),v['validation']['ibs_0_8_relative'],t['ibs_0_8_relative'],*(t['thresholds'][str(i)]['auc'] for i in (1,2,4))))
lines+=['','8维验证IBS最佳，但测试AUC仅0.52–0.55，完整32维约0.59–0.61。说明验证选出的精简概率模型没有证明在新session上保留良好排序。不能因IBS下降就宣布复用排序有效。',
'','### 8维完整测试指标','',
'|阈值|Brier(IPCW)|NLL(标签可判定样本)|AUC|可判定样本数|正例率|','|---|---:|---:|---:|---:|---:|']
for i in (1,2,4):
 t=final['test']['thresholds'][str(i)];lines.append('|%dτ|%.6f|%.6f|%.4f|%d|%.4f|'%(i,t['brier'],t['nll_known'],t['auc'],t['n'],t['positive_rate']))
lines+=['','### 测试集session bootstrap','',
'下表是8维减去比较方案的IBS，负数更好；1000次按session重采样，固定IPCW权重与已训练ensemble，不包括训练seed和split不确定性。',
'','|比较对象|IBS差值|95% CI|session等权差值|','|---|---:|---|---:|']
for n,v in comparisons.items():lines.append('|%s|%+.6f|[%+.6f, %+.6f]|%+.6f|'%(n,v['delta_ibs'],*v['ci95'],v['session_macro_delta']))
lines+=['','## 相关性与未入选项','',
'完整Spearman矩阵和threshold关联在 `correlations.json`，完整单项删除在 `screening_report.md`。高相关不能直接等同于无用，尤其缺失历史统一编码可能同时抬高多个gap字段的相关系数。',
'在最终压缩基线内，schema数量、当前最后角色、prefix位置和prefix重复需求间隔进入精简候选；绝对context长度、复杂增长/改写统计、独立session gap统计等未进入最终8维。这是条件增量结论，不是普遍宣告无效。',
'','## 当前可交付的判断','',
'- 32维池满足“特征来源只限session”的接口要求，且比精简方案丰富；不强行保留某个固定维数。',
'- 实验提供可复现的8维精简研究候选，但测试排序弱，当前不能定版为生产模型。保留32维及24维对照，不根据测试表现回头修改已经冻结的8维选择。',
'- 完全理想的时间目标还需要权威session ID和明确的session逻辑事件/response完成时间。当前数据只能支撑request-start代理标签，不能宣称已经验证理想serving-free目标。',
'- 下一步应先检查/改善session识别与标签，再用独立session数据复验；不是继续无依据堆维度。',
]
(root/'conclusion_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
manifest={'features':32,'selected_features':final['features'],'tau_source':'session history only; no global fallback','split_session_disjoint':True,'all_features_finite':True,
 'torch':torch.__version__,'numpy':np.__version__,'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py')}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('FINAL',final['features'],comparisons)
