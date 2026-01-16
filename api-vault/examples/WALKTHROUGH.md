# Api Vault Walkthrough

This walkthrough demonstrates using `api-vault` on the included sample repository.

## Sample Repository

The `sample_repo/` directory contains a simple FastAPI task management API:

```
sample_repo/
├── README.md
├── pyproject.toml
├── src/
│   ├── __init__.py
│   └── main.py          # FastAPI application
├── tests/
│   ├── __init__.py
│   └── test_main.py     # Pytest tests
└── .github/
    └── workflows/
        └── ci.yml       # GitHub Actions CI
```

## Step 1: Scan the Repository

First, scan the repository to build an index and extract signals:

```bash
cd examples
api-vault scan --repo sample_repo --out ./output
```

This creates:
- `output/repo_index.json` - File tree with hashes
- `output/signals.json` - Detected languages, frameworks, gaps

Expected output:
```
✓ Scanned 7 files
✓ Total size: 3,245 bytes
✓ Primary language: Python
✓ Detected frameworks: FastAPI, Pytest

Identified gaps:
  • No CONTRIBUTING guide for new contributors
  • No CHANGELOG to track version history
  • No architecture documentation
  • No SECURITY policy or vulnerability reporting process
```

## Step 2: Create a Plan

Generate an artifact plan based on the scan:

```bash
api-vault plan --repo sample_repo --out ./output --budget-tokens 50000
```

This creates:
- `output/plan.json` - Prioritized list of artifacts to generate

Expected output:
```
✓ Created plan with 6 jobs
✓ Estimated tokens: 32,000

╭─────────────┬──────────────────────────┬───────┬────────╮
│ Family      │ Artifact                 │ Score │ Tokens │
├─────────────┼──────────────────────────┼───────┼────────┤
│ docs        │ RUNBOOK.md               │ 42.5  │ 5,500  │
│ security    │ SECURITY_CHECKLIST.md    │ 39.2  │ 5,000  │
│ api         │ ENDPOINT_INVENTORY.md    │ 38.8  │ 6,000  │
│ docs        │ ARCHITECTURE_OVERVIEW.md │ 37.5  │ 8,500  │
│ tests       │ GOLDEN_PATH_TEST_PLAN.md │ 35.0  │ 8,500  │
│ observability│ LOGGING_CONVENTIONS.md  │ 32.0  │ 5,000  │
╰─────────────┴──────────────────────────┴───────┴────────╯
```

## Step 3: Run the Plan (Dry Run)

Test without API calls using `--dry-run`:

```bash
api-vault run --repo sample_repo --out ./output --dry-run
```

This creates mock artifacts to verify the pipeline works:
- `output/artifacts/docs/RUNBOOK.md`
- `output/artifacts/security/SECURITY_CHECKLIST.md`
- etc.

## Step 4: Run with Real API

Set your Anthropic API key and run:

```bash
export ANTHROPIC_API_KEY="your-key-here"
api-vault run --repo sample_repo --out ./output
```

Expected output:
```
✓ Completed: 6
○ Skipped: 0
✗ Failed: 0

Token usage:
  Input: 12,500
  Output: 18,200
  Total: 30,700

Generated artifacts:
  • artifacts/docs/RUNBOOK.md
  • artifacts/docs/ARCHITECTURE_OVERVIEW.md
  • artifacts/security/SECURITY_CHECKLIST.md
  • artifacts/api/ENDPOINT_INVENTORY.md
  • artifacts/tests/GOLDEN_PATH_TEST_PLAN.md
  • artifacts/observability/LOGGING_CONVENTIONS.md
```

## Step 5: View Report

See the execution summary:

```bash
api-vault report --out ./output
```

Or as JSON:

```bash
api-vault report --out ./output --json
```

## Filtering by Family

Generate only specific artifact types:

```bash
# Only documentation
api-vault plan --repo sample_repo --out ./output --families docs

# Only security and API docs
api-vault plan --repo sample_repo --out ./output --families security,api
```

## Adjusting Budget

Control token usage:

```bash
# Small budget - fewer artifacts
api-vault plan --repo sample_repo --out ./output --budget-tokens 10000

# Large budget - more artifacts
api-vault plan --repo sample_repo --out ./output --budget-tokens 100000
```

## Safe Mode

For sensitive codebases, use safe mode which only sends file paths:

```bash
api-vault scan --repo sample_repo --out ./output --safe-mode
```

## Resuming Interrupted Runs

If a run is interrupted, simply re-run:

```bash
api-vault run --repo sample_repo --out ./output
```

Already-completed artifacts with matching context hashes are skipped automatically.

## Model Selection

Use a different Claude model:

```bash
api-vault run --repo sample_repo --out ./output --model claude-3-5-haiku-20241022
```

Available models:
- `claude-sonnet-4-20250514` (default)
- `claude-3-5-sonnet-20241022`
- `claude-3-5-haiku-20241022`
- `claude-3-opus-20240229`

## Output Structure

After a full run:

```
output/
├── repo_index.json      # File index
├── signals.json         # Detected signals
├── plan.json            # Generation plan
├── report.json          # Execution report
├── artifacts/
│   ├── docs/
│   │   ├── RUNBOOK.md
│   │   ├── RUNBOOK.meta.json
│   │   ├── ARCHITECTURE_OVERVIEW.md
│   │   └── ARCHITECTURE_OVERVIEW.meta.json
│   ├── security/
│   │   ├── SECURITY_CHECKLIST.md
│   │   └── SECURITY_CHECKLIST.meta.json
│   ├── api/
│   │   ├── ENDPOINT_INVENTORY.md
│   │   └── ENDPOINT_INVENTORY.meta.json
│   ├── tests/
│   │   ├── GOLDEN_PATH_TEST_PLAN.md
│   │   └── GOLDEN_PATH_TEST_PLAN.meta.json
│   └── observability/
│       ├── LOGGING_CONVENTIONS.md
│       └── LOGGING_CONVENTIONS.meta.json
└── cache/
    └── *.json           # Cached API responses
```

## Tips

1. **Start with dry-run** to verify the pipeline before using API credits
2. **Use family filters** to generate only what you need
3. **Check signals.json** to understand what api-vault detected
4. **Re-run is safe** - completed artifacts are skipped
5. **Cache is automatic** - identical requests use cached responses
