#!/usr/bin/env python3
"""Single-feature permutation rank on the official 168-column model.

Attaches meaning, source, and group for all 169 inventory slots.
sampling.max_new_tokens is scored in the with-leaky model and flagged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/python"))
from pipeline_inventory_groups import (  # noqa: E402
    GROUPS,
    LEAKY,
    cols_of,
    load_xy,
    perm_deltas,
    summarize,
)
from rank_inventory_permutation import SPECS  # noqa: E402
from rank_session_return_features import DEFAULT_RUN  # noqa: E402
from train_session_return_lgbm import fit_lgbm  # noqa: E402

SOURCE = {
    "client": "客户端请求",
    "tokenized": "分词后 TokenizedGenerateReqInput",
    "req": "调度器 Req",
    "sampling": "Req.sampling_params",
    "time": "Req.time_stats",
    "session": "原生 SGLang Session",
    "last_node": "Radix last_node",
    "resource": "KV 分配器 / 缓存",
    "scheduler": "调度器队列",
}

KIND_ZH = {
    "num": "标量",
    "len": "序列长度",
    "cat": "类别",
    "present": "是否存在",
    "bool": "布尔",
    "effort": "推理强度序数",
}

MEANING = {
    "client.messages": "对话消息列表长度",
    "client.input_ids": "客户端直接提供的 prompt token 数",
    "client.model": "请求指定的模型名",
    "client.tools": "请求携带的工具定义条数",
    "client.tool_choice": "工具选择方式",
    "client.parallel_tool_calls": "是否允许并行工具调用",
    "client.response_format": "是否带输出格式约束",
    "client.reasoning_effort": "请求指定的推理强度",
    "client.task": "请求任务类型",
    "client.user": "客户端用户标识",
    "client.max_tokens": "原始请求最大生成 token 数",
    "client.max_completion_tokens": "原始请求 max_completion_tokens",
    "client.min_tokens": "最小生成 token 数",
    "client.n": "并行生成条数",
    "client.stop": "停止字符串条数",
    "client.stop_token_ids": "停止 token id 个数",
    "client.stop_regex": "停止正则条数",
    "client.temperature": "采样温度",
    "client.top_p": "nucleus 采样 top_p",
    "client.top_k": "top_k 采样",
    "client.min_p": "min_p 采样",
    "client.frequency_penalty": "频率惩罚",
    "client.presence_penalty": "存在惩罚",
    "client.repetition_penalty": "重复惩罚",
    "client.seed": "请求随机种子",
    "client.ignore_eos": "是否忽略 EOS",
    "client.no_stop_trim": "是否不裁剪 stop",
    "client.continue_final_message": "是否续写最后一条消息",
    "client.stream": "客户端是否流式",
    "client.extra_key": "Radix 额外键",
    "client.cache_salt": "缓存隔离 salt",
    "client.lora_path": "请求 LoRA 路径",
    "client.priority": "客户端请求优先级",
    "client.session_params": "是否携带 SGLang Session 参数",
    "client.rid": "客户端请求 ID",
    "client.image_content": "是否含图像",
    "client.audio_content": "是否含音频",
    "client.video_content": "是否含视频",
    "client.max_dynamic_patch": "多模态 max_dynamic_patch",
    "client.min_dynamic_patch": "多模态 min_dynamic_patch",
    "client.use_audio_in_video": "视频中是否用音频",
    "tokenized.input_text": "送入分词的文本长度",
    "tokenized.input_ids": "分词后 prompt token 数",
    "tokenized.mm_inputs": "是否有分词后多模态输入",
    "tokenized.sampling_params": "分词对象是否带 sampling_params",
    "tokenized.session_params": "分词对象是否带 session_params",
    "tokenized.extra_key": "分词后 extra_key",
    "tokenized.routing_key": "分词后 routing_key",
    "tokenized.priority": "分词后优先级",
    "tokenized.stream": "分词后 stream 标记",
    "tokenized.time_stats": "分词对象是否带 time_stats",
    "req.rid": "调度器请求 ID",
    "req.origin_input_ids": "进入调度器的完整输入 token 数",
    "req.origin_input_ids_unpadded": "padding 前输入 token 数",
    "req.output_ids": "已生成输出 token 数",
    "req.full_untruncated_fill_ids": "未截断填入序列 token 数",
    "req.fill_len": "当前已填充序列位置",
    "req.input_embeds": "是否直接携带 input embedding",
    "req.multimodal_inputs": "调度器是否保存多模态输入",
    "req.sampling_params": "Req 是否带 sampling_params 对象",
    "req.session": "是否关联原生 Session 对象",
    "req.extra_key": "调度器 extra_key",
    "req.lora_id": "调度器 LoRA id",
    "req.routing_key": "调度器 routing_key",
    "req.priority": "调度优先级",
    "req.require_reasoning": "是否启用 reasoning",
    "req._is_reasoning_over": "reasoning 阶段是否结束",
    "req.reasoning_tokens": "已生成 reasoning token 数",
    "req.finished_reason": "原生结束原因类型",
    "req.finished_len": "结束时的输出位置",
    "req.to_finish": "是否有待应用的终止原因",
    "req.prefix_indices": "设备 KV 命中索引个数",
    "req.last_node": "是否有设备 Radix 最后命中节点",
    "req.last_host_node": "是否有 Host 最后命中节点",
    "req.best_match_node": "是否有最佳匹配节点",
    "req.host_hit_length": "Host cache 命中长度",
    "req.swa_host_hit_length": "SWA Host cache 命中长度",
    "req.mamba_host_hit_length": "Mamba Host cache 命中长度",
    "req.num_matched_prefix_tokens": "调度器记录的前缀命中 token 数",
    "req.storage_hit_length": "存储层命中长度",
    "req.cache_protected_len": "已插入并受保护的前缀长度",
    "req.cached_tokens": "请求累计缓存 token 数",
    "req.cached_tokens_device": "设备层缓存 token 数",
    "req.cached_tokens_host": "Host 层缓存 token 数",
    "req.cached_tokens_storage": "存储层缓存 token 数",
    "req.kv_committed_len": "已提交 KV 长度",
    "req.kv_allocated_len": "已分配 KV 长度",
    "req.swa_evicted_seqlen": "已提前释放的 SWA 序列位置",
    "req.extend_input_len": "本次 prefill 要算的 token 数",
    "req.stream": "调度器 stream 标记",
    "sampling.max_new_tokens": "重放 completion cap，不是线上 max_tokens",
    "sampling.temperature": "采样温度（调度器副本）",
    "sampling.top_p": "top_p（调度器副本）",
    "sampling.top_k": "top_k（调度器副本）",
    "sampling.min_p": "min_p（调度器副本）",
    "sampling.frequency_penalty": "频率惩罚（调度器副本）",
    "sampling.presence_penalty": "存在惩罚（调度器副本）",
    "sampling.repetition_penalty": "重复惩罚（调度器副本）",
    "sampling.n": "并行生成条数（调度器副本）",
    "sampling.ignore_eos": "ignore_eos（调度器副本）",
    "sampling.no_stop_trim": "no_stop_trim（调度器副本）",
    "sampling.min_new_tokens": "最小生成 token 数（调度器副本）",
    "sampling.seed": "采样种子（调度器副本）",
    "sampling.stop_strs": "停止字符串条数（调度器）",
    "sampling.stop_token_ids": "停止 token id 个数（调度器）",
    "sampling.stop_regex_strs": "停止正则条数（调度器）",
    "time.created_time": "API 创建请求时刻（重放时钟）",
    "time.tokenize_finish_time": "分词完成时刻",
    "time.api_server_dispatch_time": "API 开始发送时刻",
    "time.api_server_dispatch_finish_time": "API 发送完成时刻",
    "time.first_token_time": "首 token 时刻",
    "time.last_time": "最近一次输出时刻",
    "time.finished_time": "请求完成时刻",
    "time.response_sent_to_client_time": "响应发给客户端时刻",
    "time.scheduler_recv_time": "调度器收到请求时刻",
    "time.wait_queue_entry_time": "进入等待队列时刻",
    "time.forward_entry_time": "进入执行阶段时刻",
    "time.prefill_finished_time": "prefill 完成时刻",
    "time.completion_time": "调度器确认完成时刻",
    "session.session_id": "原生 Session ID",
    "session.capacity_of_str_len": "Session 字符串容量",
    "session.streaming": "Session 是否流式",
    "session.timeout": "Session 超时",
    "session.last_active_time": "Session 最近活动时刻",
    "session.req_nodes": "Session 保存的请求节点数",
    "session.close_on_finish": "完成后是否关闭 Session",
    "session._inflight": "Session 是否有在飞请求",
    "last_node.children": "命中节点的子节点数",
    "last_node.parent": "父节点 id",
    "last_node.key": "是否有 RadixKey",
    "last_node.key.token_ids": "节点保存的 token 数",
    "last_node.key.extra_key": "节点 key.extra_key",
    "last_node.key.is_bigram": "key 是否 bigram",
    "last_node.value": "节点设备 KV 索引个数",
    "last_node.last_access_time": "节点最近访问值（重放时钟）",
    "last_node.hit_count": "节点命中计数",
    "last_node.host_value": "Host KV 索引个数",
    "last_node.hash_value": "页 hash 个数",
    "last_node.id": "运行时节点 ID",
    "last_node.lock_ref": "节点锁引用计数",
    "last_node.creation_time": "节点创建时刻",
    "last_node.host_ref_counter": "Host KV 保护计数",
    "last_node.write_through_pending_id": "等待写穿完成的 ID",
    "last_node.priority": "节点保存的请求优先级",
    "last_node.swa_tombstone": "SWA KV 是否已释放",
    "last_node.full_lock_ref": "Full KV 锁引用计数",
    "last_node.swa_lock_ref": "SWA 锁引用计数",
    "last_node.prev": "Full LRU 前驱 id",
    "last_node.next": "Full LRU 后继 id",
    "last_node.swa_prev": "SWA LRU 前驱 id",
    "last_node.swa_next": "SWA LRU 后继 id",
    "last_node.swa_uuid": "SWA 锁窗口标识",
    "resource.num_tokens": "本次要释放的 Full token 数（驱逐时）",
    "resource.swa_num_tokens": "本次要释放的 SWA token 数",
    "resource.size": "KV 池容量",
    "resource.page_size": "KV 页大小",
    "resource.available_size": "当前可用容量",
    "resource.evictable_size": "当前可驱逐数量",
    "resource.protected_size": "当前受保护数量",
    "resource.full_available_size": "Full 可用容量",
    "resource.swa_available_size": "SWA 可用容量",
    "resource.full_evictable_size_": "Full 可驱逐数量",
    "resource.swa_evictable_size_": "SWA 可驱逐数量",
    "resource.full_protected_size_": "Full 受保护数量",
    "resource.swa_protected_size_": "SWA 受保护数量",
    "resource.sliding_window_size": "SWA 窗口大小",
    "scheduler.waiting_queue": "等待队列请求数",
    "scheduler.running_batch": "running batch 请求数",
    "scheduler.cur_batch": "当前 batch 请求数",
}


def source_of(name: str) -> str:
    prefix = name.split(".", 1)[0]
    return SOURCE.get(prefix, prefix)


def group_of(name: str) -> str:
    for g, spec in GROUPS.items():
        if name in spec["features"]:
            return g
    return "ungrouped"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    p.add_argument("--dump-file", default="server_dump/native_pid1681410.jsonl")
    p.add_argument("--n-repeats", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "experiments/session_return/lgbm",
    )
    args = p.parse_args()
    names, X, y, d, sm = load_xy(args.run_dir, args.dump_file)
    missing_meaning = [n for n in names if n not in MEANING]
    if missing_meaning:
        raise SystemExit(f"missing meaning: {missing_meaning}")
    obs = d == 1
    tr, va, te = sm["train"], sm["val"], sm["test"]
    leaky_cols = set(cols_of(names, GROUPS[LEAKY]["features"]).tolist())
    base_keep = np.array([j for j in range(len(names)) if j not in leaky_cols], dtype=int)
    all_keep = np.arange(len(names), dtype=int)
    spec_by = {s[0]: s for s in SPECS}

    def fit(keep):
        return fit_lgbm(X[tr & obs][:, keep], y[tr & obs], X[va & obs][:, keep], y[va & obs])

    base_model = fit(base_keep)
    leaky_model = fit(all_keep)
    evals = {"val": va & obs, "test": te & obs}

    def rank_in_model(model, keep, which_names, seed0):
        pos = {names[j]: k for k, j in enumerate(keep)}
        Xmap = {s: X[evals[s]][:, keep] for s in evals}
        ymap = {s: y[evals[s]] for s in evals}
        intact = {
            s: float(mean_absolute_error(ymap[s], model.predict(Xmap[s]))) for s in evals
        }
        rows = []
        seed = seed0
        Xtr = X[tr][:, keep]
        for name in which_names:
            j = pos[name]
            finite = Xtr[:, j][np.isfinite(Xtr[:, j])]
            nuniq = int(len(np.unique(np.round(finite, 12)))) if finite.size else 0
            kind = spec_by[name][3]
            rec = {
                "feature": name,
                "group": group_of(name),
                "source": source_of(name),
                "meaning": MEANING[name],
                "kind": kind,
                "kind_zh": KIND_ZH[kind],
                "path": spec_by[name][2],
                "n_unique_train": nuniq,
                "official_model": "no_leaky" if name not in GROUPS[LEAKY]["features"] else "with_leaky",
            }
            for split in evals:
                deltas = perm_deltas(
                    model, Xmap[split], ymap[split], np.array([j]), args.n_repeats, seed
                )
                rec[split] = summarize(deltas, intact[split])
                seed += 1
            rows.append(rec)
        return rows

    base_names = [n for n in names if n not in GROUPS[LEAKY]["features"]]
    rows = rank_in_model(base_model, base_keep, base_names, args.seed)
    rows += rank_in_model(
        leaky_model, all_keep, GROUPS[LEAKY]["features"], args.seed + 10000
    )
    rows.sort(key=lambda r: (-r["val"]["delta_mae_mean"], r["feature"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    pipe = json.loads((args.out_dir / "inventory_group_pipeline.json").read_text())
    out = {
        "n_features": len(rows),
        "n_repeats": args.n_repeats,
        "feature_ranking": rows,
        "groups": pipe["groups"],
        "full_no_leaky": pipe["full_no_leaky"],
        "mean_baseline": pipe["mean_baseline"],
        "note": (
            "Feature rank = 单列 permutation ΔMAE on official 168-col model "
            "(no leaky cap). leaky_replay_cap scored in the 169-col model. "
            "Group metrics copied from inventory_group_pipeline.json."
        ),
    }
    path = args.out_dir / "inventory_importance_catalog.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("n", len(rows))
    for r in rows[:15]:
        print(
            f"{r['rank']:3d} {r['feature']:42s} {r['group']:22s} "
            f"val {r['val']['delta_mae_mean']:+.4f}  {r['meaning']}"
        )
    print("wrote", path)


if __name__ == "__main__":
    main()
