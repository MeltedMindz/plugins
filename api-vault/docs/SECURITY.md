# Security Model

Api Vault is designed with security as a primary concern. This document details how your code is protected.

## Data Flow

```
Your Repository → Scan → Extract Signals → Build Context → Redact Secrets → API Call → Artifact
       │              │                          │                │
       │              │                          │                └── Only sanitized excerpts sent
       │              │                          └── Conservative pattern matching
       │              └── File paths + hashes only
       └── Never uploaded wholesale
```

## What Is Sent to Anthropic

### Always Sent
- File paths (relative to repository root)
- File sizes and types
- Detected frameworks and languages
- Project structure summary

### Sometimes Sent (When Needed for Context)
- Small code excerpts (default max 8KB per file)
- Configuration file snippets
- README content

### Never Sent
- Full repository contents
- Detected secrets (redacted before transmission)
- Binary files
- Files from sensitive directories

## Secret Detection

Api Vault scans all content before transmission using 30+ patterns:

### High-Confidence Patterns (Always Redacted)
- AWS Access Keys (`AKIA...`)
- GitHub Tokens (`ghp_...`, `gho_...`)
- Private Keys (`-----BEGIN RSA PRIVATE KEY-----`)
- Stripe Keys (`sk_live_...`, `sk_test_...`)
- Database URLs with passwords

### Medium-Confidence Patterns
- JWT Tokens
- Generic password assignments
- High-entropy strings in quotes

### Sensitive Files (Completely Blocked)
These files are never read, regardless of content:
- `.env` and variants
- `credentials.json`
- `secrets.yaml`
- Private key files (`id_rsa`, `*.pem`, `*.key`)

## Safe Mode

For maximum security, enable safe mode:

```bash
api-vault scan --repo /path/to/repo --out ./output --safe-mode
```

In safe mode:
- Only file paths and sizes are collected
- No file contents are ever read
- Artifact generation works from structure only

## Context Limits

Default limits prevent excessive data transmission:

| Limit | Default | Flag |
|-------|---------|------|
| Max file size | 1 MB | `--max-file-size` |
| Max excerpt per file | 8 KB | (config) |
| Max total context | 64 KB | (config) |

## Verification

### Check What Would Be Sent

Run a dry-run and inspect the generated prompts:

```bash
api-vault run --repo /path/to/repo --out ./output --dry-run
```

Then examine the mock client logs.

### Review Redaction Report

After scanning, check `signals.json` for any flagged content:

```bash
cat output/signals.json | jq '.security_maturity'
```

### Audit Mode

Enable verbose logging to see all decisions:

```bash
API_VAULT_DEBUG=1 api-vault scan --repo /path/to/repo --out ./output
```

## Recommendations

1. **Always start with `--dry-run`** to verify behavior before real API calls
2. **Use `--safe-mode`** for repositories with sensitive code
3. **Review `signals.json`** before running generation
4. **Set restrictive budgets** initially (`--budget-tokens 10000`)
5. **Keep API keys in environment variables**, not command line arguments

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do not** open a public GitHub issue
2. Email security@api-vault.example.com with details
3. Include steps to reproduce if possible
4. We will respond within 48 hours

## Pattern Updates

Secret detection patterns are regularly updated. To get the latest:

```bash
pip install --upgrade api-vault
```
