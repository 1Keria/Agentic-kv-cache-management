from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from sglang.srt.mem_cache.cache_init_params import CacheInitParams

logger = logging.getLogger(__name__)


def init_reuse_value_fields(node) -> None:
    node.reuse_strength = 0.0
    node.last_turnover = 0.0
    node.reuse_count = 0
    node.terminal_count = 0
    node.prefix_depth = 0
    node.reuse_value_density = 0.0


def copy_reuse_value_on_split(new_node, child) -> None:
    new_node.reuse_strength = child.reuse_strength
    new_node.last_turnover = child.last_turnover
    new_node.reuse_count = child.reuse_count
    new_node.terminal_count = 0
    parent = new_node.parent
    if parent is not None:
        new_node.prefix_depth = parent.prefix_depth + len(new_node.key)


class ReuseValueMixin:
    def init_reuse_value_from_params(
        self,
        params: "CacheInitParams",
        eviction_policy: str,
        uses_reuse_value: bool,
    ) -> None:
        self.reuse_value_shadow_only = params.reuse_value_shadow_only
        self.reuse_value_turnover_kappa = float(params.reuse_value_turnover_kappa)
        self.reuse_value_base_cold_strength = float(
            params.reuse_value_base_cold_strength
        )
        if self.reuse_value_turnover_kappa <= 0:
            raise ValueError("reuse_value_turnover_kappa must be greater than zero")
        if self.reuse_value_base_cold_strength < 0:
            raise ValueError(
                "reuse_value_base_cold_strength must be greater than or equal to zero"
            )
        if self.reuse_value_shadow_only and eviction_policy != "lru":
            raise ValueError("reuse_value_shadow_only requires eviction_policy='lru'")
        self.reuse_value_enabled = (
            uses_reuse_value
            or params.enable_reuse_value_estimator
            or self.reuse_value_shadow_only
        )

    def reset_reuse_value_counters(self) -> None:
        self.reuse_value_inserted_tokens_total = 0
        allocator = getattr(self, "token_to_kv_pool_allocator", None)
        size = getattr(allocator, "size_full", None)
        if not isinstance(size, (int, float)):
            size = getattr(allocator, "size", 1)
        if not isinstance(size, (int, float)):
            size = 1
        self.reuse_value_cache_capacity_tokens = max(1, int(size))

    @property
    def reuse_value_global_turnover(self) -> float:
        return (
            self.reuse_value_inserted_tokens_total
            / self.reuse_value_cache_capacity_tokens
        )

    def _materialize_reuse_strength(self, node) -> float:
        current_turnover = self.reuse_value_global_turnover
        delta = max(0.0, current_turnover - node.last_turnover)
        if delta and not math.isinf(self.reuse_value_turnover_kappa):
            node.reuse_strength *= math.exp(-delta / self.reuse_value_turnover_kappa)
        node.last_turnover = current_turnover
        return node.reuse_strength

    def _record_reuse(self, node) -> None:
        if not self.reuse_value_enabled:
            return
        self._materialize_reuse_strength(node)
        node.reuse_strength += 1.0
        node.reuse_count += 1

    def _initialize_reuse_value_node(self, node, parent) -> None:
        parent_strength = self._materialize_reuse_strength(parent)
        if parent is not getattr(self, "root_node", None) and parent.terminal_count > 0:
            node.reuse_strength = parent_strength
        else:
            node.reuse_strength = self.reuse_value_base_cold_strength
        node.prefix_depth = parent.prefix_depth + len(node.key)

    def _record_reuse_value_insert(self, num_tokens: int) -> None:
        if self.reuse_value_enabled and num_tokens > 0:
            self.reuse_value_inserted_tokens_total += num_tokens

    def _refresh_reuse_value_density(self, node) -> None:
        if not self.reuse_value_enabled:
            return
        kv_size = len(node.value)
        if kv_size <= 0:
            raise RuntimeError(
                f"reuse_value eviction candidate has no KV: node_id={node.id}"
            )
        effective_strength = self._materialize_reuse_strength(node)
        recompute_tokens = len(node.key)
        node.reuse_value_density = effective_strength * recompute_tokens / kv_size

    def _log_reuse_value_shadow(self, leaves: list) -> None:
        if not self.reuse_value_shadow_only or not leaves:
            return
        for node in leaves:
            self._refresh_reuse_value_density(node)

        lru_victim = min(leaves, key=lambda node: node.last_access_time)
        value_victim = min(
            leaves,
            key=lambda node: (node.reuse_value_density, node.last_access_time),
        )
        logger.info(
            "KV_VALUE_SHADOW turnover=%.6f candidates=%d "
            "lru_victim=%d lru_victim_value=%.6f "
            "reuse_value_victim=%d reuse_value=%.6f agree=%s",
            self.reuse_value_global_turnover,
            len(leaves),
            lru_victim.id,
            lru_victim.reuse_value_density,
            value_victim.id,
            value_victim.reuse_value_density,
            lru_victim is value_victim,
        )

    def _select_reuse_value_victim(self, candidates: Iterable, fallback):
        nodes = list(candidates)
        if not nodes:
            return fallback
        self._log_reuse_value_shadow(nodes)
        if not self.reuse_value_enabled or self.reuse_value_shadow_only:
            return fallback
        for node in nodes:
            self._refresh_reuse_value_density(node)
        return min(
            nodes, key=lambda node: (node.reuse_value_density, node.last_access_time)
        )
