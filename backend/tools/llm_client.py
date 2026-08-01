"""LLM tool — unified multi-provider interface via litellm.

Supports: OpenAI, Anthropic, OpenRouter, Groq, GLM (智谱), Kimi (Moonshot),
MiniMax, and 100+ other providers through litellm.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import litellm

from config.settings import Settings, get_settings
from tools.llm_errors import format_llm_error
from tools.llm_rate_limiter import get_llm_rate_limiter


# Suppress litellm's verbose logging by default
litellm.suppress_debug_info = True
litellm.drop_params = True
logger = logging.getLogger(__name__)


_RESPONSE_FORMAT_UNSUPPORTED_PREFIXES = (
    "zai/",
)
_RESPONSE_FORMAT_UNSUPPORTED_MODEL_MARKERS = (
    "minimax",
)

_RATE_LIMIT_BACKOFF_SECONDS = (2, 5, 10)


def normalize_temperature_for_model(model: str, temperature: float) -> float:
    """Keep GPT-5-family calls compatible with OpenAI-style providers."""
    model_name = (model or "").lower()
    if "gpt-5" in model_name:
        return 1.0
    return temperature


def normalize_minimax_api_base(api_base: str) -> str:
    """Normalize MiniMax API base URLs to the OpenAI-compatible `/v1` form."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        return api_base
    if base.startswith("https://api.minimax.io"):
        base = base.replace("https://api.minimax.io", "https://api.minimaxi.com", 1)
    if base.endswith("/anthropic"):
        logger.warning("Normalizing legacy MiniMax API base from %s to OpenAI-compatible /v1", api_base)
        return base[: -len("/anthropic")] + "/v1"
    return base


def normalize_model_name(model: str) -> str:
    """Normalize legacy provider/model aliases before sending to LiteLLM.

    MiniMax is routed through its OpenAI-compatible endpoint. LiteLLM 1.79.3
    does not reliably recognize the native `minimax/` provider prefix.
    """
    if model and "minimax" in model.lower() and model.startswith(("anthropic/", "minimax/")):
        normalized = "openai/" + model.split("/", 1)[1]
        logger.warning("Normalizing legacy model alias from %s to %s", model, normalized)
        return normalized
    return model


def get_llm_completion_params(
    settings: Settings,
    scope: str = "default",
    model: str | None = None,
) -> dict[str, str]:
    """Resolve explicit LiteLLM model, API key, and optional API base."""
    resolved_model = normalize_model_name(model or _select_model(settings, scope))
    provider = resolved_model.split("/", 1)[0] if "/" in resolved_model else "openai"
    keys = _provider_key_map(settings, scope)

    env_key_by_provider = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "groq": "GROQ_API_KEY",
        "zai": "ZAI_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }
    api_key = keys.get(env_key_by_provider.get(provider, ""), "")
    params = {"model": resolved_model}

    is_minimax = "minimax" in resolved_model.lower()
    if is_minimax:
        api_key = api_key or keys.get("MINIMAX_API_KEY", "")
        api_base = settings.openai_api_base or normalize_minimax_api_base(settings.minimax_api_base)
    elif provider == "openai":
        api_base = settings.openai_api_base.strip()
    else:
        api_base = ""

    if api_key:
        params["api_key"] = api_key
    if api_base:
        params["api_base"] = api_base.rstrip("/")
    return params


def _is_retryable_rate_limit_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "rate_limit" in message
        or '"http_code":"429"' in message
        or '"http_code": "429"' in message
        or "上游返回 429" in message
        or "too many requests" in message
    )


def _provider_key_map(settings: Settings, scope: str) -> dict[str, str]:
    if scope in {"email", "email_reasoning"}:
        return {
            "OPENAI_API_KEY": settings.email_openai_api_key or settings.openai_api_key,
            "ANTHROPIC_API_KEY": settings.email_anthropic_api_key or settings.anthropic_api_key,
            "OPENROUTER_API_KEY": settings.email_openrouter_api_key or settings.openrouter_api_key,
            "GROQ_API_KEY": settings.email_groq_api_key or settings.groq_api_key,
            "ZAI_API_KEY": settings.email_zai_api_key or settings.zai_api_key,
            "MOONSHOT_API_KEY": settings.email_moonshot_api_key or settings.moonshot_api_key,
            "MINIMAX_API_KEY": settings.email_minimax_api_key or settings.minimax_api_key,
            "MINIMAX_API_BASE": normalize_minimax_api_base(settings.minimax_api_base),
            "ZHIPUAI_API_KEY": settings.email_zai_api_key or settings.zai_api_key,
        }
    return {
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "GROQ_API_KEY": settings.groq_api_key,
        "ZAI_API_KEY": settings.zai_api_key,
        "MOONSHOT_API_KEY": settings.moonshot_api_key,
        "MINIMAX_API_KEY": settings.minimax_api_key,
        "MINIMAX_API_BASE": normalize_minimax_api_base(settings.minimax_api_base),
        "ZHIPUAI_API_KEY": settings.zai_api_key,
    }


def _inject_api_keys(settings: Settings, scope: str = "default") -> None:
    """Push provider API keys from Settings into env vars for litellm."""
    _key_map = _provider_key_map(settings, scope)
    for env_var, value in _key_map.items():
        if value:
            os.environ[env_var] = value

def _select_model(settings: Settings, model_type: str) -> str:
    if model_type == "reasoning":
        return settings.reasoning_model
    if model_type == "email":
        return settings.email_llm_model or settings.llm_model
    if model_type == "email_reasoning":
        return settings.email_reasoning_model or settings.reasoning_model
    return settings.llm_model


