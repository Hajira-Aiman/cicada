"""
guard/hq_client.py
Signed guard -> head-office API calls (see contracts/request_auth.py). Outbound only: the guard asks, head office never connects in.
"""
import json
from typing import Any, Dict, Optional

import httpx

from contracts.request_auth import guard_request_headers


def hq_call(config, hq_url: str, method: str, path: str, params: Optional[Dict[str, Any]] = None,
            json_body: Optional[Any] = None) -> httpx.Response:
    url = httpx.URL(f"{hq_url}{path}", params=params)
    body = json.dumps(json_body).encode() if json_body is not None else b""
    headers = guard_request_headers(config.GUARD_ID, config.GUARD_SECRET_KEY, method, url.raw_path.decode(), body)
    headers["Content-Type"] = "application/json"
    res = httpx.request(method, url, content=body, headers=headers, timeout=3, verify=config.TLS_VERIFY)
    res.raise_for_status()
    return res
