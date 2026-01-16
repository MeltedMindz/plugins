"""
Secret guard for detecting and redacting sensitive information.

Scans content for potential secrets and sensitive data, redacting them
before any content is sent to external APIs. Errs on the side of caution
with conservative matching to prevent leaks.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from api_vault.schemas import RedactionEntry, RedactionReport


@dataclass
class SecretPattern:
    """A pattern for detecting secrets."""

    name: str
    pattern: re.Pattern
    description: str
    confidence: float = 1.0
    false_positive_patterns: list[re.Pattern] = field(default_factory=list)


# Comprehensive secret detection patterns
SECRET_PATTERNS: list[SecretPattern] = [
    # AWS
    SecretPattern(
        name="aws_access_key",
        pattern=re.compile(r"(?<![A-Z0-9])(AKIA[0-9A-Z]{16})(?![A-Z0-9])", re.IGNORECASE),
        description="AWS Access Key ID",
        confidence=0.95,
    ),
    SecretPattern(
        name="aws_secret_key",
        pattern=re.compile(
            r"(?<![A-Za-z0-9/+=])([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])",
            re.IGNORECASE,
        ),
        description="AWS Secret Access Key (high entropy 40-char string)",
        confidence=0.7,
    ),
    SecretPattern(
        name="aws_session_token",
        pattern=re.compile(r"aws[_\-]?session[_\-]?token[\s]*[=:]\s*['\"]?([^\s'\"]+)", re.IGNORECASE),
        description="AWS Session Token",
    ),
    # GitHub
    SecretPattern(
        name="github_token",
        pattern=re.compile(r"(ghp_[a-zA-Z0-9]{36})", re.IGNORECASE),
        description="GitHub Personal Access Token",
    ),
    SecretPattern(
        name="github_oauth",
        pattern=re.compile(r"(gho_[a-zA-Z0-9]{36})", re.IGNORECASE),
        description="GitHub OAuth Access Token",
    ),
    SecretPattern(
        name="github_app_token",
        pattern=re.compile(r"(ghu_[a-zA-Z0-9]{36})", re.IGNORECASE),
        description="GitHub App User Token",
    ),
    SecretPattern(
        name="github_refresh_token",
        pattern=re.compile(r"(ghr_[a-zA-Z0-9]{36})", re.IGNORECASE),
        description="GitHub Refresh Token",
    ),
    SecretPattern(
        name="github_fine_grained",
        pattern=re.compile(r"(github_pat_[a-zA-Z0-9_]{22,})", re.IGNORECASE),
        description="GitHub Fine-grained Personal Access Token",
    ),
    # GitLab
    SecretPattern(
        name="gitlab_token",
        pattern=re.compile(r"(glpat-[a-zA-Z0-9\-_]{20,})", re.IGNORECASE),
        description="GitLab Personal Access Token",
    ),
    # Slack
    SecretPattern(
        name="slack_token",
        pattern=re.compile(r"(xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{23,25})", re.IGNORECASE),
        description="Slack Token",
    ),
    SecretPattern(
        name="slack_webhook",
        pattern=re.compile(
            r"https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+",
            re.IGNORECASE,
        ),
        description="Slack Webhook URL",
    ),
    # Stripe
    SecretPattern(
        name="stripe_live_key",
        pattern=re.compile(r"(sk_live_[a-zA-Z0-9]{24,})", re.IGNORECASE),
        description="Stripe Live Secret Key",
    ),
    SecretPattern(
        name="stripe_test_key",
        pattern=re.compile(r"(sk_test_[a-zA-Z0-9]{24,})", re.IGNORECASE),
        description="Stripe Test Secret Key",
        confidence=0.9,
    ),
    SecretPattern(
        name="stripe_restricted_key",
        pattern=re.compile(r"(rk_live_[a-zA-Z0-9]{24,})", re.IGNORECASE),
        description="Stripe Restricted API Key",
    ),
    # Google
    SecretPattern(
        name="google_api_key",
        pattern=re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE),
        description="Google API Key",
    ),
    SecretPattern(
        name="google_oauth",
        pattern=re.compile(r"[0-9]+-[a-z0-9_]{32}\.apps\.googleusercontent\.com", re.IGNORECASE),
        description="Google OAuth Client ID",
    ),
    # Firebase
    SecretPattern(
        name="firebase_key",
        pattern=re.compile(r"AAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140}", re.IGNORECASE),
        description="Firebase Cloud Messaging Key",
    ),
    # Twilio
    SecretPattern(
        name="twilio_account_sid",
        pattern=re.compile(r"AC[a-f0-9]{32}", re.IGNORECASE),
        description="Twilio Account SID",
    ),
    SecretPattern(
        name="twilio_auth_token",
        pattern=re.compile(r"(?<![a-f0-9])([a-f0-9]{32})(?![a-f0-9])", re.IGNORECASE),
        description="Twilio Auth Token",
        confidence=0.5,  # Low confidence - could be many things
    ),
    # SendGrid
    SecretPattern(
        name="sendgrid_api_key",
        pattern=re.compile(r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}", re.IGNORECASE),
        description="SendGrid API Key",
    ),
    # Mailgun
    SecretPattern(
        name="mailgun_api_key",
        pattern=re.compile(r"key-[a-f0-9]{32}", re.IGNORECASE),
        description="Mailgun API Key",
    ),
    # Anthropic
    SecretPattern(
        name="anthropic_api_key",
        pattern=re.compile(r"sk-ant-api[a-zA-Z0-9\-_]{80,}", re.IGNORECASE),
        description="Anthropic API Key",
    ),
    # OpenAI
    SecretPattern(
        name="openai_api_key",
        pattern=re.compile(r"sk-[a-zA-Z0-9]{20,}T3BlbkFJ[a-zA-Z0-9]{20,}", re.IGNORECASE),
        description="OpenAI API Key (legacy format)",
    ),
    SecretPattern(
        name="openai_api_key_new",
        pattern=re.compile(r"sk-proj-[a-zA-Z0-9\-_]{40,}", re.IGNORECASE),
        description="OpenAI API Key (project format)",
    ),
    # Heroku
    SecretPattern(
        name="heroku_api_key",
        pattern=re.compile(
            r"(?:heroku[_\-]?api[_\-]?key|HEROKU_API_KEY)[\s]*[=:]\s*['\"]?([a-f0-9-]{36})['\"]?",
            re.IGNORECASE,
        ),
        description="Heroku API Key",
    ),
    # JWT
    SecretPattern(
        name="jwt_token",
        pattern=re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", re.IGNORECASE),
        description="JWT Token",
        confidence=0.85,
    ),
    # Private Keys
    SecretPattern(
        name="rsa_private_key",
        pattern=re.compile(r"-----BEGIN RSA PRIVATE KEY-----", re.IGNORECASE),
        description="RSA Private Key",
    ),
    SecretPattern(
        name="openssh_private_key",
        pattern=re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----", re.IGNORECASE),
        description="OpenSSH Private Key",
    ),
    SecretPattern(
        name="ec_private_key",
        pattern=re.compile(r"-----BEGIN EC PRIVATE KEY-----", re.IGNORECASE),
        description="EC Private Key",
    ),
    SecretPattern(
        name="pgp_private_key",
        pattern=re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----", re.IGNORECASE),
        description="PGP Private Key",
    ),
    SecretPattern(
        name="dsa_private_key",
        pattern=re.compile(r"-----BEGIN DSA PRIVATE KEY-----", re.IGNORECASE),
        description="DSA Private Key",
    ),
    SecretPattern(
        name="encrypted_private_key",
        pattern=re.compile(r"-----BEGIN ENCRYPTED PRIVATE KEY-----", re.IGNORECASE),
        description="Encrypted Private Key",
    ),
    # Database URLs
    SecretPattern(
        name="postgres_url",
        pattern=re.compile(
            r"postgres(?:ql)?://[^:]+:([^@]+)@[^/]+/[^\s'\"]+",
            re.IGNORECASE,
        ),
        description="PostgreSQL Connection URL with password",
    ),
    SecretPattern(
        name="mysql_url",
        pattern=re.compile(
            r"mysql://[^:]+:([^@]+)@[^/]+/[^\s'\"]+",
            re.IGNORECASE,
        ),
        description="MySQL Connection URL with password",
    ),
    SecretPattern(
        name="mongodb_url",
        pattern=re.compile(
            r"mongodb(?:\+srv)?://[^:]+:([^@]+)@[^/]+",
            re.IGNORECASE,
        ),
        description="MongoDB Connection URL with password",
    ),
    SecretPattern(
        name="redis_url",
        pattern=re.compile(
            r"redis://[^:]*:([^@]+)@[^/]+",
            re.IGNORECASE,
        ),
        description="Redis Connection URL with password",
    ),
    # Generic patterns
    SecretPattern(
        name="password_assignment",
        pattern=re.compile(
            r"""(?:password|passwd|pwd|secret|token|api[_\-]?key|apikey|auth[_\-]?token|access[_\-]?token|bearer|credentials?)[\s]*[=:]\s*['\"]([^'\"]{8,})['\"]""",
            re.IGNORECASE,
        ),
        description="Password or secret assignment",
        confidence=0.8,
    ),
    SecretPattern(
        name="bearer_token",
        pattern=re.compile(r"[Bb]earer\s+[a-zA-Z0-9\-_\.]+", re.IGNORECASE),
        description="Bearer Token in header",
        confidence=0.75,
    ),
    SecretPattern(
        name="basic_auth",
        pattern=re.compile(r"[Bb]asic\s+[a-zA-Z0-9+/=]{20,}", re.IGNORECASE),
        description="Basic Auth credentials",
        confidence=0.9,
    ),
    # .env patterns
    SecretPattern(
        name="env_secret",
        pattern=re.compile(
            r"^(?:DB_PASSWORD|DATABASE_URL|SECRET_KEY|API_KEY|AWS_SECRET|PRIVATE_KEY|JWT_SECRET|SESSION_SECRET|ENCRYPTION_KEY|AUTH_SECRET)[\s]*=[\s]*(.+)$",
            re.MULTILINE | re.IGNORECASE,
        ),
        description="Secret in .env file",
    ),
    # NPM tokens
    SecretPattern(
        name="npm_token",
        pattern=re.compile(r"//registry\.npmjs\.org/:_authToken=(.+)", re.IGNORECASE),
        description="NPM Registry Token",
    ),
    # PyPI tokens
    SecretPattern(
        name="pypi_token",
        pattern=re.compile(r"pypi-[a-zA-Z0-9_-]{100,}", re.IGNORECASE),
        description="PyPI API Token",
    ),
    # Azure
    SecretPattern(
        name="azure_storage_key",
        pattern=re.compile(
            r"DefaultEndpointsProtocol=https;AccountName=[^;]+;AccountKey=([^;]+)",
            re.IGNORECASE,
        ),
        description="Azure Storage Account Key",
    ),
    # Discord
    SecretPattern(
        name="discord_token",
        pattern=re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27}", re.IGNORECASE),
        description="Discord Bot Token",
    ),
    SecretPattern(
        name="discord_webhook",
        pattern=re.compile(
            r"https://discord(?:app)?\.com/api/webhooks/\d+/[a-zA-Z0-9_-]+",
            re.IGNORECASE,
        ),
        description="Discord Webhook URL",
    ),
    # High entropy strings (generic)
    SecretPattern(
        name="high_entropy_string",
        pattern=re.compile(
            r"""['\"]([a-zA-Z0-9+/=_-]{32,})['\"]""",
            re.IGNORECASE,
        ),
        description="High entropy string (possible secret)",
        confidence=0.4,  # Low confidence - needs additional context
    ),
]

