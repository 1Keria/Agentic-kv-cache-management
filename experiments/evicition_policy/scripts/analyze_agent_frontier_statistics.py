#!/usr/bin/env python3
"""Count exact content-prefix demand; explicitly leave real eviction frontiers unknown.

No serving engine, GPU, cache simulator, or hypothetical eviction is invoked.
The optional input-history tree has unlimited retention and no locks. Its leaves
are logical complete pages, NOT runtime radix nodes or legal eviction candidates.
"""

from __future__ import annotations

import argparse
import bisect
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import struct
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_agent_policy_insights import (
    DEFAULT_SUITE, PAGE_SIZE, POLICIES, ROOT, discover_runs, distribution,
    load_policy_records, read_json, save_json, sha256_file, write_csv,
)
from build_workload import read_rows
from prepare_data import canonical_digest

DEFAULT_OUTPUT = ROOT / "results/analysis/agent_frontier_statistics_20260928"


def prefix_pages(tokens: list[int], page_size: int = PAGE_SIZE) -> list[bytes]:
    """Identity includes all preceding full pages; session ID is not a salt."""
    import hashlib

    parent = b""
    result = []
    for start in range(0, len(tokens) - page_size + 1, page_size):
        parent = hashlib.sha256(
            parent + struct.pack(f"<{page_size}I", *tokens[start:start + page_size])
        ).digest()
        result.append(parent)
    return result


def generated_page_overlaps(
    input_ids: list[int], output_ids: list[int], page_size: int = PAGE_SIZE,
) -> list[tuple[bytes, int]]:
    """Full I+O content pages intersecting O, weighted by output tokens only.

    This does not assert these pages were committed to a KV pool. In particular
    the final sampled token may not have a committed KV entry.
    """
    pages = prefix_pages(input_ids + output_ids, page_size)
    start = len(input_ids) // page_size
    return [
        (pages[index], min(page_size, (index + 1) * page_size - len(input_ids)))
        for index in range(start, len(pages))
    ]


def lcp(left: list[int], right: list[int]) -> int:
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return index
    return min(len(left), len(right))


def generation_next_overlap(input_ids, output_ids, next_input_ids) -> int:
    return max(0, lcp(input_ids + output_ids, next_input_ids) - len(input_ids))


def demand_bin(count: int) -> str:
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    if count < 5:
        return "3_4"
    if count < 10:
        return "5_9"
    if count < 20:
        return "10_19"
    return "20_plus"


class InputHistoryTree:
    """Unlimited input-content page tree. Never call this an eviction frontier."""

    def __init__(self):
        self.demands = Counter()
        self.leaves = set()
        self.parents = {}

    def add_request(self, pages: list[bytes]) -> dict:
        previous_counts = [self.demands[page] for page in pages]
        parent = None
        for page in pages:
            if page not in self.parents:
                self.parents[page] = parent
                self.leaves.add(page)
                self.leaves.discard(parent)
            elif self.parents[page] != parent:
                raise ValueError("Inconsistent full-prefix identity")
            self.demands[page] += 1
            parent = page
        once = sum(self.demands[page] == 1 for page in self.leaves)
        return {
            "input_complete_pages": len(pages),
            "pages_with_no_prior_request_demand": sum(x == 0 for x in previous_counts),
            "pages_with_one_prior_request_demand": sum(x == 1 for x in previous_counts),
            "pages_with_at_least_two_prior_request_demands": sum(x >= 2 for x in previous_counts),
            "history_tree_leaf_pages": len(self.leaves),
            "history_tree_leaf_pages_one_observed_demand": once,
            "history_tree_leaf_pages_repeated_demand": len(self.leaves) - once,
            "history_tree_leaf_once_fraction": once / len(self.leaves) if self.leaves else None,
        }


