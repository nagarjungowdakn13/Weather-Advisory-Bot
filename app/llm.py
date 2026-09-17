"""Thin LLM client interface so the graph isn't hardcoded to one vendor."""

import json
import os
import re
from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """Single-turn completion. Returns raw text."""


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text


class OpenAIClient(LLMClient):
    """Also used for Groq and any other OpenAI-compatible chat completions
    API — just pass a different base_url."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
    ):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._reasoning_effort = reasoning_effort

    async def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        kwargs = {}
        if self._reasoning_effort:
            # gpt-oss/reasoning models burn completion tokens on hidden
            # reasoning before the actual answer — low effort keeps that
            # from eating the whole max_tokens budget on short replies.
            kwargs["reasoning_effort"] = self._reasoning_effort

        resp = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return resp.choices[0].message.content


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is not None:
        return _client

    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        model = os.environ.get("ANTHROPIC_MODEL")
        if not model:
            raise RuntimeError("ANTHROPIC_MODEL is not set")
        _client = AnthropicClient(api_key, model)
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get("OPENAI_MODEL")
        if not model:
            raise RuntimeError("OPENAI_MODEL is not set")
        _client = OpenAIClient(api_key, model)
    elif provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        model = os.environ.get("GROQ_MODEL")
        if not model:
            raise RuntimeError("GROQ_MODEL is not set")
        _client = OpenAIClient(
            api_key, model, base_url="https://api.groq.com/openai/v1", reasoning_effort="low"
        )
    else:
        raise RuntimeError(f"unknown LLM_PROVIDER: {provider}")

    return _client


def reset_llm_client() -> None:
    """Used by tests to force re-reading env vars / re-instantiating."""
    global _client
    _client = None


def parse_json_response(text: str) -> dict:
    """Models sometimes wrap JSON in markdown fences despite instructions
    not to. Strip that before parsing."""
    stripped = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fence_match:
        stripped = fence_match.group(1)
    return json.loads(stripped)
