"""OpenRouter chat-completion client with SSE streaming."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 2
FREE_MODEL_FALLBACK = "openrouter/free"


class OpenRouterAPIError(RuntimeError):
    """An OpenRouter API error with a user-safe message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenRouterService:
    """Send streaming chat completions to the configured OpenRouter model."""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not configured. Add your OpenRouter key "
                "to the backend environment and restart the API and worker."
            )

    async def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """Yield generated text from OpenRouter's streaming Chat Completions API."""
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        request_body = {
            "model": self.settings.openrouter_model,
            "models": [FREE_MODEL_FALLBACK],
            "messages": messages,
            "stream": True,
            "max_tokens": 2048,
        }

        timeout = httpx.Timeout(120, connect=15)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
                async with client.stream(
                    "POST",
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=request_body,
                ) as response:
                    if response.status_code == 429:
                        await response.aread()
                        if (
                            attempt < MAX_RATE_LIMIT_RETRIES
                            and not self._is_platform_rate_limit(
                                response.content, response.headers
                            )
                        ):
                            delay = self._retry_delay(response, attempt)
                            if delay <= 30:
                                logger.warning(
                                    "OpenRouter provider is rate limited; retrying "
                                    "in %.1f seconds (attempt %d/%d)",
                                    delay,
                                    attempt + 1,
                                    MAX_RATE_LIMIT_RETRIES,
                                )
                                await asyncio.sleep(delay)
                                continue
                        raise self._api_error(
                            response.status_code, response.content, response.headers
                        )

                    if not response.is_success:
                        body = await response.aread()
                        raise self._api_error(
                            response.status_code, body, response.headers
                        )

                    received_content = False
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":") or not line.startswith("data:"):
                            continue

                        event_data = line[5:].strip()
                        if event_data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(event_data)
                        except json.JSONDecodeError:
                            logger.warning("Ignoring malformed OpenRouter SSE data")
                            continue

                        if error := chunk.get("error"):
                            error_body = json.dumps({"error": error}).encode()
                            error_code = (
                                error.get("code")
                                if isinstance(error, dict)
                                else None
                            )
                            try:
                                status_code = int(error_code)
                            except (TypeError, ValueError):
                                status_code = 502
                            raise self._api_error(status_code, error_body)

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            received_content = True
                            yield content
                        elif isinstance(content, list):
                            for part in content:
                                text = part.get("text") if isinstance(part, dict) else None
                                if text:
                                    received_content = True
                                    yield text

                    if not received_content:
                        raise OpenRouterAPIError(
                            502,
                            "OpenRouter returned no response text. Please retry.",
                        )
                    return

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    seconds = (retry_at - datetime.now(UTC)).total_seconds()
                    return max(seconds, 0)
                except (TypeError, ValueError, OverflowError):
                    logger.warning("Ignoring invalid OpenRouter Retry-After header")
        return min(2 ** (attempt + 1), 30)

    @staticmethod
    def _is_platform_rate_limit(body: bytes, headers: httpx.Headers) -> bool:
        if headers.get("X-RateLimit-Limit") is not None:
            return True
        try:
            error: Any = json.loads(body).get("error", {})
        except (json.JSONDecodeError, AttributeError):
            return False
        metadata = error.get("metadata", {}) if isinstance(error, dict) else {}
        return (
            isinstance(metadata, dict)
            and metadata.get("error_type") == "rate_limit_exceeded"
            and not metadata.get("provider_code")
        )

    @staticmethod
    def _api_error(
        status_code: int,
        body: bytes,
        headers: httpx.Headers | None = None,
    ) -> OpenRouterAPIError:
        try:
            error: Any = json.loads(body).get("error", {})
        except (json.JSONDecodeError, AttributeError):
            error = {}
        metadata = error.get("metadata", {}) if isinstance(error, dict) else {}
        provider_code = (
            metadata.get("provider_code") if isinstance(metadata, dict) else None
        )

        messages = {
            401: "OpenRouter rejected the API key. Check OPENROUTER_API_KEY.",
            402: "OpenRouter reports insufficient credits for this request.",
            403: "OpenRouter denied this request. Check the key and model access.",
            404: "The configured OpenRouter model was not found or is unavailable.",
        }
        if message := messages.get(status_code):
            return OpenRouterAPIError(status_code, message)

        detail = error.get("message") if isinstance(error, dict) else None
        if status_code == 429 and provider_code:
            message = (
                "The Gemma provider is temporarily rate-limited or at capacity. "
                "OpenRouter could not find another available provider for this "
                "request. Wait briefly and try again; this may not appear as "
                "account usage."
            )
        elif status_code == 429:
            message = (
                "OpenRouter returned HTTP 429. This can mean your free-model "
                "per-minute/daily quota is exhausted or Gemma providers are at "
                "capacity. Check the key endpoint's free_model_daily_requests "
                "field; if quota remains, wait and retry because this is likely "
                "provider capacity."
            )
        else:
            message = detail or f"OpenRouter request failed with HTTP {status_code}."

        retry_after = headers.get("Retry-After") if headers else None
        if retry_after and status_code == 429:
            message += f" OpenRouter asked clients to retry after {retry_after}."
        return OpenRouterAPIError(status_code, message)
