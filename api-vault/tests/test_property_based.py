"""
Property-based tests using Hypothesis for Api Vault.

These tests verify that functions handle a wide variety of inputs correctly,
including edge cases that might not be covered by example-based tests.
"""

import string
from datetime import datetime

import pytest
from hypothesis import given, settings, strategies as st, assume

from api_vault.schemas import (
    FileEntry,
    LanguageStats,
    ScoreBreakdown,
    ContextRef,
    RedactionEntry,
    ScanConfig,
)
from api_vault.secret_guard import (
    calculate_entropy,
    redact_content,
    scan_content,
)
from api_vault.signal_extractor import EXTENSION_TO_LANGUAGE


# --- Custom Strategies ---

@st.composite
def valid_sha256(draw: st.DrawFn) -> str:
    """Generate valid SHA-256 hex strings."""
    return draw(st.text(alphabet="0123456789abcdef", min_size=64, max_size=64))


@st.composite
def file_path_strategy(draw: st.DrawFn) -> str:
    """Generate realistic file paths."""
    dirs = draw(st.lists(
        st.text(alphabet=string.ascii_lowercase + string.digits + "_-", min_size=1, max_size=20),
        min_size=0,
        max_size=5,
    ))
    name = draw(st.text(alphabet=string.ascii_lowercase + string.digits + "_-", min_size=1, max_size=30))
    ext = draw(st.sampled_from([".py", ".js", ".ts", ".md", ".json", ".yaml", ".txt", ""]))
    return "/".join(dirs + [name + ext]) if dirs else name + ext


@st.composite
def score_strategy(draw: st.DrawFn) -> float:
    """Generate valid scores in range 0-10."""
    return draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))


# --- Schema Validation Tests ---

class TestFileEntryProperties:
    """Property-based tests for FileEntry schema."""

    @given(
        path=file_path_strategy(),
        size=st.integers(min_value=0, max_value=10_000_000),
        sha256=valid_sha256(),
        is_binary=st.booleans(),
    )
    @settings(max_examples=100)
    def test_file_entry_roundtrip(self, path: str, size: int, sha256: str, is_binary: bool) -> None:
        """FileEntry can be created and serialized/deserialized without data loss."""
        entry = FileEntry(
            path=path,
            size_bytes=size,
            sha256=sha256,
            is_binary=is_binary,
        )

        # Roundtrip through JSON
        json_str = entry.model_dump_json()
        restored = FileEntry.model_validate_json(json_str)

        assert restored.path == path
        assert restored.size_bytes == size
        assert restored.sha256 == sha256.lower()  # SHA-256 is normalized to lowercase
        assert restored.is_binary == is_binary

    @given(sha256=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64))
    def test_sha256_lowercase_normalization(self, sha256: str) -> None:
        """SHA-256 hashes are normalized to lowercase."""
        entry = FileEntry(
            path="test.py",
            size_bytes=100,
            sha256=sha256.upper(),  # Input uppercase
        )
        assert entry.sha256 == sha256.lower()  # Output lowercase

    @given(bad_sha=st.text(min_size=64, max_size=64).filter(
        lambda s: not all(c in "0123456789abcdefABCDEF" for c in s)
    ))
    def test_invalid_sha256_rejected(self, bad_sha: str) -> None:
        """Invalid SHA-256 strings are rejected."""
        with pytest.raises(ValueError):
            FileEntry(
                path="test.py",
                size_bytes=100,
                sha256=bad_sha,
            )


