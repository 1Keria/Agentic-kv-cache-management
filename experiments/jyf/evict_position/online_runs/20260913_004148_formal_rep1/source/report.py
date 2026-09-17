"""Strict run validation and human-readable comparison from actual measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def read_rows(path):
    with path.open() as f:return [json.loads(line) for line in f if line.strip()]
def quant(rows,key):
    a=[r[key] for r in rows]
    return dict(zip(('p50','p90','p99'),map(float,np.percentile(a,[50,90,99])))) if a else None
def analyze(run):
    result={}
    reference=None
    capacities_ref=None
    for mode in ('lru','on_demand','precompute'):
        arm=run/mode
        summary=json.loads((arm/'replay/summary.json').read_text())
        meta=json.loads((arm/'replay/meta.json').read_text())
        info=json.loads((arm/'server_info.json').read_text())
        requests=read_rows(arm/'replay/replay.jsonl')
        sig=sorted((r['trace_id'],r['prompt_tokens'],r['max_tokens']) for r in requests)
        if reference is None:reference=sig
        else:assert sig==reference, 'different request identities or tokenization'
        assert summary['integrity']['n_err']==0
        assert summary['integrity']['n_ok']==meta['n_turns']==len(requests)
        capacities=set()
        def visit(x):
            if isinstance(x,dict):
                if isinstance(x.get('memory_usage'),dict):capacities.add(x['memory_usage'].get('token_capacity'))
                for v in x.values():visit(v)
            elif isinstance(x,list):
                for v in x:visit(v)
        visit(info)
        config={k:info.get(k) for k in ('model_path','tp_size','mem_fraction_static','page_size','random_seed','kv_cache_dtype','chunked_prefill_size','max_running_requests')}
        config.update(capacities=sorted(v for v in capacities if v is not None),arrival=meta['arrival'],gap_scale=meta['gap_scale'])
        if capacities_ref is None:capacities_ref=config
        else:assert config==capacities_ref,'effective serving configuration differs'
        ranks={}
        for f in (arm/'metrics').glob('rank*_pid*.jsonl'):
            rows=read_rows(f)
            init=[r for r in rows if r['kind']=='init']
            assert len(init)==1 and init[0]['mode']==mode
            assert init[0]['source_sha256']==hashlib.sha256((run/'source/serving_patch.py').read_bytes()).hexdigest(),'runtime source differs from saved snapshot'
            assert init[0]['checkpoint_sha256']==hashlib.sha256((run.parent.parent/'training/model.pt').read_bytes()).hexdigest(),'checkpoint differs'
            rank=init[0]['rank']
            assert rank not in ranks
            ranks[rank]=rows
        assert set(ranks)==set(range(8)),list(ranks)
        signatures=[]
        for rank in range(8):
            signatures.append([(r['index'],r['seq'],r['freed_full'],r['freed_swa'],r['digest']) for r in ranks[rank] if r['kind']=='evict'])
        assert all(s==signatures[0] for s in signatures),'TP victims or released tokens diverged'
        active=[r for r in ranks[0] if r['wall_s']>=meta['created_unix']]
        es=[r for r in active if r['kind']=='evict']
        fs=[r for r in active if r['kind']=='finish']
        ss=[r for r in active if r['kind']=='submit']
        ps=[r for r in active if r['kind']=='prediction']
        assert es,'no eviction pressure'
        choices=sum(r['choices'] for r in es)
        fresh=sum(r['fresh_predictions'] for r in es)
        if mode!='lru':
            assert choices>0
            assert max(r['max_frontier'] for r in es)>16,'did not exercise complete frontier beyond 16'
            assert sum(r['changed_choices'] for r in es)>0,'never departed from LRU'
        if mode=='precompute':assert fresh==0,'MLP was started inside eviction'
        sources={}
        for r in ss:
            x=sources.setdefault(r['source'],dict(calls=0,predictions=0,submit_us=0.))
            x['calls']+=1
            x['predictions']+=r['predictions']
            x['submit_us']+=r['snapshot_submit_us']
        metrics=dict(tp_consistent=True,evictions=len(es),choices=choices,
                     changed_choices=sum(r['changed_choices'] for r in es),
                     max_frontier=max(r['max_frontier'] for r in es),
                     candidate_exposures=sum(r['candidate_exposures'] for r in es),
                     fresh_predictions=fresh,pending_waits=sum(r['pending_waits'] for r in es),
                     wait_total_s=sum(r['wait_us'] for r in es)/1e6,
                     inference_total_s=sum(r['inference_us'] for r in es)/1e6,
                     precompute_inference_total_s=sum(r['inference_us'] for r in ps)/1e6,
                     precompute_completed_rows=sum(r['rows'] for r in ps),
                     max_prediction_age_s=max(r['max_prediction_age_s'] for r in es),
                     evict_us=quant(es,'total_us'),finish_us=quant(fs,'total_us'),
                     evict_wait_us=quant(es,'wait_us'),submit_sources=sources,
                     submitted_predictions=sum(r['predictions'] for r in ss))
        result[mode]=dict(summary=summary,metrics=metrics,config=config)
    (run/'comparison.json').write_text(json.dumps(result,indent=2))
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('runs',type=Path,nargs='+')
    p.add_argument('--output',type=Path,default=Path('report_zh.md'))
    a=p.parse_args()
    all_runs=[analyze(r) for r in a.runs]
    labels=('lru','on_demand','precompute')
    lines=['# 完整 frontier：秒级 MLP 的推理时机对比','',
           f'每组 {len(all_runs)} 次实际 TP=8 serving 运行。候选无 LRU 截断；所有运行的请求集合、有效配置及八个 TP rank 的 victim/释放量已通过检查。','',
           '| 指标（各次运行均值） | LRU | On-demand | 预计算并等待 |',
           '|---|---:|---:|---:|']
    def row(label,fn):
        vals=[np.mean([fn(r[m]) for r in all_runs]) for m in labels]
        lines.append('| '+label+' | '+' | '.join(f'{v:,.3f}' for v in vals)+' |')
    row('成功请求',lambda x:x['summary']['integrity']['n_ok'])
    row('Token 命中率 %',lambda x:100*x['summary']['kv']['cached_tokens_sum']/x['summary']['kv']['prompt_tokens_sum'])
    row('未命中 prompt tokens',lambda x:x['summary']['kv']['prompt_tokens_sum']-x['summary']['kv']['cached_tokens_sum'])
    for k,label in [('ttft_ms','TTFT'),('e2e_ms','E2E')]:
        for q in ('p50','p90','p99'):row(f'{label} {q} ms',lambda x,k=k,q=q:x['summary']['latency'][k][q])
    row('请求/秒',lambda x:x['summary']['throughput']['req_per_s'])
    row('回放秒数',lambda x:x['summary']['integrity']['wall_clock_s'])
    for k,label in [('evict_us','Eviction'),('finish_us','Request-end')]:
        for q in ('p50','p99'):row(f'{label} {q} µs',lambda x,k=k,q=q:x['metrics'][k][q])
    for k,label in [('max_frontier','最大合法 frontier'),('fresh_predictions','Eviction 内预测节点数'),
                    ('submitted_predictions','提前提交预测数'),('pending_waits','遇到未完成任务次数'),
                    ('wait_total_s','读取/等待预测合计秒数')]:row(label,lambda x,k=k:x['metrics'][k])
    row('MLP 推理合计秒数',lambda x:x['metrics']['inference_total_s']+x['metrics']['precompute_inference_total_s'])
    lines+=['','## 逐次结果','']
    for path,r in zip(a.runs,all_runs):
        lines += [f'### {path.name}','','| 策略 | Token 命中率 % | TTFT p50 ms | E2E p50 ms | 完成请求/秒 |','|---|---:|---:|---:|---:|']
        for m in labels:
            s=r[m]['summary']
            lines.append(f"| {m} | {100*s['kv']['cached_tokens_sum']/s['kv']['prompt_tokens_sum']:.3f} | {s['latency']['ttft_ms']['p50']:.3f} | {s['latency']['e2e_ms']['p50']:.3f} | {s['throughput']['req_per_s']:.3f} |")
        lines+=['','预计算提交来源：','', '```json',json.dumps(r['precompute']['metrics']['submit_sources'],indent=2),'```','']
    lines+=['## 实现与解释边界','',
      '- 同一验证集选出的单模型 checkpoint；完整合法 frontier 每轮比较，新暴露父节点继续参与。',
      '- On-demand 在每次 eviction 为当前候选预测；同一次 eviction 内缓存结果，新暴露候选再批量补算。',
      '- 预计算在请求结束等 mutation boundary 提交相关节点和祖先。eviction 只等待已存在任务，缺失 ticket 直接失败，零 LRU fallback。',
      '- SWA 内部节点可在请求结束前成为候选；match/split、unfinished cache 和提前解锁边界也可提交，实际比例见上表。',
      '- 时间条件化仍在比较时执行，没有改写全部缓存 hazard。为获得当前完整 frontier 最小值，原型逐轮重算便宜的标量价值；测得开销包含这部分和 TP 通信。',
      '- V = path_tokens / node_tokens × Σp_k D_k；未来区间 0/2/5/10/20/60 秒，D_k=2^(-区间中点/20)，60 秒以外权重为零。',
      '- M 按当前受压 Full 或 SWA pool 的 token 占用计算，同 pool 的固定 bytes/token 在排序中抵消；没有声称精确建模跨池联合释放或共享祖先的边际重算成本。',
      '- 训练是旧 frozen frontier 的秒级标签，包含 cold 和右删失；不是无压力请求服务耗时。请求结束预测存在观测时刻分布偏移。',
      '- 预计算缓存历史快照，仅因等待而条件化，不因其他请求推进 event/LRU 特征而全树重推；这些变化是两种执行策略的真实区别。',
      '- 测试排除了训练请求来源中的 session、轨迹和首条 user message 重叠；公共 system prefix 仍可能重叠。',
      '- 同 session 后续请求等待上轮结束，因此策略会改变实际到达时刻。这是闭环 serving 效果，不是固定时间线下仅比较 CPU 开销。',
      '- 未命中 prompt tokens 包含首次访问，不能全部称为 eviction 导致的重算；请求/秒也不是饱和吞吐上限。',
      '- 原生 SWA tombstone 强制清理不属于可自由选择的 victim；保留原生内存管理。',
      '- 等待时长包括获取已完成 future 的开销；pending_waits 才表示读到未完成任务。','']
    a.output.write_text('\n'.join(lines))
    print(a.output)
if __name__=='__main__':main()
