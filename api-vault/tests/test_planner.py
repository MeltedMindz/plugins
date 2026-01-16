"""Tests for planner."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from api_vault.planner import (
    ARTIFACT_TEMPLATES,
    check_prerequisites,
    compute_gap_weight,
    create_plan,
    generate_job_id,
    generate_plan_id,
    score_artifact,
)
from api_vault.repo_scanner import scan_repository
from api_vault.schemas import ArtifactFamily, RepoSignals
from api_vault.signal_extractor import extract_signals


@pytest.fixture
def sample_signals():
    """Create sample signals for testing."""
    return RepoSignals(
        repo_path="/test/repo",
        repo_name="test-repo",
        primary_language="Python",
        languages=[],
        frameworks=[],
        package_managers=["pip"],
        build_tools=[],
        has_api=True,
        has_web_ui=False,
        has_cli=True,
        has_database=True,
        has_auth=True,
        identified_gaps=[
            "No architecture documentation",
            "API exists but lacks documentation",
            "No SECURITY policy or vulnerability reporting process",
        ],
    )


@pytest.fixture
def sample_repo():
    """Create a sample repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "tests").mkdir()

        (root / "README.md").write_text("# Test")
        (root / "pyproject.toml").write_text('[project]\nname = "test"')
        (root / "src" / "main.py").write_text("print('hello')")
        (root / "src" / "api.py").write_text("from flask import Flask")
        (root / "tests" / "test_main.py").write_text("def test(): pass")

        yield root


class TestGeneratePlanId:
    """Tests for plan ID generation."""

    def test_deterministic(self):
        """Test that plan ID is deterministic."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0)
        id1 = generate_plan_id("/path/to/repo", timestamp)
        id2 = generate_plan_id("/path/to/repo", timestamp)

        assert id1 == id2

    def test_different_for_different_repos(self):
        """Test different repos get different IDs."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0)
        id1 = generate_plan_id("/path/to/repo1", timestamp)
        id2 = generate_plan_id("/path/to/repo2", timestamp)

        assert id1 != id2

    def test_format(self):
        """Test ID format."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0)
        plan_id = generate_plan_id("/path/to/repo", timestamp)

        assert len(plan_id) == 16
        assert all(c in "0123456789abcdef" for c in plan_id)


class TestGenerateJobId:
    """Tests for job ID generation."""

    def test_deterministic(self):
        """Test that job ID is deterministic."""
        id1 = generate_job_id("plan123", "RUNBOOK.md")
        id2 = generate_job_id("plan123", "RUNBOOK.md")

        assert id1 == id2

    def test_different_for_different_artifacts(self):
        """Test different artifacts get different IDs."""
        id1 = generate_job_id("plan123", "RUNBOOK.md")
        id2 = generate_job_id("plan123", "TROUBLESHOOTING.md")

        assert id1 != id2


class TestComputeGapWeight:
    """Tests for gap weight computation."""

    def test_high_weight_for_matched_gaps(self):
        """Test high weight when gaps match template."""
        template = ARTIFACT_TEMPLATES[0]  # RUNBOOK.md
        gaps = ["No architecture documentation", "README is minimal"]

        weight = compute_gap_weight(template, gaps)
        assert weight >= 7.0

    def test_default_weight_for_no_match(self):
        """Test default weight when no gaps match."""
        template = ARTIFACT_TEMPLATES[0]
        gaps = ["Some unrelated gap"]

        weight = compute_gap_weight(template, gaps)
        assert weight == 5.0


class TestCheckPrerequisites:
    """Tests for prerequisite checking."""

    def test_passes_when_no_prerequisites(self, sample_signals):
        """Test pass when no prerequisites required."""
        # RUNBOOK has no prerequisites
        runbook = next(t for t in ARTIFACT_TEMPLATES if t.name == "RUNBOOK.md")
        assert check_prerequisites(runbook, sample_signals) is True

    def test_passes_when_prerequisites_met(self, sample_signals):
        """Test pass when prerequisites are met."""
        # AUTHZ_AUTHN_NOTES requires has_auth
        auth_notes = next(t for t in ARTIFACT_TEMPLATES if t.name == "AUTHZ_AUTHN_NOTES.md")
        assert check_prerequisites(auth_notes, sample_signals) is True

    def test_fails_when_prerequisites_not_met(self, sample_signals):
        """Test fail when prerequisites not met."""
        sample_signals.has_auth = False
        auth_notes = next(t for t in ARTIFACT_TEMPLATES if t.name == "AUTHZ_AUTHN_NOTES.md")
        assert check_prerequisites(auth_notes, sample_signals) is False


class TestScoreArtifact:
    """Tests for artifact scoring."""

    def test_score_structure(self, sample_signals):
        """Test score breakdown structure."""
        template = ARTIFACT_TEMPLATES[0]
        score = score_artifact(template, sample_signals, 1000)

        assert score.reusability >= 0
        assert score.time_saved >= 0
        assert score.leverage >= 0
        assert score.context_cost >= 0
        assert score.gap_weight >= 0
        assert score.total_score > 0

    def test_higher_context_cost_for_more_tokens(self, sample_signals):
        """Test that more context tokens increases cost."""
        template = ARTIFACT_TEMPLATES[0]
        score_small = score_artifact(template, sample_signals, 100)
        score_large = score_artifact(template, sample_signals, 10000)

        assert score_large.context_cost > score_small.context_cost


class TestCreatePlan:
    """Tests for plan creation."""

    def test_creates_plan(self, sample_repo):
        """Test basic plan creation."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
        )

        assert plan.plan_id is not None
        assert len(plan.jobs) > 0
        assert plan.total_estimated_tokens > 0

    def test_respects_budget(self, sample_repo):
        """Test that plan respects token budget."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=10000,  # Small budget
            budget_seconds=3600,
        )

        assert plan.total_estimated_tokens <= 10000

    def test_filters_by_family(self, sample_repo):
        """Test filtering by artifact family."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=100000,
            budget_seconds=3600,
            families=[ArtifactFamily.DOCS],
        )

        # All jobs should be in docs family
        assert all(job.family == ArtifactFamily.DOCS for job in plan.jobs)

    def test_excludes_jobs_over_budget(self, sample_repo):
        """Test that jobs over budget are excluded."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=5000,  # Very small
            budget_seconds=3600,
        )

        # Should have excluded jobs
        if len(ARTIFACT_TEMPLATES) > len(plan.jobs):
            assert len(plan.excluded_jobs) > 0

    def test_deterministic_ordering(self, sample_repo):
        """Test that plan creation is deterministic."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan1 = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
        )

        plan2 = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
        )

        # Job ordering should be the same
        assert [j.artifact_name for j in plan1.jobs] == [j.artifact_name for j in plan2.jobs]

    def test_jobs_have_context_refs(self, sample_repo):
        """Test that jobs have context references."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
        )

        # At least some jobs should have context refs
        jobs_with_refs = [j for j in plan.jobs if len(j.context_refs) > 0]
        assert len(jobs_with_refs) > 0

    def test_jobs_have_reasons(self, sample_repo):
        """Test that jobs have selection reasons."""
        index = scan_repository(sample_repo)
        signals = extract_signals(index, sample_repo)

        plan = create_plan(
            index=index,
            signals=signals,
            budget_tokens=50000,
            budget_seconds=3600,
        )

        for job in plan.jobs:
            assert job.reason is not None
            assert len(job.reason) > 0
