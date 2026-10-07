from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Optional

import torch

if TYPE_CHECKING:
    from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator
    from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
    from sglang.srt.mem_cache.unified_cache_components import ComponentType
    from sglang.srt.mem_cache.unified_cache_components.tree_component import (
        TreeComponent,
    )


@dataclasses.dataclass
class CacheInitParams:
    disable: bool
    req_to_token_pool: ReqToTokenPool
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator
    page_size: int

    is_eagle: bool = False
    tp_cache_group: Optional[torch.distributed.ProcessGroup] = None
    attn_cp_cache_group: Optional[torch.distributed.ProcessGroup] = None
    attn_tp_cache_group: Optional[torch.distributed.ProcessGroup] = None
    pp_cache_group: Optional[torch.distributed.ProcessGroup] = None
    eviction_policy: str = "lru"
    enable_reuse_value_estimator: bool = False
    reuse_value_shadow_only: bool = False
    reuse_value_turnover_kappa: float = 1.0
    reuse_value_base_cold_strength: float = 1.0
    disable_finished_insert: bool = False

    # Optional fixed or dynamic KV-token quotas for request identity regions.
    enable_request_cache_regions: bool = False
    request_agent_cache_ratio: float = 0.5
    request_cache_region_policy: str = "fixed"
    # Deprecated compatibility field; dynamic mode is eviction-feedback driven.
    request_cache_ratio_window_requests: int = 0
    request_cache_ratio_alpha: float = 0.2
    request_cache_ratio_feedback_mode: str = "normalized_pressure"
    request_cache_ratio_max_step: float = 0.05
    request_cache_ratio_pressure_hysteresis: float = 0.02
    request_cache_ratio_cooldown_evicted_tokens: int = 4096
    request_cache_agent_min_ratio: float = 0.2
    # The Agent upper bound implies an ordinary-request minimum of
    # (1 - request_cache_agent_max_ratio).
    request_cache_agent_max_ratio: float = 0.8
    # Elastic shared-pool reclaim order. ``request_first`` preserves the
    # historical Agent-continuation preference; ``pressure_first`` reclaims
    # the requesting region's borrowed pages before touching the opposite
    # region, which is useful when a burst should leave a return reserve.
    request_cache_elastic_reclaim_order: str = "request_first"
    # If false, elastic pressure uses the ordinary borrowed-page LRU tier
    # directly.  The preferred tier remains available for controlled
    # comparisons with the soft-line variant.
    request_cache_elastic_preferred_reclaim: bool = True
    # Maximum movement of the elastic soft split per pressure boundary.
    # One means follow the resident mix immediately; smaller values provide
    # temporal hysteresis when traffic changes phases.
    request_cache_elastic_soft_step: float = 1.0
    # Gate tail-first reclaim on recent activity from the region whose
    # minimum is currently under-filled. Zero keeps the ungated behavior.
    request_cache_elastic_activity_window: int = 0
    # If true, refresh elastic activity only after a real prefix/host hit.
    request_cache_elastic_activity_requires_hit: bool = False
    # Optional bounded ghost feedback for elastic shared-pool placement.  The
    # ghost stores only prefix fingerprints; zero keeps the production path
    # unchanged.  Pressure is decayed per classified match.
    request_cache_elastic_ghost_capacity_tokens: int = 0
    request_cache_elastic_ghost_pressure_decay: float = 0.95
    request_cache_elastic_ghost_bias: float = 0.5
    request_cache_elastic_ghost_reclaim: bool = True
    # Protect borrowed radix nodes only after the bounded ghost has observed
    # that evicting their prefix caused real recomputation.  Disabled by
    # default so existing elastic experiments retain their exact behavior.
    request_cache_elastic_ghost_protect: bool = False
    # Minimum decayed revisit score (tokens) required to protect a node. Zero
    # means one cache page, which avoids keeping a stale prefix alive forever.
    request_cache_elastic_ghost_protect_min_tokens: int = 0
    # Opt-in online cold-start feedback for elastic mode. When enabled, the
    # quota controller consumes borrowed-page eviction pressure and moves the
    # inactive-region return-reserve line.
    request_cache_elastic_feedback: bool = False
    # Dynamic mode updates from actual region evictions. Zero means each
    # eviction event can provide feedback; positive values aggregate tokens.
    request_cache_feedback_min_evicted_tokens: int = 0
    # Zero disables proactive reclaim; global capacity pressure still reclaims
    # borrowed prefixes when the shared pool is full.
    request_cache_borrow_high_watermark_tokens: int = 0
    request_cache_borrow_low_watermark_tokens: int = 0
    # Experimental: promote stale surplus pages only at a borrow-aware
    # allocator fallback, rather than during every quota check.
    request_cache_borrow_lazy_reclassify: bool = False
    # Experimental bound on newly inserted borrowed radix suffix segments.
    # Zero preserves the historical whole-suffix node layout.
    request_cache_borrowed_segment_tokens: int = 0

    mlp_checkpoint: Optional[str] = None
    mlp_hold_lambda: float = 0.05
    mlp_delta_alpha: str = "1.0,0.7,0.5"
    mlp_horizon_index: int = -1
    mlp_occupancy_hi: float = 0.90
    mlp_occupancy_mid: float = 0.75
    mlp_shadow_only: bool = False

    enable_metrics: bool = False
    enable_kv_cache_events: bool = False

    enable_mamba_extra_buffer: bool = False
    enable_mamba_extra_buffer_lazy: bool = False

    pp_rank: int = 0
    pp_size: int = 1

    attn_cp_rank: int = 0
    attn_cp_size: int = 1

    chunked_prefill_size: Optional[int] = None

    sliding_window_size: Optional[int] = None

    # Time-to-live for cache entries in seconds. If None, TTL is disabled.
    cache_ttl_seconds: Optional[float] = None

    tree_components: Optional[tuple[ComponentType, ...]] = None
    component_registry_override: Optional[dict[ComponentType, type[TreeComponent]]] = (
        None
    )
