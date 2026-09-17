"""Generate the reviewable comparison from saved results; no retraining."""
import json
from pathlib import Path
import numpy as np
import run_experiment as m

root=Path(__file__).resolve().parent
run=root/'runs/20260915_v1'
r=json.loads((run/'results.json').read_text())
z=np.load(run/'samples.npz'); d={k:z[k] for k in z.files}; test=np.where(d['split']==2)[0]
lines=['# Absolute Time vs Relative Time：实验结论','',
'结论：Relative 对合成时间尺度变化有优势，但没有同时通过预设的 ID 精度与跨 session 排序要求，因此当前结果不支持直接替换 Absolute。',
'','## 实验实际设置','',
'- 原始真实 frontier trace：29,885 条。共享/未知 prefix 排除 8,807 条；无历史 owner demand 排除 5,697 条；gap 无法一致重建排除 1,039 条。',
'- 保留 14,342 条、100 个 session；按 session 固定切分为训练 70、验证 15、测试 15。测试 3,008 条。',
'- 25% 训练规模实际抽取 17 个 session、770 条；100% 为 70 个 session、8,248 条。25% 指 session 数量，不是 exposure 数量。',
'- 每个规模分别训练 Absolute / Relative，各 5 seeds（41–45），共 20 次训练。两层 128-unit Unified MLP，相同初始化、优化器和最大 180 epoch；early stopping patience=12。',
'- 输入沿用 both_candidate16。Relative 仅将五个 seconds 字段先除以当前 τ，再 log1p；events/token/hits/traffic 等字段保持相同。Relative 不额外输入 τ。',
'- τ 是该 session 最近最多 8 个已完成请求间隔的 median；按 (session, turn) 去重请求。没有历史时使用训练集确定的默认尺度。默认尺度计算为每个训练 session 历史 τ 的 median，再对 session 取 median，避免 exposure 多的 session 主导。',
'- 25%% / 100%% 训练的默认 τ 分别为 %.5fs / %.5fs。'%(r['0.25']['default_tau'],r['1.0']['default_tau']),
'- Absolute finite edges=2/5/10/20/60/180/600/1800/7200 秒。Relative edges=这些边界除以训练默认 τ。9 个 hazard 输出加剩余尾部质量，对应 K=10。',
'- 训练使用同一 censor-aware hazard loss、sqrt-token 权重、cold/warm 等总权重。各自的验证 loss 只用于本模型 early stopping，不作跨模型指标比较。',
'- OOD 同步缩放 seconds 输入、已知历史 τ、目标和删失时长；保持缓存状态和 event 计数不变。×5/×10 为全体同倍缩放，mixed 按 session hash 分配 ×1/×5/×10。不是新在线 replay。',
'- 每个方案以 5 seeds hazard 平均后评估；预测用 S_seconds(t)=S_relative(t/τ) 还原。',
'','## 主指标：秒级 Integrated Brier（越低越好）','',
'IBS 在固定 0–600 秒上积分，使用逆删失概率权重（IPCW）。相对变化=(Relative/Absolute−1)，负数表示 Relative 更好。',
'','|训练规模|测试|Absolute IBS|Relative IBS|Relative 相对变化|IBS 差值 95% CI|',
'|---|---|---:|---:|---:|---|']
for frac,v in r.items():
 for sc in ('ID','x5','x10','mixed'):
  a=v['models']['absolute']['scenarios'][sc]; b=v['models']['relative']['scenarios'][sc]; ci=v['comparisons'][sc]['ibs_delta_ci95']
  lines.append('|%s|%s|%.5f|%.5f|%+.1f%%|[%+.5f, %+.5f]|'%(frac,sc,a['ibs_0_600s'],b['ibs_0_600s'],100*(b['ibs_0_600s']/a['ibs_0_600s']-1),*ci))
