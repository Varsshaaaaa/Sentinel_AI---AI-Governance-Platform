"""Sliding-window rate limiter tests (PS-5.1)."""

from datetime import datetime, timezone

from shared.storage.memory import MemoryRepository


def test_count_accumulates_within_window():
    repo = MemoryRepository()
    counts = [repo.increment_rate_counter("a1", "tool", window_seconds=60) for _ in range(5)]
    assert counts == [1, 2, 3, 4, 5]


def test_old_calls_are_evicted_from_window():
    repo = MemoryRepository()
    key = "a1:tool"
    now = datetime.now(timezone.utc).timestamp()
    # Seed 3 calls that are older than the window and should be pruned.
    repo._rate_windows[key] = [now - 120, now - 90, now - 61]
    count = repo.increment_rate_counter("a1", "tool", window_seconds=60)
    assert count == 1  # only the new call remains inside the 60s window


def test_recent_calls_are_retained():
    repo = MemoryRepository()
    key = "a1:tool"
    now = datetime.now(timezone.utc).timestamp()
    repo._rate_windows[key] = [now - 30, now - 10]
    count = repo.increment_rate_counter("a1", "tool", window_seconds=60)
    assert count == 3  # two recent + the new one


def test_per_key_isolation():
    repo = MemoryRepository()
    repo.increment_rate_counter("a1", "toolA", window_seconds=60)
    repo.increment_rate_counter("a1", "toolA", window_seconds=60)
    b = repo.increment_rate_counter("a1", "toolB", window_seconds=60)
    assert b == 1
