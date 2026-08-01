"""Email provider factory exports."""

from emailing.providers.smtp_provider import provider_from_account, provider_from_settings

__all__ = ["provider_from_account", "provider_from_settings"]
