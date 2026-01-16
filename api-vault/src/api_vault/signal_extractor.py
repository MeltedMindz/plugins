"""
Signal extractor for detecting repository characteristics.

Analyzes the repository index to extract signals about:
- Programming languages used
- Frameworks and libraries
- Package managers and build tools
- Documentation maturity
- Testing maturity
- CI/CD configuration
- Security posture
"""

import json
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from api_vault.repo_scanner import get_file_content, get_files_by_pattern, get_key_files
from api_vault.schemas import (
    CIMaturity,
    DocsMaturity,
    FrameworkDetection,
    LanguageStats,
    RepoIndex,
    RepoSignals,
    SecurityMaturity,
    TestingMaturity,
)

# Language detection by extension
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    "py": "Python",
    "js": "JavaScript",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "jsx": "JavaScript",
    "java": "Java",
    "go": "Go",
    "rs": "Rust",
    "c": "C",
    "cpp": "C++",
    "cc": "C++",
    "cxx": "C++",
    "h": "C",
    "hpp": "C++",
    "cs": "C#",
    "rb": "Ruby",
    "php": "PHP",
    "swift": "Swift",
    "kt": "Kotlin",
    "kts": "Kotlin",
    "scala": "Scala",
    "sh": "Shell",
    "bash": "Shell",
    "zsh": "Shell",
    "ps1": "PowerShell",
    "sql": "SQL",
    "graphql": "GraphQL",
    "gql": "GraphQL",
    "r": "R",
    "lua": "Lua",
    "pl": "Perl",
    "ex": "Elixir",
    "exs": "Elixir",
    "erl": "Erlang",
    "clj": "Clojure",
    "hs": "Haskell",
    "ml": "OCaml",
    "fs": "F#",
    "dart": "Dart",
    "vue": "Vue",
    "svelte": "Svelte",
}

