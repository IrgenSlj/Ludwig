"""Reference only: the loopback token and same-origin checks from the old daemon (webapp/server.py)."""
import hmac


def token_ok(configured: str | None, provided: str | None) -> bool:
    """The loopback-auth rule (D1). No token configured → open (local dev + the public demo, which
    set none — back-compat). A token configured → require an exact, constant-time match. This is the
    whole security boundary the embedding shell relies on; keep it a pure function so --selftest can
    exercise it without a socket."""
    if not configured:
        return True
    return bool(provided) and hmac.compare_digest(str(provided), str(configured))


def origin_ok(origin: str | None, host: str | None, *, allowed: tuple[str, ...] = ()) -> bool:
    """The CSRF rule: a *browser* may only reach `/api/*` from the daemon's own page.

    The daemon is open by default (no token) and binds a predictable localhost port, so any web page
    the user happens to be visiting could POST to `http://127.0.0.1:8765/api/build` and drive a tool
    that writes fabrication files. A cross-origin POST can't be read back, but the write still lands —
    so the reply being unreadable is not a defence.

    The check is same-origin by *comparison*, never a hardcoded localhost: the browser's `Origin`
    authority must equal the `Host` the request was addressed to. That holds for `cli.py --serve` on
    a random port AND for the public demo behind a real hostname, with no per-deployment config.

    A request with **no** `Origin` is allowed: `curl`, the MCP server, the desktop shell and every
    other non-browser client omit it, and browsers omit it on same-origin GETs. That is the whole
    back-compat story — this adds no header requirement to any existing caller. Browsers are the only
    thing that attaches `Origin` to a cross-site request, which is exactly the case being refused.
    """
    if not origin:
        return True
    from urllib.parse import urlparse
    if origin in allowed:                      # explicit escape hatch (embedding shells, e.g. tauri://)
        return True
    netloc = urlparse(origin).netloc or origin
    return bool(host) and netloc == host