lines+=['','ID 两个训练规模的点估计分别恶化约 4.3% 和 5.4%，超过预设 2% 容忍值；置信区间跨零，不能证明显著变差，也不能证明非劣。×10 的改善在两种训练规模下都有不跨零的 IBS 差值区间。100% 训练下 ×5、mixed 的区间仍跨零。',
'','## 跨 session 排序','',
'仅取同 frontier、不同 session、真实先后可由 observed/censored 标签确定的样本对。以恢复到秒的预测中位数排序，无法定位的尾桶中位数为 +inf，预测并列计 0.5，不丢弃。',
'','|训练规模|测试|Absolute|Relative|只按 τ 排序|Relative−Absolute 的 95% CI|','|---|---|---:|---:|---:|---|']
for frac,v in r.items():
 for sc in ('ID','x5','x10','mixed'):
  a=v['models']['absolute']['scenarios'][sc]['ranking']['accuracy']; b=v['models']['relative']['scenarios'][sc]['ranking']['accuracy']; co=v['comparisons'][sc]
  lines.append('|%s|%s|%.2f%%|%.2f%%|%.2f%%|[%+.2f, %+.2f] pp|'%(frac,sc,100*a,100*b,100*co['tau_only_ranking']['accuracy'],*(100*x for x in co['ranking_delta_ci95'])))
lines+=['','每个场景有 1,200 个可比较 exposure 对，但只覆盖 48 个 frontier、10 个 session 和 **6 种不同 session 对**；不是 1,200 个独立比较。所有排序差值区间跨零，排序优势没有被可靠确立。τ-only 基线明显更好，所以不能证明 hazard 网络比简单历史尺度更适合当前跨 session 排序。',
'','## 100% 训练的完整短期概率指标','',
'Brier 越低越好；NLL 为同一秒数上 Bernoulli NLL，越低越好；AUC 越高越好。@5/20/60 在当前测试集均可观测，无需丢弃样本。',
'','|场景|模型|Brier@5/20/60s|NLL@5/20/60s|AUC@5/20/60s|尾桶中位数比例|','|---|---|---|---|---|---:|']
for sc in ('ID','x5','x10','mixed'):
 for kind in ('absolute','relative'):
  a=r['1.0']['models'][kind]['scenarios'][sc]; cells=a['horizons']
  vals=[' / '.join('%.4f'%cells[str(h)][metric] for h in (5,20,60)) for metric in ('brier_ipcw','nll_known','auc_known')]
  lines.append('|%s|%s|%s|%s|%s|%.1f%%|'%(sc,kind,*vals,100*a['tail_median_fraction']))
lines+=['','## 证据边界与判断','',
'1. 保留后的测试集只有 15 条 cold exposure；所有 3,008 个测试样本都有历史 τ，因此本实验没有验证无历史 fallback 或普遍的 cold-start 效果。',
'2. 合成缩放后 Relative 的归一化输入不变，ID 与 ×10 的预测 hazard 数值最大差为 0。这是设计的尺度等变性；它不证明跨 agent/工具/任务类型的泛化。',
'3. 置信区间使用 500 次 session bootstrap；pair 权重为两端 session 重采样次数的乘积。IBS bootstrap 固定测试 cohort 的 IPCW 权重，不包含重新估计删失分布的不确定性。仅一个 session split，未覆盖 split 随机性。',
'4. 超过最后有限 bucket，代码保持 survival 为剩余尾部质量，不拟合额外 tail rate。Relative 的最后有限边界对应 τ×7200/default_tau 秒，随 session 变化；0–600s IBS 部分查询可能落入未解析尾部，须连同短期指标和尾桶比例解释。',
'5. 这次 session split 和严格数据过滤与之前 digest split 不同，绝对数值不能与旧 feature ablation 的 AUC 直接比较。',
'6. 结论：支持“Relative 在稳定时间尺度放大下更稳”这个有限假设；未通过“ID 非劣 + 排序优于简单 τ 基线”的完整采用条件。暂不据此替换现有 Absolute，也无需先优化复杂 τ 算法。',
'','## 文件','',
'- `run_experiment.py`：数据过滤、因果 τ、session split、20 次训练、ID/OOD 预测、IPCW Brier 与 session bootstrap。',
'- `write_report.py`：从保存的 results.json 生成本报告，不重新训练。',
'- `runs/20260915_v1/audit.json`：过滤与切分数量。',
'- `runs/20260915_v1/samples.npz`：16 维特征、τ、标签、session/digest/frontier 标识、切分。',
'- `runs/20260915_v1/*.pt`：每个规模/模型/seed 的权重、标准化参数、桶边界和默认 τ。',
'- `runs/20260915_v1/*predictions.npz`：各场景 ensemble hazard、秒级中位数、逐样本 IBS 贡献。',
'- `runs/20260915_v1/results.json`：全部场景、短期指标、排序、置信区间和训练 epoch。',
'- `runs/20260915_v1/run.log`：执行日志。',
]
(root/'conclusion_zh.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
