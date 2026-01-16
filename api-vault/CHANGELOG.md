# Changelog

All notable changes to Api Vault will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Property-based testing with Hypothesis
- Plugin architecture for custom artifact generators
- Historical learning for improved estimates

## [1.0.0] - 2024-01-15

### Added
- **Core Features**
  - Repository scanning with file indexing and SHA256 hashing
  - Language and framework detection (20+ languages, 30+ frameworks)
  - Gap analysis for missing documentation and artifacts
  - Deterministic planning with scoring algorithm
  - Content-addressed caching for resumable operations
  - Anthropic Claude API integration with retry/backoff

- **CLI Commands**
  - `scan` - Scan repository and extract signals
  - `plan` - Create artifact generation plan with budget constraints
  - `run` - Execute plan and generate artifacts
  - `report` - View execution report with detailed statistics
  - `estimate` - Preview API costs before running
  - `init` - Interactive setup wizard
  - `config` - Manage configuration files
  - `audit` - Security audit for secret detection

- **Secret Detection**
  - 30+ secret patterns (API keys, tokens, passwords)
  - Entropy-based detection for high-entropy strings
  - Content redaction in generated contexts
  - Detailed audit reports with risk levels

- **Configuration**
  - TOML configuration file support (`api-vault.toml`)
  - Hierarchical settings for scan, plan, run, secrets, output
  - Environment variable overrides
  - pyproject.toml `[tool.api-vault]` integration

- **Progress & UX**
  - Rich progress bars with ETA
  - Token usage tracking in real-time
  - Colorized output with status indicators
  - Shell completion support (bash, zsh)

- **Error Handling**
  - Custom exception hierarchy with error codes
  - Structured error context for debugging
  - Recoverability hints and suggestions
  - Factory functions for common errors

- **Artifact Families**
  - `docs` - README, architecture docs, API documentation
  - `security` - Security policies, threat models
  - `tests` - Test plans, test cases
  - `api` - API specifications, endpoint docs
  - `observability` - Monitoring guides, runbooks
  - `product` - Product requirements, user guides

- **Documentation**
  - Comprehensive README with examples
  - Installation guide
  - Security documentation
  - Usage examples
  - Contributing guidelines

### Security
- Secret detection prevents leaking sensitive data
- Content redaction in all generated contexts
- Minimal API key exposure (environment variable only)
- No secrets stored in cache or outputs

## [0.1.0] - 2024-01-01

### Added
- Initial prototype with basic scanning
- Simple artifact generation
- Basic CLI interface

---

## Release Notes Format

### Added
New features and capabilities.

### Changed
Changes in existing functionality.

### Deprecated
Features that will be removed in future versions.

### Removed
Features that have been removed.

### Fixed
Bug fixes.

### Security
Security-related changes and fixes.