# Framework detection patterns
FRAMEWORK_PATTERNS: dict[str, dict] = {
    # Python frameworks
    "Django": {
        "category": "framework",
        "files": ["manage.py", "settings.py", "urls.py"],
        "deps": ["django"],
        "patterns": [r"from django", r"import django"],
    },
    "Flask": {
        "category": "framework",
        "deps": ["flask"],
        "patterns": [r"from flask import", r"Flask\(__name__\)"],
    },
    "FastAPI": {
        "category": "framework",
        "deps": ["fastapi"],
        "patterns": [r"from fastapi import", r"FastAPI\(\)"],
    },
    "Pytest": {
        "category": "tool",
        "files": ["pytest.ini", "conftest.py", "pyproject.toml"],
        "deps": ["pytest"],
        "patterns": [r"def test_", r"import pytest"],
    },
    # JavaScript/TypeScript frameworks
    "React": {
        "category": "framework",
        "deps": ["react", "react-dom"],
        "patterns": [r"import React", r"from ['\"]react['\"]", r"useState", r"useEffect"],
    },
    "Next.js": {
        "category": "framework",
        "files": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "deps": ["next"],
        "dirs": [".next", "pages", "app"],
    },
    "Vue.js": {
        "category": "framework",
        "files": ["vue.config.js", "nuxt.config.js", "nuxt.config.ts"],
        "deps": ["vue"],
        "patterns": [r"<template>", r"createApp"],
    },
    "Angular": {
        "category": "framework",
        "files": ["angular.json", ".angular"],
        "deps": ["@angular/core"],
        "patterns": [r"@Component", r"@NgModule"],
    },
    "Express": {
        "category": "framework",
        "deps": ["express"],
        "patterns": [r"express\(\)", r"app\.get\(", r"app\.post\("],
    },
    "NestJS": {
        "category": "framework",
        "deps": ["@nestjs/core"],
        "patterns": [r"@Module", r"@Controller", r"@Injectable"],
    },
    "Jest": {
        "category": "tool",
        "files": ["jest.config.js", "jest.config.ts"],
        "deps": ["jest"],
        "patterns": [r"describe\(", r"test\(", r"expect\("],
    },
    "Mocha": {
        "category": "tool",
        "files": [".mocharc.js", ".mocharc.json"],
        "deps": ["mocha"],
    },
    "Vitest": {
        "category": "tool",
        "files": ["vitest.config.ts", "vitest.config.js"],
        "deps": ["vitest"],
    },
    # Go frameworks
    "Gin": {
        "category": "framework",
        "deps": ["github.com/gin-gonic/gin"],
        "patterns": [r"gin\.Default\(\)", r"gin\.New\(\)"],
    },
    "Echo": {
        "category": "framework",
        "deps": ["github.com/labstack/echo"],
        "patterns": [r"echo\.New\(\)"],
    },
    # Rust frameworks
    "Actix": {
        "category": "framework",
        "deps": ["actix-web"],
        "patterns": [r"actix_web::", r"HttpServer::new"],
    },
    "Axum": {
        "category": "framework",
        "deps": ["axum"],
        "patterns": [r"axum::", r"Router::new\(\)"],
    },
    # Java frameworks
    "Spring Boot": {
        "category": "framework",
        "files": ["pom.xml", "build.gradle"],
        "deps": ["spring-boot"],
        "patterns": [r"@SpringBootApplication", r"@RestController"],
    },
    # Ruby frameworks
    "Rails": {
        "category": "framework",
        "files": ["Gemfile", "config/routes.rb", "app/controllers"],
        "deps": ["rails"],
        "patterns": [r"class.*<.*ApplicationController"],
    },
    # Database/ORM
    "SQLAlchemy": {
        "category": "library",
        "deps": ["sqlalchemy"],
        "patterns": [r"from sqlalchemy", r"create_engine"],
    },
    "Prisma": {
        "category": "library",
        "files": ["prisma/schema.prisma"],
        "deps": ["@prisma/client", "prisma"],
    },
    "TypeORM": {
        "category": "library",
        "deps": ["typeorm"],
        "patterns": [r"@Entity", r"@Column"],
    },
    "Sequelize": {
        "category": "library",
        "deps": ["sequelize"],
    },
    "Mongoose": {
        "category": "library",
        "deps": ["mongoose"],
        "patterns": [r"mongoose\.Schema", r"mongoose\.model"],
    },
    # Auth
    "Passport.js": {
        "category": "library",
        "deps": ["passport"],
        "patterns": [r"passport\.authenticate"],
    },
    "NextAuth": {
        "category": "library",
        "deps": ["next-auth"],
        "files": ["pages/api/auth/[...nextauth].ts", "app/api/auth/[...nextauth]/route.ts"],
    },
    "Auth0": {
        "category": "service",
        "deps": ["auth0", "@auth0/nextjs-auth0"],
    },
    # Containerization
    "Docker": {
        "category": "tool",
        "files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"],
    },
    "Kubernetes": {
        "category": "tool",
        "files": ["k8s/", "kubernetes/", "helm/"],
        "patterns": [r"apiVersion:.*v1", r"kind:\s*Deployment"],
    },
    # CI/CD
    "GitHub Actions": {
        "category": "tool",
        "files": [".github/workflows/"],
    },
    "GitLab CI": {
        "category": "tool",
        "files": [".gitlab-ci.yml"],
    },
    "CircleCI": {
        "category": "tool",
        "files": [".circleci/config.yml"],
    },
    "Jenkins": {
        "category": "tool",
        "files": ["Jenkinsfile"],
    },
    # API tools
    "OpenAPI": {
        "category": "tool",
        "files": ["openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"],
        "patterns": [r"openapi:\s*['\"]?3\.", r"swagger:\s*['\"]?2\."],
    },
    "GraphQL": {
        "category": "library",
        "deps": ["graphql", "apollo-server", "@apollo/client"],
        "files": ["schema.graphql"],
        "patterns": [r"type Query", r"gql`"],
    },
    # Monitoring
    "Prometheus": {
        "category": "tool",
        "deps": ["prom-client", "prometheus_client"],
        "patterns": [r"prometheus", r"Counter\(", r"Gauge\("],
    },
    "Sentry": {
        "category": "service",
        "deps": ["@sentry/node", "@sentry/react", "sentry-sdk"],
    },
    "Datadog": {
        "category": "service",
        "deps": ["dd-trace", "datadog"],
    },
}

# Package manager detection
PACKAGE_MANAGER_FILES: dict[str, str] = {
    "package.json": "npm",
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "pyproject.toml": "pip/poetry",
    "requirements.txt": "pip",
    "Pipfile": "pipenv",
    "Pipfile.lock": "pipenv",
    "setup.py": "pip",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "Cargo.toml": "cargo",
    "Cargo.lock": "cargo",
    "go.mod": "go modules",
    "go.sum": "go modules",
    "Gemfile": "bundler",
    "Gemfile.lock": "bundler",
    "composer.json": "composer",
    "composer.lock": "composer",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "mix.exs": "mix",
    "pubspec.yaml": "pub",
}

