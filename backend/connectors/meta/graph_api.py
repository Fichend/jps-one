"""Meta Graph API connector for authorized Facebook and Instagram assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


GRAPH_BASE = "https://graph.facebook.com"


@dataclass(frozen=True)
class MetaConfig:
    graph_version: str = "v25.0"
    app_id: str = ""
    app_secret: str = ""
    access_token: str = ""
    page_access_token: str = ""
    page_id: str = ""
    instagram_account_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetaConfig":
        version = str(data.get("graph_version") or "v25.0").strip()
        if not version.startswith("v"):
            version = f"v{version}"
        return cls(
            graph_version=version,
            app_id=str(data.get("app_id") or "").strip(),
            app_secret=str(data.get("app_secret") or "").strip(),
            access_token=str(data.get("access_token") or data.get("long_lived_access_token") or "").strip(),
            page_access_token=str(data.get("page_access_token") or data.get("access_token") or "").strip(),
            page_id=str(data.get("page_id") or "").strip(),
            instagram_account_id=str(data.get("instagram_account_id") or "").strip(),
        )

    @property
    def token(self) -> str:
        return self.page_access_token or self.access_token


class MetaGraphError(RuntimeError):
    """Raised when Meta Graph API returns an error response."""


def normalize_social_target(url_or_handle: str) -> tuple[str, str]:
    """Return provider hint and handle/id from a social URL or pasted handle."""
    raw = str(url_or_handle or "").strip()
    if not raw:
        return "", ""
    if raw.startswith("@"):
        return "instagram", raw[1:]
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")
    first = path.split("/")[0] if path else ""
    if "instagram.com" in host:
        return "instagram", first
    if "facebook.com" in host or "fb.com" in host:
        return "facebook", first
    if re.fullmatch(r"[A-Za-z0-9_.]+", raw):
        return "instagram", raw
    return "", raw


class MetaGraphClient:
    def __init__(self, config: MetaConfig, timeout: float = 15.0) -> None:
        self.config = config
        self.timeout = timeout

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{GRAPH_BASE}/{self.config.graph_version}/{path}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self.config.token
        if not token:
            raise MetaGraphError("Missing Meta access token")
        query = dict(params or {})
        query["access_token"] = token
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self._url(path), params=query)
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            error = data.get("error") if isinstance(data, dict) else None
            message = error.get("message") if isinstance(error, dict) else response.text
            raise MetaGraphError(str(message or f"Meta Graph API returned {response.status_code}"))
        if not isinstance(data, dict):
            raise MetaGraphError("Meta Graph API returned an unexpected response")
        return data

    async def test_connection(self) -> dict[str, Any]:
        me = await self._get("me", {"fields": "id,name"})
        result: dict[str, Any] = {"me": me, "assets": {}}
        if self.config.page_id:
            result["assets"]["page"] = await self.get_page(self.config.page_id)
        if self.config.instagram_account_id:
            result["assets"]["instagram"] = await self.get_instagram_account(self.config.instagram_account_id)
        return result

    async def get_page(self, page_id: str) -> dict[str, Any]:
        fields = "id,name,category,link,fan_count,followers_count,website,about,instagram_business_account{id,username,name,profile_picture_url}"
        return await self._get(page_id, {"fields": fields})

    async def get_instagram_account(self, account_id: str) -> dict[str, Any]:
        fields = "id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url"
        return await self._get(account_id, {"fields": fields})

    async def discover_instagram_business(self, username: str) -> dict[str, Any]:
        if not self.config.instagram_account_id:
            raise MetaGraphError("Instagram Account ID is required for Business Discovery by username")
        fields = (
            "business_discovery.username("
            f"{username}"
            "){id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url}"
        )
        data = await self._get(self.config.instagram_account_id, {"fields": fields})
        discovered = data.get("business_discovery") if isinstance(data, dict) else None
        if not isinstance(discovered, dict):
            raise MetaGraphError("Instagram Business Discovery returned no profile data")
        return discovered

    async def enrich(self, url_or_handle: str) -> dict[str, Any]:
        provider, handle = normalize_social_target(url_or_handle)
        if not handle:
            raise MetaGraphError("Missing social profile URL or handle")
        if provider == "facebook":
            data = await self.get_page(handle)
        elif provider == "instagram":
            if handle == "me":
                data = await self.get_instagram_account(self.config.instagram_account_id)
            elif handle.isdigit():
                data = await self.get_instagram_account(handle)
            else:
                data = await self.discover_instagram_business(handle)
        else:
            raise MetaGraphError("Only Facebook Page and Instagram professional account enrichment is supported")
        return {"provider": provider, "handle": handle, "profile": data}


def public_profile_payload(result: dict[str, Any]) -> dict[str, Any]:
    profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
    allowed = {
        "id",
        "username",
        "name",
        "category",
        "link",
        "website",
        "about",
        "biography",
        "fan_count",
        "followers_count",
        "follows_count",
        "media_count",
        "profile_picture_url",
    }
    return {
        "provider": result.get("provider") or "",
        "handle": result.get("handle") or "",
        "profile": {key: value for key, value in profile.items() if key in allowed},
    }
