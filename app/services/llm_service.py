"""Async OpenAI-compatible Chat Completions, without provider SDKs."""

import logging

import httpx
from pydantic import ValidationError

from app.schemas.analysis import LLMIncidentAnalysis

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    """The configured provider cannot be used."""


class LLMProviderError(Exception):
    """The provider request failed."""


class LLMResponseError(Exception):
    """The provider or model response is malformed."""


class LLMService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate_analysis(
        self, system_prompt: str, user_prompt: str
    ) -> LLMIncidentAnalysis:
        if not self._api_key or not self._api_key.strip() or not self.model.strip():
            raise LLMConfigurationError("LLM provider is not configured")
        try:
            url = httpx.URL(self.base_url + "/chat/completions")
            if url.scheme not in {"http", "https"} or not url.host:
                raise ValueError("Invalid provider URL")
        except (httpx.InvalidURL, ValueError):
            raise LLMConfigurationError("LLM provider is not configured") from None

        try:
            response = await self.client.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException:
            logger.warning("LLM provider request timed out")
            raise LLMProviderError("LLM provider request failed") from None
        except httpx.HTTPError:
            logger.warning("LLM provider connection failed")
            raise LLMProviderError("LLM provider request failed") from None

        if not response.is_success:
            logger.warning("LLM provider returned HTTP %s", response.status_code)
            raise LLMProviderError("LLM provider request failed")

        try:
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete or refused response")
            message = choice["message"]
            if message.get("refusal") or not isinstance(message["content"], str):
                raise ValueError("Missing textual response")
            return LLMIncidentAnalysis.model_validate_json(message["content"])
        except (
            ValueError,
            ValidationError,
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
        ):
            logger.warning("LLM provider returned an invalid analysis")
            raise LLMResponseError(
                "LLM provider returned an invalid analysis"
            ) from None