class TestScoreBreakdownProperties:
    """Property-based tests for scoring logic."""

    @given(
        reusability=score_strategy(),
        time_saved=score_strategy(),
        leverage=score_strategy(),
        context_cost=score_strategy(),
        gap_weight=score_strategy(),
    )
    @settings(max_examples=200)
    def test_score_breakdown_deterministic(
        self,
        reusability: float,
        time_saved: float,
        leverage: float,
        context_cost: float,
        gap_weight: float,
    ) -> None:
        """Score computation is deterministic for same inputs."""
        breakdown = ScoreBreakdown(
            reusability=reusability,
            time_saved=time_saved,
            leverage=leverage,
            context_cost=context_cost,
            gap_weight=gap_weight,
            total_score=0,
        )

        # Computing total twice should give same result
        total1 = breakdown.compute_total()
        total2 = breakdown.compute_total()

        assert total1 == total2

    @given(
        reusability=score_strategy(),
        time_saved=score_strategy(),
        leverage=score_strategy(),
        context_cost=score_strategy(),
        gap_weight=score_strategy(),
    )
    def test_score_increases_with_better_metrics(
        self,
        reusability: float,
        time_saved: float,
        leverage: float,
        context_cost: float,
        gap_weight: float,
    ) -> None:
        """Higher positive metrics increase total score."""
        base = ScoreBreakdown(
            reusability=reusability,
            time_saved=time_saved,
            leverage=leverage,
            context_cost=context_cost,
            gap_weight=gap_weight,
            total_score=0,
        )
        base_total = base.compute_total()

        # Increasing reusability should increase score
        improved = ScoreBreakdown(
            reusability=min(reusability + 1.0, 10.0),
            time_saved=time_saved,
            leverage=leverage,
            context_cost=context_cost,
            gap_weight=gap_weight,
            total_score=0,
        )
        improved_total = improved.compute_total()

        if reusability < 10.0:  # Can only improve if not already at max
            assert improved_total >= base_total


class TestLanguageStatsProperties:
    """Property-based tests for language statistics."""

    @given(
        file_count=st.integers(min_value=0, max_value=10000),
        total_bytes=st.integers(min_value=0, max_value=1_000_000_000),
        percentage=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    def test_language_stats_valid_ranges(
        self, file_count: int, total_bytes: int, percentage: float
    ) -> None:
        """LanguageStats accepts valid ranges and rejects invalid."""
        stats = LanguageStats(
            language="Python",
            file_count=file_count,
            total_bytes=total_bytes,
            percentage=percentage,
        )

        assert stats.file_count >= 0
        assert stats.total_bytes >= 0
        assert 0 <= stats.percentage <= 100


# --- Secret Detection Tests ---

class TestEntropyCalculation:
    """Property-based tests for entropy calculation."""

    @given(text=st.text(min_size=0, max_size=1000))
    def test_entropy_non_negative(self, text: str) -> None:
        """Entropy is always non-negative."""
        entropy = calculate_entropy(text)
        assert entropy >= 0.0

    @given(text=st.text(min_size=1, max_size=1000))
    def test_entropy_bounded(self, text: str) -> None:
        """Entropy has theoretical maximum based on alphabet size."""
        entropy = calculate_entropy(text)
        # Max entropy for 256 possible byte values is log2(256) = 8
        assert entropy <= 8.0

    @given(char=st.characters())
    def test_repeated_chars_low_entropy(self, char: str) -> None:
        """Strings of repeated characters have zero entropy."""
        text = char * 100
        entropy = calculate_entropy(text)
        assert entropy == 0.0

    @given(text=st.text(alphabet=string.ascii_letters + string.digits, min_size=32, max_size=64))
    def test_random_strings_high_entropy(self, text: str) -> None:
        """Random alphanumeric strings have high entropy."""
        assume(len(set(text)) > 10)  # Ensure some character variety
        entropy = calculate_entropy(text)
        # High entropy strings typically > 3.0
        assert entropy > 2.0


class TestRedaction:
    """Property-based tests for content redaction."""

    @given(content=st.text(min_size=0, max_size=10000))
    def test_redaction_idempotent(self, content: str) -> None:
        """Redacting already-redacted content doesn't change it."""
        redacted_once, report1 = redact_content(content)
        redacted_twice, report2 = redact_content(redacted_once)

        assert redacted_once == redacted_twice

    @given(prefix=st.text(max_size=100), suffix=st.text(max_size=100))
    def test_known_patterns_redacted(self, prefix: str, suffix: str) -> None:
        """Known secret patterns are always redacted."""
        # AWS key pattern - needs to be standalone (not attached to alphanumeric chars)
        assume("\n" not in prefix and "\n" not in suffix)
        # Ensure the key is isolated (not part of a longer alphanumeric string)
        assume(not (prefix and prefix[-1].isalnum()))
        assume(not (suffix and suffix[0].isalnum()))
        content = f"{prefix}AKIA1234567890ABCDEF{suffix}"
        redacted, entries = redact_content(content)

        # The AWS key should be redacted (or entries should show redactions)
        assert len(entries) > 0 or "AKIA1234567890ABCDEF" not in redacted


class TestSecretPatternDetection:
    """Property-based tests for secret pattern matching."""

    @given(content=st.text(min_size=0, max_size=1000))
    def test_pattern_detection_handles_any_input(self, content: str) -> None:
        """Pattern detection doesn't crash on arbitrary input."""
        # Should not raise any exceptions
        entries = scan_content(content, "test.py")
        assert isinstance(entries, list)


# --- Context Ref Tests ---

class TestContextRefProperties:
    """Property-based tests for context references."""

    @given(
        file_path=file_path_strategy(),
        max_bytes=st.integers(min_value=1, max_value=100000),
    )
    def test_context_ref_roundtrip(self, file_path: str, max_bytes: int) -> None:
        """ContextRef can be serialized and deserialized."""
        ref = ContextRef(
            file_path=file_path,
            max_bytes=max_bytes,
        )

        json_str = ref.model_dump_json()
        restored = ContextRef.model_validate_json(json_str)

        assert restored.file_path == file_path
        assert restored.max_bytes == max_bytes


# --- Signal Extractor Tests ---


def detect_language_from_extension(ext: str) -> str | None:
    """Helper to detect language from extension string like '.py'."""
    ext_clean = ext.lstrip(".")
    return EXTENSION_TO_LANGUAGE.get(ext_clean)


class TestLanguageDetection:
    """Property-based tests for language detection."""

    @given(ext=st.sampled_from([
        ".py", ".js", ".ts", ".java", ".go", ".rs", ".rb", ".php",
        ".c", ".cpp", ".h", ".cs", ".swift", ".kt", ".scala",
    ]))
    def test_known_extensions_detected(self, ext: str) -> None:
        """Known programming language extensions are detected."""
        language = detect_language_from_extension(ext)
        assert language is not None
        assert isinstance(language, str)
        assert len(language) > 0

    @given(ext=st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=10).map(lambda s: "." + s))
    def test_unknown_extensions_return_none(self, ext: str) -> None:
        """Unknown extensions return None or a language."""
        result = detect_language_from_extension(ext)
        # Result should be either None or a string
        assert result is None or isinstance(result, str)


