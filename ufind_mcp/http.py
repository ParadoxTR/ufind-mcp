from __future__ import annotations

import asyncio
import time

import httpx

from .cache import cache_get, cache_set
from .config import MAX_RETRIES, MIN_REQUEST_GAP_S, TIMEOUT_S, USER_AGENT

_ACCEPT = {
    "xml": "application/xml,text/xml,*/*",
    "html": "text/html,application/xhtml+xml",
    "text": "text/plain,*/*",
}


class UfindHttpError(RuntimeError):
    def __init__(self, message: str, status: int, url: str) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


_lock = asyncio.Lock()
_client: httpx.AsyncClient | None = None
_last_request_at = 0.0


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=TIMEOUT_S,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "de,en"},
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _explain(status: int, reason: str) -> str:
    if status == 501:
        return "the XML API rejects unknown query parameters (only `query` and `from` are accepted)"
    if status == 404:
        return "no such record for this id/semester combination"
    return reason or "unexpected response"


async def _raw_get(url: str, kind: str) -> str:
    global _last_request_at
    gap = MIN_REQUEST_GAP_S - (time.monotonic() - _last_request_at)
    if gap > 0:
        await asyncio.sleep(gap)
    _last_request_at = time.monotonic()

    response = await _get_client().get(url, headers={"Accept": _ACCEPT.get(kind, _ACCEPT["xml"])})
    if response.status_code >= 400:
        raise UfindHttpError(
            f"u:find returned HTTP {response.status_code}: "
            f"{_explain(response.status_code, response.reason_phrase)}",
            response.status_code,
            url,
        )
    return response.text


def _retryable(err: BaseException) -> bool:
    if isinstance(err, UfindHttpError):
        return err.status >= 500 and err.status != 501
    return isinstance(err, (httpx.TransportError, httpx.TimeoutException))


async def get(url: str, ttl_s: float, kind: str = "xml", refresh: bool = False) -> str:
    if not refresh:
        cached = cache_get(url, ttl_s)
        if cached is not None:
            return cached

    async with _lock:
        if not refresh:
            cached = cache_get(url, ttl_s)
            if cached is not None:
                return cached
        last_error: BaseException | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                body = await _raw_get(url, kind)
            except BaseException as err:
                last_error = err
                if not _retryable(err) or attempt == MAX_RETRIES:
                    break
                await asyncio.sleep(attempt * 0.8)
            else:
                cache_set(url, body)
                return body
        assert last_error is not None
        raise last_error