def load_content(workload: dict, policy_records: dict):
    inputs = {}
    outputs = {policy: [] for policy in POLICIES}
    paths = []
    for entry in workload["sessions"]:
        rows = read_rows(entry)
        paths.append(ROOT / entry["path"])
        for index, row in enumerate(rows):
            key = (row["session_id"], row["turn_index"])
            ids = row["input_ids"]
            previous = rows[index - 1] if index else None
            next_row = rows[index + 1] if index + 1 < len(rows) else None
            prefix_length = lcp(previous["input_ids"], ids) if previous else None
            inputs[key] = {
                "session_id": key[0], "turn_index": key[1], "task_id": row["task_id"],
                "pages": prefix_pages(ids), "prompt_tokens": len(ids),
                "input_ids_sha256": row["input_ids_sha256"],
                "is_last_observed_session_request": next_row is None,
                "is_strict_append_from_previous": None if previous is None else prefix_length == len(previous["input_ids"]),
                "previous_input_lcp_tokens": prefix_length,
            }
            for policy in POLICIES:
                record = policy_records[policy][key]
                if record["input_ids_sha256"] != row["input_ids_sha256"] or record["prompt_tokens"] != len(ids):
                    raise ValueError(f"Input mismatch: {policy} {key}")
                output_ids = record["output_ids"]
                if len(output_ids) != record["actual_output_tokens"] or canonical_digest(output_ids) != record["output_ids_sha256"]:
                    raise ValueError(f"Output hash or length mismatch: {policy} {key}")
                if next_row is not None:
                    following = policy_records[policy][(key[0], key[1] + 1)]
                    if record["completed_seconds"] > following["submitted_seconds"]:
                        raise ValueError("Session dependency overlaps; this analysis assumes serial requests")
                outputs[policy].append({
                    "policy": policy, "session_id": key[0], "turn_index": key[1],
                    "task_id": row["task_id"], "output_tokens": len(output_ids),
                    "completed_seconds": record["completed_seconds"],
                    "has_observed_next_session_request": next_row is not None,
                    "next_input_raw_output_prefix_tokens": None if next_row is None else generation_next_overlap(ids, output_ids, next_row["input_ids"]),
                    "pages": generated_page_overlaps(ids, output_ids),
                })
        del rows
    expected = set(policy_records["lru"])
    if set(inputs) != expected or len(inputs) != workload["requests"]:
        raise ValueError("Frozen workload and measured requests differ")
    return inputs, outputs, paths


