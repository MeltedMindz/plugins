# Plugins

Production-ready Claude Code plugins and CLI tools.

## Contents

| Plugin | Description | Status |
|--------|-------------|--------|
| [api-vault](./api-vault) | Convert API quota into durable local artifacts through intelligent repo analysis | Ready |
| [recall](./recall) | Capture and query architectural decisions - your codebase finally has a memory | Ready |

## Installation

Each plugin has its own installation instructions. Navigate to the plugin directory and follow its README.

### Quick Start

```bash
# Example: Install api-vault
cd api-vault
pip install -e .
api-vault --help
```

## Plugin Overview

### api-vault

A CLI tool that inspects local git repositories, detects stack/maturity/gaps, and generates high-quality documentation artifacts using the Anthropic API.

**Features:**
- Repository scanning with language/framework detection
- Secret detection and redaction (45+ patterns)
- Intelligent artifact planning with budget constraints
- Content-addressed caching for resumable operations
- TOML configuration support
- Plugin architecture for extensibility

```bash
api-vault scan --repo .
api-vault plan --budget-tokens 50000
api-vault estimate
api-vault run --dry-run
```

### recall

A Claude Code plugin + MCP server that automatically captures architectural decisions and makes them queryable.

**Features:**
- Auto-detection of architectural decisions via hooks
- SQLite + FTS5 full-text search
- MCP tools for natural language queries
- Export to JSON, Markdown, and ADR formats

```bash
/decision Using Redis for session storage
/decisions
/decision-search "why redis"
```

## License

Each plugin is individually licensed. See the LICENSE file in each plugin directory.