# Build tool detection
BUILD_TOOL_FILES: dict[str, str] = {
    "Makefile": "make",
    "CMakeLists.txt": "cmake",
    "webpack.config.js": "webpack",
    "webpack.config.ts": "webpack",
    "vite.config.js": "vite",
    "vite.config.ts": "vite",
    "rollup.config.js": "rollup",
    "esbuild.config.js": "esbuild",
    "turbo.json": "turborepo",
    "nx.json": "nx",
    "lerna.json": "lerna",
    "tsconfig.json": "typescript",
    "babel.config.js": "babel",
    ".babelrc": "babel",
    "gulpfile.js": "gulp",
    "Gruntfile.js": "grunt",
    "justfile": "just",
    "taskfile.yml": "task",
}


def detect_languages(index: RepoIndex) -> list[LanguageStats]:
    """
    Detect programming languages used in the repository.

    Args:
        index: Repository index

    Returns:
        List of LanguageStats sorted by percentage
    """
    lang_bytes: dict[str, int] = defaultdict(int)
    lang_files: dict[str, int] = defaultdict(int)
    lang_extensions: dict[str, set[str]] = defaultdict(set)

    for file_entry in index.files:
        if file_entry.is_binary:
            continue
        ext = file_entry.extension
        if ext in EXTENSION_TO_LANGUAGE:
            lang = EXTENSION_TO_LANGUAGE[ext]
            lang_bytes[lang] += file_entry.size_bytes
            lang_files[lang] += 1
            lang_extensions[lang].add(ext)

    # Calculate percentages
    total_bytes = sum(lang_bytes.values())
    if total_bytes == 0:
        return []

    stats: list[LanguageStats] = []
    for lang, byte_count in lang_bytes.items():
        stats.append(
            LanguageStats(
                language=lang,
                file_count=lang_files[lang],
                total_bytes=byte_count,
                percentage=round((byte_count / total_bytes) * 100, 2),
                extensions=sorted(lang_extensions[lang]),
            )
        )

    # Sort by percentage descending
    stats.sort(key=lambda x: x.percentage, reverse=True)
    return stats