def input_demand_evidence(inputs: dict):
    global_visits = defaultdict(list)
    session_visits = defaultdict(lambda: defaultdict(list))
    for key, row in sorted(inputs.items()):
        for page in row["pages"]:
            global_visits[page].append(key)
            session_visits[key[0]][page].append(key[1])
    counts = Counter(len(visits) for visits in global_visits.values())
    histogram = []
    for label in ("1", "2", "3_4", "5_9", "10_19", "20_plus"):
        members = [len(visits) for visits in global_visits.values() if demand_bin(len(visits)) == label]
        histogram.append({
            "observed_request_demand_count_bin": label,
            "distinct_content_pages": len(members), "distinct_content_tokens": len(members) * PAGE_SIZE,
            "page_request_references": sum(members),
        })
    singletons = [visits[0] for visits in global_visits.values() if len(visits) == 1]
    singleton_last = sum(inputs[key]["is_last_observed_session_request"] for key in singletons)
    sessions = []
    for session, pages in sorted(session_visits.items()):
        session_keys = sorted(key for key in inputs if key[0] == session)
        last_turn = session_keys[-1][1]
        one = [turns[0] for turns in pages.values() if len(turns) == 1]
        sessions.append({
            "session_id": session, "task_id": inputs[session_keys[0]]["task_id"],
            "requests": len(session_keys), "unique_content_pages": len(pages),
            "pages_with_one_observed_demand": len(one),
            "pages_with_at_least_two_observed_demands": len(pages) - len(one),
            "single_demand_pages_first_seen_in_last_observed_request": sum(t == last_turn for t in one),
            "single_demand_pages_despite_later_observed_requests": sum(t < last_turn for t in one),
        })
    cohort_rows = []
    for key, row in sorted(inputs.items()):
        pages = session_visits[key[0]]
        first_pages = [page for page in row["pages"] if pages[page][0] == key[1]]
        later = sum(len(pages[page]) >= 2 for page in first_pages)
        next_turn = sum(key[1] + 1 in pages[page] for page in first_pages)
        cohort_rows.append({
            "session_id": key[0], "task_id": row["task_id"], "turn_index": key[1],
            "has_observed_next_session_request": not row["is_last_observed_session_request"],
            "is_strict_append_from_previous": row["is_strict_append_from_previous"],
            "new_to_session_complete_pages": len(first_pages),
            "new_pages_demanded_by_next_session_request": next_turn,
            "new_pages_demanded_by_any_later_observed_session_request": later,
            "new_pages_without_observed_later_session_demand": len(first_pages) - later,
        })
    with_next = [row for row in cohort_rows if row["has_observed_next_session_request"]]
    born_eligible = sum(row["new_to_session_complete_pages"] for row in with_next)
    strata = {}
    for label, shape in (("first_observed_request", None), ("strict_append", True), ("rewrite", False)):
        members = [row for row in with_next if row["is_strict_append_from_previous"] is shape]
        strata[label] = {
            "requests_with_observed_next_request": len(members),
            "new_to_session_complete_pages": sum(row["new_to_session_complete_pages"] for row in members),
            "pages_demanded_in_next_request": sum(row["new_pages_demanded_by_next_session_request"] for row in members),
            "pages_demanded_in_any_later_observed_request": sum(row["new_pages_demanded_by_any_later_observed_session_request"] for row in members),
        }
    summary = {
        "unique_complete_input_content_pages": len(global_visits),
        "unique_complete_input_content_tokens": len(global_visits) * PAGE_SIZE,
        "page_request_references": sum(len(visits) for visits in global_visits.values()),
        "complete_page_input_token_references": sum(len(visits) for visits in global_visits.values()) * PAGE_SIZE,
        "unaligned_input_tail_token_references": sum(row["prompt_tokens"] % PAGE_SIZE for row in inputs.values()),
        "pages_with_one_observed_request_demand": counts[1],
        "pages_with_at_least_two_observed_request_demands": len(global_visits) - counts[1],
        "fraction_unique_pages_with_repeated_demand": (len(global_visits) - counts[1]) / len(global_visits) if global_visits else None,
        "singleton_pages_first_seen_in_last_observed_session_request": singleton_last,
        "singleton_pages_despite_later_observed_session_requests": len(singletons) - singleton_last,
        "pages_referenced_by_multiple_sessions": sum(len({key[0] for key in visits}) > 1 for visits in global_visits.values()),
        "next_request_cohort": {
            "eligible_requests": len(with_next),
            "new_to_session_complete_pages": born_eligible,
            "pages_demanded_in_next_request": sum(row["new_pages_demanded_by_next_session_request"] for row in with_next),
            "pages_demanded_in_any_later_observed_request": sum(row["new_pages_demanded_by_any_later_observed_session_request"] for row in with_next),
        },
        "next_request_cohort_by_transition_into_birth_request": strata,
        "censoring": "All pages without an observed later demand have unknown future; the last-request group has no following same-session opportunity at all. No singleton is labeled permanently useless.",
    }
    return summary, histogram, sessions, cohort_rows, global_visits, session_visits


def history_tree_evidence(inputs: dict, policy_records: dict):
    snapshots = []
    summaries = {}
    for policy in POLICIES:
        tree = InputHistoryTree()
        selected = []
        for key in sorted(inputs, key=lambda k: (policy_records[policy][k]["submitted_seconds"], k)):
            state = tree.add_request(inputs[key]["pages"])
            selected.append({"policy": policy, "session_id": key[0], "turn_index": key[1], **state})
        snapshots.extend(selected)
        leaves = len(tree.leaves)
        once = sum(tree.demands[page] == 1 for page in tree.leaves)
        reference_count = sum(row["input_complete_pages"] for row in selected)
        prior_two = sum(row["pages_with_at_least_two_prior_request_demands"] for row in selected)
        summaries[policy] = {
            "observation_points": len(selected),
            "pages_with_no_prior_demand_total": sum(row["pages_with_no_prior_request_demand"] for row in selected),
            "pages_with_one_prior_demand_total": sum(row["pages_with_one_prior_request_demand"] for row in selected),
            "pages_with_at_least_two_prior_demands_total": prior_two,
            "fraction_request_page_references_with_at_least_two_prior_demands": prior_two / reference_count if reference_count else None,
            "leaf_once_fraction_across_request_snapshots": distribution(row["history_tree_leaf_once_fraction"] for row in selected if row["history_tree_leaf_once_fraction"] is not None),
            "snapshots_with_all_history_leaves_single_demand": sum(row["history_tree_leaf_once_fraction"] == 1 for row in selected),
            "final_history_leaf_pages": leaves,
            "final_history_leaf_pages_single_demand": once,
            "final_history_leaf_pages_repeated_demand": leaves - once,
            "final_history_internal_pages": len(tree.demands) - leaves,
            "final_history_internal_pages_repeated_demand": sum(count >= 2 for page, count in tree.demands.items() if page not in tree.leaves),
        }
    return summaries, snapshots


