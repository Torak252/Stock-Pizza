"""Shared, polite HTTP client used by every collector.

Policy (see docs/ARCHITECTURE.md §2):
  * identify ourselves with a real User-Agent and contact address,
  * enforce a per-host minimum interval (token-bucket-lite),
  * honour Retry-After / 429 / 503 with exponential backoff,
  * cache responses briefly so repeated reads in one cycle never re-hit upstream.

There is deliberately no proxy rotation or fingerprint spoofing: we only use sources
that permit automated access, so there is nothing to evade.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import httpx

from ..config import get_settings


class PoliteClient:
    def __init__(self, min_interval_s: float | None = None, cache_ttl_s: float = 30.0, max_retries: int | None = None,
                 timeout_s: float | None = None):
        s = get_settings()
        ua = s.user_agent if not s.contact_email else f"{s.user_agent} <{s.contact_email}>"
        self._client = httpx.Client(timeout=timeout_s or s.http_timeout_s, headers={"User-Agent": ua}, follow_redirects=True)
        self._min_interval = min_interval_s if min_interval_s is not None else s.default_min_interval_s
        self._max_retries = s.http_max_retries if max_retries is None else max_retries
        self._last_hit: dict[str, float] = {}
        self._cache: dict[str, tuple[float, httpx.Response]] = {}
        self._cache_ttl = cache_ttl_s
        self._lock = threading.Lock()

    def _wait_for_host(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last_hit.get(host, 0.0) + self._min_interval - now
            self._last_hit[host] = now + max(wait, 0.0)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, **kwargs) -> httpx.Response:
        key = url + repr(sorted(kwargs.get("params", {}).items()))
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < self._cache_ttl:
            return cached[1]

        host = urlparse(url).netloc
        backoff = 2.0
        for attempt in range(self._max_retries + 1):
            self._wait_for_host(host)
            try:
                resp = self._client.get(url, **kwargs)
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.TimeoutException):
                if attempt >= self._max_retries:
                    raise
                time.sleep(backoff)  # transient resets are common on busy public APIs
                backoff *= 2
                continue
            if resp.status_code in (429, 503) and attempt < self._max_retries:
                retry_after = resp.headers.get("Retry-After", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            self._cache[key] = (time.monotonic(), resp)
            return resp
        resp.raise_for_status()
        return resp

    def post(self, url: str, **kwargs) -> httpx.Response:
        self._wait_for_host(urlparse(url).netloc)
        resp = self._client.post(url, **kwargs)
        resp.raise_for_status()
        return resp
