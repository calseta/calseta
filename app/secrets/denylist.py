"""Global secret-name denylist (S3).

A secret name (env var name, allowlist entry, etc.) is *denied* when it
matches any of the regex patterns below. Denial means the resolver / accessor
layer must not return the value — even if the caller has the name on a
per-workflow allowlist.

The denylist exists so workflow code, custom adapters, and resolved
LLMIntegration refs can never reach back into the platform's own
credentials (DATABASE_URL, ENCRYPTION_KEY, AWS_*, etc.) just because the
process happens to inherit them in ``os.environ``.

Patterns are compiled once at module import; ``is_denied()`` is hot-path
safe (no allocation per call beyond ``re.match`` internals).

Pattern source of truth: ``docs/plans/2026-04-15-agent-runtime-hardening.md``
under "Chunk S3" → "Design decisions locked 2026-05-05" → Global denylist.
"""

from __future__ import annotations

import re

# Compiled at import time — no per-call cost.
DENYLIST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^CALSETA_"),
    re.compile(r"_API_KEY$"),
    re.compile(r"_SECRET$"),
    re.compile(r"_TOKEN$"),
    re.compile(r"_PASSWORD$"),
    re.compile(r"^DATABASE_URL$"),
    re.compile(r"^ENCRYPTION_KEY$"),
    re.compile(r"^AWS_"),
    re.compile(r"^AZURE_"),
)


def is_denied(name: str) -> bool:
    """Return True if ``name`` matches any denylist pattern.

    The check is *case-sensitive*. All denylist names are conventional
    SHOUTING_SNAKE_CASE env var names; lower-case variants are not on the
    denylist by design (we don't want to silently swallow misspellings).
    """
    if not name:
        return False
    return any(pattern.search(name) for pattern in DENYLIST_PATTERNS)