def detect_frameworks(
    index: RepoIndex,
    repo_path: Path,
) -> list[FrameworkDetection]:
    """
    Detect frameworks and tools used in the repository.

    Args:
        index: Repository index
        repo_path: Path to repository

    Returns:
        List of detected frameworks
    """
    detected: list[FrameworkDetection] = []
    file_paths = {f.path.lower() for f in index.files}
    file_paths_exact = {f.path for f in index.files}

    # Load package.json dependencies if present
    npm_deps: set[str] = set()
    for f in index.files:
        if f.path == "package.json":
            content = get_file_content(repo_path, f, max_bytes=65536)
            if content:
                try:
                    pkg = json.loads(content)
                    npm_deps.update(pkg.get("dependencies", {}).keys())
                    npm_deps.update(pkg.get("devDependencies", {}).keys())
                except json.JSONDecodeError:
                    pass
            break

    # Load pyproject.toml dependencies if present
    py_deps: set[str] = set()
    for f in index.files:
        if f.path == "pyproject.toml":
            content = get_file_content(repo_path, f, max_bytes=65536)
            if content:
                # Simple TOML parsing for dependencies
                in_deps_section = False
                for line in content.splitlines():
                    if "[project.dependencies]" in line or "[tool.poetry.dependencies]" in line:
                        in_deps_section = True
                        continue
                    if in_deps_section:
                        if line.startswith("["):
                            in_deps_section = False
                            continue
                        # Extract package name
                        match = re.match(r'^[\s]*["\']?([a-zA-Z0-9_-]+)', line)
                        if match:
                            py_deps.add(match.group(1).lower())
            break

    # Load requirements.txt if present
    for f in index.files:
        if f.path == "requirements.txt":
            content = get_file_content(repo_path, f, max_bytes=65536)
            if content:
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        # Extract package name (before any version specifier)
                        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                        if match:
                            py_deps.add(match.group(1).lower())
            break

    # Load Cargo.toml dependencies if present
    cargo_deps: set[str] = set()
    for f in index.files:
        if f.path == "Cargo.toml":
            content = get_file_content(repo_path, f, max_bytes=65536)
            if content:
                in_deps = False
                for line in content.splitlines():
                    if "[dependencies]" in line or "[dev-dependencies]" in line:
                        in_deps = True
                        continue
                    if in_deps:
                        if line.startswith("["):
                            in_deps = False
                            continue
                        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
                        if match:
                            cargo_deps.add(match.group(1).lower())
            break

    # Load go.mod dependencies if present
    go_deps: set[str] = set()
    for f in index.files:
        if f.path == "go.mod":
            content = get_file_content(repo_path, f, max_bytes=65536)
            if content:
                for line in content.splitlines():
                    if line.strip().startswith("require") or "\t" in line:
                        # Extract module path
                        match = re.search(r"(github\.com/[^\s]+|[a-zA-Z0-9./]+)", line)
                        if match:
                            go_deps.add(match.group(1).lower())
            break

    all_deps = npm_deps | py_deps | cargo_deps | go_deps

    for framework_name, config in FRAMEWORK_PATTERNS.items():
        evidence: list[str] = []
        confidence = 0.0

        # Check for specific files
        if "files" in config:
            for file_pattern in config["files"]:
                file_pattern_lower = file_pattern.lower()
                if file_pattern_lower.endswith("/"):
                    # Directory check
                    for fp in file_paths:
                        if fp.startswith(file_pattern_lower) or f"/{file_pattern_lower}" in fp:
                            evidence.append(f"Directory: {file_pattern}")
                            confidence += 0.3
                            break
                else:
                    # File check
                    if file_pattern_lower in file_paths or file_pattern in file_paths_exact:
                        evidence.append(f"File: {file_pattern}")
                        confidence += 0.4

        # Check for dependencies
        if "deps" in config:
            for dep in config["deps"]:
                dep_lower = dep.lower()
                if dep_lower in all_deps or dep in all_deps:
                    evidence.append(f"Dependency: {dep}")
                    confidence += 0.5

        # Check for code patterns (sample a few files)
        if "patterns" in config and confidence > 0:
            # Only check patterns if we have some initial evidence
            sample_files = [f for f in index.files if not f.is_binary][:50]
            for file_entry in sample_files:
                content = get_file_content(repo_path, file_entry, max_bytes=4096)
                if content:
                    for pattern in config["patterns"]:
                        if re.search(pattern, content):
                            evidence.append(f"Pattern in {file_entry.path}")
                            confidence += 0.2
                            break  # One pattern match per file is enough

        # Normalize confidence
        confidence = min(confidence, 1.0)

        if confidence >= 0.3:
            detected.append(
                FrameworkDetection(
                    name=framework_name,
                    category=config.get("category", "framework"),
                    confidence=round(confidence, 2),
                    evidence=evidence[:5],  # Limit evidence entries
                )
            )

    # Sort by confidence
    detected.sort(key=lambda x: x.confidence, reverse=True)
    return detected


def detect_package_managers(index: RepoIndex) -> list[str]:
    """Detect package managers used in the repository."""
    managers: set[str] = set()
    for file_entry in index.files:
        filename = Path(file_entry.path).name
        if filename in PACKAGE_MANAGER_FILES:
            managers.add(PACKAGE_MANAGER_FILES[filename])
    return sorted(managers)


def detect_build_tools(index: RepoIndex) -> list[str]:
    """Detect build tools used in the repository."""
    tools: set[str] = set()
    for file_entry in index.files:
        filename = Path(file_entry.path).name
        if filename in BUILD_TOOL_FILES:
            tools.add(BUILD_TOOL_FILES[filename])
    return sorted(tools)


