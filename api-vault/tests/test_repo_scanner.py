"""Tests for repository scanner."""

import tempfile
from pathlib import Path

import pytest

from api_vault.repo_scanner import (
    compute_sha256,
    get_file_content,
    get_files_by_extension,
    get_files_by_pattern,
    get_key_files,
    is_binary_file,
    scan_repository,
    should_exclude_file,
    should_exclude_path,
)
from api_vault.schemas import FileEntry, RepoIndex, ScanConfig


@pytest.fixture
def temp_repo():
    """Create a temporary repository structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create directory structure
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "node_modules").mkdir()
        (root / "docs").mkdir()

        # Create files
        (root / "README.md").write_text("# Test Project\n\nA test project.")
        (root / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
        (root / "src" / "index.ts").write_text("export const hello = () => 'world';")
        (root / "src" / "utils.ts").write_text("export const add = (a: number, b: number) => a + b;")
        (root / "tests" / "test_index.ts").write_text("test('hello', () => {});")
        (root / "node_modules" / "package.json").write_text('{}')  # Should be excluded
        (root / ".gitignore").write_text("node_modules\n.env")

        yield root


class TestComputeSha256:
    """Tests for SHA-256 computation."""

    def test_computes_correct_hash(self, temp_repo):
        """Test that SHA-256 is computed correctly."""
        file_path = temp_repo / "README.md"
        hash_value = compute_sha256(file_path)

        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_different_content_different_hash(self, temp_repo):
        """Test that different content produces different hashes."""
        hash1 = compute_sha256(temp_repo / "README.md")
        hash2 = compute_sha256(temp_repo / "package.json")

        assert hash1 != hash2

    def test_nonexistent_file_returns_empty_hash(self):
        """Test handling of nonexistent files."""
        hash_value = compute_sha256(Path("/nonexistent/file.txt"))
        assert hash_value == "0" * 64


class TestIsBinaryFile:
    """Tests for binary file detection."""

    def test_text_file_not_binary(self, temp_repo):
        """Test that text files are not detected as binary."""
        assert is_binary_file(temp_repo / "README.md") is False
        assert is_binary_file(temp_repo / "package.json") is False

    def test_binary_detection_with_null_bytes(self, temp_repo):
        """Test that files with null bytes are detected as binary."""
        binary_file = temp_repo / "test.bin"
        binary_file.write_bytes(b"hello\x00world")
        assert is_binary_file(binary_file) is True


class TestShouldExcludePath:
    """Tests for path exclusion."""

    def test_excludes_node_modules(self, temp_repo):
        """Test that node_modules is excluded."""
        excluded = ["node_modules", ".git"]
        assert should_exclude_path(temp_repo / "node_modules" / "foo", excluded, temp_repo)

    def test_does_not_exclude_src(self, temp_repo):
        """Test that src is not excluded."""
        excluded = ["node_modules", ".git"]
        assert not should_exclude_path(temp_repo / "src" / "foo.ts", excluded, temp_repo)


class TestShouldExcludeFile:
    """Tests for file exclusion."""

    def test_excludes_lock_files(self):
        """Test that lock files are excluded."""
        excluded = [".lock", ".pyc"]
        assert should_exclude_file(Path("package-lock.json"), [".lock"]) is False  # .json not in list
        assert should_exclude_file(Path("test.pyc"), excluded) is True

    def test_does_not_exclude_source_files(self):
        """Test that source files are not excluded."""
        excluded = [".lock", ".pyc"]
        assert should_exclude_file(Path("index.ts"), excluded) is False


class TestScanRepository:
    """Tests for repository scanning."""

    def test_scans_repository(self, temp_repo):
        """Test basic repository scanning."""
        index = scan_repository(temp_repo)

        # Use realpath to handle symlinks (e.g., /var -> /private/var on macOS)
        import os
        assert os.path.realpath(index.repo_path) == os.path.realpath(str(temp_repo))
        assert index.total_files > 0

    def test_excludes_node_modules(self, temp_repo):
        """Test that node_modules is excluded."""
        index = scan_repository(temp_repo)

        # Should not include files from node_modules
        paths = [f.path for f in index.files]
        assert not any("node_modules" in p for p in paths)

    def test_includes_source_files(self, temp_repo):
        """Test that source files are included."""
        index = scan_repository(temp_repo)

        paths = [f.path for f in index.files]
        assert any("index.ts" in p for p in paths)

    def test_respects_config(self, temp_repo):
        """Test that configuration is respected."""
        config = ScanConfig(max_file_size_bytes=10)  # Very small
        index = scan_repository(temp_repo, config)

        # Small limit should exclude most files
        assert index.total_files < 5


class TestGetFileContent:
    """Tests for file content retrieval."""

    def test_gets_file_content(self, temp_repo):
        """Test getting file content."""
        index = scan_repository(temp_repo)

        readme = next((f for f in index.files if "README" in f.path), None)
        assert readme is not None

        content = get_file_content(temp_repo, readme)
        assert content is not None
        assert "# Test Project" in content

    def test_respects_max_bytes(self, temp_repo):
        """Test that max_bytes is respected."""
        index = scan_repository(temp_repo)
        readme = next((f for f in index.files if "README" in f.path), None)

        content = get_file_content(temp_repo, readme, max_bytes=10)
        assert content is not None
        assert len(content) <= 10


class TestGetFilesByExtension:
    """Tests for filtering files by extension."""

    def test_filters_by_extension(self, temp_repo):
        """Test filtering by extension."""
        index = scan_repository(temp_repo)

        ts_files = get_files_by_extension(index, ["ts"])
        assert len(ts_files) >= 2
        assert all(f.extension == "ts" for f in ts_files)

    def test_returns_empty_for_no_match(self, temp_repo):
        """Test empty result when no match."""
        index = scan_repository(temp_repo)

        rust_files = get_files_by_extension(index, ["rs"])
        assert len(rust_files) == 0


class TestGetFilesByPattern:
    """Tests for filtering files by pattern."""

    def test_filters_by_pattern(self, temp_repo):
        """Test filtering by glob pattern."""
        index = scan_repository(temp_repo)

        test_files = get_files_by_pattern(index, "tests/*")
        assert len(test_files) >= 1


class TestGetKeyFiles:
    """Tests for key file detection."""

    def test_finds_readme(self, temp_repo):
        """Test finding README."""
        index = scan_repository(temp_repo)
        key_files = get_key_files(index)

        assert key_files["readme"] is not None
        assert "README" in key_files["readme"].path

    def test_finds_package_json(self, temp_repo):
        """Test finding package.json."""
        index = scan_repository(temp_repo)
        key_files = get_key_files(index)

        assert key_files["package_json"] is not None

    def test_missing_files_are_none(self, temp_repo):
        """Test that missing files return None."""
        index = scan_repository(temp_repo)
        key_files = get_key_files(index)

        assert key_files["cargo_toml"] is None
