"""
Plan execution runner.

Executes artifact generation plans, managing:
- Job execution and artifact writing
- Progress tracking and resumption
- Error handling and reporting
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol

from api_vault.context_packager import build_base_context, build_full_context, package_context
from api_vault.schemas import (
    ArtifactMeta,
    JobResult,
    Plan,
    PlanJob,
    RepoIndex,
    RepoSignals,
    Report,
    ScanConfig,
)
from api_vault.templates import render_prompt

logger = logging.getLogger(__name__)


class GenerationClient(Protocol):
    """Protocol for generation clients."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        use_cache: bool,
    ) -> Any:
        ...

    def generate_with_cached_context(
        self,
        cached_context: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        use_local_cache: bool,
    ) -> Any:
        ...

    def get_usage_summary(self) -> dict[str, Any]:
        ...


def compute_context_hash(context: str) -> str:
    """Compute hash of context for caching."""
    return hashlib.sha256(context.encode()).hexdigest()[:16]


class Runner:
    """
    Executes artifact generation plans.
    """

    def __init__(
        self,
        output_dir: Path,
        client: GenerationClient,
        repo_path: Path,
        index: RepoIndex,
        signals: RepoSignals,
        config: ScanConfig | None = None,
    ):
        """
        Initialize the runner.

        Args:
            output_dir: Directory for output artifacts
            client: Generation client (Anthropic or mock)
            repo_path: Path to repository
            index: Repository index
            signals: Extracted signals
            config: Scan configuration
        """
        self.output_dir = output_dir
        self.client = client
        self.repo_path = repo_path
        self.index = index
        self.signals = signals
        self.config = config or ScanConfig()

        # Ensure output directories exist
        self.artifacts_dir = output_dir / "artifacts"
        self.cache_dir = output_dir / "cache"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Convert signals to dict for context packaging
        self.signals_dict = (
            signals.model_dump() if hasattr(signals, "model_dump") else signals.__dict__
        )

        # Build base context once for Anthropic prompt caching
        # This is shared across all artifact generations
        self.base_context, self.base_context_tokens = build_base_context(
            repo_path, index, self.signals_dict, config
        )
        logger.info(
            f"Built base context: ~{self.base_context_tokens} tokens "
            "(will be cached by Anthropic for subsequent requests)"
        )

    def _get_artifact_path(self, job: PlanJob) -> Path:
        """Get full path for artifact output."""
        return self.output_dir / job.output_path

    def _get_meta_path(self, job: PlanJob) -> Path:
        """Get full path for artifact metadata."""
        artifact_path = self._get_artifact_path(job)
        return artifact_path.with_suffix(".meta.json")

    def _should_skip_job(self, job: PlanJob) -> tuple[bool, str]:
        """
        Check if job should be skipped (already completed with same hash).

        Args:
            job: Job to check

        Returns:
            Tuple of (should_skip, reason)
        """
        meta_path = self._get_meta_path(job)
        if not meta_path.exists():
            return False, ""

        try:
            with open(meta_path) as f:
                meta = json.load(f)

            # Check if request hash matches (indicates same input)
            existing_hash = meta.get("request_hash", "")
            if existing_hash:
                # Build context to compare hashes
                context, _, _ = build_full_context(
                    self.repo_path,
                    self.index,
                    self.signals_dict,
                    job.context_refs,
                    self.config,
                )
                context_hash = compute_context_hash(context)

                if meta.get("context_hash") == context_hash:
                    return True, "Artifact exists with matching context"

            return False, ""

        except (json.JSONDecodeError, OSError):
            return False, ""

    def _execute_job(
        self,
        job: PlanJob,
        progress_callback: Callable[[str], None] | None = None,
    ) -> JobResult:
        """
        Execute a single job.

        Args:
            job: Job to execute
            progress_callback: Optional progress callback

        Returns:
            JobResult with execution outcome
        """
        if progress_callback:
            progress_callback(f"Executing: {job.artifact_name}")

        # Check if should skip
        should_skip, skip_reason = self._should_skip_job(job)
        if should_skip:
            logger.info(f"Skipping {job.artifact_name}: {skip_reason}")
            return JobResult(
                job_id=job.id,
                status="skipped",
                artifact_path=str(self._get_artifact_path(job)),
                meta_path=str(self._get_meta_path(job)),
            )

        # Build artifact-specific context (additional file excerpts beyond base)
        if progress_callback:
            progress_callback(f"Building context for: {job.artifact_name}")

        # Package artifact-specific file excerpts
        artifact_excerpts, files_used, excerpt_bytes = package_context(
            self.repo_path,
            self.index,
            job.context_refs,
            self.config,
        )

        # Combine base context with artifact-specific excerpts for hash
        full_context = self.base_context
        if artifact_excerpts:
            full_context += f"\n\n## Artifact-Specific Files\n\n{artifact_excerpts}"
        context_hash = compute_context_hash(full_context)

        # Get prompt template (pass artifact excerpts, not full context)
        prompt_result = render_prompt(job.prompt_template_id, artifact_excerpts or "No additional context files.")
        if prompt_result is None:
            logger.error(f"Unknown prompt template: {job.prompt_template_id}")
            return JobResult(
                job_id=job.id,
                status="failed",
                error_message=f"Unknown prompt template: {job.prompt_template_id}",
            )

        system_prompt, user_prompt = prompt_result

        # Generate artifact using Anthropic prompt caching
        # The base_context is cached server-side, saving ~90% on repeated input tokens
        if progress_callback:
            progress_callback(f"Generating: {job.artifact_name}")

        result = self.client.generate_with_cached_context(
            cached_context=self.base_context,
            system_prompt=system_prompt,
            user_prompt=user_prompt if not artifact_excerpts else f"{user_prompt}\n\n## Additional Context\n\n{artifact_excerpts}",
            max_tokens=job.max_output_tokens,
            temperature=0.0,
            use_local_cache=True,
        )

        if result.error:
            logger.error(f"Generation failed for {job.artifact_name}: {result.error}")
            return JobResult(
                job_id=job.id,
                status="failed",
                error_message=result.error,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                generation_time_seconds=result.generation_time_seconds,
            )

        # Write artifact
        artifact_path = self._get_artifact_path(job)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(result.text)

        # Write metadata
        meta = ArtifactMeta(
            artifact_id=str(uuid.uuid4()),
            job_id=job.id,
            family=job.family,
            artifact_name=job.artifact_name,
            output_path=job.output_path,
            generated_at=datetime.utcnow(),
            request_hash=result.request_hash,
            model_used=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            generation_time_seconds=result.generation_time_seconds,
            context_files_used=files_used,
            prompt_template_id=job.prompt_template_id,
        )

        # Add context hash to meta for skip detection
        meta_dict = meta.model_dump()
        meta_dict["context_hash"] = context_hash
        meta_dict["generated_at"] = meta_dict["generated_at"].isoformat()

        meta_path = self._get_meta_path(job)
        with open(meta_path, "w") as f:
            json.dump(meta_dict, f, indent=2, default=str)

        logger.info(
            f"Generated {job.artifact_name}: "
            f"{result.input_tokens} in, {result.output_tokens} out, "
            f"{result.generation_time_seconds:.2f}s"
        )

        return JobResult(
            job_id=job.id,
            status="completed",
            artifact_path=str(artifact_path),
            meta_path=str(meta_path),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            generation_time_seconds=result.generation_time_seconds,
            cached=result.cached,
        )

    def run(
        self,
        plan: Plan,
        progress_callback: Callable[[str], None] | None = None,
    ) -> Report:
        """
        Execute a complete plan.

        Args:
            plan: Plan to execute
            progress_callback: Optional progress callback

        Returns:
            Report with execution results
        """
        started_at = datetime.utcnow()
        report_id = str(uuid.uuid4())[:8]

        job_results: list[JobResult] = []
        artifacts_generated: list[str] = []
        errors: list[str] = []

        total_jobs = len(plan.jobs)

        for idx, job in enumerate(plan.jobs, 1):
            if progress_callback:
                progress_callback(f"Job {idx}/{total_jobs}: {job.artifact_name}")

            try:
                result = self._execute_job(job, progress_callback)
                job_results.append(result)

                if result.status == "completed" and result.artifact_path:
                    artifacts_generated.append(result.artifact_path)
                elif result.status == "failed" and result.error_message:
                    errors.append(f"{job.artifact_name}: {result.error_message}")

            except Exception as e:
                logger.exception(f"Unexpected error executing {job.artifact_name}")
                job_results.append(
                    JobResult(
                        job_id=job.id,
                        status="failed",
                        error_message=str(e),
                    )
                )
                errors.append(f"{job.artifact_name}: {str(e)}")

        completed_at = datetime.utcnow()

        # Count results
        completed = sum(1 for r in job_results if r.status == "completed")
        skipped = sum(1 for r in job_results if r.status == "skipped")
        failed = sum(1 for r in job_results if r.status == "failed")
        cached = sum(1 for r in job_results if r.cached)

        # Sum tokens and time
        total_input = sum(r.input_tokens for r in job_results)
        total_output = sum(r.output_tokens for r in job_results)
        total_time = sum(r.generation_time_seconds for r in job_results)

        report = Report(
            report_id=report_id,
            repo_path=plan.repo_path,
            repo_name=plan.repo_name,
            plan_id=plan.plan_id,
            started_at=started_at,
            completed_at=completed_at,
            total_jobs=total_jobs,
            jobs_completed=completed,
            jobs_skipped=skipped,
            jobs_failed=failed,
            jobs_cached=cached,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_generation_time_seconds=total_time,
            job_results=job_results,
            artifacts_generated=artifacts_generated,
            errors=errors,
        )

        # Write report
        report_path = self.output_dir / "report.json"
        with open(report_path, "w") as f:
            f.write(report.model_dump_json(indent=2))

        return report


def load_report(path: Path) -> Report:
    """
    Load report from JSON file.

    Args:
        path: Path to report.json

    Returns:
        Report object
    """
    with open(path) as f:
        data = json.load(f)
    return Report.model_validate(data)
