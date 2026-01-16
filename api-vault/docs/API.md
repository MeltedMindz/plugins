# Api Vault API Reference

This document describes the Python API for programmatic use of Api Vault.

## Quick Start

```python
from pathlib import Path

from api_vault.repo_scanner import scan_repository
from api_vault.signal_extractor import extract_signals
from api_vault.planner import create_plan
from api_vault.runner import Runner
from api_vault.anthropic_client import AnthropicClient
from api_vault.schemas import ArtifactFamily

# Scan repository
repo_path = Path("/path/to/your/repo")
output_dir = Path("./output")

index = scan_repository(repo_path)
signals = extract_signals(index, repo_path)

# Create plan
plan = create_plan(
    index=index,
    signals=signals,
    budget_tokens=50000,
    budget_seconds=3600,
    families=[ArtifactFamily.DOCS, ArtifactFamily.SECURITY],
)

# Execute plan
client = AnthropicClient(cache_dir=output_dir / "cache")
runner = Runner(
    output_dir=output_dir,
    client=client,
    repo_path=repo_path,
    index=index,
    signals=signals,
)

report = runner.run(plan)
print(f"Generated {report.jobs_completed} artifacts")
```

## Core Modules

### repo_scanner

Scans repositories and builds file indexes.

```python
from api_vault.repo_scanner import (
    scan_repository,
    get_file_content,
    get_files_by_extension,
    get_key_files,
)
from api_vault.schemas import ScanConfig

# Basic scan
index = scan_repository(Path("/path/to/repo"))

# With custom config
config = ScanConfig(
    max_file_size_bytes=500_000,
    safe_mode=True,
)
index = scan_repository(Path("/path/to/repo"), config)

# Get file content
content = get_file_content(
    repo_path=Path("/path/to/repo"),
    file_entry=index.files[0],
    max_bytes=4096,
)

# Filter files
py_files = get_files_by_extension(index, ["py"])
key_files = get_key_files(index)  # README, package.json, etc.
```

### signal_extractor

Extracts signals about languages, frameworks, and maturity.

```python
from api_vault.signal_extractor import (
    extract_signals,
    detect_languages,
    detect_frameworks,
    assess_docs_maturity,
)

# Full signal extraction
signals = extract_signals(index, repo_path)

# Individual extractions
languages = detect_languages(index)
frameworks = detect_frameworks(index, repo_path)
docs_maturity = assess_docs_maturity(index, repo_path)
```

### secret_guard

Detects and redacts sensitive content.

```python
from api_vault.secret_guard import (
    scan_content,
    redact_content,
    get_safe_content,
    is_sensitive_file,
)

# Check if file is sensitive
if is_sensitive_file(".env"):
    print("Sensitive file, skipping")

# Scan for secrets
entries = scan_content(content, "config.py", min_confidence=0.7)

# Get redacted content
safe_content, report = get_safe_content(content, "config.py")
print(f"Redacted {report.total_redactions} secrets")
```

### planner

Creates artifact generation plans.

```python
from api_vault.planner import create_plan, load_plan
from api_vault.schemas import ArtifactFamily

# Create plan
plan = create_plan(
    index=index,
    signals=signals,
    budget_tokens=50000,
    budget_seconds=3600,
    families=[ArtifactFamily.DOCS],
)

# Access plan details
for job in plan.jobs:
    print(f"{job.artifact_name}: score {job.score_breakdown.total_score}")

# Save/load plan
plan_path = Path("./plan.json")
with open(plan_path, "w") as f:
    f.write(plan.model_dump_json(indent=2))

loaded_plan = load_plan(plan_path)
```

### anthropic_client

Wrapper around Anthropic API with caching.

