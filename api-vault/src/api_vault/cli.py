"""
Command-line interface for Api Vault.

Provides commands for:
- scan: Scan repository and extract signals
- plan: Create artifact generation plan
- run: Execute plan and generate artifacts
- report: View execution report
- estimate: Estimate costs before running
- init: Interactive setup wizard
- config: Manage configuration
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.tree import Tree

from api_vault import __version__
from api_vault.anthropic_client import AnthropicClient, MockAnthropicClient
from api_vault.config import (
    ApiVaultConfig,
    generate_default_config,
    load_config,
    save_default_config,
)
from api_vault.errors import ConfigError, ApiVaultError
from api_vault.planner import create_plan, load_plan
from api_vault.repo_scanner import scan_repository
from api_vault.runner import Runner, load_report
from api_vault.schemas import ArtifactFamily, RepoIndex, RepoSignals, ScanConfig
from api_vault.signal_extractor import extract_signals

# Configure logging
logging.basicConfig(
    level=logging.INFO if not os.environ.get("API_VAULT_DEBUG") else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# CLI app
app = typer.Typer(
    name="api-vault",
    help="Convert expiring API quota into durable local artifacts",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# Global config (loaded once)
_config: ApiVaultConfig | None = None


def get_config(config_path: Path | None = None) -> ApiVaultConfig:
    """Get or load configuration."""
    global _config
    if _config is None:
        try:
            _config = load_config(config_path)
        except ConfigError as e:
            console.print(f"[yellow]Warning:[/yellow] {e.message}")
            _config = ApiVaultConfig.default()
    return _config


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold]api-vault[/bold] version {__version__}")
        raise typer.Exit()


def completion_callback(value: bool) -> None:
    """Generate shell completion script."""
    if value:
        import subprocess
        shell = os.environ.get("SHELL", "/bin/bash")
        if "zsh" in shell:
            script = subprocess.run(
                [sys.executable, "-m", "typer", "api_vault.cli", "utils", "complete", "zsh"],
                capture_output=True, text=True
            ).stdout
            console.print("# Add this to ~/.zshrc:")
            console.print(script)
        elif "fish" in shell:
            console.print("# Fish completion not yet supported")
        else:
            script = subprocess.run(
                [sys.executable, "-m", "typer", "api_vault.cli", "utils", "complete", "bash"],
                capture_output=True, text=True
            ).stdout
            console.print("# Add this to ~/.bashrc:")
            console.print(script)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True,
                     help="Show version and exit"),
    ] = None,
    config: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="Path to configuration file"),
    ] = None,
    completion: Annotated[
        Optional[bool],
        typer.Option("--completion", callback=completion_callback, is_eager=True,
                     help="Generate shell completion script"),
    ] = None,
) -> None:
    """Api Vault - Convert API quota into durable artifacts."""
    if config:
        get_config(config)


@app.command()
def scan(
    repo: Annotated[Path, typer.Option("--repo", "-r", help="Path to repository")] = Path("."),
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("./api-vault-output"),
    max_file_size: Annotated[Optional[int], typer.Option(help="Max file size in bytes")] = None,
    safe_mode: Annotated[bool, typer.Option("--safe-mode", help="Don't read file contents")] = False,
) -> None:
    """
    Scan repository and extract signals.

    Builds a file index, detects languages/frameworks, and identifies gaps.
    """
    cfg = get_config()
    repo = repo.resolve()
    out = out.resolve()

    if not repo.exists():
        console.print(f"[red]Error:[/red] Repository path does not exist: {repo}")
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)

    config = ScanConfig(
        max_file_size_bytes=max_file_size or cfg.scan.max_file_size_bytes,
        safe_mode=safe_mode or cfg.scan.safe_mode,
    )

    console.print(Panel(f"[bold]Scanning repository:[/bold] {repo}", title="Api Vault"))

    # Scan repository with enhanced progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning files...", total=None)
        file_count = 0

        def scan_progress(current: int, total: int, path: str) -> None:
            nonlocal file_count
            file_count = current
            progress.update(task, description=f"[bold blue]Scanned {current} files[/bold blue]")

        index = scan_repository(repo, config, scan_progress)

        progress.update(task, description="[bold green]Extracting signals...[/bold green]")
        signals = extract_signals(index, repo)

    # Save results
    index_path = out / "repo_index.json"
    with open(index_path, "w") as f:
        f.write(index.model_dump_json(indent=2))

    signals_path = out / "signals.json"
    with open(signals_path, "w") as f:
        f.write(signals.model_dump_json(indent=2))

    # Display results
    console.print()
    console.print(f"[green]✓[/green] Scanned [bold]{index.total_files}[/bold] files")
    console.print(f"[green]✓[/green] Total size: [bold]{index.total_size_bytes:,}[/bold] bytes")

    if signals.primary_language:
        console.print(f"[green]✓[/green] Primary language: [bold]{signals.primary_language}[/bold]")

    if signals.frameworks:
        frameworks = [f.name for f in signals.frameworks[:5]]
        console.print(f"[green]✓[/green] Detected frameworks: [bold]{', '.join(frameworks)}[/bold]")

    if signals.identified_gaps:
        console.print()
        console.print("[yellow]Identified gaps:[/yellow]")
        for gap in signals.identified_gaps[:5]:
            console.print(f"  • {gap}")

    console.print()
    console.print(f"[dim]Results saved to:[/dim] {out}")


@app.command()
def plan(
    repo: Annotated[Path, typer.Option("--repo", "-r", help="Path to repository")] = Path("."),
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("./api-vault-output"),
    budget_tokens: Annotated[Optional[int], typer.Option("--budget-tokens", "-t", help="Token budget")] = None,
    budget_seconds: Annotated[Optional[int], typer.Option("--budget-seconds", "-s", help="Time budget in seconds")] = None,
    families: Annotated[
        Optional[str],
        typer.Option("--families", "-f", help="Comma-separated families: docs,security,tests,api,observability,product"),
    ] = None,
) -> None:
    """
    Create artifact generation plan.

    Uses repo scan to select optimal artifacts within budget.
    """
    cfg = get_config()
    repo = repo.resolve()
    out = out.resolve()

    # Use config defaults if not specified
    budget_tokens = budget_tokens or cfg.plan.default_budget_tokens
    budget_seconds = budget_seconds or cfg.plan.default_budget_seconds

    # Load existing scan results or scan
    index_path = out / "repo_index.json"
    signals_path = out / "signals.json"

    if not index_path.exists() or not signals_path.exists():
        console.print("[yellow]No scan results found. Running scan first...[/yellow]")
        console.print()

        config = ScanConfig(
            max_file_size_bytes=cfg.scan.max_file_size_bytes,
            safe_mode=cfg.scan.safe_mode,
        )
        out.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning...", total=None)
            index = scan_repository(repo, config)
            progress.update(task, description="[bold green]Extracting signals...[/bold green]")
            signals = extract_signals(index, repo)

        with open(index_path, "w") as f:
            f.write(index.model_dump_json(indent=2))
        with open(signals_path, "w") as f:
            f.write(signals.model_dump_json(indent=2))
    else:
        with open(index_path) as f:
            index = RepoIndex.model_validate_json(f.read())
        with open(signals_path) as f:
            signals = RepoSignals.model_validate_json(f.read())

    # Parse families
    family_list: list[ArtifactFamily] | None = None
    if families:
        family_list = []
        for name in families.split(","):
            name = name.strip().lower()
            try:
                family_list.append(ArtifactFamily(name))
            except ValueError:
                console.print(f"[red]Error:[/red] Unknown family: {name}")
                console.print(f"Valid families: {', '.join(f.value for f in ArtifactFamily)}")
                raise typer.Exit(1)
    else:
        family_list = cfg.get_families()

    console.print(Panel(
        f"[bold]Creating plan for:[/bold] {repo.name}\n"
        f"Token budget: {budget_tokens:,}\n"
        f"Time budget: {budget_seconds}s\n"
        f"Families: {', '.join(f.value for f in family_list)}",
        title="Api Vault",
    ))

    # Create plan
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating plan...", total=None)
        plan_obj = create_plan(
            index=index,
            signals=signals,
            budget_tokens=budget_tokens,
            budget_seconds=budget_seconds,
            families=family_list,
        )

    # Save plan
    plan_path = out / "plan.json"
    with open(plan_path, "w") as f:
        f.write(plan_obj.model_dump_json(indent=2))

    # Display plan
    console.print()
    console.print(f"[green]✓[/green] Created plan with [bold]{len(plan_obj.jobs)}[/bold] jobs")
    console.print(f"[green]✓[/green] Estimated tokens: [bold]{plan_obj.total_estimated_tokens:,}[/bold]")

    if plan_obj.jobs:
        console.print()
        table = Table(title="Planned Artifacts")
        table.add_column("Family", style="cyan")
        table.add_column("Artifact", style="green")
        table.add_column("Score", justify="right")
        table.add_column("Tokens", justify="right")

        for job in plan_obj.jobs:
            table.add_row(
                job.family.value,
                job.artifact_name,
                f"{job.score_breakdown.total_score:.1f}",
                f"{job.estimated_input_tokens + job.max_output_tokens:,}",
            )

        console.print(table)

    if plan_obj.excluded_jobs:
        console.print()
        console.print(f"[yellow]Excluded {len(plan_obj.excluded_jobs)} jobs due to budget constraints[/yellow]")

    console.print()
    console.print(f"[dim]Plan saved to:[/dim] {plan_path}")


@app.command()
def estimate(
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory with plan.json")] = Path("./api-vault-output"),
    model: Annotated[str, typer.Option("--model", "-m", help="Model for pricing")] = "claude-sonnet-4-20250514",
) -> None:
    """
    Estimate API costs for a plan.

    Shows token counts and estimated costs before running.
    """
    out = out.resolve()
    plan_path = out / "plan.json"

    if not plan_path.exists():
        console.print(f"[red]Error:[/red] Plan not found: {plan_path}")
        console.print("[dim]Run 'api-vault plan' first to create a plan.[/dim]")
        raise typer.Exit(1)

    plan_obj = load_plan(plan_path)

    # Pricing (approximate, as of 2024)
    # Claude Sonnet: $3 / 1M input, $15 / 1M output
    # Claude Opus: $15 / 1M input, $75 / 1M output
    # Claude Haiku: $0.25 / 1M input, $1.25 / 1M output
    pricing = {
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    prices = pricing.get(model, pricing["claude-sonnet-4-20250514"])

    console.print(Panel(
        f"[bold]Cost Estimate[/bold]\n"
        f"Plan: {plan_obj.plan_id}\n"
        f"Model: {model}",
        title="Api Vault",
    ))

    # Calculate totals
    total_input = 0
    total_output = 0

    table = Table(title="Job Estimates")
    table.add_column("Artifact", style="cyan")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Est. Cost", justify="right", style="green")

    for job in plan_obj.jobs:
        input_tokens = job.estimated_input_tokens
        output_tokens = job.max_output_tokens
        cost = (input_tokens * prices["input"] / 1_000_000) + (output_tokens * prices["output"] / 1_000_000)

        total_input += input_tokens
        total_output += output_tokens

        table.add_row(
            job.artifact_name,
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            f"${cost:.4f}",
        )

    console.print(table)

    # Totals
    total_cost = (total_input * prices["input"] / 1_000_000) + (total_output * prices["output"] / 1_000_000)

    console.print()
    console.print("[bold]Summary[/bold]")
    console.print(f"  Total input tokens:  {total_input:>12,}")
    console.print(f"  Total output tokens: {total_output:>12,}")
    console.print(f"  [bold]Estimated cost:    ${total_cost:>11.4f}[/bold]")

    console.print()
    console.print("[dim]Note: Actual costs may vary. Cached requests are free.[/dim]")
    console.print("[dim]Use --dry-run to test without API calls.[/dim]")


@app.command()
def run(
    repo: Annotated[Path, typer.Option("--repo", "-r", help="Path to repository")] = Path("."),
    plan_file: Annotated[
        Optional[Path],
        typer.Option("--plan", "-p", help="Path to plan.json"),
    ] = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("./api-vault-output"),
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Anthropic model to use")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Use mock client, no API calls")] = False,
) -> None:
    """
    Execute plan and generate artifacts.

    Calls Anthropic API to generate artifacts specified in plan.
    """
    cfg = get_config()
    repo = repo.resolve()
    out = out.resolve()

    model = model or cfg.run.model

    # Determine plan path
    if plan_file:
        plan_path = plan_file.resolve()
    else:
        plan_path = out / "plan.json"

    if not plan_path.exists():
        console.print(f"[red]Error:[/red] Plan file not found: {plan_path}")
        console.print("[dim]Run 'api-vault plan' first to create a plan.[/dim]")
        raise typer.Exit(1)

    # Load plan
    plan_obj = load_plan(plan_path)

    # Load index and signals
    index_path = out / "repo_index.json"
    signals_path = out / "signals.json"

    if not index_path.exists() or not signals_path.exists():
        console.print("[red]Error:[/red] Scan results not found. Run 'api-vault scan' first.")
        raise typer.Exit(1)

    with open(index_path) as f:
        index = RepoIndex.model_validate_json(f.read())
    with open(signals_path) as f:
        signals = RepoSignals.model_validate_json(f.read())

    # Check API key
    if not dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY environment variable not set.")
        console.print("[dim]Set it or use --dry-run for testing.[/dim]")
        raise typer.Exit(1)

    # Create client
    if dry_run:
        console.print("[yellow]Running in dry-run mode (no API calls)[/yellow]")
        client = MockAnthropicClient(model=model)
    else:
        client = AnthropicClient(
            cache_dir=out / "cache" if cfg.run.cache_enabled else None,
            model=model,
        )

    console.print(Panel(
        f"[bold]Executing plan:[/bold] {plan_obj.plan_id}\n"
        f"Jobs: {len(plan_obj.jobs)}\n"
        f"Model: {model}",
        title="Api Vault",
    ))

    # Run plan with enhanced progress
    runner = Runner(
        output_dir=out,
        client=client,
        repo_path=repo,
        index=index,
        signals=signals,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("[dim]{task.fields[tokens]} tokens[/dim]"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Generating artifacts...",
            total=len(plan_obj.jobs),
            tokens=0,
        )
        tokens_used = 0

        def run_progress(msg: str, job_tokens: int = 0) -> None:
            nonlocal tokens_used
            tokens_used += job_tokens
            progress.update(task, description=f"[bold blue]{msg}[/bold blue]", tokens=tokens_used)
            progress.advance(task)

        report = runner.run(plan_obj, run_progress)

    # Display results
    console.print()
    console.print(f"[green]✓[/green] Completed: [bold]{report.jobs_completed}[/bold]")
    console.print(f"[cyan]○[/cyan] Skipped: [bold]{report.jobs_skipped}[/bold]")
    console.print(f"[red]✗[/red] Failed: [bold]{report.jobs_failed}[/bold]")

    if report.jobs_cached > 0:
        console.print(f"[dim]Cached: {report.jobs_cached}[/dim]")

    console.print()
    console.print(f"[bold]Token usage:[/bold]")
    console.print(f"  Input: {report.total_input_tokens:,}")
    console.print(f"  Output: {report.total_output_tokens:,}")
    console.print(f"  Total: {report.total_input_tokens + report.total_output_tokens:,}")

    if report.artifacts_generated:
        console.print()
        console.print("[bold]Generated artifacts:[/bold]")
        for artifact in report.artifacts_generated[:10]:
            console.print(f"  • {Path(artifact).relative_to(out) if out in Path(artifact).parents else artifact}")
        if len(report.artifacts_generated) > 10:
            console.print(f"  ... and {len(report.artifacts_generated) - 10} more")

    if report.errors:
        console.print()
        console.print("[red]Errors:[/red]")
        for error in report.errors[:5]:
            console.print(f"  • {error}")

    console.print()
    console.print(f"[dim]Report saved to:[/dim] {out / 'report.json'}")


@app.command()
def report(
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("./api-vault-output"),
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """
    View execution report.

    Display summary of last run.
    """
    out = out.resolve()
    report_path = out / "report.json"

    if not report_path.exists():
        console.print(f"[red]Error:[/red] Report not found: {report_path}")
        console.print("[dim]Run 'api-vault run' first.[/dim]")
        raise typer.Exit(1)

    report_obj = load_report(report_path)

    if json_output:
        console.print(report_obj.model_dump_json(indent=2))
        return

    # Display report
    duration = (report_obj.completed_at - report_obj.started_at).total_seconds()

    console.print(Panel(
        f"[bold]Report ID:[/bold] {report_obj.report_id}\n"
        f"[bold]Repository:[/bold] {report_obj.repo_name}\n"
        f"[bold]Plan ID:[/bold] {report_obj.plan_id}\n"
        f"[bold]Duration:[/bold] {duration:.1f}s",
        title="Execution Report",
    ))

    # Job summary
    table = Table(title="Job Results")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("[green]Completed[/green]", str(report_obj.jobs_completed))
    table.add_row("[cyan]Skipped[/cyan]", str(report_obj.jobs_skipped))
    table.add_row("[red]Failed[/red]", str(report_obj.jobs_failed))
    table.add_row("[dim]Cached[/dim]", str(report_obj.jobs_cached))
    table.add_row("[bold]Total[/bold]", str(report_obj.total_jobs))

    console.print(table)

    # Token usage
    console.print()
    console.print("[bold]Token Usage[/bold]")
    console.print(f"  Input tokens:  {report_obj.total_input_tokens:>10,}")
    console.print(f"  Output tokens: {report_obj.total_output_tokens:>10,}")
    console.print(f"  [bold]Total:[/bold]        {report_obj.total_input_tokens + report_obj.total_output_tokens:>10,}")

    # Artifacts tree
    if report_obj.artifacts_generated:
        console.print()
        console.print("[bold]Generated Artifacts[/bold]")
        tree = Tree("[bold]artifacts/[/bold]")

        by_family: dict[str, list[str]] = {}
        for path in report_obj.artifacts_generated:
            rel_path = Path(path).relative_to(out) if out in Path(path).parents else Path(path)
            parts = rel_path.parts
            if len(parts) >= 2 and parts[0] == "artifacts":
                family = parts[1]
                if family not in by_family:
                    by_family[family] = []
                by_family[family].append(str(rel_path))

        for family, paths in sorted(by_family.items()):
            branch = tree.add(f"[cyan]{family}/[/cyan]")
            for path in paths:
                filename = Path(path).name
                branch.add(filename)

        console.print(tree)

    if report_obj.errors:
        console.print()
        console.print("[bold red]Errors[/bold red]")
        for error in report_obj.errors:
            console.print(f"  [red]•[/red] {error}")


@app.command()
def init(
    repo: Annotated[Path, typer.Option("--repo", "-r", help="Path to repository")] = Path("."),
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory")] = Path("./api-vault-output"),
) -> None:
    """
    Interactive setup wizard.

    Guides you through scan, plan, and run steps.
    """
    repo = repo.resolve()
    out = out.resolve()

    console.print(Panel(
        "[bold]Welcome to Api Vault![/bold]\n\n"
        "This wizard will help you:\n"
        "1. Scan your repository\n"
        "2. Create a generation plan\n"
        "3. Generate documentation artifacts",
        title="Setup Wizard",
    ))

    console.print()

    # Step 1: Confirm repository
    console.print(f"[bold]Repository:[/bold] {repo}")
    if not repo.exists():
        console.print("[red]Error:[/red] Repository path does not exist")
        raise typer.Exit(1)

    proceed = Confirm.ask("Scan this repository?", default=True)
    if not proceed:
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit(0)

    # Step 2: Scan
    console.print()
    console.print("[bold]Step 1: Scanning repository...[/bold]")

    config = ScanConfig()
    out.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Scanning...", total=None)
        index = scan_repository(repo, config)
        progress.update(task, description="Extracting signals...")
        signals = extract_signals(index, repo)

    with open(out / "repo_index.json", "w") as f:
        f.write(index.model_dump_json(indent=2))
    with open(out / "signals.json", "w") as f:
        f.write(signals.model_dump_json(indent=2))

    console.print(f"[green]✓[/green] Found {index.total_files} files")
    if signals.primary_language:
        console.print(f"[green]✓[/green] Primary language: {signals.primary_language}")
    if signals.identified_gaps:
        console.print(f"[green]✓[/green] Identified {len(signals.identified_gaps)} documentation gaps")

    # Step 3: Plan
    console.print()
    console.print("[bold]Step 2: Creating plan...[/bold]")

    budget = IntPrompt.ask("Token budget", default=50000)

    plan_obj = create_plan(
        index=index,
        signals=signals,
        budget_tokens=budget,
        budget_seconds=3600,
    )

    with open(out / "plan.json", "w") as f:
        f.write(plan_obj.model_dump_json(indent=2))

    console.print(f"[green]✓[/green] Planned {len(plan_obj.jobs)} artifacts")

    # Show planned artifacts
    if plan_obj.jobs:
        console.print()
        for job in plan_obj.jobs[:5]:
            console.print(f"  • {job.artifact_name}")
        if len(plan_obj.jobs) > 5:
            console.print(f"  ... and {len(plan_obj.jobs) - 5} more")

    # Step 4: Run?
    console.print()
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        console.print("[yellow]ANTHROPIC_API_KEY not set.[/yellow]")
        run_dry = Confirm.ask("Run in dry-run mode (no API calls)?", default=True)
        if run_dry:
            client = MockAnthropicClient()
        else:
            console.print()
            console.print("[dim]To generate artifacts, set ANTHROPIC_API_KEY and run:[/dim]")
            console.print(f"  api-vault run --repo {repo} --out {out}")
            raise typer.Exit(0)
    else:
        run_now = Confirm.ask("Generate artifacts now?", default=True)
        if not run_now:
            console.print()
            console.print("[dim]To generate artifacts later, run:[/dim]")
            console.print(f"  api-vault run --repo {repo} --out {out}")
            raise typer.Exit(0)
        client = AnthropicClient(cache_dir=out / "cache")

    # Step 5: Run
    console.print()
    console.print("[bold]Step 3: Generating artifacts...[/bold]")

    runner = Runner(
        output_dir=out,
        client=client,
        repo_path=repo,
        index=index,
        signals=signals,
    )

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Generating...", total=None)
        report = runner.run(plan_obj, lambda msg, _=0: progress.update(task, description=msg))

    console.print(f"[green]✓[/green] Generated {report.jobs_completed} artifacts")

    # Done
    console.print()
    console.print(Panel(
        f"[bold green]Setup complete![/bold green]\n\n"
        f"Output directory: {out}\n"
        f"Artifacts: {out / 'artifacts'}\n\n"
        f"[dim]View report: api-vault report --out {out}[/dim]",
        title="Done",
    ))


@app.command("config")
def config_cmd(
    init_config: Annotated[bool, typer.Option("--init", help="Create default config file")] = False,
    show: Annotated[bool, typer.Option("--show", help="Show current configuration")] = False,
    path: Annotated[Optional[Path], typer.Option("--path", help="Config file path for --init")] = None,
) -> None:
    """
    Manage configuration.

    Create or view configuration files.
    """
    if init_config:
        config_path = save_default_config(path)
        console.print(f"[green]✓[/green] Created config file: {config_path}")
        console.print("[dim]Edit this file to customize settings.[/dim]")
        return

    if show:
        cfg = get_config()
        console.print("[bold]Current Configuration[/bold]")
        console.print()
        console.print(cfg.model_dump_json(indent=2))
        return

    # Default: show help
    console.print("Use --init to create a config file or --show to view current config.")
    console.print()
    console.print("Example config file location: ./api-vault.toml")
    console.print()
    console.print("[dim]Config is searched in:[/dim]")
    console.print("  • ./api-vault.toml")
    console.print("  • ./.api-vault.toml")
    console.print("  • ./pyproject.toml [tool.api-vault]")


@app.command()
def audit(
    repo: Annotated[Path, typer.Option("--repo", "-r", help="Path to repository")] = Path("."),
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Output file for report")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show all findings")] = False,
) -> None:
    """
    Audit repository for secrets.

    Scans for potential secrets and generates a security report.
    """
    from api_vault.secret_guard import scan_file, create_redaction_report, SECRET_PATTERNS

    repo = repo.resolve()

    if not repo.exists():
        console.print(f"[red]Error:[/red] Repository path does not exist: {repo}")
        raise typer.Exit(1)

    console.print(Panel(f"[bold]Security Audit[/bold]\n{repo}", title="Api Vault"))

    # Scan all files
    all_entries = []
    file_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning for secrets...", total=None)

        for file_path in repo.rglob("*"):
            if file_path.is_file():
                file_count += 1
                progress.update(task, description=f"Scanning {file_path.name}...")

                try:
                    entries = scan_file(file_path)
                    all_entries.extend(entries)
                except Exception:
                    pass

    report = create_redaction_report(all_entries)

    # Display results
    console.print()
    console.print(f"[bold]Files scanned:[/bold] {file_count}")
    console.print(f"[bold]Secrets found:[/bold] {report.total_redactions}")
    console.print(f"[bold]Files affected:[/bold] {report.files_affected}")

    if report.patterns_matched:
        console.print()
        console.print("[bold]Findings by type:[/bold]")

        table = Table()
        table.add_column("Pattern", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Risk", style="yellow")

        for pattern_name, count in sorted(report.patterns_matched.items(), key=lambda x: -x[1]):
            risk = "High" if "key" in pattern_name.lower() or "token" in pattern_name.lower() else "Medium"
            table.add_row(pattern_name, str(count), risk)

        console.print(table)

    if verbose and report.redactions:
        console.print()
        console.print("[bold]Detailed findings:[/bold]")
        for entry in report.redactions[:20]:
            console.print(f"  [cyan]{entry.file_path}[/cyan]:{entry.line_number}")
            console.print(f"    Pattern: {entry.pattern_name}")
        if len(report.redactions) > 20:
            console.print(f"  ... and {len(report.redactions) - 20} more")

    # Save report if requested
    if out:
        with open(out, "w") as f:
            json.dump({
                "repo_path": str(repo),
                "files_scanned": file_count,
                "total_findings": report.total_redactions,
                "files_affected": report.files_affected,
                "patterns_matched": report.patterns_matched,
                "findings": [e.model_dump() for e in report.redactions] if verbose else [],
            }, f, indent=2, default=str)
        console.print()
        console.print(f"[dim]Report saved to:[/dim] {out}")

    # Exit code based on findings
    if report.total_redactions > 0:
        console.print()
        console.print("[yellow]⚠ Potential secrets detected. Review before committing.[/yellow]")


if __name__ == "__main__":
    app()
