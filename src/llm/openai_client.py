"""OpenAI client with retry logic and structured output support."""

import json
from typing import Any, Optional, Type, TypeVar

import structlog
from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from src.core.config import Settings, get_settings
from src.core.exceptions import (LLMError, LLMRateLimitError,
                                 LLMResponseParseError, LLMTimeoutError)

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class OpenAIClient:
    """OpenAI API client with retry logic and structured output."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize OpenAI client.

        Args:
            settings: Application settings
        """
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        self.logger = logger.bind(component="OpenAIClient")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((LLMRateLimitError, LLMTimeoutError)),
    )
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Generate structured output using JSON schema.

        Args:
            system_prompt: System message
            user_prompt: User message
            response_schema: Pydantic model for response validation
            model: Model to use (defaults to settings.openai_model)
            temperature: Sampling temperature

        Returns:
            Parsed response as Pydantic model

        Raises:
            LLMError: If generation fails
        """
        model = model or self.settings.openai_model

        self.logger.debug(
            "Generating structured output",
            model=model,
            schema=response_schema.__name__,
        )

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_schema.__name__,
                        "schema": self._enforce_strict_json_schema(
                            response_schema.model_json_schema()
                        ),
                        "strict": True,
                    },
                },
                temperature=temperature,
            )

            content = response.choices[0].message.content

            if not content:
                raise LLMResponseParseError("Empty response from LLM")

            # Parse JSON response
            try:
                data = json.loads(content)
                return response_schema.model_validate(data)
            except json.JSONDecodeError as e:
                raise LLMResponseParseError(f"Failed to parse JSON: {e}")
            except Exception as e:
                raise LLMResponseParseError(f"Failed to validate response: {e}")

        except RateLimitError as e:
            self.logger.warning("Rate limit hit", error=str(e))
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            self.logger.warning("API timeout", error=str(e))
            raise LLMTimeoutError(f"API timeout: {e}")
        except APIError as e:
            self.logger.error("API error", error=str(e))
            raise LLMError(f"OpenAI API error: {e}")

    def _enforce_strict_json_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Recursively ensure schema meets OpenAI's strict mode requirements."""
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                # OpenAI strict mode requires additionalProperties: false
                schema["additionalProperties"] = False

            # Recurse into properties
            if "properties" in schema:
                for prop in schema["properties"].values():
                    self._enforce_strict_json_schema(prop)

            # Recurse into $defs
            if "$defs" in schema:
                for def_schema in schema["$defs"].values():
                    self._enforce_strict_json_schema(def_schema)

            # Recurse into items
            if "items" in schema:
                self._enforce_strict_json_schema(schema["items"])

        return schema

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((LLMRateLimitError, LLMTimeoutError)),
    )
    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate plain text response.

        Args:
            system_prompt: System message
            user_prompt: User message
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails
        """
        model = model or self.settings.openai_model

        self.logger.debug("Generating text", model=model)

        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            response = await self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content

            return content or ""

        except RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            raise LLMTimeoutError(f"API timeout: {e}")
        except APIError as e:
            raise LLMError(f"OpenAI API error: {e}")

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Generate JSON response without schema validation.

        Args:
            system_prompt: System message
            user_prompt: User message
            model: Model to use
            temperature: Sampling temperature

        Returns:
            Parsed JSON dictionary

        Raises:
            LLMError: If generation fails
        """
        model = model or self.settings.openai_model

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )

            content = response.choices[0].message.content

            if not content:
                raise LLMResponseParseError("Empty response from LLM")

            return json.loads(content)

        except json.JSONDecodeError as e:
            raise LLMResponseParseError(f"Failed to parse JSON: {e}")
        except RateLimitError as e:
            raise LLMRateLimitError(f"Rate limit exceeded: {e}")
        except APITimeoutError as e:
            raise LLMTimeoutError(f"API timeout: {e}")
        except APIError as e:
            raise LLMError(f"OpenAI API error: {e}")

    async def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Count tokens in text.

        Args:
            text: Text to count
            model: Model for tokenization

        Returns:
            Token count
        """
        import tiktoken

        model = model or self.settings.openai_model

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")

        return len(encoding.encode(text))
