# Configuration Guide

Api Vault supports flexible configuration through TOML files, environment variables, and command-line options.

## Configuration File

### File Locations

Api Vault searches for configuration in this order:

1. `./api-vault.toml` - Current directory
2. `./.api-vault.toml` - Hidden file in current directory
3. `./pyproject.toml` - Under `[tool.api-vault]` section

### Creating a Config File

Generate a default configuration file:

```bash
api-vault config --init
```

This creates `api-vault.toml` with all available options:

```toml
# Api Vault Configuration
# https://github.com/api-vault/api-vault

[scan]
max_file_size_bytes = 1_000_000    # 1 MB
max_excerpt_bytes = 8192           # 8 KB per file
max_total_context_bytes = 65536    # 64 KB total
safe_mode = false                  # Set true to only collect file paths
docs_only_mode = false             # Set true to only use documentation files
additional_excluded_dirs = []      # Add custom directories to exclude

[plan]
default_budget_tokens = 100_000
default_budget_seconds = 3600
default_families = ["docs", "security", "tests", "api", "observability", "product"]
min_score_threshold = 10.0

[plan.weights]
reusability = 1.0
time_saved = 1.5
leverage = 2.0
context_cost = -0.5
gap_weight = 1.5

[run]
model = "claude-sonnet-4-20250514"
cache_enabled = true
max_retries = 3
retry_delay_seconds = 1.0
timeout_seconds = 300

[secrets]
min_confidence = 0.5
sensitivity = "medium"  # low, medium, high, paranoid
additional_patterns = []
skip_files = []

[output]
default_output_dir = "./api-vault-output"
pretty_json = true
generate_html_report = false
```

### pyproject.toml Integration

Add configuration to your existing `pyproject.toml`:

```toml
[tool.api-vault]
[tool.api-vault.scan]
max_file_size_bytes = 500_000
safe_mode = true

[tool.api-vault.plan]
default_budget_tokens = 50_000
default_families = ["docs", "security"]

[tool.api-vault.run]
model = "claude-3-haiku-20240307"
```

## Configuration Sections

### [scan] - Repository Scanning

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_file_size_bytes` | int | 1,000,000 | Maximum file size to read |
| `max_excerpt_bytes` | int | 8,192 | Maximum bytes per file excerpt |
| `max_total_context_bytes` | int | 65,536 | Maximum total context per job |
| `safe_mode` | bool | false | Only collect file paths, no content |
| `docs_only_mode` | bool | false | Only scan documentation files |
| `excluded_dirs` | list | (see below) | Directories to exclude |
| `additional_excluded_dirs` | list | [] | Extra directories to exclude |

**Default excluded directories:**
- `node_modules`, `dist`, `build`, `.next`, `.git`
- `coverage`, `vendor`, `__pycache__`, `target`
- `.venv`, `venv`

### [plan] - Planning Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_budget_tokens` | int | 100,000 | Default token budget |
| `default_budget_seconds` | int | 3,600 | Default time budget (seconds) |
| `default_families` | list | all | Artifact families to generate |
| `min_score_threshold` | float | 10.0 | Minimum score for artifacts |

**Available families:**
- `docs` - Documentation artifacts
- `security` - Security documentation
- `tests` - Test plans and cases
- `api` - API documentation
- `observability` - Monitoring guides
- `product` - Product documentation

### [plan.weights] - Scoring Weights

| Weight | Default | Description |
|--------|---------|-------------|
| `reusability` | 1.0 | How often artifact will be referenced |
| `time_saved` | 1.5 | Developer time saved |
| `leverage` | 2.0 | Impact multiplier |
| `context_cost` | -0.5 | Context size penalty (negative) |
| `gap_weight` | 1.5 | How much repo needs this |

### [run] - Execution Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | string | claude-sonnet-4-20250514 | Anthropic model to use |
| `cache_enabled` | bool | true | Enable response caching |
| `max_retries` | int | 3 | Max API retry attempts |
| `retry_delay_seconds` | float | 1.0 | Delay between retries |
| `timeout_seconds` | int | 300 | API timeout |

**Available models:**
- `claude-sonnet-4-20250514` - Default, balanced
- `claude-3-5-sonnet-20241022` - Previous Sonnet
- `claude-3-opus-20240229` - Highest quality
- `claude-3-haiku-20240307` - Fastest, cheapest

### [secrets] - Secret Detection

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `min_confidence` | float | 0.5 | Minimum detection confidence |
| `sensitivity` | string | "medium" | Detection sensitivity |
| `additional_patterns` | list | [] | Extra regex patterns |
| `skip_files` | list | [] | Files to skip scanning |

**Sensitivity levels:**
- `low` - Only obvious secrets
- `medium` - Standard detection
- `high` - Aggressive detection
- `paranoid` - Maximum detection (more false positives)

### [output] - Output Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default_output_dir` | string | ./api-vault-output | Output directory |
| `pretty_json` | bool | true | Format JSON output |
| `generate_html_report` | bool | false | Generate HTML report |

## Environment Variables

Override any setting with environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | **Required** for API calls |
| `API_VAULT_DEBUG` | Enable debug logging |
| `API_VAULT_CONFIG` | Path to config file |

## Command-Line Overrides

Most settings can be overridden on the command line:

```bash
# Override token budget
api-vault plan --budget-tokens 50000

# Override model
api-vault run --model claude-3-haiku-20240307

# Override output directory
api-vault scan --out ./my-output

# Use safe mode
api-vault scan --safe-mode
```

## Configuration Precedence

1. **Command-line options** (highest priority)
2. **Environment variables**
3. **Config file in current directory**
4. **pyproject.toml [tool.api-vault]**
5. **Built-in defaults** (lowest priority)

## View Current Configuration

```bash
# Show effective configuration
api-vault config --show
```

Output:

```json
{
  "scan": {
    "max_file_size_bytes": 1000000,
    "max_excerpt_bytes": 8192,
    ...
  },
  "plan": {
    "default_budget_tokens": 100000,
    ...
  },
  ...
}
```

## Example Configurations

### Cost-Conscious Setup

```toml
[plan]
default_budget_tokens = 25_000
default_families = ["docs"]

[run]
model = "claude-3-haiku-20240307"
```

### Enterprise/Paranoid Security

```toml
[scan]
safe_mode = true

[secrets]
sensitivity = "paranoid"
additional_patterns = [
    "CORP_[A-Z0-9]{24}",
    "internal-token-[a-f0-9]{32}",
]

[output]
generate_html_report = true
```

### Large Monorepo

```toml
[scan]
max_file_size_bytes = 500_000
max_total_context_bytes = 131072
additional_excluded_dirs = ["packages/legacy", "apps/deprecated"]

[plan]
default_budget_tokens = 500_000
```

### CI/CD Pipeline

```toml
[scan]
docs_only_mode = true

[plan]
default_families = ["docs", "api"]
default_budget_tokens = 50_000

[run]
max_retries = 1
timeout_seconds = 120
```
