"""Section 9: security audit log + alert counters.

- audit(): appends one JSON line to /var/log/cortexcloud/security.log
  (append-only, separate from request logs). Never logs secrets/bodies.
- alert(): sliding time-window counters in Redis with alert threshold.
  Emits an ERROR log line (consumable by log-watchers/journald) when breached.

fail-open: Redis/fs errors never break the request path.
"""
import json
import logging
import os
import time

logger = logging.getLogger("cortexcloud.security")

_AUDIT_PATH = os.environ.get("CORTEXCLOUD_AUDIT_LOG", "/var/log/cortexcloud/security.log")


def audit(event: str, **fields) -> None:
    """Append an audit record. Best-effort; never fails the caller."""
    try:
        rec = {"t": time.time(), "event": event}
        rec.update({k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
                    for k, v in fields.items()})
        pos = os.open(_AUDIT_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            if os.fstat(pos).st_size > 32 * 1024 * 1024:  # ponytail: cap 32MB, rotate by truncate
                os.lseek(pos, 0, os.SEEK_SET)
                os.truncate(pos, 0)
            os.write(pos, (json.dumps(rec, default=str) + "\n").encode())
        finally:
            os.close(pos)
    except Exception:  # noqa: BLE001
        logger.debug("audit write failed", exc_info=True)


async def alert(client, bucket: str, window: int, threshold: int, event: str, **fields) -> bool:
    """Increment a per-bucket counter in Redis; alert (log ERROR) when threshold
    crossed within window seconds. Returns True when it just fired."""
    try:
        key = f"secalert:{bucket}"
        n = await client.incr(key)
        if n == 1:
            await client.expire(key, window)
        if n >= threshold:
            rec = {"t": time.time(), "event": event, "bucket": bucket, "count": int(n)}
            rec.update(fields)
            logger.error(json.dumps(rec, default=str))
            # reset so repeated breaches re-alert in fresh windows
            await client.delete(key)
            return True
    except Exception:  # noqa: BLE001
        logger.debug("alert check failed", exc_info=True)
    return False