```python
from api_vault.anthropic_client import (
    AnthropicClient,
    MockAnthropicClient,
    compute_request_hash,
)

# Real client
client = AnthropicClient(
    api_key="sk-ant-...",  # Or use ANTHROPIC_API_KEY env var
    cache_dir=Path("./cache"),
    model="claude-sonnet-4-20250514",
)

# Generate content
result = client.generate(
    system_prompt="You are helpful.",
    user_prompt="Hello!",
    max_tokens=1000,
)

print(result.text)
print(f"Tokens: {result.input_tokens} in, {result.output_tokens} out")

# Check usage
summary = client.get_usage_summary()

# Mock client for testing
mock = MockAnthropicClient()
mock_result = mock.generate("system", "user", 100)
```

### runner

Executes plans and generates artifacts.

```python
from api_vault.runner import Runner, load_report

# Create runner
runner = Runner(
    output_dir=output_dir,
    client=client,
    repo_path=repo_path,
    index=index,
    signals=signals,
)

# Run with progress callback
def on_progress(message: str):
    print(f"Progress: {message}")

report = runner.run(plan, progress_callback=on_progress)

# Access results
print(f"Completed: {report.jobs_completed}")
print(f"Skipped: {report.jobs_skipped}")
print(f"Failed: {report.jobs_failed}")

# Load existing report
loaded_report = load_report(output_dir / "report.json")
```

### templates

Access prompt templates.

```python
from api_vault.templates import (
    PROMPT_TEMPLATES,
    get_prompt_template,
    list_templates,
    render_prompt,
)

# List available templates
for template_id in list_templates():
    template = get_prompt_template(template_id)
    print(f"{template_id}: {template.name}")

# Render a prompt
result = render_prompt("runbook", context_string)
if result:
    system_prompt, user_prompt = result
```

## Schemas

All data structures are Pydantic models in `api_vault.schemas`.

### Key Models

```python
from api_vault.schemas import (
    # Index
    FileEntry,
    RepoIndex,
    ScanConfig,

    # Signals
    LanguageStats,
    FrameworkDetection,
    DocsMaturity,
    TestingMaturity,
    CIMaturity,
    SecurityMaturity,
    RepoSignals,

    # Planning
    ContextRef,
    ScoreBreakdown,
    PlanJob,
    Plan,
    ArtifactFamily,

    # Execution
    ArtifactMeta,
    JobResult,
    Report,

    # Caching
    CacheEntry,
    RedactionEntry,
    RedactionReport,
)
```

### Serialization

All models support JSON serialization:

```python
# To JSON string
json_str = model.model_dump_json(indent=2)

# To dict
data = model.model_dump()

# From JSON
loaded = ModelClass.model_validate_json(json_str)
loaded = ModelClass.model_validate(data)
```

## Error Handling

```python
from api_vault.anthropic_client import AnthropicClient

client = AnthropicClient()

result = client.generate(...)

if result.error:
    print(f"Generation failed: {result.error}")
else:
    print(result.text)
```

## Customization

### Custom Artifact Templates

Extend the planner with custom artifacts:

```python
from api_vault.planner import ArtifactTemplate, ARTIFACT_TEMPLATES
from api_vault.schemas import ArtifactFamily

# Add custom template
custom = ArtifactTemplate(
    name="CUSTOM_DOC.md",
    family=ArtifactFamily.DOCS,
    output_filename="CUSTOM_DOC.md",
    prompt_template_id="custom",  # Must exist in templates
    description="Custom documentation",
    base_reusability=7.0,
    base_time_saved=6.0,
    base_leverage=5.0,
    base_context_cost=4.0,
)

ARTIFACT_TEMPLATES.append(custom)
```

### Custom Secret Patterns

Add secret detection patterns:

```python
from api_vault.secret_guard import SecretPattern, SECRET_PATTERNS
import re

# Add custom pattern
custom_pattern = SecretPattern(
    name="custom_api_key",
    pattern=re.compile(r"CUSTOM_[A-Z0-9]{32}"),
    description="Custom service API key",
    confidence=0.9,
)

SECRET_PATTERNS.append(custom_pattern)
```
