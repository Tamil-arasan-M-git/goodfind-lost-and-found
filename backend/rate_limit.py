"""Small in-process safeguard for development/single-worker deployments.

Production should additionally enforce limits at the reverse proxy or gateway.
"""
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_requests = defaultdict(deque)
_lock = threading.Lock()


def sensitive_rate_limit(request: Request):
    window = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    maximum = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "20"))
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{request.url.path}"
    now = time.monotonic()
    with _lock:
        bucket = _requests[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= maximum:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        bucket.append(now)
