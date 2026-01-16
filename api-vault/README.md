# Api Vault

Convert expiring API quota into durable local artifacts.

Api Vault inspects your Git repositories, detects your technology stack and documentation gaps, then intelligently generates high-quality, repo-specific documentation artifacts using the Anthropic API.

## Why?

API credits and tokens often have expiration dates. Rather than letting quota expire unused, Api Vault converts it into valuable, permanent local assets:

- Runbooks and troubleshooting guides
- Architecture documentation
- Security checklists and threat models
- Test plans and API inventories
- Logging and metrics conventions

## Features

- **Intelligent Scanning**: Detects languages, frameworks, and project characteristics
- **Gap Analysis**: Identifies missing documentation and weak areas
- **Smart Planning**: Prioritizes artifacts by value within your token budget
- **Secret Protection**: Aggressive redaction of secrets before any API calls
- **Anthropic Prompt Caching**: Repo context is cached server-side, saving ~80% on input tokens across multiple artifacts
- **Deterministic Caching**: Same inputs produce same outputs; completed work is skipped
- **Resumable**: Interrupt and restart without losing progress

## Installation

```bash
pip install api-vault
```

Or install from source:

```bash
git clone https://github.com/api-vault/api-vault
cd api-vault
pip install -e .
```

## Quick Start

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Scan a repository
api-vault scan --repo /path/to/your/repo --out ./output

# Create a generation plan
api-vault plan --repo /path/to/your/repo --out ./output --budget-tokens 50000

# Generate artifacts (use --dry-run first to test)
api-vault run --repo /path/to/your/repo --out ./output --dry-run
api-vault run --repo /path/to/your/repo --out ./output

# View report
api-vault report --out ./output
```

## Commands

### `api-vault scan`

Scans a repository and extracts signals about its structure, languages, and maturity.

```bash
api-vault scan --repo PATH --out OUTDIR [--safe-mode] [--max-file-size BYTES]
```

Options:
- `--repo`, `-r`: Path to repository (default: current directory)
- `--out`, `-o`: Output directory (default: ./api-vault-output)
- `--safe-mode`: Don't read file contents, only paths
- `--max-file-size`: Maximum file size to process (default: 1MB)

### `api-vault plan`

Creates an artifact generation plan within budget constraints.

```bash
api-vault plan --repo PATH --out OUTDIR --budget-tokens N --budget-seconds S [--families FAMILIES]
```

Options:
- `--budget-tokens`, `-t`: Token budget (default: 100,000)
- `--budget-seconds`, `-s`: Time budget in seconds (default: 3600)
- `--families`, `-f`: Comma-separated artifact families to include

### `api-vault run`

Executes the plan and generates artifacts.

```bash
api-vault run --repo PATH --out OUTDIR [--plan PLAN_FILE] [--model MODEL] [--dry-run]
```

Options:
- `--plan`, `-p`: Path to plan.json (default: OUTDIR/plan.json)
- `--model`, `-m`: Anthropic model to use (default: claude-sonnet-4-20250514)
- `--dry-run`: Use mock client, no real API calls

### `api-vault report`

Displays execution report.

```bash
api-vault report --out OUTDIR [--json]
```

Options:
- `--json`: Output as JSON instead of formatted display

## Artifact Families

| Family | Artifacts |
|--------|-----------|
| **docs** | RUNBOOK.md, TROUBLESHOOTING.md, ARCHITECTURE_OVERVIEW.md |
| **security** | THREAT_MODEL.md, SECURITY_CHECKLIST.md, AUTHZ_AUTHN_NOTES.md |
| **tests** | GOLDEN_PATH_TEST_PLAN.md, MINIMUM_TESTS_SUGGESTION.md |
| **api** | ENDPOINT_INVENTORY.md, openapi_draft.json |
| **observability** | LOGGING_CONVENTIONS.md, METRICS_PLAN.md |
| **product** | UX_COPY_BANK.md |

## Output Structure

```
output/
├── repo_index.json      # File tree with hashes
├── signals.json         # Detected characteristics
├── plan.json            # Generation plan
├── report.json          # Execution report
├── artifacts/
│   ├── docs/
│   │   ├── RUNBOOK.md
│   │   └── RUNBOOK.meta.json
│   └── ...
└── cache/
    └── *.json           # Cached API responses
