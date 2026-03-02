"""
Deterministic variant selection for mock enrichment providers.

Uses SHA-256 hash of the indicator value to pick a stable variant index.
Same input always returns the same variant — mock results are reproducible.
"""

from __future__ import annotations

import hashlib


def select_variant(value: str, n: int) -> int:
    """Return a deterministic variant index in [0, n) based on the SHA-256 hash of *value*."""
    digest = hashlib.sha256(value.encode()).hexdigest()
    return int(digest, 16) % n
