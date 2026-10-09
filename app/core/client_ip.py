def client_ip(request) -> str:
    """Real client IP behind Cloudflare -> tunnel -> uvicorn.
    request.client.host is the tunnel peer (same for everyone), so per-IP
    limits without this are one global bucket. Trust the proxy headers only
    because Cloudflare is the sole ingress.
    ponytail: header-spoofable by anyone who can reach the origin directly;
    tighten with a Cloudflare IP allowlist at nftables when it matters."""
    for h in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        v = (request.headers.get(h) or "").split(",")[0].strip()
        if v:
            return v
    return request.client.host if request.client else "unknown"
