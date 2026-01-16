"""
Anthropic API client wrapper with caching and retry logic.

Provides a robust interface to the Anthropic API with:
- Request hashing for deterministic caching
- Automatic retry with exponential backoff
- Rate limit handling
- Structured usage logging
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from anthropic import APIError, RateLimitError

from api_vault.schemas import CacheEntry

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of a generation request."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cached: bool
    request_hash: str
    generation_time_seconds: float
    error: str | None = None


def canonicalize_json(data: Any) -> str:
    """
    Create canonical JSON string for hashing.

    Args:
        data: Data to canonicalize

    Returns:
        Canonical JSON string
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_request_hash(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> str:
    """
    Compute deterministic hash for a request.

    Args:
        model: Model name
        system_prompt: System prompt
        user_prompt: User prompt
        max_tokens: Maximum tokens

    Returns:
        SHA-256 hash of request parameters
    """
    request_data = {
        "model": model,
        "system": system_prompt,
        "user": user_prompt,
        "max_tokens": max_tokens,
    }
    canonical = canonicalize_json(request_data)
    return hashlib.sha256(canonical.encode()).hexdigest()


class CacheManager:
    """Manages caching of API responses."""

    def __init__(self, cache_dir: Path):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, request_hash: str) -> Path:
        """Get path for cache file."""
        return self.cache_dir / f"{request_hash}.json"

    def get(self, request_hash: str) -> CacheEntry | None:
        """
        Get cached response if available.

        Args:
            request_hash: Request hash

        Returns:
            CacheEntry or None
        """
        path = self._cache_path(request_hash)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)
            return CacheEntry.model_validate(data)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(f"Failed to load cache entry: {e}")
            return None

    def set(self, entry: CacheEntry) -> None:
        """
        Store response in cache.

        Args:
            entry: Cache entry to store
        """
        path = self._cache_path(entry.request_hash)
        try:
            with open(path, "w") as f:
                f.write(entry.model_dump_json(indent=2))
        except OSError as e:
            logger.warning(f"Failed to write cache entry: {e}")


class AnthropicClient:
    """
    Wrapper around Anthropic API with caching and retry logic.
    """

    # Default models
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    AVAILABLE_MODELS = [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ]

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 60.0  # seconds

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | None = None,
        model: str | None = None,
    ):
        """
        Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            cache_dir: Directory for caching (optional)
            model: Model to use (defaults to DEFAULT_MODEL)
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL
        self.cache_manager = CacheManager(cache_dir) if cache_dir else None

        # Usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0

    def _retry_with_backoff(
        self,
        func: callable,
        max_retries: int = MAX_RETRIES,
    ) -> Any:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Function to execute
            max_retries: Maximum retry attempts

        Returns:
            Function result

        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        delay = self.BASE_DELAY

        for attempt in range(max_retries + 1):
            try:
                return func()
            except RateLimitError as e:
                last_exception = e
                if attempt < max_retries:
                    # Use retry-after header if available
                    retry_after = getattr(e, "retry_after", None)
                    wait_time = retry_after if retry_after else delay
                    logger.warning(
                        f"Rate limited. Waiting {wait_time:.1f}s before retry "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    delay = min(delay * 2, self.MAX_DELAY)
            except APIError as e:
                last_exception = e
                if e.status_code and e.status_code >= 500:
                    # Server error, retry
                    if attempt < max_retries:
                        logger.warning(
                            f"Server error ({e.status_code}). Retrying in {delay:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        delay = min(delay * 2, self.MAX_DELAY)
                else:
                    # Client error, don't retry
                    raise

        raise last_exception

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        use_cache: bool = True,
    ) -> GenerationResult:
        """
        Generate a completion with caching and retry.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt
            max_tokens: Maximum output tokens
            temperature: Sampling temperature
            use_cache: Whether to use cache

        Returns:
            GenerationResult with response and metadata
        """
        start_time = time.time()
        request_hash = compute_request_hash(
            self.model, system_prompt, user_prompt, max_tokens
        )

        # Check cache
        if use_cache and self.cache_manager:
            cached = self.cache_manager.get(request_hash)
            if cached:
                logger.info(f"Cache hit for request {request_hash[:8]}")
                return GenerationResult(
                    text=cached.response_text,
                    input_tokens=cached.input_tokens,
                    output_tokens=cached.output_tokens,
                    model=cached.model,
                    cached=True,
                    request_hash=request_hash,
                    generation_time_seconds=0.0,
                )

        # Make API request with retry
        def make_request():
            return self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

        try:
            response = self._retry_with_backoff(make_request)
            generation_time = time.time() - start_time

            # Extract text from response
            text = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

            # Update usage tracking
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.request_count += 1

            # Cache the response
            if use_cache and self.cache_manager:
                cache_entry = CacheEntry(
                    request_hash=request_hash,
                    created_at=datetime.utcnow(),
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    response_text=text,
                    prompt_template_id="",  # Will be set by caller if needed
                    context_hash="",  # Will be set by caller if needed
                )
                self.cache_manager.set(cache_entry)

            logger.info(
                f"Generated response: {input_tokens} in, {output_tokens} out, "
                f"{generation_time:.2f}s"
            )

            return GenerationResult(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=self.model,
                cached=False,
                request_hash=request_hash,
                generation_time_seconds=generation_time,
            )

        except Exception as e:
            generation_time = time.time() - start_time
            logger.error(f"Generation failed: {e}")
            return GenerationResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                model=self.model,
                cached=False,
                request_hash=request_hash,
                generation_time_seconds=generation_time,
                error=str(e),
            )

    def get_usage_summary(self) -> dict[str, Any]:
        """
        Get summary of API usage.

        Returns:
            Dictionary with usage statistics
        """
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "request_count": self.request_count,
            "model": self.model,
        }


class MockAnthropicClient:
    """
    Mock client for testing without API calls.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        cache_dir: Path | None = None,
        model: str | None = None,
    ):
        """
        Initialize mock client.

        Args:
            responses: Map of request hashes to responses
            cache_dir: Not used, for interface compatibility
            model: Model name to report
        """
        self.responses = responses or {}
        self.model = model or "mock-model"
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_count = 0
        self.requests: list[dict[str, Any]] = []

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        use_cache: bool = True,
    ) -> GenerationResult:
        """Generate mock response."""
        request_hash = compute_request_hash(
            self.model, system_prompt, user_prompt, max_tokens
        )

        # Store request for verification
        self.requests.append({
            "system": system_prompt,
            "user": user_prompt,
            "max_tokens": max_tokens,
            "hash": request_hash,
        })

        # Return predefined response or default
        text = self.responses.get(
            request_hash,
            f"# Mock Response\n\nThis is a mock response for testing.\n\nRequest hash: {request_hash[:16]}"
        )

        # Simulate token counts
        input_tokens = len(system_prompt + user_prompt) // 4
        output_tokens = len(text) // 4

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.request_count += 1

        return GenerationResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            cached=False,
            request_hash=request_hash,
            generation_time_seconds=0.1,
        )

    def get_usage_summary(self) -> dict[str, Any]:
        """Get usage summary."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "request_count": self.request_count,
            "model": self.model,
        }