# Files that should never have their contents sent
SENSITIVE_FILENAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    "credentials.json",
    "service-account.json",
    "secrets.yaml",
    "secrets.yml",
    "secrets.json",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    "htpasswd",
    ".htpasswd",
    "shadow",
    "passwd",
}

# File extensions that should never be sent
SENSITIVE_EXTENSIONS: set[str] = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".cer",
    ".crt",
}


def is_sensitive_file(file_path: str) -> bool:
    """
    Check if a file is inherently sensitive and should not be sent.

    Args:
        file_path: Path to the file

    Returns:
        True if the file is sensitive
    """
    path = Path(file_path)
    filename = path.name.lower()

    # Check filename
    if filename in SENSITIVE_FILENAMES:
        return True

    # Check extension
    if path.suffix.lower() in SENSITIVE_EXTENSIONS:
        return True

    # Check for private key files
    if "private" in filename and ("key" in filename or path.suffix in {".pem", ".key"}):
        return True

    return False


def calculate_entropy(data: str) -> float:
    """
    Calculate Shannon entropy of a string.

    Higher entropy indicates more randomness (potential secret).

    Args:
        data: String to analyze

    Returns:
        Entropy value (0-8 for ASCII)
    """
    if not data:
        return 0.0

    import math
    from collections import Counter

    counts = Counter(data)
    length = len(data)

    entropy = 0.0
    for count in counts.values():
        if count > 0:
            freq = count / length
            entropy -= freq * math.log2(freq)

    return entropy


