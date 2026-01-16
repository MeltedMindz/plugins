# Plugin Development Guide

Api Vault supports plugins for extending its functionality. This guide covers how to create and use custom plugins.

## Plugin Types

Api Vault supports four types of plugins:

| Type | Purpose |
|------|---------|
| **Artifact Generator** | Custom artifact generation logic |
| **Signal Detector** | Custom framework/language detection |
| **Secret Pattern** | Custom secret detection patterns |
| **Post Processor** | Transform generated content |

## Quick Start

### Creating a Simple Plugin

Create a Python file in your plugins directory:

```python
# my_plugins.py
from api_vault.plugins import (
    ArtifactGeneratorPlugin,
    SecretPatternPlugin,
    artifact_generator,
    secret_pattern,
)
from api_vault.schemas import ArtifactFamily, RepoIndex, RepoSignals


# Using class-based approach
class MyCustomGenerator(ArtifactGeneratorPlugin):
    @property
    def name(self) -> str:
        return "my-custom-doc"

    @property
    def family(self) -> ArtifactFamily:
        return ArtifactFamily.DOCS

    @property
    def description(self) -> str:
        return "Generates custom documentation"

    def should_generate(self, index: RepoIndex, signals: RepoSignals) -> bool:
        # Only generate for Python projects
        return signals.primary_language == "Python"

    def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
        return f"""Generate custom documentation for {signals.repo_name}.

Context:
{context}

Create comprehensive documentation in Markdown format."""


# Using decorator approach
@artifact_generator("quick-start-guide", ArtifactFamily.DOCS)
def quick_start_generator(index: RepoIndex, signals: RepoSignals, context: str) -> str:
    return f"""Generate a quick start guide for {signals.repo_name}.

Based on the context below, create a beginner-friendly guide.

{context}"""


# Custom secret pattern
@secret_pattern("internal-api-key", r"INTERNAL_KEY_[A-Za-z0-9]{32}", severity="high")
def validate_internal_key(match: str) -> bool:
    # Additional validation logic
    return len(match) > 40
```

### Loading Plugins

Plugins are automatically loaded from:
- `~/.api-vault/plugins/`
- Current directory `./plugins/`

Or load manually:

```python
from api_vault.plugins import load_plugin_from_file, load_plugins_from_directory
from pathlib import Path

# Load a single plugin file
load_plugin_from_file(Path("my_plugins.py"))

# Load all plugins from a directory
load_plugins_from_directory(Path("./plugins"))
```

## Artifact Generator Plugins

Artifact generators create new types of documentation or other artifacts.

### Interface

```python
class ArtifactGeneratorPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this generator."""
        ...

    @property
    @abstractmethod
    def family(self) -> ArtifactFamily:
        """Artifact family this generates."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    @property
    def priority(self) -> int:
        """Priority for ordering (higher = earlier). Default 0."""
        return 0

    @abstractmethod
    def should_generate(self, index: RepoIndex, signals: RepoSignals) -> bool:
        """Determine if this artifact should be generated."""
        ...

    @abstractmethod
    def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
        """Generate the prompt for artifact creation."""
        ...

    def score_artifact(self, index: RepoIndex, signals: RepoSignals) -> ScoreBreakdown:
        """Score this artifact for planning prioritization."""
        ...

    def post_process(self, content: str) -> str:
        """Post-process generated content."""
        return content
```

### Example: Framework-Specific Documentation

```python
class ReactComponentGuide(ArtifactGeneratorPlugin):
    @property
    def name(self) -> str:
        return "react-component-guide"

    @property
    def family(self) -> ArtifactFamily:
        return ArtifactFamily.DOCS

    @property
    def description(self) -> str:
        return "Generates React component documentation"

    @property
    def priority(self) -> int:
        return 20  # High priority

    def should_generate(self, index: RepoIndex, signals: RepoSignals) -> bool:
        # Only for React projects
        return any(f.name == "React" for f in signals.frameworks)

    def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
        return f"""Generate a React component guide for {signals.repo_name}.

Include:
1. Component hierarchy
2. Props documentation
3. State management patterns
4. Best practices used

Context:
{context}"""

    def score_artifact(self, index: RepoIndex, signals: RepoSignals) -> ScoreBreakdown:
        # Higher score for projects with many components
        component_count = sum(
            1 for f in index.files
            if f.path.endswith(('.tsx', '.jsx'))
        )
        leverage = min(10, component_count / 5)

        return ScoreBreakdown(
            reusability=8.0,
            time_saved=7.0,
            leverage=leverage,
            context_cost=4.0,
            gap_weight=6.0,
            total_score=0,
        )
```

## Signal Detector Plugins

Signal detectors identify frameworks, languages, or other characteristics.

### Interface

```python
class SignalDetectorPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this detector."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    @property
    def priority(self) -> int:
        """Detection priority (higher = earlier). Default 0."""
        return 0

    @abstractmethod
    def detect(self, index: RepoIndex) -> dict[str, Any]:
        """Detect signals from repository index."""
        ...
```

### Example: Custom Framework Detection

