"""Shared httpx clients with connection pooling. One persistent client per
(name, timeout, headers) — never open a new connection per request."""
import httpx

_clients: dict[tuple, httpx.AsyncClient] = {}


def shared_client(name: str, timeout: float = 10.0, headers: dict | None = None) -> httpx.AsyncClient:
    key = (name, timeout, tuple(sorted(headers.items())) if headers else ())
    client = _clients.get(key)
    if client is None:
        # ponytail: creation race can orphan a duplicate client; harmless in
        # single-process uvicorn, per-worker pools if we ever scale out.
        client = httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        _clients[key] = client
    return client
