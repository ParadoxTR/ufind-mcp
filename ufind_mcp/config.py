from __future__ import annotations

import os

API_BASE = "https://m1-ufind.univie.ac.at"

WEB_BASE = "https://ufind.univie.ac.at"

WEB_LANG = "en" if os.environ.get("UFIND_MCP_LANG") == "en" else "de"
OTHER_LANG = "de" if WEB_LANG == "en" else "en"

USER_AGENT = os.environ.get(
    "UFIND_MCP_USER_AGENT",
    "ufind-mcp/0.1 (personal MCP client; low-volume, cached)",
)

API_PAGE_SIZE = 6

TTL_VVZ_INDEX = 12 * 60 * 60
TTL_VVZ_COURSES = 3 * 60 * 60
TTL_COURSE = 3 * 60 * 60
TTL_SEARCH = 60 * 60
TTL_ENTITY = 24 * 60 * 60

TIMEOUT_S = float(os.environ.get("UFIND_MCP_TIMEOUT_S", "60"))

MIN_REQUEST_GAP_S = float(os.environ.get("UFIND_MCP_MIN_GAP_S", "0.25"))
MAX_RETRIES = 3