class LLMTool:
    """Unified LLM client powered by litellm.

    All calls go through a single interface so agents don't care about the
    provider.  Just set ``llm_model`` in Settings (or ``LLM_MODEL`` in .env)
    using litellm model naming, e.g.:
      - ``gpt-4o``
      - ``anthropic/claude-3-5-sonnet-20241022``
      - ``openrouter/google/gemini-pro``
      - ``groq/llama-3.3-70b-versatile``
      - ``zai/glm-4.7``
      - ``moonshot/moonshot-v1-128k``
      - ``minimax/MiniMax-Text-01``

    Args:
        model_type: ``"default"`` uses ``llm_model`` (fast, cheap — data extraction).
                    ``"reasoning"`` uses ``reasoning_model`` (strong reasoning — ReAct decisions).
        settings: Optional Settings override.
        hunt_id: Optional hunt ID for cost tracking.
        agent: Agent name label for cost tracking (e.g. "keyword_gen", "email_craft").
        hunt_round: Current hunt round for per-round cost breakdown.
    """

    def __init__(
        self,
        model_type: str = "default",
        settings: Settings | None = None,
        hunt_id: str = "",
        agent: str = "unknown",
        hunt_round: int = 0,
    ) -> None:
        self._settings = settings or get_settings()
        self._model_type = model_type
        self._hunt_id = hunt_id
        self._agent = agent
        self._hunt_round = hunt_round
        _inject_api_keys(self._settings, self._model_type)

    @property
    def model(self) -> str:
        return normalize_model_name(_select_model(self._settings, self._model_type))

    @property
    def _default_temperature(self) -> float:
        if self._model_type in {"reasoning", "email_reasoning"}:
            return self._settings.reasoning_temperature
        return self._settings.llm_temperature

    @property
    def _default_max_tokens(self) -> int:
        if self._model_type in {"reasoning", "email_reasoning"}:
            return self._settings.reasoning_max_tokens
        return self._settings.llm_max_tokens

    @property
    def _requests_per_minute(self) -> int:
        if self._model_type == "reasoning":
            return self._settings.reasoning_requests_per_minute or self._settings.llm_requests_per_minute
        if self._model_type == "email":
            return self._settings.email_llm_requests_per_minute or self._settings.llm_requests_per_minute
        if self._model_type == "email_reasoning":
            return self._settings.email_reasoning_requests_per_minute or self._settings.reasoning_requests_per_minute or self._settings.llm_requests_per_minute
        return self._settings.llm_requests_per_minute

    def _supports_response_format(self) -> bool:
        """Return whether the current provider accepts OpenAI-style response_format."""
        model_name = self.model.lower()
        if self.model.startswith(_RESPONSE_FORMAT_UNSUPPORTED_PREFIXES):
            return False
        return not any(marker in model_name for marker in _RESPONSE_FORMAT_UNSUPPORTED_MODEL_MARKERS)

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        """Generate a completion from the LLM.

        Args:
            prompt: User message / main prompt.
            system: Optional system message.
            temperature: Override default temperature.
            max_tokens: Override default max_tokens.
            response_format: Optional JSON mode config.
            timeout_seconds: Optional provider request timeout in seconds.

        Returns:
            The generated text content.
        """
        temp = temperature if temperature is not None else self._default_temperature
        temp = normalize_temperature_for_model(self.model, temp)
        tokens = max_tokens or self._default_max_tokens

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            **get_llm_completion_params(self._settings, self._model_type, self.model),
            "messages": messages,
            "temperature": temp,
            "max_tokens": tokens,
        }
        if response_format:
            if self._supports_response_format():
                kwargs["response_format"] = response_format
            else:
                logger.info(
                    "Skipping response_format for model %s because the provider does not support it",
                    self.model,
                )
        if timeout_seconds is not None:
            kwargs["timeout"] = max(1.0, float(timeout_seconds))

        limiter = get_llm_rate_limiter(self._model_type, self._requests_per_minute)
        last_exc: Exception | None = None
        response = None
        for attempt in range(len(_RATE_LIMIT_BACKOFF_SECONDS) + 1):
            try:
                await limiter.acquire()
                response = await litellm.acompletion(**kwargs)
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= len(_RATE_LIMIT_BACKOFF_SECONDS) or not _is_retryable_rate_limit_error(exc):
                    raise RuntimeError(format_llm_error(exc)) from exc
                delay_seconds = _RATE_LIMIT_BACKOFF_SECONDS[attempt]
                logger.warning(
                    "LLM rate limited for model %s; retrying in %ss (attempt %s/%s)",
                    self.model,
                    delay_seconds,
                    attempt + 1,
                    len(_RATE_LIMIT_BACKOFF_SECONDS) + 1,
                )
                await asyncio.sleep(delay_seconds)

        if response is None and last_exc is not None:
            raise RuntimeError(format_llm_error(last_exc)) from last_exc

        # Record cost to tracker if hunt_id is set
        if self._hunt_id:
            try:
                from observability.cost_tracker import get_tracker
                usage = getattr(response, "usage", None)
                if usage:
                    cost = getattr(response, "_hidden_params", {}).get("response_cost") or 0.0
                    get_tracker(self._hunt_id).record_llm_call(
                        agent=self._agent,
                        model=self.model,
                        prompt_tokens=getattr(usage, "prompt_tokens", 0),
                        completion_tokens=getattr(usage, "completion_tokens", 0),
                        cost_usd=float(cost),
                        hunt_round=self._hunt_round,
                    )
            except Exception:
                pass  # Never let tracking break the main flow

        return response.choices[0].message.content

    async def close(self) -> None:
        """No-op — litellm manages its own connections."""
        pass
