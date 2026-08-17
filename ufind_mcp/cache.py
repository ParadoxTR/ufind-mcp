from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

_DISABLED = os.environ.get("UFIND_MCP_NO_CACHE") == "1"


def _cache_dir() -> Path:
    override = os.environ.get("UFIND_MCP_CACHE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "ufind-mcp"


def _file_for(key: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return _cache_dir() / f"{digest}.json"


def cache_get(key: str, ttl_s: float) -> str | None:
    if _DISABLED or ttl_s <= 0:
        return None
    try:
        entry = json.loads(_file_for(key).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - float(entry.get("ts", 0)) > ttl_s:
        return None
    body = entry.get("body")
    return body if isinstance(body, str) else None


def cache_set(key: str, body: str) -> None:
    if _DISABLED:
        return
    try:
        directory = _cache_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = _file_for(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "key": key, "body": body}), "utf-8")
        tmp.replace(path)
    except OSError:
        pass


def cache_location() -> str:
    return "(disabled)" if _DISABLED else str(_cache_dir())
