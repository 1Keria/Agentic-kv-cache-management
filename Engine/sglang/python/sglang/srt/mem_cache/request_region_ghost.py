"""Bounded ghost metadata for request-region cache feedback.

The ghost index remembers only page-prefix fingerprints for entries that were
removed from the device cache.  A later request can therefore tell whether a
miss follows a real eviction, without retaining KV tensors or predicting a
tool/turn return time.  The index is intentionally independent of Full/SWA so
both cache implementations feed the same region-level signal.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Optional


def _update_unit(hasher: "hashlib._Hash", unit: Any) -> None:
    """Add one logical token (or Eagle bigram) to a rolling fingerprint."""

    if isinstance(unit, tuple):
        hasher.update(b"B")
        hasher.update(len(unit).to_bytes(2, "little", signed=False))
        for value in unit:
            hasher.update(int(value).to_bytes(8, "little", signed=True))
    else:
        hasher.update(b"I")
        hasher.update(int(unit).to_bytes(8, "little", signed=True))


def _seed_hasher(extra_key: Any) -> "hashlib._Hash":
    hasher = hashlib.sha256()
    hasher.update(b"agentkv-request-ghost-v1\0")
    encoded = repr(extra_key).encode("utf-8", errors="backslashreplace")
    hasher.update(len(encoded).to_bytes(4, "little", signed=False))
    hasher.update(encoded)
    return hasher


def logical_pages(key: Any, page_size: int) -> tuple[tuple[Any, ...], ...]:
    """Return page-sized logical units for a RadixKey-like object."""

    if page_size <= 0:
        raise ValueError("page_size must be positive")
    units = tuple(key)
    aligned = len(units) // page_size * page_size
    return tuple(
        units[start : start + page_size]
        for start in range(0, aligned, page_size)
    )


def prefix_pages_for_node(node: Any, page_size: int) -> tuple[tuple[Any, ...], ...]:
    """Build the complete logical prefix ending at ``node``.

    Radix nodes store segments, so an evicted leaf alone is insufficient to
    identify a future prefix.  Walking the parent chain is cheap at eviction
    time and works for both the classic and SWA radix caches.
    """

    segments: list[Any] = []
    current = node
    while current is not None and getattr(current, "parent", None) is not None:
        key = getattr(current, "key", None)
        if key is not None:
            segments.append(key)
        current = current.parent
    units: list[Any] = []
    for key in reversed(segments):
        units.extend(tuple(key))
    aligned = len(units) // page_size * page_size
    return tuple(
        tuple(units[start : start + page_size])
        for start in range(0, aligned, page_size)
    )


def rolling_prefix_keys(
    pages: Iterable[tuple[Any, ...]], extra_key: Any
) -> tuple[tuple[int, bytes], ...]:
    """Return ``(logical_length, digest)`` at every page boundary."""

    hasher = _seed_hasher(extra_key)
    result: list[tuple[int, bytes]] = []
    logical_length = 0
    for page in pages:
        for unit in page:
            _update_unit(hasher, unit)
            logical_length += 1
        result.append((logical_length, hasher.digest()))
    return tuple(result)


@dataclass
class GhostRecord:
    region: str
    prefix_tokens: int
    eviction_count: int = 1
    # Revisit evidence is kept with the prefix that was actually lost.  The
    # score is lazily decayed in request-event time, so querying a candidate
    # does not require a full scan of the bounded ghost table.
    revisit_tokens: int = 0
    revisit_events: int = 0
    revisit_score: float = 0.0
    last_revisit_step: int = 0


class RequestRegionGhostIndex:
    """Bounded prefix ghost with exponentially decayed revisit pressure."""

    def __init__(
        self,
        *,
        page_size: int,
        capacity_tokens: int,
        pressure_decay: float = 0.95,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        if capacity_tokens < 0:
            raise ValueError("capacity_tokens must be non-negative")
        if not 0.0 < pressure_decay <= 1.0:
            raise ValueError("pressure_decay must be in (0, 1]")
        self.page_size = int(page_size)
        self.capacity_tokens = int(capacity_tokens)
        self.pressure_decay = float(pressure_decay)
        self.entries: "OrderedDict[bytes, GhostRecord]" = OrderedDict()
        self.resident_metadata_tokens = 0
        self.region_metadata_tokens = {"agent": 0, "request": 0}
        # Keep a small metadata return path for each class once both classes
        # have produced evictions.  Without this, a long Agent burst can evict
        # every ordinary ghost before the ordinary class gets a chance to
        # report its first real revisit.
        self.reserve_tokens = max(self.page_size, self.capacity_tokens // 10)
        self.seen_regions: set[str] = set()
        self.pressure = {"agent": 0.0, "request": 0.0}
        self.eviction_events = 0
        self.evicted_tokens = {"agent": 0, "request": 0}
        self.revisit_events = {"agent": 0, "request": 0}
        self.revisit_tokens = {"agent": 0, "request": 0}
        self.last_revisit_tokens = {"agent": 0, "request": 0}
        self.event_step = 0
        # ``match_prefix`` may be called several times for one request when
        # prefill is chunked.  Production callers pass Req.rid here so the
        # decay/window clock advances once per classified request instead of
        # once per chunk.  ``None`` keeps the standalone API's historical
        # behaviour (each observation is a separate event).
        self._last_request_event_key: Any = None

    @property
    def enabled(self) -> bool:
        return self.capacity_tokens > 0

    def reset(self) -> None:
        self.entries.clear()
        self.resident_metadata_tokens = 0
        self.region_metadata_tokens = {"agent": 0, "request": 0}
        self.seen_regions.clear()
        self.pressure = {"agent": 0.0, "request": 0.0}
        self.eviction_events = 0
        self.evicted_tokens = {"agent": 0, "request": 0}
        self.revisit_events = {"agent": 0, "request": 0}
        self.revisit_tokens = {"agent": 0, "request": 0}
        self.last_revisit_tokens = {"agent": 0, "request": 0}
        self.event_step = 0
        self._last_request_event_key = None

    def _materialize_record_score(self, record: GhostRecord) -> float:
        """Apply event-time decay to one record and return its score."""

        elapsed = max(self.event_step - record.last_revisit_step, 0)
        if elapsed:
            record.revisit_score *= self.pressure_decay**elapsed
            record.last_revisit_step = self.event_step
        return record.revisit_score

    def _drop_oldest(self, *, incoming_region: Optional[str] = None) -> bool:
        selected_key = None
        selected_record = None
        for key, record in self.entries.items():
            # Once both regions have been observed, do not spend the last
            # reserve of the opposite region on the incoming class.
            opposite = "request" if record.region == "agent" else "agent"
            if (
                len(self.seen_regions) >= 2
                and self.region_metadata_tokens[record.region] <= self.reserve_tokens
                and incoming_region == opposite
            ):
                continue
            selected_key = key
            selected_record = record
            break
        if selected_key is None:
            return False
        self.entries.pop(selected_key)
        self.resident_metadata_tokens = max(
            self.resident_metadata_tokens - self.page_size, 0
        )
        self.region_metadata_tokens[selected_record.region] = max(
            self.region_metadata_tokens[selected_record.region] - self.page_size,
            0,
        )
        return True

    def record_eviction(
        self,
        pages: tuple[tuple[Any, ...], ...],
        *,
        extra_key: Any,
        region: Optional[str],
        evicted_tokens: int,
    ) -> None:
        """Remember every page prefix ending at an evicted node."""

        if not self.enabled or region not in self.evicted_tokens or not pages:
            return
        self.seen_regions.add(region)
        keys = rolling_prefix_keys(pages, extra_key)
        self.eviction_events += 1
        self.evicted_tokens[region] += max(int(evicted_tokens), 0)
        for prefix_tokens, digest in keys:
            existing = self.entries.pop(digest, None)
            if existing is None:
                # Each record represents one page of metadata.  A node with a
                # long segment therefore cannot consume an unbounded amount.
                while self.resident_metadata_tokens + self.page_size > self.capacity_tokens:
                    if not self.entries:
                        return
                    if not self._drop_oldest(incoming_region=region):
                        # Both regions are at their metadata reserve.  The
                        # incoming class may reclaim its own oldest entry;
                        # otherwise the bounded index is already full of the
                        # protected return paths.
                        if not self._drop_oldest(incoming_region=region):
                            return
                self.resident_metadata_tokens += self.page_size
                self.region_metadata_tokens[region] += self.page_size
                existing = GhostRecord(region=region, prefix_tokens=prefix_tokens)
            else:
                existing.region = region
                existing.prefix_tokens = prefix_tokens
                existing.eviction_count += 1
            self.entries[digest] = existing

    def observe_match(
        self,
        pages: tuple[tuple[Any, ...], ...],
        *,
        extra_key: Any,
        actual_tokens: int,
        request_region: Optional[str],
        request_event_key: Any = None,
    ) -> int:
        """Record the portion of a ghost prefix recomputed by this request."""

        # One step represents one classified request.  Decay is tied to
        # observed traffic rather than wall-clock/tool-return predictions.
        advance_event = (
            request_event_key is None
            or request_event_key != self._last_request_event_key
        )
        if advance_event:
            self.event_step += 1
            for region in self.pressure:
                self.pressure[region] *= self.pressure_decay
            self._last_request_event_key = request_event_key
        self.last_revisit_tokens = {"agent": 0, "request": 0}
        if not self.enabled or request_region not in self.pressure or not pages:
            return 0

        actual_tokens = max(int(actual_tokens), 0)
        candidate: Optional[GhostRecord] = None
        for prefix_tokens, digest in rolling_prefix_keys(pages, extra_key):
            if prefix_tokens <= actual_tokens:
                continue
            record = self.entries.get(digest)
            if record is not None and (
                candidate is None or record.prefix_tokens > candidate.prefix_tokens
            ):
                candidate = record
        if candidate is None:
            return 0

        lost_tokens = max(candidate.prefix_tokens - actual_tokens, 0)
        if lost_tokens <= 0:
            return 0
        self._materialize_record_score(candidate)
        candidate.revisit_tokens += lost_tokens
        candidate.revisit_events += 1
        candidate.revisit_score += lost_tokens
        candidate.last_revisit_step = self.event_step
        self.pressure[request_region] += lost_tokens
        self.revisit_events[request_region] += 1
        self.revisit_tokens[request_region] += lost_tokens
        self.last_revisit_tokens[request_region] = lost_tokens
        return lost_tokens

    def revisit_score_for_pages(
        self,
        pages: tuple[tuple[Any, ...], ...],
        *,
        extra_key: Any,
        region: Optional[str] = None,
    ) -> float:
        """Return decayed revisit pressure for a resident prefix.

        A resident radix node is protected only by evidence for one of its
        page-aligned prefixes.  The longest-prefix score is used so a large
        node does not accumulate duplicate credit from every ancestor page.
        """

        return self.revisit_score_for_keys(
            rolling_prefix_keys(pages, extra_key), region=region
        )

    def revisit_score_for_keys(
        self,
        keys: tuple[tuple[int, bytes], ...],
        *,
        region: Optional[str] = None,
        max_age_steps: Optional[int] = None,
    ) -> float:
        """Return the score for precomputed rolling prefix fingerprints."""

        if not self.enabled or not keys:
            return 0.0
        best = 0.0
        for _prefix_tokens, digest in keys:
            record = self.entries.get(digest)
            if record is None or (region is not None and record.region != region):
                continue
            if (
                max_age_steps is not None
                and max_age_steps > 0
                and self.event_step - record.last_revisit_step > max_age_steps
            ):
                continue
            best = max(best, self._materialize_record_score(record))
        return best

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "page_size": self.page_size,
            "capacity_tokens": self.capacity_tokens,
            "resident_metadata_tokens": self.resident_metadata_tokens,
            "region_metadata_tokens": dict(self.region_metadata_tokens),
            "reserve_tokens": self.reserve_tokens,
            "seen_regions": sorted(self.seen_regions),
            "entry_count": len(self.entries),
            "pressure_decay": self.pressure_decay,
            "pressure_tokens": dict(self.pressure),
            "eviction_events": self.eviction_events,
            "evicted_tokens": dict(self.evicted_tokens),
            "revisit_events": dict(self.revisit_events),
            "revisit_tokens": dict(self.revisit_tokens),
            "last_revisit_tokens": dict(self.last_revisit_tokens),
            "event_step": self.event_step,
            "request_event_tracking": self._last_request_event_key is not None,
            "records_with_revisit": sum(
                1 for record in self.entries.values() if record.revisit_score > 0.0
            ),
            "revisit_score_total": sum(
                self._materialize_record_score(record)
                for record in self.entries.values()
            ),
        }