def output_demand_evidence(outputs, inputs, global_visits, session_visits, policy_records):
    summaries = {}
    details = []
    for policy in POLICIES:
        demand_times = {
            page: sorted(policy_records[policy][key]["submitted_seconds"] for key in visits)
            for page, visits in global_visits.items()
        }
        policy_details = []
        unique_output_pages = set()
        for record in outputs[policy]:
            session, turn = record["session_id"], record["turn_index"]
            metrics = Counter()
            for page, overlap in record["pages"]:
                unique_output_pages.add(page)
                metrics["complete_output_intersecting_page_occurrences"] += 1
                metrics["output_tokens_covered_by_complete_content_pages"] += overlap
                local_turns = session_visits[session].get(page, [])
                global_times = demand_times.get(page, [])
                next_hit = turn + 1 in local_turns
                later_local = bool(local_turns and local_turns[-1] > turn)
                later_global = bisect.bisect_right(global_times, record["completed_seconds"]) < len(global_times)
                for name, hit in (("next_session_input", next_hit), ("later_session_input", later_local), ("later_any_session_input_after_completion", later_global)):
                    if hit:
                        metrics[f"page_occurrences_matched_in_{name}"] += 1
                        metrics[f"output_tokens_in_pages_matched_in_{name}"] += overlap
            row = {k: v for k, v in record.items() if k != "pages"}
            for name in (
                "complete_output_intersecting_page_occurrences", "output_tokens_covered_by_complete_content_pages",
                "page_occurrences_matched_in_next_session_input", "output_tokens_in_pages_matched_in_next_session_input",
                "page_occurrences_matched_in_later_session_input", "output_tokens_in_pages_matched_in_later_session_input",
                "page_occurrences_matched_in_later_any_session_input_after_completion", "output_tokens_in_pages_matched_in_later_any_session_input_after_completion",
            ):
                row[name] = metrics[name]
            row["output_tokens_not_covered_by_complete_content_pages"] = record["output_tokens"] - metrics["output_tokens_covered_by_complete_content_pages"]
            policy_details.append(row)
        eligible = [row for row in policy_details if row["has_observed_next_session_request"]]
        terminal = [row for row in policy_details if not row["has_observed_next_session_request"]]
        total_fields = [key for key in policy_details[0] if key.startswith(("output_tokens", "page_occurrences", "complete_output"))]
        def totals(group):
            return {field: sum(row[field] for row in group) for field in total_fields}
        summaries[policy] = {
            "requests": len(policy_details),
            "unique_output_intersecting_content_pages": len(unique_output_pages),
            "all_observed_requests": totals(policy_details),
            "requests_with_next_session_input": {
                "requests": len(eligible), **totals(eligible),
                "raw_output_prefix_match_tokens_total": sum(row["next_input_raw_output_prefix_tokens"] for row in eligible),
                "requests_with_entire_raw_output_matching_next_input": sum(row["next_input_raw_output_prefix_tokens"] == row["output_tokens"] for row in eligible),
                "requests_with_any_complete_output_page_matching_next_input": sum(row["page_occurrences_matched_in_next_session_input"] > 0 for row in eligible),
            },
            "last_observed_session_requests_future_unknown": {"requests": len(terminal), **totals(terminal)},
        }
        details.extend(policy_details)
    return summaries, details


def format_percent(numerator, denominator):
    return "未知" if not denominator else f"{100 * numerator / denominator:.2f}%"


