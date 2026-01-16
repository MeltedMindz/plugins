"""Tests for secret guard."""

import pytest

from api_vault.secret_guard import (
    calculate_entropy,
    create_redaction_report,
    get_safe_content,
    is_sensitive_file,
    redact_content,
    scan_content,
)


class TestIsSensitiveFile:
    """Tests for sensitive file detection."""

    def test_detects_env_file(self):
        """Test .env file detection."""
        assert is_sensitive_file(".env") is True
        assert is_sensitive_file(".env.local") is True
        assert is_sensitive_file(".env.production") is True

    def test_detects_key_files(self):
        """Test key file detection."""
        assert is_sensitive_file("id_rsa") is True
        assert is_sensitive_file("private.key") is True
        assert is_sensitive_file("server.pem") is True

    def test_detects_credentials(self):
        """Test credentials file detection."""
        assert is_sensitive_file("credentials.json") is True
        assert is_sensitive_file("secrets.yaml") is True

    def test_allows_normal_files(self):
        """Test that normal files are allowed."""
        assert is_sensitive_file("index.ts") is False
        assert is_sensitive_file("README.md") is False
        assert is_sensitive_file("package.json") is False


class TestCalculateEntropy:
    """Tests for entropy calculation."""

    def test_high_entropy_for_random(self):
        """Test high entropy for random-looking strings."""
        random_str = "aB3dE5gH7jK9mN1pQ3sT5vW7yZ"
        entropy = calculate_entropy(random_str)
        assert entropy > 4.0

    def test_low_entropy_for_repetitive(self):
        """Test low entropy for repetitive strings."""
        repetitive = "aaaaaaaaaa"
        entropy = calculate_entropy(repetitive)
        assert entropy < 1.0

    def test_empty_string(self):
        """Test empty string returns zero."""
        assert calculate_entropy("") == 0.0


class TestScanContent:
    """Tests for secret scanning."""

    def test_detects_aws_key(self):
        """Test AWS access key detection."""
        content = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        entries = scan_content(content, "config.py")

        assert len(entries) > 0
        aws_entries = [e for e in entries if "aws" in e.pattern_name.lower()]
        assert len(aws_entries) > 0

    def test_detects_github_token(self):
        """Test GitHub token detection."""
        content = 'token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"'
        entries = scan_content(content, "config.py")

        github_entries = [e for e in entries if "github" in e.pattern_name.lower()]
        assert len(github_entries) > 0

    def test_detects_private_key(self):
        """Test private key detection."""
        content = """-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""
        entries = scan_content(content, "key.pem")

        key_entries = [e for e in entries if "private_key" in e.pattern_name.lower()]
        assert len(key_entries) > 0

    def test_detects_jwt(self):
        """Test JWT detection."""
        content = 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"'
        entries = scan_content(content, "auth.py")

        jwt_entries = [e for e in entries if "jwt" in e.pattern_name.lower()]
        assert len(jwt_entries) > 0

    def test_detects_database_url(self):
        """Test database URL with password detection."""
        content = 'DATABASE_URL = "postgres://user:s3cr3tpassword@localhost:5432/mydb"'
        entries = scan_content(content, "config.py")

        db_entries = [e for e in entries if "postgres" in e.pattern_name.lower()]
        assert len(db_entries) > 0

    def test_detects_password_assignment(self):
        """Test password assignment detection."""
        content = 'PASSWORD = "mysecretpassword123"'
        entries = scan_content(content, "settings.py")

        pw_entries = [e for e in entries if "password" in e.pattern_name.lower()]
        assert len(pw_entries) > 0

    def test_no_false_positive_on_normal_code(self):
        """Test that normal code doesn't trigger false positives."""
        content = """
def hello_world():
    return "Hello, World!"

class User:
    def __init__(self, name):
        self.name = name
"""
        entries = scan_content(content, "main.py", min_confidence=0.7)

        # Should have few or no entries
        assert len(entries) < 2

    def test_respects_min_confidence(self):
        """Test minimum confidence filtering."""
        content = 'x = "short"'

        high_conf = scan_content(content, "test.py", min_confidence=0.9)
        low_conf = scan_content(content, "test.py", min_confidence=0.1)

        assert len(high_conf) <= len(low_conf)


class TestRedactContent:
    """Tests for content redaction."""

    def test_redacts_aws_key(self):
        """Test AWS key redaction."""
        content = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
        redacted, entries = redact_content(content)

        assert "AKIAIOSFODNN7EXAMPLE" not in redacted
        assert "[REDACTED" in redacted

    def test_redacts_multiple_secrets(self):
        """Test multiple secret redaction."""
        content = """
API_KEY = "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DATABASE_URL = "postgres://user:mysecret123@host/db"
"""
        redacted, entries = redact_content(content)

        assert "sk-ant" not in redacted
        assert "mysecret123" not in redacted

    def test_preserves_structure(self):
        """Test that redaction preserves code structure."""
        content = """
def connect():
    password = "secret123"
    return db.connect(password)
"""
        redacted, _ = redact_content(content)

        # Should still have function definition
        assert "def connect():" in redacted
        assert "return db.connect" in redacted


class TestCreateRedactionReport:
    """Tests for redaction reporting."""

    def test_creates_summary(self):
        """Test report creation."""
        content = 'api_key = "AKIAIOSFODNN7EXAMPLE"'
        entries = scan_content(content, "config.py")
        report = create_redaction_report(entries)

        assert report.total_redactions >= 1
        assert report.files_affected == 1
        assert len(report.patterns_matched) > 0


class TestGetSafeContent:
    """Tests for safe content retrieval."""

    def test_blocks_sensitive_files(self):
        """Test that sensitive files are completely blocked."""
        content = "SECRET_KEY=abc123"
        safe, report = get_safe_content(content, ".env")

        assert "SECRET_KEY" not in safe
        assert "SENSITIVE_FILE" in safe
        assert report.total_redactions == 1

    def test_redacts_secrets_in_normal_files(self):
        """Test redaction in normal files."""
        content = 'api_key = "AKIAIOSFODNN7EXAMPLE"'
        safe, report = get_safe_content(content, "config.py")

        assert "AKIAIOSFODNN7EXAMPLE" not in safe
        assert report.total_redactions >= 1

    def test_passes_through_clean_content(self):
        """Test that clean content passes through."""
        content = """
def add(a, b):
    return a + b
"""
        safe, report = get_safe_content(content, "math.py", min_confidence=0.9)

        # Should be mostly unchanged
        assert "def add" in safe
        assert "return a + b" in safe
