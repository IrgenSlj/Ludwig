"""Request guards: an optional shared token and a same-origin rule for browsers."""

from __future__ import annotations

import hmac
from urllib.parse import urlparse


def token_ok(configured: str | None, provided: str | None) -> bool:
    """No token configured: open (local use). Configured: exact, constant-time match."""
    if not configured:
        return True
    return bool(provided) and hmac.compare_digest(str(provided), str(configured))


def origin_ok(origin: str | None, host: str | None, allowed: tuple[str, ...] = ()) -> bool:
    """A browser may change data only from the service's own page or an allowed origin.

    Requests without an Origin header (curl, scripts, same-origin GETs) pass: only browsers
    attach Origin to a cross-site request, which is the case refused.
    """
    if not origin or origin in allowed:
        return True
    netloc = urlparse(origin).netloc or origin
    return bool(host) and netloc == host
