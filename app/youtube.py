"""YouTube Data API v3 client. Every response adds its quota cost."""

from __future__ import annotations

import threading
import time

import httpx

API = "https://www.googleapis.com/youtube/v3"
COSTS = {
    "search": 100,
    "commentThreads": 1,
    "comments": 1,
    "videos": 1,
    "playlistItems": 1,
    "channels": 1,
}


class QuotaExceeded(RuntimeError):
    pass


class CommentsDisabled(RuntimeError):
    pass


class YouTubeError(RuntimeError):
    pass


class YouTube:
    def __init__(self, key: str):
        self._key = key
        self.units = 0
        self.by_method: dict[str, int] = {name: 0 for name in COSTS}
        self._lock = threading.Lock()
        self.stop = False
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def get(self, method: str, params: dict) -> dict:
        if method not in COSTS:
            raise YouTubeError(f"unknown method {method}")
        if self.stop:
            raise QuotaExceeded("stopped after quotaExceeded")
        query = {"prettyPrint": "false", "key": self._key, **params}
        url = f"{API}/{method}"
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self._client.get(url, params=query)
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(1 + attempt)
                continue
            with self._lock:
                self.units += COSTS[method]
                self.by_method[method] += COSTS[method]
            if response.status_code in (500, 503) or response.status_code == 429:
                last_error = YouTubeError(f"{method} HTTP {response.status_code}")
                time.sleep(1 + attempt)
                continue
            body = _json(response)
            if response.status_code >= 400:
                reason = _reason(body)
                if reason == "commentsDisabled":
                    raise CommentsDisabled(method)
                if reason in ("quotaExceeded", "dailyLimitExceeded"):
                    self.stop = True
                    raise QuotaExceeded(reason)
                raise YouTubeError(f"{method} HTTP {response.status_code} {reason}")
            return body
        raise YouTubeError(f"{method} failed after retries: {last_error}")

    def all_replies(self, parent_id: str, channel_id: str, page_cap: int) -> tuple[list[dict], bool]:
        """Page comments.list until the brand replies or the thread ends.

        The second value is True when the page cap stopped the scan early.
        """
        found: list[dict] = []
        token = None
        pages = 0
        while pages < page_cap:
            params = {
                "part": "snippet",
                "parentId": parent_id,
                "maxResults": 100,
                "textFormat": "plainText",
            }
            if token:
                params["pageToken"] = token
            data = self.get("comments", params)
            pages += 1
            batch = data.get("items") or []
            found.extend(batch)
            if any(_is_brand(item.get("snippet") or {}, channel_id) for item in batch):
                return found, False
            token = data.get("nextPageToken")
            if not token:
                return found, False
        return found, True


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _reason(body: dict) -> str:
    error = body.get("error") or {}
    errors = error.get("errors") or []
    if errors and isinstance(errors[0], dict):
        return str(errors[0].get("reason") or error.get("message") or "")
    return str(error.get("message") or "")


def _is_brand(snippet: dict, channel_id: str) -> bool:
    author = (snippet.get("authorChannelId") or {}).get("value")
    return bool(author and channel_id and author == channel_id)