def assess_docs_maturity(index: RepoIndex, repo_path: Path) -> DocsMaturity:
    """Assess documentation maturity of the repository."""
    key_files = get_key_files(index)

    # Check for docs folder
    has_docs_folder = any(
        f.path.lower().startswith(("docs/", "doc/", "documentation/")) for f in index.files
    )

    # Check for API docs
    has_api_docs = any(
        f.path.lower().endswith(("openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"))
        or "api" in f.path.lower() and f.path.lower().endswith((".md", ".rst"))
        for f in index.files
    )

    # Check for architecture docs
    has_architecture_docs = any(
        "architecture" in f.path.lower() or "design" in f.path.lower()
        for f in index.files
        if f.path.lower().endswith((".md", ".rst"))
    )

    # Count doc files
    doc_extensions = {".md", ".rst", ".txt", ".adoc"}
    doc_file_count = sum(1 for f in index.files if f.extension in doc_extensions)

    readme_size = key_files["readme"].size_bytes if key_files["readme"] else 0

    # Calculate maturity score
    score = 0.0
    if key_files["readme"]:
        score += 0.25
        if readme_size > 1000:
            score += 0.1
    if key_files["license"]:
        score += 0.1
    if key_files["contributing"]:
        score += 0.15
    if key_files["changelog"]:
        score += 0.1
    if has_docs_folder:
        score += 0.15
    if has_api_docs:
        score += 0.1
    if has_architecture_docs:
        score += 0.05

    return DocsMaturity(
        has_readme=key_files["readme"] is not None,
        has_contributing=key_files["contributing"] is not None,
        has_changelog=key_files["changelog"] is not None,
        has_license=key_files["license"] is not None,
        has_docs_folder=has_docs_folder,
        has_api_docs=has_api_docs,
        has_architecture_docs=has_architecture_docs,
        readme_size_bytes=readme_size,
        doc_file_count=doc_file_count,
        maturity_score=round(min(score, 1.0), 2),
    )


def assess_testing_maturity(index: RepoIndex, frameworks: list[FrameworkDetection]) -> TestingMaturity:
    """Assess testing maturity of the repository."""
    # Check for test folders
    test_patterns = ["test/", "tests/", "__tests__/", "spec/", "specs/"]
    has_test_folder = any(
        any(f.path.lower().startswith(pattern) for pattern in test_patterns) for f in index.files
    )

    # Check for test config files
    test_configs = [
        "pytest.ini",
        "conftest.py",
        "jest.config.js",
        "jest.config.ts",
        "vitest.config.ts",
        ".mocharc.js",
        "karma.conf.js",
        "phpunit.xml",
    ]
    has_test_config = any(
        Path(f.path).name.lower() in [c.lower() for c in test_configs] for f in index.files
    )

    # Extract test frameworks from detected frameworks
    test_framework_names = ["Pytest", "Jest", "Mocha", "Vitest"]
    test_frameworks = [f.name for f in frameworks if f.name in test_framework_names]

    # Count test files
    test_file_patterns = ["test_", "_test.", ".test.", ".spec.", "_spec."]
    test_file_count = sum(
        1
        for f in index.files
        if any(pattern in f.path.lower() for pattern in test_file_patterns)
    )

    # Calculate maturity score
    score = 0.0
    if has_test_folder:
        score += 0.3
    if has_test_config:
        score += 0.2
    if test_frameworks:
        score += 0.2
    if test_file_count > 0:
        score += min(test_file_count / 20, 0.3)  # Cap at 0.3 for file count

    return TestingMaturity(
        has_test_folder=has_test_folder,
        has_test_config=has_test_config,
        test_frameworks=test_frameworks,
        test_file_count=test_file_count,
        maturity_score=round(min(score, 1.0), 2),
    )


def assess_ci_maturity(index: RepoIndex, frameworks: list[FrameworkDetection]) -> CIMaturity:
    """Assess CI/CD maturity of the repository."""
    ci_platforms: list[str] = []

    # Check for CI config files
    ci_checks = [
        (".github/workflows/", "GitHub Actions"),
        (".gitlab-ci.yml", "GitLab CI"),
        (".circleci/", "CircleCI"),
        ("Jenkinsfile", "Jenkins"),
        (".travis.yml", "Travis CI"),
        ("azure-pipelines.yml", "Azure Pipelines"),
        (".drone.yml", "Drone"),
        ("bitbucket-pipelines.yml", "Bitbucket Pipelines"),
    ]

    for pattern, platform in ci_checks:
        if pattern.endswith("/"):
            if any(f.path.startswith(pattern) for f in index.files):
                ci_platforms.append(platform)
        else:
            if any(f.path == pattern for f in index.files):
                ci_platforms.append(platform)

    has_ci_config = len(ci_platforms) > 0

    # Check for deployment config
    deploy_patterns = ["deploy/", "deployment/", "k8s/", "kubernetes/", "helm/", "terraform/"]
    has_deployment_config = any(
        any(f.path.lower().startswith(pattern) for pattern in deploy_patterns) for f in index.files
    )

    # Check for Docker
    has_docker = any(
        f.path.lower() in ["dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml"]
        or f.path.lower().startswith("docker/")
        for f in index.files
    )

    # Check for Kubernetes
    has_kubernetes = any(
        f.name == "Kubernetes" for f in frameworks
    ) or any(
        f.path.lower().startswith(("k8s/", "kubernetes/", "helm/")) for f in index.files
    )

    # Calculate maturity score
    score = 0.0
    if has_ci_config:
        score += 0.4
    if has_deployment_config:
        score += 0.2
    if has_docker:
        score += 0.2
    if has_kubernetes:
        score += 0.2

    return CIMaturity(
        has_ci_config=has_ci_config,
        ci_platforms=ci_platforms,
        has_deployment_config=has_deployment_config,
        has_docker=has_docker,
        has_kubernetes=has_kubernetes,
        maturity_score=round(min(score, 1.0), 2),
    )