```

## Security Model

Api Vault is designed with security in mind:

### What Gets Sent to the API

- **File paths**: Yes (needed for context)
- **Small code excerpts**: Yes, but limited (default max 8KB per file, 64KB total)
- **Secrets**: **NO** - Aggressive redaction before any transmission

### Secret Detection

The following patterns are automatically detected and redacted:

- AWS credentials (access keys, secret keys)
- GitHub/GitLab tokens
- Private keys (RSA, SSH, PGP)
- Database connection strings with passwords
- JWT tokens
- API keys (Stripe, Anthropic, OpenAI, etc.)
- Environment variable assignments with sensitive names

### Safe Mode

For maximum security, use `--safe-mode`:

```bash
api-vault scan --repo /path/to/repo --out ./output --safe-mode
```

In safe mode, only file paths are collected—no file contents are read.

### Sensitive Files

These files are never read:
- `.env`, `.env.local`, `.env.production`
- `credentials.json`, `secrets.yaml`
- Private keys (`id_rsa`, `*.pem`, `*.key`)

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Required for API calls |

### Budget Guidelines

| Budget | Typical Output |
|--------|----------------|
| 10,000 tokens | 1-2 artifacts |
| 50,000 tokens | 5-7 artifacts |
| 100,000 tokens | 10-12 artifacts |
| 200,000 tokens | All artifact types |

### Anthropic Prompt Caching

Api Vault uses [Anthropic's prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) to dramatically reduce costs when generating multiple artifacts.

**How it works:**
1. On the first artifact, the repository context (file tree, signals, key files) is sent and cached server-side
2. For subsequent artifacts, the cached context is reused at 90% discount
3. Only artifact-specific prompts incur full token costs

**Cost savings example (10 artifacts, 8k context):**
- Without caching: 10 × 8,000 = 80,000 input tokens
- With caching: 8,000 + (9 × 800) = 15,200 effective input tokens
- **Savings: ~81%**

The report shows cache statistics:
```
Cache read tokens: 72,000 (from Anthropic cache)
Effective input tokens: 15,200
Cache savings: 81%
```

## Development

### Setup

```bash
git clone https://github.com/api-vault/api-vault
cd api-vault
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

Tests use mocked Anthropic client—no real API calls are made.

### Code Quality

```bash
ruff check src/
mypy src/
```

## Architecture

```
api_vault/
├── cli.py              # Typer CLI commands
├── schemas.py          # Pydantic data models
├── repo_scanner.py     # File indexing and hashing
├── signal_extractor.py # Language/framework detection
├── secret_guard.py     # Secret detection and redaction
├── context_packager.py # Context preparation for prompts
├── planner.py          # Artifact selection and scoring
├── anthropic_client.py # API wrapper with caching
├── runner.py           # Plan execution
└── templates/
    └── prompts.py      # Prompt templates for each artifact
```

## Limitations

- Requires Python 3.11+
- Only supports Anthropic API (no OpenAI, etc.)
- Best results with codebases under 10,000 files
- Some artifact types require specific project characteristics (e.g., API docs require API detection)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## FAQ

### Is this violating API terms of service?

No. Api Vault simply uses API quota to generate documentation. It doesn't attempt to transfer, preserve, or bypass any quota restrictions.

### How accurate are the generated artifacts?

Artifacts are generated based on actual code context. Each artifact includes self-check instructions that flag uncertain information. Always review generated content before using in production.

### Can I use this offline?

The scan and plan commands work offline. Only the run command requires API access.

### How much does this cost?

Costs depend on your Anthropic API pricing and the number of artifacts generated. Use `--dry-run` to estimate before committing.