def scan_content(
    content: str,
    file_path: str = "",
    min_confidence: float = 0.5,
) -> list[RedactionEntry]:
    """
    Scan content for secrets.

    Args:
        content: Content to scan
        file_path: Path to file (for reporting)
        min_confidence: Minimum confidence threshold

    Returns:
        List of RedactionEntry for found secrets
    """
    entries: list[RedactionEntry] = []
    lines = content.splitlines()

    for pattern_def in SECRET_PATTERNS:
        if pattern_def.confidence < min_confidence:
            continue

        for match in pattern_def.pattern.finditer(content):
            # Find line number
            line_start = content.count("\n", 0, match.start()) + 1

            # Check false positive patterns
            is_false_positive = False
            for fp_pattern in pattern_def.false_positive_patterns:
                if fp_pattern.search(match.group(0)):
                    is_false_positive = True
                    break

            if is_false_positive:
                continue

            # For high entropy pattern, verify entropy
            if pattern_def.name == "high_entropy_string":
                matched_str = match.group(1) if match.lastindex else match.group(0)
                entropy = calculate_entropy(matched_str)
                if entropy < 4.5:  # Require high entropy
                    continue

            entries.append(
                RedactionEntry(
                    file_path=file_path,
                    line_number=line_start,
                    pattern_name=pattern_def.name,
                    original_length=len(match.group(0)),
                    redacted_placeholder=f"[REDACTED:{pattern_def.name}]",
                    confidence=pattern_def.confidence,
                )
            )

    return entries


