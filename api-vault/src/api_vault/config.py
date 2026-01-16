"""
Configuration file support for Api Vault.

Supports TOML configuration files (api-vault.toml) for persistent settings.
"""

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from api_vault.errors import ConfigError, ErrorCode
from api_vault.schemas import ArtifactFamily

# Default config file names (searched in order)
CONFIG_FILE_NAMES = [
    "api-vault.toml",
    ".api-vault.toml",
    "pyproject.toml",  # Will look for [tool.api-vault] section
]


class ScanSettings(BaseModel):
    """Scan-related configuration."""

    max_file_size_bytes: int = Field(default=1_000_000, ge=1024, le=100_000_000)
    max_excerpt_bytes: int = Field(default=8192, ge=256, le=65536)
    max_total_context_bytes: int = Field(default=65536, ge=4096, le=262144)
    safe_mode: bool = Field(default=False)
    docs_only_mode: bool = Field(default=False)
    excluded_dirs: list[str] = Field(default_factory=lambda: [
        "node_modules", "dist", "build", ".next", ".git", "coverage",
        "vendor", "__pycache__", "target", ".venv", "venv",
    ])
    additional_excluded_dirs: list[str] = Field(default_factory=list)


class PlanSettings(BaseModel):
    """Planning-related configuration."""

    default_budget_tokens: int = Field(default=100_000, ge=1000, le=10_000_000)
    default_budget_seconds: int = Field(default=3600, ge=60, le=86400)
    default_families: list[str] = Field(default_factory=lambda: [
        "docs", "security", "tests", "api", "observability", "product"
    ])
    weights: dict[str, float] = Field(default_factory=lambda: {
        "reusability": 1.0,
        "time_saved": 1.5,
        "leverage": 2.0,
        "context_cost": -0.5,
        "gap_weight": 1.5,
    })
    min_score_threshold: float = Field(default=10.0, ge=0.0)


class RunSettings(BaseModel):
    """Run-related configuration."""

    model: str = Field(default="claude-sonnet-4-20250514")
    cache_enabled: bool = Field(default=True)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    timeout_seconds: int = Field(default=300, ge=30, le=3600)


class SecretSettings(BaseModel):
    """Secret detection configuration."""

    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sensitivity: str = Field(default="medium")  # low, medium, high, paranoid
    additional_patterns: list[str] = Field(default_factory=list)
    skip_files: list[str] = Field(default_factory=list)


class OutputSettings(BaseModel):
    """Output-related configuration."""

    default_output_dir: str = Field(default="./api-vault-output")
    pretty_json: bool = Field(default=True)
    generate_html_report: bool = Field(default=False)


class ApiVaultConfig(BaseModel):
    """Complete Api Vault configuration."""

    scan: ScanSettings = Field(default_factory=ScanSettings)
    plan: PlanSettings = Field(default_factory=PlanSettings)
    run: RunSettings = Field(default_factory=RunSettings)
    secrets: SecretSettings = Field(default_factory=SecretSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)

    @classmethod
    def default(cls) -> "ApiVaultConfig":
        """Create config with all defaults."""
        return cls()

    def get_families(self) -> list[ArtifactFamily]:
        """Get artifact families from config."""
        families = []
        for name in self.plan.default_families:
            try:
                families.append(ArtifactFamily(name.lower()))
            except ValueError:
                pass  # Skip invalid families
        return families or list(ArtifactFamily)


def _parse_toml(content: str) -> dict[str, Any]:
    """Parse TOML content."""
    try:
        import tomllib
    except ImportError:
        # Python < 3.11 fallback
        try:
            import tomli as tomllib
        except ImportError:
            raise ConfigError(
                message="TOML parsing requires Python 3.11+ or 'tomli' package",
                code=ErrorCode.CONFIG_INVALID,
                suggestion="Install tomli: pip install tomli",
            )
    return tomllib.loads(content)


def _find_config_file(start_dir: Path | None = None) -> Path | None:
    """
    Find configuration file by searching up from start directory.

    Args:
        start_dir: Directory to start search (default: current directory)

    Returns:
        Path to config file if found, None otherwise
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Search up the directory tree
    while True:
        for name in CONFIG_FILE_NAMES:
            config_path = current / name
            if config_path.exists():
                return config_path

        # Stop at filesystem root
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def load_config(config_path: Path | None = None) -> ApiVaultConfig:
    """
    Load configuration from file.

    Args:
        config_path: Explicit path to config file (optional)

    Returns:
        ApiVaultConfig with loaded settings

    Raises:
        ConfigError: If config file is invalid
    """
    # If no explicit path, search for config file
    if config_path is None:
        config_path = _find_config_file()

    # No config file found - use defaults
    if config_path is None:
        return ApiVaultConfig.default()

    # Load and parse config file
    try:
        content = config_path.read_text()
    except OSError as e:
        raise ConfigError(
            message=f"Failed to read config file: {e}",
            code=ErrorCode.CONFIG_FILE_NOT_FOUND,
            config_path=str(config_path),
        )

    try:
        data = _parse_toml(content)
    except Exception as e:
        raise ConfigError(
            message=f"Failed to parse config file: {e}",
            code=ErrorCode.CONFIG_INVALID,
            config_path=str(config_path),
        )

    # Handle pyproject.toml (look for [tool.api-vault] section)
    if config_path.name == "pyproject.toml":
        data = data.get("tool", {}).get("api-vault", {})
        if not data:
            # No api-vault section in pyproject.toml
            return ApiVaultConfig.default()

    # Parse into config object
    try:
        return ApiVaultConfig.model_validate(data)
    except Exception as e:
        raise ConfigError(
            message=f"Invalid configuration values: {e}",
            code=ErrorCode.CONFIG_INVALID,
            config_path=str(config_path),
        )


def generate_default_config() -> str:
    """
    Generate default configuration file content.

    Returns:
        TOML string with default configuration
    """
    return '''# Api Vault Configuration
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
'''


def save_default_config(path: Path | None = None) -> Path:
    """
    Save default configuration to file.

    Args:
        path: Path to save config (default: ./api-vault.toml)

    Returns:
        Path where config was saved
    """
    if path is None:
        path = Path("api-vault.toml")

    content = generate_default_config()
    path.write_text(content)
    return path