```python
class InternalFrameworkDetector(SignalDetectorPlugin):
    @property
    def name(self) -> str:
        return "internal-framework"

    @property
    def description(self) -> str:
        return "Detects our internal framework"

    def detect(self, index: RepoIndex) -> dict[str, Any]:
        # Look for framework-specific files
        has_framework = any(
            f.path.endswith("internal.config.json")
            for f in index.files
        )

        if has_framework:
            return {
                "framework": {
                    "name": "InternalFramework",
                    "category": "framework",
                    "confidence": 0.95,
                }
            }
        return {}
```

## Secret Pattern Plugins

Secret patterns add custom secret detection rules.

### Interface

```python
class SecretPatternPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this pattern."""
        ...

    @property
    @abstractmethod
    def pattern(self) -> str:
        """Regex pattern for detection."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    @property
    def severity(self) -> str:
        """Severity level: low, medium, high, critical."""
        return "medium"

    def validate_match(self, match: str) -> bool:
        """Validate a potential match. Return True if real secret."""
        return True
```

### Example: Custom API Key Pattern

```python
class InternalAPIKeyPattern(SecretPatternPlugin):
    @property
    def name(self) -> str:
        return "internal-api-key"

    @property
    def pattern(self) -> str:
        return r"INT_[A-Z0-9]{32}_KEY"

    @property
    def description(self) -> str:
        return "Internal API keys"

    @property
    def severity(self) -> str:
        return "critical"

    def validate_match(self, match: str) -> bool:
        # Must have correct checksum
        key_body = match[4:-4]  # Remove INT_ and _KEY
        return len(key_body) == 32 and key_body.isupper()
```

## Post Processor Plugins

Post processors transform generated content.

### Interface

```python
class PostProcessorPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this processor."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

    @property
    def priority(self) -> int:
        """Processing order (higher = later). Default 0."""
        return 0

    @property
    def applies_to_families(self) -> list[ArtifactFamily] | None:
        """Families this applies to, or None for all."""
        return None

    @abstractmethod
    def process(self, content: str, family: ArtifactFamily, context: dict) -> str:
        """Process generated content."""
        ...
```

### Example: Add Company Header

```python
class CompanyHeaderProcessor(PostProcessorPlugin):
    @property
    def name(self) -> str:
        return "company-header"

    @property
    def description(self) -> str:
        return "Adds company header to documentation"

    @property
    def priority(self) -> int:
        return 100  # Run early

    @property
    def applies_to_families(self) -> list[ArtifactFamily]:
        return [ArtifactFamily.DOCS]

    def process(self, content: str, family: ArtifactFamily, context: dict) -> str:
        header = """<!--
Generated by Api Vault
Company: ACME Corp
Confidential
-->

"""
        return header + content
```

## Plugin Registry

Access the global plugin registry:

```python
from api_vault.plugins import get_registry, reset_registry

# Get registry
registry = get_registry()

# List all plugins
for plugin in registry.list_plugins():
    print(f"{plugin.type}: {plugin.name} - {plugin.description}")

# Get generators for a family
docs_generators = registry.get_generators_for_family(ArtifactFamily.DOCS)

# Reset registry (useful for testing)
reset_registry()
```

## Best Practices

### 1. Use Unique Names

Plugin names must be unique. Use a namespace prefix for organization plugins:

```python
@property
def name(self) -> str:
    return "acme-corp/custom-docs"
```

### 2. Handle Errors Gracefully

Plugins should never crash the main application:

```python
def detect(self, index: RepoIndex) -> dict[str, Any]:
    try:
        # Detection logic
        return {"detected": True}
    except Exception as e:
        logger.warning(f"Detection failed: {e}")
        return {}
```

### 3. Provide Good Descriptions

Descriptions help users understand what plugins do:

```python
@property
def description(self) -> str:
    return "Generates API documentation following OpenAPI 3.0 spec for FastAPI projects"
```

### 4. Use Priority Wisely

- **High priority (50+)**: Framework-specific plugins that should run first
- **Default (0)**: General-purpose plugins
- **Low priority (-50)**: Fallback plugins

### 5. Test Your Plugins

```python
def test_my_generator():
    from api_vault.plugins import get_registry, reset_registry
    from my_plugins import MyCustomGenerator

    reset_registry()  # Clean slate

    gen = MyCustomGenerator()
    assert gen.name == "my-custom-doc"
    assert gen.family == ArtifactFamily.DOCS
```

## Directory Structure

Recommended plugin directory structure:

```
~/.api-vault/
└── plugins/
    ├── __init__.py         # Optional
    ├── company_plugins.py  # Company-specific plugins
    ├── extra_patterns.py   # Additional secret patterns
    └── post_processors.py  # Custom post-processors
```

## Debugging Plugins

Enable debug logging to troubleshoot plugins:

```bash
API_VAULT_DEBUG=1 api-vault scan --repo .
```

View loaded plugins:

```python
from api_vault.plugins import get_registry

for info in get_registry().list_plugins():
    print(f"[{info.type}] {info.name}: {info.description}")
```
