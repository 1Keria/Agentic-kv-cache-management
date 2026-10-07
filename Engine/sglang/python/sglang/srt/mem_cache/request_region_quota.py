"""Feedback controller for request-identity cache-region quotas.

The controller deliberately reacts to cache pressure rather than to a fixed
number of completed requests. A ratio update is therefore only possible after
the cache has actually evicted prefixes. This keeps an idle or all-hit
workload from moving the partition for no reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestRegionRatioUpdate:
    old_ratio: float
    new_ratio: float
    agent_evicted_tokens: int
    request_evicted_tokens: int
    agent_eviction_share: float

    # Normalized-pressure diagnostics.  The raw share remains available for
    # compatibility and for comparing the two controllers.
    agent_pressure: float = 0.0
    request_pressure: float = 0.0
    pressure_gap: float = 0.0
    applied_step: float = 0.0

    # Compatibility aliases for old diagnostics consumers. Dynamic mode no
    # longer uses insertion demand to update the ratio.
    agent_inserted_tokens: int = 0
    request_inserted_tokens: int = 0
    agent_demand_ratio: Optional[float] = None


class RequestRegionQuotaController:
    """Adjust the Agent quota from observed region eviction pressure.

    ``feedback_min_evicted_tokens`` is a token threshold, rather than a
    request-count window. The default zero means that each eviction event is
    eligible for feedback. A positive value aggregates small page-level
    events before changing the ratio.

    ``max_ratio`` is also the ordinary-request safety bound: at every point
    the request region receives at least ``1 - max_ratio`` of the cache
    capacity. Keeping this relationship in the controller makes the safety
    guarantee independent of the feedback mode or the update direction.
    """

    def __init__(
        self,
        *,
        initial_ratio: float,
        min_ratio: float,
        max_ratio: float,
        alpha: float,
        feedback_mode: str = "normalized_pressure",
        feedback_min_evicted_tokens: int = 0,
        max_ratio_step: float = 0.05,
        pressure_hysteresis: float = 0.0,
        cooldown_evicted_tokens: int = 0,
        policy_name: str = "dynamic",
        # Accept the old argument while callers are migrated. It is not used
        # to trigger updates anymore.
        window_requests: Optional[int] = None,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        if not 0.0 < min_ratio < max_ratio < 1.0:
            raise ValueError("min_ratio and max_ratio must satisfy 0 < min < max < 1")
        if not min_ratio <= initial_ratio <= max_ratio:
            raise ValueError("initial_ratio must be within [min_ratio, max_ratio]")
        if feedback_mode not in ("eviction_share", "normalized_pressure"):
            raise ValueError(
                "feedback_mode must be 'eviction_share' or 'normalized_pressure'"
            )
        if feedback_min_evicted_tokens < 0:
            raise ValueError("feedback_min_evicted_tokens must be non-negative")
        if not 0.0 < max_ratio_step <= 1.0:
            raise ValueError("max_ratio_step must be in (0, 1]")
        if pressure_hysteresis < 0.0:
            raise ValueError("pressure_hysteresis must be non-negative")
        if cooldown_evicted_tokens < 0:
            raise ValueError("cooldown_evicted_tokens must be non-negative")

        self.initial_ratio = float(initial_ratio)
        self.alpha = float(alpha)
        self.min_ratio = float(min_ratio)
        self.max_ratio = float(max_ratio)
        self.feedback_mode = feedback_mode
        self.feedback_min_evicted_tokens = int(feedback_min_evicted_tokens)
        self.max_ratio_step = float(max_ratio_step)
        self.pressure_hysteresis = float(pressure_hysteresis)
        self.cooldown_evicted_tokens = int(cooldown_evicted_tokens)
        self.policy_name = str(policy_name)
        self.legacy_window_requests = window_requests
        self.reset()

    @property
    def request_min_ratio(self) -> float:
        """Minimum ordinary-request fraction implied by ``max_ratio``."""
        return 1.0 - self.max_ratio

    def reset(self) -> None:
        self.current_ratio = self.initial_ratio
        self.feedback_evicted_tokens = {"agent": 0, "request": 0}
        self.last_feedback_agent_evicted_tokens = 0
        self.last_feedback_request_evicted_tokens = 0
        self.last_feedback_agent_eviction_share: Optional[float] = None
        self.last_feedback_agent_pressure: Optional[float] = None
        self.last_feedback_request_pressure: Optional[float] = None
        self.last_feedback_pressure_gap: Optional[float] = None
        self.last_feedback_applied_step = 0.0
        self.cooldown_evicted_tokens_remaining = 0
        self.feedback_update_count = 0

    def observe_insert(self, region: Optional[str], num_tokens: int) -> None:
        """Compatibility no-op.

        Insertions remain useful for diagnostics, but do not change the
        dynamic quota. The quota controller is intentionally pressure driven.
        """
        del region, num_tokens

    def observe_eviction(self, region: Optional[str], num_tokens: int) -> None:
        if region not in self.feedback_evicted_tokens or num_tokens <= 0:
            return
        self.feedback_evicted_tokens[region] += int(num_tokens)

    def discard_pending_feedback(self) -> None:
        """Drop evictions caused solely by applying a new quota.

        Rebalancing after a ratio update is an implementation cost of the
        control action, not fresh workload pressure. Feeding it back on the
        next request would make the ratio oscillate between the two regions.
        """
        self.feedback_evicted_tokens = {"agent": 0, "request": 0}

    def consume_feedback(
        self,
        *,
        agent_capacity_tokens: Optional[int] = None,
        request_capacity_tokens: Optional[int] = None,
    ) -> Optional[RequestRegionRatioUpdate]:
        """Consume pending eviction feedback at a safe request boundary.

        Only actual evictions determine pressure. The caller chooses a safe
        boundary so that quota changes cannot invalidate an active request.

        ``normalized_pressure`` compares evicted tokens with the current
        region quota.  This prevents a larger Agent working set from turning
        its absolute eviction volume directly into a target ratio.  The
        resulting movement is bounded and can be held behind a token-based
        cooldown, so a single page-level event cannot repeatedly resize the
        partition.
        """
        agent_tokens = self.feedback_evicted_tokens["agent"]
        request_tokens = self.feedback_evicted_tokens["request"]
        total_tokens = agent_tokens + request_tokens
        if total_tokens <= 0:
            return None
        required_tokens = max(
            self.feedback_min_evicted_tokens,
            self.cooldown_evicted_tokens_remaining,
        )
        if total_tokens < required_tokens:
            return None

        old_ratio = self.current_ratio
        eviction_share = agent_tokens / total_tokens
        agent_capacity = max(int(agent_capacity_tokens or 0), 1)
        request_capacity = max(int(request_capacity_tokens or 0), 1)
        agent_pressure = agent_tokens / agent_capacity
        request_pressure = request_tokens / request_capacity
        pressure_gap = agent_pressure - request_pressure
        outward_feedback_region: Optional[str] = None

        if self.feedback_mode == "normalized_pressure":
            if abs(pressure_gap) <= self.pressure_hysteresis:
                applied_step = 0.0
                new_ratio = old_ratio
            else:
                desired_step = self.alpha * pressure_gap
                applied_step = max(
                    -self.max_ratio_step,
                    min(desired_step, self.max_ratio_step),
                )
                new_ratio = min(
                    max(old_ratio + applied_step, self.min_ratio), self.max_ratio
                )
                applied_step = new_ratio - old_ratio
                if new_ratio == old_ratio:
                    if desired_step > 0.0 and old_ratio >= self.max_ratio:
                        outward_feedback_region = "agent"
                    elif desired_step < 0.0 and old_ratio <= self.min_ratio:
                        outward_feedback_region = "request"
        else:
            # Preserve the original controller for historical comparisons.
            new_ratio = (1.0 - self.alpha) * old_ratio + self.alpha * eviction_share
            new_ratio = min(max(new_ratio, self.min_ratio), self.max_ratio)
            applied_step = new_ratio - old_ratio
            if new_ratio == old_ratio:
                if eviction_share > old_ratio and old_ratio >= self.max_ratio:
                    outward_feedback_region = "agent"
                elif eviction_share < old_ratio and old_ratio <= self.min_ratio:
                    outward_feedback_region = "request"

        self.last_feedback_agent_evicted_tokens = agent_tokens
        self.last_feedback_request_evicted_tokens = request_tokens
        self.last_feedback_agent_eviction_share = eviction_share
        self.last_feedback_agent_pressure = agent_pressure
        self.last_feedback_request_pressure = request_pressure
        self.last_feedback_pressure_gap = pressure_gap
        self.last_feedback_applied_step = applied_step

        # A hysteresis hit (or a ratio bound) is not evidence that the
        # pressure disappeared. Keep the observations so several small page
        # evictions can accumulate into a meaningful update. This matters in
        # particular for ordinary prefixes, whose evictions are often much
        # smaller than an Agent context eviction.
        if new_ratio == old_ratio:
            if outward_feedback_region is not None:
                self.feedback_evicted_tokens[outward_feedback_region] = 0
            return None

        self.feedback_evicted_tokens = {"agent": 0, "request": 0}
        self.cooldown_evicted_tokens_remaining = 0

        self.current_ratio = new_ratio
        self.feedback_update_count += 1
        self.cooldown_evicted_tokens_remaining = self.cooldown_evicted_tokens
        return RequestRegionRatioUpdate(
            old_ratio=old_ratio,
            new_ratio=new_ratio,
            agent_evicted_tokens=agent_tokens,
            request_evicted_tokens=request_tokens,
            agent_eviction_share=eviction_share,
            agent_pressure=agent_pressure,
            request_pressure=request_pressure,
            pressure_gap=pressure_gap,
            applied_step=applied_step,
        )

    def observe_request_finished(
        self, region: Optional[str] = None
    ) -> Optional[RequestRegionRatioUpdate]:
        """Compatibility alias for older cache call sites."""
        del region
        return self.consume_feedback()

    def stats(self) -> dict[str, object]:
        return {
            "policy": self.policy_name,
            "feedback_mode": self.feedback_mode,
            "current_agent_ratio": self.current_ratio,
            "initial_agent_ratio": self.initial_ratio,
            "agent_min_ratio": self.min_ratio,
            "agent_max_ratio": self.max_ratio,
            # The ordinary region is guaranteed this fraction because the
            # Agent ratio can never exceed ``agent_max_ratio``.
            "request_min_ratio": self.request_min_ratio,
            "alpha": self.alpha,
            "feedback_min_evicted_tokens": self.feedback_min_evicted_tokens,
            "max_ratio_step": self.max_ratio_step,
            "pressure_hysteresis": self.pressure_hysteresis,
            "cooldown_evicted_tokens": self.cooldown_evicted_tokens,
            "cooldown_evicted_tokens_remaining": self.cooldown_evicted_tokens_remaining,
            "feedback_agent_evicted_tokens": self.feedback_evicted_tokens["agent"],
            "feedback_request_evicted_tokens": self.feedback_evicted_tokens[
                "request"
            ],
            "last_feedback_agent_evicted_tokens": self.last_feedback_agent_evicted_tokens,
            "last_feedback_request_evicted_tokens": self.last_feedback_request_evicted_tokens,
            "last_feedback_agent_eviction_share": self.last_feedback_agent_eviction_share,
            "last_feedback_agent_pressure": self.last_feedback_agent_pressure,
            "last_feedback_request_pressure": self.last_feedback_request_pressure,
            "last_feedback_pressure_gap": self.last_feedback_pressure_gap,
            "last_feedback_applied_step": self.last_feedback_applied_step,
            "feedback_update_count": self.feedback_update_count,
            # Compatibility keys for existing reports.
            "window_requests": None,
            "window_finished_requests": 0,
            "window_agent_inserted_tokens": 0,
            "window_request_inserted_tokens": 0,
            "last_window_agent_inserted_tokens": 0,
            "last_window_request_inserted_tokens": 0,
            "last_window_agent_demand_ratio": None,
            "completed_window_count": 0,
            "update_count": self.feedback_update_count,
        }
