"""Meta / Instagram integration service."""

from __future__ import annotations

from typing import Any

from config.secure_config_store import (
    get_integration,
    list_integrations,
    save_integration,
    store_social_profile,
    update_test_result,
)
from connectors.meta.graph_api import MetaConfig, MetaGraphClient, public_profile_payload


SUPPORTED_PROVIDERS = {"meta_instagram"}


class IntegrationProviderError(ValueError):
    """Raised for unsupported integration providers."""


class IntegrationConfigError(ValueError):
    """Raised when a configured integration cannot be used."""


def ensure_supported_provider(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise IntegrationProviderError("Unsupported integration provider")


def list_supported_integrations() -> list[dict[str, Any]]:
    existing = {item["provider"]: item for item in list_integrations()}
    for provider in SUPPORTED_PROVIDERS:
        existing.setdefault(provider, get_integration(provider))
    return [existing[key] for key in sorted(existing)]


def read_integration(provider: str) -> dict[str, Any]:
    ensure_supported_provider(provider)
    return get_integration(provider)


def write_integration(provider: str, config: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    ensure_supported_provider(provider)
    return save_integration(provider, config, enabled=enabled)


def meta_client() -> MetaGraphClient:
    saved = get_integration("meta_instagram", include_secrets=True)
    config = MetaConfig.from_dict(saved.get("config") or {})
    if not config.token:
        raise IntegrationConfigError("Meta / Instagram access token is not configured")
    return MetaGraphClient(config)


async def test_meta_connection() -> dict[str, Any]:
    provider = "meta_instagram"
    try:
        result = await meta_client().test_connection()
    except Exception as exc:
        update_test_result(provider, ok=False, message=str(exc))
        raise
    update_test_result(provider, ok=True, message="Meta Graph API connection successful", scopes="configured_token")
    return result


async def enrich_meta_profile(profile_url: str = "", handle: str = "") -> dict[str, Any]:
    raw = await meta_client().enrich(profile_url or handle)
    public = public_profile_payload(raw)
    store_social_profile("meta_instagram", profile_url, handle or str(public.get("handle") or ""), public, raw)
    return public