def build_markdown(summary):
    inputs = summary["input_content_demand"]
    tree = summary["unbounded_input_history_tree_reference"]["policies"]["lru"]
    cohort = inputs["next_request_cohort"]
    append_cohort = inputs["next_request_cohort_by_transition_into_birth_request"]["strict_append"]
    unique = inputs["unique_complete_input_content_pages"]
    lines = [
        "# Agent 前缀重复需求与候选可观测性统计", "",
        "日期：2026-09-28。范围：冻结的 20 个会话、1,206 次请求及 LRU/LFU/SLRU 三次实测输出。", "",
        "## 1. 先说明哪些数字不存在", "",
        "现有 events.jsonl 是客户端请求/stream 事件。它未记录逐次回收的完整候选集合、节点身份、锁定、split 或父节点暴露。因此，真实回收候选中的新尾部、暴露祖先、已有真实回访叶子的节点数与物理字节占比均为 **未知（null）**，不是 0。无法从这批旧日志追溯这些统计。", "",
        "以下内容需求统计可直接复现；内容树只是无容量、无锁、永不淘汰的结构参照，不能称为真实 candidate frontier。", "",
        "## 2. 完整输入前缀页是否几乎都会重复出现", "",
        "单位为 256-token 完整前缀页。页身份包含其全部祖先 token；同一内容在不同位置或不同祖先下不能合并。session_id 不参与内容哈希。统计按不同请求的输入需求计数，不把首次插入、decode 步或调度器内部访问当作再次需求。", "",
        "| 指标 | 数量 |", "|---|---:|",
        f"| 冻结子集的不同完整输入前缀页 | {unique:,} |",
        f"| 观察到至少两次请求需求的页 | {inputs['pages_with_at_least_two_observed_request_demands']:,}（{format_percent(inputs['pages_with_at_least_two_observed_request_demands'], unique)}） |",
        f"| 观察到一次需求的页 | {inputs['pages_with_one_observed_request_demand']:,} |",
        f"| 单次页：首次出现在会话最后一次已观测请求 | {inputs['singleton_pages_first_seen_in_last_observed_session_request']:,} |",
        f"| 单次页：此后仍有同会话请求，但窗口内没有再次需求 | {inputs['singleton_pages_despite_later_observed_session_requests']:,} |",
        f"| 跨 session 共同引用的完整输入页 | {inputs['pages_referenced_by_multiple_sessions']:,} |", "",
        "所有窗口内未再需求的页，其窗口之后的未来都未知；末轮组更是没有后续同会话观测机会。不能把这些页全部叫永久无用或任务结束残留。", "",
        f"在有下一轮的 {cohort['eligible_requests']:,} 个请求中，新出现于该 session 的完整页共有 {cohort['new_to_session_complete_pages']:,} 个，其中 {cohort['pages_demanded_in_next_request']:,} 个在下一轮再次需求（{format_percent(cohort['pages_demanded_in_next_request'], cohort['new_to_session_complete_pages'])}），{cohort['pages_demanded_in_any_later_observed_request']:,} 个在观察到的后续请求中再次需求。", "",
        f"上项包含每个 session 的首次请求。单独只取由严格追加产生、且后面还有下一轮的请求：新页 {append_cohort['new_to_session_complete_pages']:,} 个，下一轮再次需求 {append_cohort['pages_demanded_in_next_request']:,} 个（{format_percent(append_cohort['pages_demanded_in_next_request'], append_cohort['new_to_session_complete_pages'])}）。此处『新』指首次出现在请求输入中，不是首次实际分配 KV。", "",
        "## 3. 重复页是否集中在内容树内部", "",
        "将所有已提交输入按 LRU 那次运行的客户端提交顺序加入一个永不淘汰的完整页前缀树，在每次输入加入后观察一次；LFU/SLRU 顺序另行复算。这个过程无容量限制、无真实缓存写入、无锁、无回收，也没有加入生成输出。", "",
        f"最终内容树有 {tree['final_history_leaf_pages']:,} 个末端页，其中 {tree['final_history_leaf_pages_single_demand']:,} 个只有一次已观测输入需求，{tree['final_history_leaf_pages_repeated_demand']:,} 个有重复需求；内部页有 {tree['final_history_internal_pages']:,} 个，其中 {tree['final_history_internal_pages_repeated_demand']:,} 个有重复需求。", "",
        f"在 {tree['observation_points']:,} 次输入后的结构快照中，末端页单次需求占比的中位数为 {100 * tree['leaf_once_fraction_across_request_snapshots']['p50']:.2f}%；全部末端页均只有一次需求的快照有 {tree['snapshots_with_all_history_leaves_single_demand']:,} 次。这里的末端页既不是压缩 radix 节点，也不是实际可回收集合。", "",
        f"另一个分母是请求×页需求：共有 {inputs['page_request_references']:,} 次完整页需求，其中 {tree['pages_with_at_least_two_prior_demands_total']:,} 次在到达前就已有至少两次历史输入需求（{100 * tree['fraction_request_page_references_with_at_least_two_prior_demands']:.2f}%）。这描述全体输入需求的门槛饱和程度，同样不能替代合法候选中的分布。", "",
        "这项结构参照用来检验『复用资格可能集中于内部历史，而新尾部缺少自身回访证据』，不能据此断言真实候选也有相同比例。尤其旧祖先被回收过程暴露的次数在此参照中根本不存在，必须另采引擎事件。", "",
        "## 4. 实测生成与历史下一轮是否沿同一分支", "",
        "下表只取有下一轮的请求；20 个会话末轮单列未知。完整页可以跨越 input/output 边界，但只按其中属于 output 的 token 计权；未满页的输出尾部不进入页级分母。所有数字都是内容匹配，未确认实际 KV 是否提交到缓存。", "",
        "| 策略 | 有下一轮的请求 | 输出 token | 完整页覆盖的输出 token | 下一轮匹配这些页的输出 token | 页内输出匹配率 |", "|---|---:|---:|---:|---:|---:|",
    ]
    for policy in POLICIES:
        row = summary["generated_output_content"][policy]["requests_with_next_session_input"]
        matched = row["output_tokens_in_pages_matched_in_next_session_input"]
        covered = row["output_tokens_covered_by_complete_content_pages"]
        lines.append(f"| {policy.upper()} | {row['requests']:,} | {row['output_tokens']:,} | {covered:,} | {matched:,} | {format_percent(matched, covered)} |")
    lines += [
        "", "观察到的输入历史持续追加，不代表每次本地生成都成为下一轮历史；输出分支的内容证据必须单列。未匹配不代表曾驻留、曾被淘汰或永久无用，也不能由完整输出不匹配推出一个 token 都未复用。", "",
        "## 5. 对二次机会的判断", "",
        "应把两个问题拆开：全体输入内容是否普遍复用，以及真正回收时的合法候选能否被复用信号区分。前者由本报告直接统计；后者仍缺事件证据。若重复需求主要集中在结构内部，仅按累计需求门槛保护不一定能区分初始新尾部候选，但可能影响删尾后继续向祖先回收的深度。这个作用尚未测量。", "",
        "不能据此宣布二次机会有效或无效，也不能由 LRU/SLRU 正反案例宣布父链信用已被证伪。下一步所需的是只读的、按池区分的完整候选快照，以及每次删叶后新暴露父节点的记录。首次插入、结构性 split 继承和不同请求的真实 demand 必须分开计数。", "",
        "## 6. 复现、文件与限制", "",
        "- 先用 `scripts/audit_agent_frontier_logs.py --output <audit.json>` 生成审计，再运行 `scripts/analyze_agent_frontier_statistics.py --audit <audit.json> --output <new_analysis_directory>`；路径均须位于本实验目录。脚本拒绝覆盖已有 summary。",
        "- `input_page_demand_histogram.csv`、`session_page_demands.csv`：全局与每会话的页需求次数。",
        "- `new_input_page_cohorts.csv`：新内容第一次、下一次和后续需求。",
        "- `input_history_tree_snapshots.csv`：三种提交顺序下的无容量输入内容树结构参照。",
        "- `generated_output_page_demand.csv`：每次生成的完整页及 raw token 后续匹配。",
        "- `log_coverage_audit.json`、`summary.json`、`manifest.json`：日志证据能力、汇总与输入/输出哈希。",
        "- 前缀标识仅在单一声明模型/编码上下文内比较；运行时完整 namespace 没有逐请求采集，不能把内容身份当物理缓存身份。",
        "- 完整页 token 数不是实际 KV 字节，未合并 Full/SWA；页面不等于压缩 radix 节点。",
        "- 无穷历史内容树、客户端提交/完成时间均不能恢复引擎内部匹配、写入、锁定和淘汰顺序。",
        "- 一次观测的内容可能在窗口之后再需求；任何策略选择都不得使用本报告的未来标签作为在线信号。", "",
    ]
    return "\n".join(lines)


