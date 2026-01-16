"""Tests for runner with mocked Anthropic client."""

import tempfile
from pathlib import Path

import pytest

from api_vault.anthropic_client import MockAnthropicClient
from api_vault.planner import create_plan
from api_vault.repo_scanner import scan_repository
from api_vault.runner import Runner
from api_vault.schemas import ArtifactFamily
from api_vault.signal_extractor import extract_signals


@pytest.fixture
def sample_repo():
    """Create a sample repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create structure
        (root / "src").mkdir()
        (root / "tests").mkdir()

        # Create files
        (root / "README.md").write_text("# Test Project\n\nA test project for api-vault.")
        (root / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "1.0.0"
dependencies = ["fastapi", "sqlalchemy"]
""")
        (root / "src" / "__init__.py").write_text("")
        (root / "src" / "main.py").write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello"}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"user_id": user_id}
""")
        (root / "tests" / "test_main.py").write_text("""
def test_example():
    assert True
""")

        yield root


@pytest.fixture
def output_dir():
    """Create output directory for test artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestRunner:
    """Tests for the Runner class."""

    def test_executes_plan(self, sample_repo, output_dir):
        """Test that runner executes a plan successfully."""
        # Scan and create plan
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],  # Just docs for speed
        )

        # Create mock client
        client = MockAnthropicClient()

        # Run
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        report = runner.run(plan)

        # Verify
        assert report.total_jobs > 0
        assert report.jobs_completed > 0
        assert len(report.artifacts_generated) > 0

    def test_creates_artifact_files(self, sample_repo, output_dir):
        """Test that artifact files are created."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        report = runner.run(plan)

        # Check files exist
        for artifact_path in report.artifacts_generated:
            assert Path(artifact_path).exists()

    def test_creates_metadata_files(self, sample_repo, output_dir):
        """Test that metadata files are created."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        report = runner.run(plan)

        # Check that metadata files exist alongside artifacts
        for artifact_path in report.artifacts_generated:
            meta_path = Path(artifact_path).with_suffix(".meta.json")
            assert meta_path.exists()

    def test_skips_existing_artifacts(self, sample_repo, output_dir):
        """Test that runner skips existing artifacts with same context."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        # Run twice
        report1 = runner.run(plan)
        report2 = runner.run(plan)

        # Second run should skip all
        assert report2.jobs_skipped == report2.total_jobs

    def test_tracks_token_usage(self, sample_repo, output_dir):
        """Test that token usage is tracked."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        report = runner.run(plan)

        assert report.total_input_tokens > 0
        assert report.total_output_tokens > 0

    def test_writes_report_file(self, sample_repo, output_dir):
        """Test that report file is written."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        runner.run(plan)

        report_path = output_dir / "report.json"
        assert report_path.exists()

    def test_handles_all_families(self, sample_repo, output_dir):
        """Test running with all artifact families."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)
        signals.has_api = True
        signals.has_auth = True

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=100000,
            budget_seconds=3600,
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        report = runner.run(plan)

        # Should have jobs from multiple families
        families_used = set()
        for result in report.job_results:
            job = next((j for j in plan.jobs if j.id == result.job_id), None)
            if job:
                families_used.add(job.family.value)

        assert len(families_used) >= 2

    def test_progress_callback(self, sample_repo, output_dir):
        """Test that progress callback is called."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        client = MockAnthropicClient()
        runner = Runner(
            output_dir=output_dir,
            client=client,
            repo_path=sample_repo,
            index=index,
            signals=signals,
        )

        progress_messages = []

        def callback(msg: str) -> None:
            progress_messages.append(msg)

        runner.run(plan, callback)

        assert len(progress_messages) > 0