def redact_content(
    content: str,
    entries: list[RedactionEntry] | None = None,
    min_confidence: float = 0.5,
) -> tuple[str, list[RedactionEntry]]:
    """
    Redact secrets from content.

    Args:
        content: Content to redact
        entries: Pre-computed entries (if None, will scan)
        min_confidence: Minimum confidence threshold

    Returns:
        Tuple of (redacted_content, redaction_entries)
    """
    if entries is None:
        entries = scan_content(content, min_confidence=min_confidence)

    if not entries:
        return content, []

    # Sort by position (reverse order for replacement)
    redacted = content

    for pattern_def in SECRET_PATTERNS:
        if pattern_def.confidence < min_confidence:
            continue

        def replace_match(match: re.Match) -> str:
            return f"[REDACTED:{pattern_def.name}]"

        redacted = pattern_def.pattern.sub(replace_match, redacted)

    return redacted, entries


def scan_file(
    file_path: Path,
    max_bytes: int = 1_000_000,
    min_confidence: float = 0.5,
) -> list[RedactionEntry]:
    """
    Scan a file for secrets.

    Args:
        file_path: Path to file
        max_bytes: Maximum bytes to read
        min_confidence: Minimum confidence threshold

    Returns:
        List of RedactionEntry for found secrets
    """
    # Check if file is inherently sensitive
    if is_sensitive_file(str(file_path)):
        return [
            RedactionEntry(
                file_path=str(file_path),
                line_number=0,
                pattern_name="sensitive_file",
                original_length=0,
                redacted_placeholder="[SENSITIVE_FILE:entire_file_blocked]",
                confidence=1.0,
            )
        ]

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
    except (OSError, IOError):
        return []

    return scan_content(content, str(file_path), min_confidence)


def create_redaction_report(entries: list[RedactionEntry]) -> RedactionReport:
    """
    Create a summary report of all redactions.

    Args:
        entries: All redaction entries

    Returns:
        RedactionReport summarizing redactions
    """
    files_affected = len(set(e.file_path for e in entries))
    patterns_matched: dict[str, int] = {}

    for entry in entries:
        patterns_matched[entry.pattern_name] = patterns_matched.get(entry.pattern_name, 0) + 1

    return RedactionReport(
        total_redactions=len(entries),
        files_affected=files_affected,
        redactions=entries,
        patterns_matched=patterns_matched,
    )


def get_safe_content(
    content: str,
    file_path: str = "",
    min_confidence: float = 0.5,
) -> tuple[str, RedactionReport]:
    """
    Get content safe for external transmission.

    Scans and redacts all detected secrets.

    Args:
        content: Original content
        file_path: Path to file (for reporting)
        min_confidence: Minimum confidence threshold

    Returns:
        Tuple of (safe_content, redaction_report)
    """
    # Check if entire file should be blocked
    if file_path and is_sensitive_file(file_path):
        entry = RedactionEntry(
            file_path=file_path,
            line_number=0,
            pattern_name="sensitive_file",
            original_length=len(content),
            redacted_placeholder="[SENSITIVE_FILE:entire_content_blocked]",
            confidence=1.0,
        )
        return "[SENSITIVE_FILE:entire_content_blocked]", create_redaction_report([entry])

    entries = scan_content(content, file_path, min_confidence)
    redacted_content, _ = redact_content(content, entries, min_confidence)
    report = create_redaction_report(entries)

    return redacted_content, report