def run(suite: Path, output: Path, audit_path: Path):
    for path in (suite, output, audit_path):
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError("All paths must stay inside this experiment")
    if (output / "summary.json").exists():
        raise FileExistsError("Refusing to overwrite an existing analysis")
    output.mkdir(parents=True, exist_ok=True)
    audit = read_json(audit_path)
    if audit["run_id"] != suite.name:
        raise ValueError("Audit and source suite differ")
    runs = discover_runs(suite)
    records = load_policy_records(runs)
    workloads = {policy: read_json(folder / "workload.json") for policy, folder in runs.items()}
    if any(value != workloads["lru"] for value in workloads.values()):
        raise ValueError("Policies do not use the same workload")
    inputs, outputs, encoded_paths = load_content(workloads["lru"], records)
    demand, histogram, sessions, cohorts, visits, session_visits = input_demand_evidence(inputs)
    trees, snapshots = history_tree_evidence(inputs, records)
    output_demand, output_details = output_demand_evidence(outputs, inputs, visits, session_visits, records)
    summary = {
        "analysis_id": output.name, "created_date": "2026-09-28",
        "scope": {"sessions": len(workloads["lru"]["sessions"]), "requests": len(inputs),
                  "input_tokens": sum(row["prompt_tokens"] for row in inputs.values()), "page_size": PAGE_SIZE,
                  "source_suite": str(suite.relative_to(ROOT))},
        "real_eviction_frontier": {
            "status": "not_observable_from_existing_logs",
            "fresh_tail_candidate_nodes": None, "fresh_tail_candidate_physical_bytes": None,
            "newly_exposed_ancestor_candidate_nodes": None, "newly_exposed_ancestor_candidate_physical_bytes": None,
            "revisited_leaf_candidate_nodes": None, "revisited_leaf_candidate_physical_bytes": None,
            "reference_bit_after_scan_distribution": None,
            "evidence_audit": str(audit_path.relative_to(ROOT)),
        },
        "input_content_demand": demand,
        "unbounded_input_history_tree_reference": {
            "is_real_eviction_frontier": False, "includes_generated_outputs": False,
            "unit": "complete content-prefix page, not compressed radix node", "policies": trees,
        },
        "generated_output_content": output_demand,
        "semantic_limits": [
            "Content identity under one declared model/encoding context; full runtime namespace not observed.",
            "All unmatched future demand is right-censored; final observed request is not an explicit lifecycle end.",
            "Input demand, KV insertion, cache hit, decode reuse and eviction eligibility are distinct.",
            "Output content pages do not prove KV commit; final sampled-token KV is especially unknown.",
            "No physical occupancy, per-pool eviction cause, lost-retention cost or finite-cache counterfactual is estimated.",
        ],
    }
    tables = {
        "input_page_demand_histogram.csv": histogram, "session_page_demands.csv": sessions,
        "new_input_page_cohorts.csv": cohorts, "input_history_tree_snapshots.csv": snapshots,
        "generated_output_page_demand.csv": output_details,
    }
    for name, rows in tables.items():
        write_csv(output / name, rows)
    save_json(output / "summary.json", summary)
    (output / "frontier_statistics.md").write_text(build_markdown(summary), encoding="utf-8")
    sources = {"suite": suite / "suite.json", "audit": audit_path,
               "script": Path(__file__), "input_loader": SCRIPT_DIR / "build_workload.py",
               "analysis_helpers": SCRIPT_DIR / "analyze_agent_policy_insights.py",
               "token_digest_helper": SCRIPT_DIR / "prepare_data.py"}
    for policy, folder in runs.items():
        sources[f"{policy}_requests"] = folder / "measurement/requests.jsonl"
        sources[f"{policy}_workload"] = folder / "workload.json"
    for path in encoded_paths:
        sources[f"encoded_{path.name}"] = path
    produced = list(tables) + ["summary.json", "frontier_statistics.md"]
    save_json(output / "manifest.json", {
        "analysis_id": output.name,
        "inputs": {name: {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)} for name, path in sorted(sources.items())},
        "outputs": {name: sha256_file(output / name) for name in produced},
        "csv_data_rows": {name: len(rows) for name, rows in tables.items()},
    })
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    suite, output = args.suite.resolve(), args.output.resolve()
    audit_path = (args.audit or DEFAULT_OUTPUT / "log_coverage_audit.json").resolve()
    summary = run(suite, output, audit_path)
    print(json.dumps({"scope": summary["scope"], "input_content_demand": summary["input_content_demand"],
                      "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
