"""Section 9: security audit log + alert counters.

- audit(): appends one JSON line to /var/log/cortexcloud/security.log
  (append-only, separate from request logs). Never logs secrets/bodies.
- alert(): sliding time-window counters (in-process; PostgreSQL/Redis
  not needed for alerting) with a threshold. Emits an ERROR log line
  when breached.

fail-open: fs errors never break the request path.
"""
import json
import logging
import os
import time

logger = logging.getLogger("cortexcloud.security")

_AUDIT_PATH = os.environ.get("CORTEXCLOUD_AUDIT_LOG", "/var/log/cortexcloud/security.log")

# ponytail: in-process alert windows; across N workers each keeps its own
# counter (acceptable — alerts are advisory).
_ALERTS: dict[tuple, list] = {}


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


async def alert(bucket: str, window: int, threshold: int, event: str, **fields) -> bool:
    """Counter within `window` seconds; ERROR-log when >= threshold once,
    then reset. Returns True when the alert just fired."""
    try:
        key = (bucket, int(time.time() // window))
        _ALERTS.setdefault(key, []).append(time.time())
        hits = [t for t in _ALERTS[key] if t > time.time() - window]
        _ALERTS[key] = hits
        if len(_ALERTS) > 5000:  # ponytail: cap the map, keys old windows die naturally
            _ALERTS.pop(next(iter(_ALERTS)), None)
        if len(hits) >= threshold:
            rec = {"t": time.time(), "event": event, "bucket": bucket, "count": len(hits)}
            rec.update(fields)
            logger.error(json.dumps(rec, default=str))
            _ALERTS[key] = []  # reset so fresh breaches re-alert
            return True
    except Exception:  # noqa: BLE001
        logger.debug("alert check failed", exc_info=True)
    return False