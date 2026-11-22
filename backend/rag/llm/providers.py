"""LLM provider abstraction (OpenAI or Anthropic), lazily imported.

Both SDKs are optional at import time: the rest of the pipeline, and the test
suite, work without them. ``build_provider`` returns ``None`` when the LLM is
disabled, so callers fall back to deterministic or extractive behaviour.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Protocol

from rag.config.settings import RagSettings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, timeout: int, max_tokens: int) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment guard
            raise LLMError("openai package is not installed") from exc
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=timeout)

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:  # pragma: no cover - network
        response = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=user,
            max_output_tokens=max_tokens or self.max_tokens,
        )
        return response.output_text


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, timeout: int, max_tokens: int) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment guard
            raise LLMError("anthropic package is not installed; run `pip install anthropic`") from exc
        self.model = model
        self.max_tokens = max_tokens
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=timeout)

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:  # pragma: no cover - network
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


class RetryingProvider:
    """Retries transient failures with exponential backoff."""

    def __init__(self, inner: LLMProvider, attempts: int = 2, backoff_seconds: float = 0.8) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model
        self.attempts = max(1, attempts)
        self.backoff_seconds = backoff_seconds

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return self.inner.complete(system, user, max_tokens)
            except Exception as exc:  # noqa: BLE001 - SDKs raise many types
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(self.backoff_seconds * (2 ** attempt))
        raise LLMError(f"{self.name} completion failed") from last_error


def default_model(settings: RagSettings) -> str:
    if settings.llm_provider == "anthropic" and settings.gpt_model.startswith("gpt"):
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    return settings.gpt_model


def build_provider(settings: RagSettings, purpose: str = "decision") -> LLMProvider | None:
    enabled = settings.gpt_enabled if purpose == "decision" else settings.llm_qa_enabled
    if not enabled:
        return None
    provider_class = AnthropicProvider if settings.llm_provider == "anthropic" else OpenAIProvider
    try:
        provider = provider_class(default_model(settings), settings.gpt_timeout_seconds, settings.llm_max_output_tokens)
    except (LLMError, KeyError):
        logger.exception("LLM provider %s could not be initialised; LLM features disabled", settings.llm_provider)
        return None
    return RetryingProvider(provider)