def assess_security_maturity(index: RepoIndex) -> SecurityMaturity:
    """Assess security maturity of the repository."""
    key_files = get_key_files(index)

    has_security_policy = key_files["security"] is not None or any(
        f.path.lower() == ".github/security.md" for f in index.files
    )

    has_dependabot = any(
        f.path.lower() in [".github/dependabot.yml", ".github/dependabot.yaml"] for f in index.files
    )

    has_codeowners = any(f.path.lower() in ["codeowners", ".github/codeowners"] for f in index.files)

    has_env_example = key_files["env_example"] is not None

    # Calculate maturity score
    score = 0.0
    if has_security_policy:
        score += 0.3
    if has_dependabot:
        score += 0.25
    if has_codeowners:
        score += 0.2
    if has_env_example:
        score += 0.25

    return SecurityMaturity(
        has_security_policy=has_security_policy,
        has_dependabot=has_dependabot,
        has_codeowners=has_codeowners,
        has_env_example=has_env_example,
        secrets_in_code_risk=0.0,  # Will be updated by secret_guard
        maturity_score=round(min(score, 1.0), 2),
    )


def detect_project_characteristics(
    index: RepoIndex,
    frameworks: list[FrameworkDetection],
) -> dict[str, bool]:
    """Detect high-level project characteristics."""
    chars: dict[str, bool] = {
        "is_monorepo": False,
        "has_api": False,
        "has_web_ui": False,
        "has_cli": False,
        "has_database": False,
        "has_auth": False,
    }

    # Monorepo detection
    monorepo_indicators = ["lerna.json", "pnpm-workspace.yaml", "turbo.json", "nx.json"]
    if any(Path(f.path).name in monorepo_indicators for f in index.files):
        chars["is_monorepo"] = True
    if any(f.path.startswith("packages/") for f in index.files):
        chars["is_monorepo"] = True

    # API detection
    api_frameworks = ["Express", "FastAPI", "Flask", "Django", "NestJS", "Gin", "Echo", "Actix", "Axum", "Spring Boot"]
    if any(f.name in api_frameworks for f in frameworks):
        chars["has_api"] = True
    if any("api" in f.path.lower() for f in index.files if f.path.endswith((".py", ".ts", ".js", ".go"))):
        chars["has_api"] = True

    # Web UI detection
    ui_frameworks = ["React", "Vue.js", "Angular", "Next.js", "Svelte"]
    if any(f.name in ui_frameworks for f in frameworks):
        chars["has_web_ui"] = True

    # CLI detection
    cli_indicators = ["cli.py", "cli.ts", "cli.js", "main.go", "bin/"]
    for f in index.files:
        if any(f.path.lower().endswith(ind) or f.path.lower().startswith(ind) for ind in cli_indicators):
            chars["has_cli"] = True
            break

    # Database detection
    db_frameworks = ["SQLAlchemy", "Prisma", "TypeORM", "Sequelize", "Mongoose"]
    if any(f.name in db_frameworks for f in frameworks):
        chars["has_database"] = True
    db_files = ["migrations/", "schema.prisma", "alembic/", "models/"]
    if any(any(f.path.lower().startswith(db) for db in db_files) for f in index.files):
        chars["has_database"] = True

    # Auth detection
    auth_frameworks = ["Passport.js", "NextAuth", "Auth0"]
    if any(f.name in auth_frameworks for f in frameworks):
        chars["has_auth"] = True
    auth_patterns = ["auth/", "login", "authenticate", "jwt", "oauth"]
    if any(any(p in f.path.lower() for p in auth_patterns) for f in index.files):
        chars["has_auth"] = True

    return chars


