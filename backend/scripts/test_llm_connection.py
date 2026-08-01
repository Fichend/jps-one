"""Minimal connectivity test for the configured default and reasoning LLMs."""

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

import litellm

from config.settings import get_settings
from tools.llm_client import get_llm_completion_params


async def _test(scope: str) -> bool:
    settings = get_settings()
    params = get_llm_completion_params(settings, scope)
    model = params["model"]
    print(f"Testing {scope}: model={model}, api_base={params.get('api_base', '(provider default)')}")
    print(f"  api_key={'configured' if params.get('api_key') else 'missing'}")
    try:
        response = await litellm.acompletion(
            **params,
            messages=[{"role": "user", "content": "Reply with exactly: LLM OK"}],
            temperature=0,
            max_tokens=20,
        )
        content = response.choices[0].message.content or ""
        print(f"  success: {content.strip()}")
        return True
    except Exception as exc:
        print(f"  failed: {type(exc).__name__}: {exc}")
        return False


async def main() -> int:
    results = [await _test("default"), await _test("reasoning")]
    return 0 if all(results) else 1


if __name__ == "__main__":
    litellm.suppress_debug_info = True
    raise SystemExit(asyncio.run(main()))