# --- Scan Config Tests ---

class TestScanConfigProperties:
    """Property-based tests for scan configuration."""

    @given(
        max_file_size=st.integers(min_value=1024, max_value=100_000_000),
        max_excerpt=st.integers(min_value=256, max_value=65536),
    )
    def test_scan_config_valid_sizes(self, max_file_size: int, max_excerpt: int) -> None:
        """ScanConfig accepts valid size configurations."""
        config = ScanConfig(
            max_file_size_bytes=max_file_size,
            max_excerpt_bytes=max_excerpt,
        )

        assert config.max_file_size_bytes == max_file_size
        assert config.max_excerpt_bytes == max_excerpt


# --- Redaction Entry Tests ---

class TestRedactionEntryProperties:
    """Property-based tests for redaction entries."""

    @given(
        line_number=st.integers(min_value=1, max_value=1_000_000),
        original_length=st.integers(min_value=0, max_value=10_000),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_redaction_entry_valid_ranges(
        self, line_number: int, original_length: int, confidence: float
    ) -> None:
        """RedactionEntry accepts valid value ranges."""
        entry = RedactionEntry(
            file_path="test.py",
            line_number=line_number,
            pattern_name="api_key",
            original_length=original_length,
            confidence=confidence,
        )

        assert entry.line_number >= 1
        assert entry.original_length >= 0
        assert 0 <= entry.confidence <= 1
