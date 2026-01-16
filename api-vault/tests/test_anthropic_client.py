"""Tests for Anthropic client."""

import tempfile
from pathlib import Path

import pytest

from api_vault.anthropic_client import (
    CacheManager,
    MockAnthropicClient,
    canonicalize_json,
    compute_request_hash,
)
from api_vault.schemas import CacheEntry


class TestCanonicalizeJson:
    """Tests for JSON canonicalization."""

    def test_consistent_ordering(self):
        """Test that keys are consistently ordered."""
        data1 = {"b": 1, "a": 2}
        data2 = {"a": 2, "b": 1}

        assert canonicalize_json(data1) == canonicalize_json(data2)

    def test_no_whitespace(self):
        """Test that output has no extra whitespace."""
        data = {"key": "value", "nested": {"inner": 1}}
        result = canonicalize_json(data)

        assert " " not in result
        assert "\n" not in result


class TestComputeRequestHash:
    """Tests for request hash computation."""

    def test_deterministic(self):
        """Test that hash is deterministic."""
        hash1 = compute_request_hash("model", "system", "user", 1000)
        hash2 = compute_request_hash("model", "system", "user", 1000)

        assert hash1 == hash2

    def test_different_for_different_inputs(self):
        """Test different inputs produce different hashes."""
        hash1 = compute_request_hash("model", "system", "user1", 1000)
        hash2 = compute_request_hash("model", "system", "user2", 1000)

        assert hash1 != hash2

    def test_format(self):
        """Test hash format."""
        hash_value = compute_request_hash("model", "system", "user", 1000)

        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)


class TestCacheManager:
    """Tests for cache manager."""

    def test_stores_and_retrieves(self):
        """Test storing and retrieving cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir))

            entry = CacheEntry(
                request_hash="a" * 64,
                model="test-model",
                input_tokens=100,
                output_tokens=200,
                response_text="Hello, world!",
                prompt_template_id="test",
                context_hash="b" * 16,
            )

            cache.set(entry)
            retrieved = cache.get("a" * 64)

            assert retrieved is not None
            assert retrieved.response_text == "Hello, world!"
            assert retrieved.input_tokens == 100

    def test_returns_none_for_missing(self):
        """Test that missing entries return None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(Path(tmpdir))
            result = cache.get("nonexistent" + "a" * 54)

            assert result is None


class TestMockAnthropicClient:
    """Tests for mock Anthropic client."""

    def test_generates_response(self):
        """Test that mock generates responses."""
        client = MockAnthropicClient()
        result = client.generate(
            system_prompt="You are helpful.",
            user_prompt="Hello!",
            max_tokens=100,
        )

        assert result.text is not None
        assert len(result.text) > 0
        assert result.error is None

    def test_tracks_usage(self):
        """Test that usage is tracked."""
        client = MockAnthropicClient()

        client.generate("system", "user", 100)
        client.generate("system", "user2", 100)

        summary = client.get_usage_summary()
        assert summary["request_count"] == 2
        assert summary["total_input_tokens"] > 0

    def test_returns_predefined_responses(self):
        """Test returning predefined responses."""
        # Compute hash for expected request
        request_hash = compute_request_hash("mock-model", "system", "user", 100)

        client = MockAnthropicClient(
            responses={request_hash: "Custom response!"}
        )

        result = client.generate("system", "user", 100)
        assert result.text == "Custom response!"

    def test_stores_requests(self):
        """Test that requests are stored for verification."""
        client = MockAnthropicClient()

        client.generate("system prompt", "user prompt", 100)

        assert len(client.requests) == 1
        assert client.requests[0]["system"] == "system prompt"
        assert client.requests[0]["user"] == "user prompt"

    def test_request_hash_stable(self):
        """Test that request hashes are stable."""
        client = MockAnthropicClient()

        result1 = client.generate("system", "user", 100)
        result2 = client.generate("system", "user", 100)

        assert result1.request_hash == result2.request_hash