def identify_gaps(
    docs_maturity: DocsMaturity,
    testing_maturity: TestingMaturity,
    ci_maturity: CIMaturity,
    security_maturity: SecurityMaturity,
    characteristics: dict[str, bool],
) -> list[str]:
    """Identify gaps and areas for improvement."""
    gaps: list[str] = []

    # Documentation gaps
    if not docs_maturity.has_readme:
        gaps.append("Missing README documentation")
    elif docs_maturity.readme_size_bytes < 500:
        gaps.append("README is minimal and could be expanded")

    if not docs_maturity.has_contributing:
        gaps.append("No CONTRIBUTING guide for new contributors")

    if not docs_maturity.has_changelog:
        gaps.append("No CHANGELOG to track version history")

    if not docs_maturity.has_architecture_docs:
        gaps.append("No architecture documentation")

    if characteristics.get("has_api") and not docs_maturity.has_api_docs:
        gaps.append("API exists but lacks documentation")

    # Testing gaps
    if not testing_maturity.has_test_folder:
        gaps.append("No test directory found")

    if testing_maturity.test_file_count < 5:
        gaps.append("Limited test coverage")

    if not testing_maturity.test_frameworks:
        gaps.append("No test framework configured")

    # CI/CD gaps
    if not ci_maturity.has_ci_config:
        gaps.append("No CI/CD pipeline configured")

    if not ci_maturity.has_docker:
        gaps.append("No containerization (Docker) setup")

    # Security gaps
    if not security_maturity.has_security_policy:
        gaps.append("No SECURITY policy or vulnerability reporting process")

    if not security_maturity.has_dependabot:
        gaps.append("No automated dependency updates (Dependabot)")

    if not security_maturity.has_env_example:
        gaps.append("No .env.example for environment configuration")

    if characteristics.get("has_auth"):
        gaps.append("Authentication present but security documentation may be lacking")

    return gaps


def extract_signals(
    index: RepoIndex,
    repo_path: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> RepoSignals:
    """
    Extract all signals from a repository.

    Args:
        index: Repository index
        repo_path: Path to repository
        progress_callback: Optional progress callback

    Returns:
        RepoSignals with all extracted information
    """
    if progress_callback:
        progress_callback("Detecting languages...")

    languages = detect_languages(index)
    primary_language = languages[0].language if languages else None

    if progress_callback:
        progress_callback("Detecting frameworks...")

    frameworks = detect_frameworks(index, repo_path)

    if progress_callback:
        progress_callback("Detecting tools...")

    package_managers = detect_package_managers(index)
    build_tools = detect_build_tools(index)

    if progress_callback:
        progress_callback("Assessing maturity...")

    docs_maturity = assess_docs_maturity(index, repo_path)
    testing_maturity = assess_testing_maturity(index, frameworks)
    ci_maturity = assess_ci_maturity(index, frameworks)
    security_maturity = assess_security_maturity(index)

    if progress_callback:
        progress_callback("Analyzing characteristics...")

    characteristics = detect_project_characteristics(index, frameworks)

    if progress_callback:
        progress_callback("Identifying gaps...")

    gaps = identify_gaps(
        docs_maturity,
        testing_maturity,
        ci_maturity,
        security_maturity,
        characteristics,
    )

    return RepoSignals(
        repo_path=str(repo_path),
        repo_name=repo_path.name,
        primary_language=primary_language,
        languages=languages,
        frameworks=frameworks,
        package_managers=package_managers,
        build_tools=build_tools,
        docs_maturity=docs_maturity,
        testing_maturity=testing_maturity,
        ci_maturity=ci_maturity,
        security_maturity=security_maturity,
        is_monorepo=characteristics["is_monorepo"],
        has_api=characteristics["has_api"],
        has_web_ui=characteristics["has_web_ui"],
        has_cli=characteristics["has_cli"],
        has_database=characteristics["has_database"],
        has_auth=characteristics["has_auth"],
        identified_gaps=gaps,
    )
