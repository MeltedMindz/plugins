"""
Deterministic planner for artifact selection.

Scores candidate artifacts based on multiple factors and selects
the optimal set within budget constraints.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from api_vault.context_packager import estimate_tokens, select_context_refs_for_artifact
from api_vault.schemas import (
    ArtifactFamily,
    ContextRef,
    Plan,
    PlanJob,
    RepoIndex,
    RepoSignals,
    ScoreBreakdown,
)


@dataclass
class ArtifactTemplate:
    """Definition of an artifact that can be generated."""

    name: str
    family: ArtifactFamily
    output_filename: str
    prompt_template_id: str
    description: str
    base_reusability: float = 5.0
    base_time_saved: float = 5.0
    base_leverage: float = 5.0
    base_context_cost: float = 5.0
    max_output_tokens: int = 4096
    required_signals: list[str] = field(default_factory=list)
    boosted_by_gaps: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)


# Define all artifact templates
ARTIFACT_TEMPLATES: list[ArtifactTemplate] = [
    # Documentation family
    ArtifactTemplate(
        name="RUNBOOK.md",
        family=ArtifactFamily.DOCS,
        output_filename="RUNBOOK.md",
        prompt_template_id="runbook",
        description="Step-by-step guide for running, building, and testing the project",
        base_reusability=8.0,
        base_time_saved=7.0,
        base_leverage=7.0,
        base_context_cost=4.0,
        boosted_by_gaps=["README is minimal and could be expanded", "No architecture documentation"],
    ),
    ArtifactTemplate(
        name="TROUBLESHOOTING.md",
        family=ArtifactFamily.DOCS,
        output_filename="TROUBLESHOOTING.md",
        prompt_template_id="troubleshooting",
        description="Common issues, error messages, and their solutions",
        base_reusability=7.0,
        base_time_saved=8.0,
        base_leverage=6.0,
        base_context_cost=5.0,
        boosted_by_gaps=["No CONTRIBUTING guide for new contributors"],
    ),
    ArtifactTemplate(
        name="ARCHITECTURE_OVERVIEW.md",
        family=ArtifactFamily.DOCS,
        output_filename="ARCHITECTURE_OVERVIEW.md",
        prompt_template_id="architecture",
        description="High-level system architecture and component relationships",
        base_reusability=9.0,
        base_time_saved=6.0,
        base_leverage=8.0,
        base_context_cost=6.0,
        max_output_tokens=8192,
        boosted_by_gaps=["No architecture documentation"],
    ),
    # Security family
    ArtifactTemplate(
        name="THREAT_MODEL.md",
        family=ArtifactFamily.SECURITY,
        output_filename="THREAT_MODEL.md",
        prompt_template_id="threat_model",
        description="Security threat analysis using STRIDE methodology",
        base_reusability=7.0,
        base_time_saved=9.0,
        base_leverage=8.0,
        base_context_cost=6.0,
        max_output_tokens=8192,
        boosted_by_gaps=[
            "No SECURITY policy or vulnerability reporting process",
            "Authentication present but security documentation may be lacking",
        ],
    ),
    ArtifactTemplate(
        name="SECURITY_CHECKLIST.md",
        family=ArtifactFamily.SECURITY,
        output_filename="SECURITY_CHECKLIST.md",
        prompt_template_id="security_checklist",
        description="Security audit checklist tailored to the project stack",
        base_reusability=8.0,
        base_time_saved=7.0,
        base_leverage=7.0,
        base_context_cost=4.0,
        boosted_by_gaps=["No SECURITY policy or vulnerability reporting process"],
    ),
    ArtifactTemplate(
        name="AUTHZ_AUTHN_NOTES.md",
        family=ArtifactFamily.SECURITY,
        output_filename="AUTHZ_AUTHN_NOTES.md",
        prompt_template_id="auth_notes",
        description="Documentation of authentication and authorization flows",
        base_reusability=7.0,
        base_time_saved=8.0,
        base_leverage=7.0,
        base_context_cost=5.0,
        required_signals=["has_auth"],
        boosted_by_gaps=["Authentication present but security documentation may be lacking"],
    ),
    # Testing family
    ArtifactTemplate(
        name="GOLDEN_PATH_TEST_PLAN.md",
        family=ArtifactFamily.TESTS,
        output_filename="GOLDEN_PATH_TEST_PLAN.md",
        prompt_template_id="golden_path_tests",
        description="Test plan covering critical user journeys and happy paths",
        base_reusability=7.0,
        base_time_saved=8.0,
        base_leverage=8.0,
        base_context_cost=6.0,
        max_output_tokens=8192,
        boosted_by_gaps=["Limited test coverage", "No test directory found"],
    ),
    ArtifactTemplate(
        name="MINIMUM_TESTS_SUGGESTION.md",
        family=ArtifactFamily.TESTS,
        output_filename="MINIMUM_TESTS_SUGGESTION.md",
        prompt_template_id="minimum_tests",
        description="Suggestions for minimum viable test coverage",
        base_reusability=6.0,
        base_time_saved=7.0,
        base_leverage=7.0,
        base_context_cost=5.0,
        boosted_by_gaps=["Limited test coverage", "No test framework configured"],
    ),
    # API family
    ArtifactTemplate(
        name="ENDPOINT_INVENTORY.md",
        family=ArtifactFamily.API,
        output_filename="ENDPOINT_INVENTORY.md",
        prompt_template_id="endpoint_inventory",
        description="Comprehensive inventory of API endpoints with request/response details",
        base_reusability=8.0,
        base_time_saved=7.0,
        base_leverage=7.0,
        base_context_cost=5.0,
        required_signals=["has_api"],
        boosted_by_gaps=["API exists but lacks documentation"],
    ),
    ArtifactTemplate(
        name="openapi_draft.json",
        family=ArtifactFamily.API,
        output_filename="openapi_draft.json",
        prompt_template_id="openapi_draft",
        description="Draft OpenAPI 3.0 specification based on detected endpoints",
        base_reusability=9.0,
        base_time_saved=8.0,
        base_leverage=8.0,
        base_context_cost=7.0,
        max_output_tokens=16384,
        required_signals=["has_api"],
        boosted_by_gaps=["API exists but lacks documentation"],
    ),
    # Observability family
    ArtifactTemplate(
        name="LOGGING_CONVENTIONS.md",
        family=ArtifactFamily.OBSERVABILITY,
        output_filename="LOGGING_CONVENTIONS.md",
        prompt_template_id="logging_conventions",
        description="Standardized logging conventions and structured logging guide",
        base_reusability=7.0,
        base_time_saved=6.0,
        base_leverage=6.0,
        base_context_cost=4.0,
    ),
    ArtifactTemplate(
        name="METRICS_PLAN.md",
        family=ArtifactFamily.OBSERVABILITY,
        output_filename="METRICS_PLAN.md",
        prompt_template_id="metrics_plan",
        description="Metrics and monitoring strategy with recommended instruments",
        base_reusability=7.0,
        base_time_saved=7.0,
        base_leverage=7.0,
        base_context_cost=5.0,
    ),
    # Product family
    ArtifactTemplate(
        name="UX_COPY_BANK.md",
        family=ArtifactFamily.PRODUCT,
        output_filename="UX_COPY_BANK.md",
        prompt_template_id="ux_copy_bank",
        description="Collection of UI copy, error messages, and microcopy guidelines",
        base_reusability=6.0,
        base_time_saved=5.0,
        base_leverage=5.0,
        base_context_cost=4.0,
        required_signals=["has_web_ui"],
    ),
]


def compute_gap_weight(template: ArtifactTemplate, gaps: list[str]) -> float:
    """
    Compute how much a repo needs this artifact based on gaps.

    Args:
        template: Artifact template
        gaps: List of identified gaps

    Returns:
        Gap weight score (0-10)
    """
    if not template.boosted_by_gaps:
        return 5.0  # Default neutral weight

    matched_gaps = sum(1 for gap in gaps if any(bg.lower() in gap.lower() for bg in template.boosted_by_gaps))

    # More matched gaps = higher weight
    if matched_gaps >= 3:
        return 10.0
    elif matched_gaps == 2:
        return 8.0
    elif matched_gaps == 1:
        return 7.0
    else:
        return 5.0


def check_prerequisites(template: ArtifactTemplate, signals: RepoSignals) -> bool:
    """
    Check if artifact prerequisites are met.

    Args:
        template: Artifact template
        signals: Repository signals

    Returns:
        True if prerequisites are met
    """
    if not template.required_signals:
        return True

    signals_dict = signals.model_dump() if hasattr(signals, "model_dump") else signals.__dict__

    for signal in template.required_signals:
        if not signals_dict.get(signal, False):
            return False

    return True


def score_artifact(
    template: ArtifactTemplate,
    signals: RepoSignals,
    estimated_context_tokens: int,
) -> ScoreBreakdown:
    """
    Score an artifact candidate.

    Args:
        template: Artifact template
        signals: Repository signals
        estimated_context_tokens: Estimated tokens needed for context

    Returns:
        ScoreBreakdown with all scores
    """
    gaps = signals.identified_gaps if hasattr(signals, "identified_gaps") else []

    # Calculate context cost based on estimated tokens
    # Lower context cost is better (inverse relationship)
    context_cost = min(template.base_context_cost + (estimated_context_tokens / 2000), 10.0)

    gap_weight = compute_gap_weight(template, gaps)

    breakdown = ScoreBreakdown(
        reusability=template.base_reusability,
        time_saved=template.base_time_saved,
        leverage=template.base_leverage,
        context_cost=context_cost,
        gap_weight=gap_weight,
        total_score=0.0,  # Will be computed
    )

    # Compute total score
    breakdown.total_score = breakdown.compute_total()

    return breakdown


def generate_plan_id(repo_path: str, timestamp: datetime) -> str:
    """Generate deterministic plan ID."""
    data = f"{repo_path}:{timestamp.isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def generate_job_id(plan_id: str, artifact_name: str) -> str:
    """Generate deterministic job ID."""
    data = f"{plan_id}:{artifact_name}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def create_plan(
    index: RepoIndex,
    signals: RepoSignals,
    budget_tokens: int,
    budget_seconds: int,
    families: list[ArtifactFamily] | None = None,
) -> Plan:
    """
    Create an artifact generation plan.

    Args:
        index: Repository index
        signals: Extracted signals
        budget_tokens: Token budget
        budget_seconds: Time budget (seconds)
        families: Artifact families to include (None = all)

    Returns:
        Plan with selected jobs
    """
    if families is None:
        families = list(ArtifactFamily)

    timestamp = datetime.utcnow()
    plan_id = generate_plan_id(index.repo_path, timestamp)

    # Score all candidate artifacts
    candidates: list[tuple[ArtifactTemplate, ScoreBreakdown, list[ContextRef], int]] = []

    signals_dict = signals.model_dump() if hasattr(signals, "model_dump") else {}

    for template in ARTIFACT_TEMPLATES:
        # Filter by family
        if template.family not in families:
            continue

        # Check prerequisites
        if not check_prerequisites(template, signals):
            continue

        # Select context references
        context_refs = select_context_refs_for_artifact(
            template.name,
            template.family.value,
            index,
            signals_dict,
        )

        # Estimate context tokens (rough estimate)
        estimated_context_tokens = sum(
            min(ref.max_bytes, 4096) // 4 for ref in context_refs
        )

        # Score the artifact
        score = score_artifact(template, signals, estimated_context_tokens)

        candidates.append((template, score, context_refs, estimated_context_tokens))

    # Sort by total score (descending)
    candidates.sort(key=lambda x: x[1].total_score, reverse=True)

    # Select jobs within budget
    jobs: list[PlanJob] = []
    excluded_jobs: list[dict[str, Any]] = []
    total_estimated_tokens = 0

    # Estimate tokens per job: context + output + overhead
    OVERHEAD_TOKENS = 500  # System prompt, formatting, etc.

    for template, score, context_refs, est_context_tokens in candidates:
        job_tokens = est_context_tokens + template.max_output_tokens + OVERHEAD_TOKENS

        if total_estimated_tokens + job_tokens <= budget_tokens:
            job = PlanJob(
                id=generate_job_id(plan_id, template.name),
                family=template.family,
                artifact_name=template.name,
                output_path=f"artifacts/{template.family.value}/{template.output_filename}",
                prompt_template_id=template.prompt_template_id,
                max_output_tokens=template.max_output_tokens,
                context_refs=context_refs,
                score_breakdown=score,
                reason=_generate_reason(template, score, signals),
                estimated_input_tokens=est_context_tokens + OVERHEAD_TOKENS,
            )
            jobs.append(job)
            total_estimated_tokens += job_tokens
        else:
            excluded_jobs.append({
                "artifact_name": template.name,
                "family": template.family.value,
                "score": score.total_score,
                "estimated_tokens": job_tokens,
                "reason": "Exceeded token budget",
            })

    return Plan(
        plan_id=plan_id,
        repo_path=index.repo_path,
        repo_name=index.repo_name,
        created_at=timestamp,
        budget_tokens=budget_tokens,
        budget_seconds=budget_seconds,
        families_requested=families,
        jobs=jobs,
        total_estimated_tokens=total_estimated_tokens,
        jobs_within_budget=len(jobs),
        excluded_jobs=excluded_jobs,
    )


def _generate_reason(
    template: ArtifactTemplate,
    score: ScoreBreakdown,
    signals: RepoSignals,
) -> str:
    """
    Generate a human-readable reason for selecting an artifact.

    Args:
        template: Artifact template
        score: Score breakdown
        signals: Repository signals

    Returns:
        Reason string
    """
    reasons: list[str] = []

    # Primary reason based on highest scoring factor
    factors = [
        ("high reusability", score.reusability),
        ("significant time savings", score.time_saved),
        ("high leverage impact", score.leverage),
        ("addresses identified gaps", score.gap_weight),
    ]
    top_factor = max(factors, key=lambda x: x[1])
    reasons.append(f"Selected for {top_factor[0]} (score: {top_factor[1]:.1f})")

    # Gap-specific reasons
    if hasattr(signals, "identified_gaps") and template.boosted_by_gaps:
        matched = [g for g in signals.identified_gaps if any(bg.lower() in g.lower() for bg in template.boosted_by_gaps)]
        if matched:
            reasons.append(f"Addresses: {matched[0]}")

    # Prerequisite context
    if template.required_signals:
        sig_names = ", ".join(template.required_signals)
        reasons.append(f"Applicable because project has: {sig_names.replace('_', ' ')}")

    return "; ".join(reasons)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    """
    Convert plan to serializable dictionary.

    Args:
        plan: Plan object

    Returns:
        Dictionary representation
    """
    return json.loads(plan.model_dump_json())


def load_plan(path: Path) -> Plan:
    """
    Load plan from JSON file.

    Args:
        path: Path to plan.json

    Returns:
        Plan object
    """
    with open(path) as f:
        data = json.load(f)
    return Plan.model_validate(data)
