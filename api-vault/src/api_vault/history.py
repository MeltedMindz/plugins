"""
Historical learning module for Api Vault.

Tracks execution history to improve future estimates by learning from:
- Actual token usage vs estimates
- Generation times
- Success/failure rates per artifact type
"""

import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ExecutionRecord(BaseModel):
    """Record of a single artifact generation execution."""

    job_id: str
    artifact_name: str
    family: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Estimates
    estimated_input_tokens: int
    estimated_output_tokens: int

    # Actuals
    actual_input_tokens: int
    actual_output_tokens: int
    generation_time_seconds: float
    success: bool

    # Context info
    repo_name: str
    model: str
    context_size_bytes: int = 0


class HistoryStats(BaseModel):
    """Aggregated statistics from history."""

    total_executions: int = 0
    success_rate: float = 0.0

    # Token estimation accuracy
    input_token_ratio_mean: float = 1.0  # actual/estimated
    input_token_ratio_std: float = 0.0
    output_token_ratio_mean: float = 1.0
    output_token_ratio_std: float = 0.0

    # Time tracking
    avg_generation_time: float = 0.0
    tokens_per_second: float = 0.0

    # Per-family stats
    family_stats: dict[str, dict[str, float]] = Field(default_factory=dict)


class ExecutionHistory:
    """
    Manages execution history for learning.

    Stores and analyzes past executions to improve future estimates.
    """

    def __init__(self, history_dir: Path | None = None) -> None:
        """
        Initialize history manager.

        Args:
            history_dir: Directory to store history files.
                        Defaults to ~/.api-vault/history/
        """
        if history_dir is None:
            history_dir = Path.home() / ".api-vault" / "history"

        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self._records: list[ExecutionRecord] = []
        self._stats_cache: HistoryStats | None = None
        self._load_history()

    def _history_file(self) -> Path:
        """Get path to main history file."""
        return self.history_dir / "executions.jsonl"

    def _load_history(self) -> None:
        """Load history from disk."""
        history_file = self._history_file()
        if not history_file.exists():
            return

        try:
            with open(history_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = ExecutionRecord.model_validate_json(line)
                        self._records.append(record)
            logger.info(f"Loaded {len(self._records)} execution records")
        except Exception as e:
            logger.warning(f"Failed to load history: {e}")

    def record_execution(
        self,
        job_id: str,
        artifact_name: str,
        family: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        actual_input_tokens: int,
        actual_output_tokens: int,
        generation_time_seconds: float,
        success: bool,
        repo_name: str,
        model: str,
        context_size_bytes: int = 0,
    ) -> None:
        """
        Record an execution for future learning.

        Args:
            job_id: Job identifier
            artifact_name: Name of generated artifact
            family: Artifact family
            estimated_input_tokens: Pre-execution estimate
            estimated_output_tokens: Pre-execution estimate
            actual_input_tokens: Actual tokens used
            actual_output_tokens: Actual tokens generated
            generation_time_seconds: Time taken
            success: Whether generation succeeded
            repo_name: Repository name
            model: Model used
            context_size_bytes: Size of context provided
        """
        record = ExecutionRecord(
            job_id=job_id,
            artifact_name=artifact_name,
            family=family,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            actual_input_tokens=actual_input_tokens,
            actual_output_tokens=actual_output_tokens,
            generation_time_seconds=generation_time_seconds,
            success=success,
            repo_name=repo_name,
            model=model,
            context_size_bytes=context_size_bytes,
        )

        self._records.append(record)
        self._stats_cache = None  # Invalidate cache

        # Append to file
        try:
            with open(self._history_file(), "a") as f:
                f.write(record.model_dump_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to save execution record: {e}")

    def get_stats(self, max_age_days: int | None = 90) -> HistoryStats:
        """
        Get aggregated statistics from history.

        Args:
            max_age_days: Only consider records from the last N days

        Returns:
            Aggregated statistics
        """
        if self._stats_cache is not None:
            return self._stats_cache

        if not self._records:
            return HistoryStats()

        # Filter by age
        records = self._records
        if max_age_days is not None:
            cutoff = datetime.utcnow().timestamp() - (max_age_days * 86400)
            records = [r for r in records if r.timestamp.timestamp() > cutoff]

        if not records:
            return HistoryStats()

        # Calculate stats
        successes = [r for r in records if r.success]
        success_rate = len(successes) / len(records) if records else 0.0

        # Token ratios (only for successful, non-zero estimates)
        input_ratios = []
        output_ratios = []
        for r in successes:
            if r.estimated_input_tokens > 0:
                input_ratios.append(r.actual_input_tokens / r.estimated_input_tokens)
            if r.estimated_output_tokens > 0:
                output_ratios.append(r.actual_output_tokens / r.estimated_output_tokens)

        input_ratio_mean = statistics.mean(input_ratios) if input_ratios else 1.0
        input_ratio_std = statistics.stdev(input_ratios) if len(input_ratios) > 1 else 0.0
        output_ratio_mean = statistics.mean(output_ratios) if output_ratios else 1.0
        output_ratio_std = statistics.stdev(output_ratios) if len(output_ratios) > 1 else 0.0

        # Time stats
        times = [r.generation_time_seconds for r in successes if r.generation_time_seconds > 0]
        avg_time = statistics.mean(times) if times else 0.0

        # Tokens per second
        total_tokens = sum(r.actual_output_tokens for r in successes)
        total_time = sum(r.generation_time_seconds for r in successes)
        tokens_per_second = total_tokens / total_time if total_time > 0 else 0.0

        # Per-family stats
        family_stats: dict[str, dict[str, float]] = {}
        families = set(r.family for r in records)
        for family in families:
            family_records = [r for r in records if r.family == family]
            family_successes = [r for r in family_records if r.success]

            family_input_ratios = [
                r.actual_input_tokens / r.estimated_input_tokens
                for r in family_successes
                if r.estimated_input_tokens > 0
            ]
            family_output_ratios = [
                r.actual_output_tokens / r.estimated_output_tokens
                for r in family_successes
                if r.estimated_output_tokens > 0
            ]

            family_stats[family] = {
                "count": len(family_records),
                "success_rate": len(family_successes) / len(family_records) if family_records else 0.0,
                "input_ratio": statistics.mean(family_input_ratios) if family_input_ratios else 1.0,
                "output_ratio": statistics.mean(family_output_ratios) if family_output_ratios else 1.0,
            }

        stats = HistoryStats(
            total_executions=len(records),
            success_rate=success_rate,
            input_token_ratio_mean=input_ratio_mean,
            input_token_ratio_std=input_ratio_std,
            output_token_ratio_mean=output_ratio_mean,
            output_token_ratio_std=output_ratio_std,
            avg_generation_time=avg_time,
            tokens_per_second=tokens_per_second,
            family_stats=family_stats,
        )

        self._stats_cache = stats
        return stats

    def adjust_estimate(
        self,
        estimated_tokens: int,
        family: str | None = None,
        is_input: bool = True,
    ) -> int:
        """
        Adjust a token estimate based on historical accuracy.

        Args:
            estimated_tokens: Original estimate
            family: Artifact family (optional, for family-specific adjustment)
            is_input: True for input tokens, False for output

        Returns:
            Adjusted estimate
        """
        stats = self.get_stats()

        if stats.total_executions < 10:
            # Not enough history, return original
            return estimated_tokens

        # Get ratio to apply
        if family and family in stats.family_stats:
            ratio = stats.family_stats[family].get(
                "input_ratio" if is_input else "output_ratio", 1.0
            )
        else:
            ratio = stats.input_token_ratio_mean if is_input else stats.output_token_ratio_mean

        # Apply ratio with some dampening to avoid over-correction
        dampening = 0.7  # Move 70% toward historical average
        adjusted_ratio = 1.0 + (ratio - 1.0) * dampening

        return int(estimated_tokens * adjusted_ratio)

    def estimate_time(self, output_tokens: int) -> float:
        """
        Estimate generation time based on history.

        Args:
            output_tokens: Expected output tokens

        Returns:
            Estimated time in seconds
        """
        stats = self.get_stats()

        if stats.tokens_per_second > 0:
            return output_tokens / stats.tokens_per_second

        # Default estimate: ~50 tokens/second for Claude
        return output_tokens / 50.0

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of historical data for display."""
        stats = self.get_stats()

        return {
            "total_executions": stats.total_executions,
            "success_rate": f"{stats.success_rate:.1%}",
            "estimate_accuracy": {
                "input_tokens": f"{stats.input_token_ratio_mean:.2f}x (±{stats.input_token_ratio_std:.2f})",
                "output_tokens": f"{stats.output_token_ratio_mean:.2f}x (±{stats.output_token_ratio_std:.2f})",
            },
            "avg_generation_time": f"{stats.avg_generation_time:.1f}s",
            "tokens_per_second": f"{stats.tokens_per_second:.1f}",
            "families": {
                family: {
                    "count": int(data.get("count", 0)),
                    "success_rate": f"{data.get('success_rate', 0):.1%}",
                }
                for family, data in stats.family_stats.items()
            },
        }

    def clear_history(self) -> None:
        """Clear all execution history."""
        self._records = []
        self._stats_cache = None

        history_file = self._history_file()
        if history_file.exists():
            history_file.unlink()

        logger.info("Cleared execution history")


# Global instance
_history: ExecutionHistory | None = None


def get_history(history_dir: Path | None = None) -> ExecutionHistory:
    """Get the global history manager."""
    global _history
    if _history is None:
        _history = ExecutionHistory(history_dir)
    return _history


def reset_history() -> None:
    """Reset the global history manager (mainly for testing)."""
    global _history
    _history = None
