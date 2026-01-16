"""
Plugin architecture for Api Vault.

Allows users to extend functionality with custom:
- Artifact generators (new artifact types)
- Signal detectors (new framework/language detection)
- Secret patterns (custom secret detection)
- Post-processors (transform generated content)
"""

import importlib
import importlib.util
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

from api_vault.schemas import (
    ArtifactFamily,
    PlanJob,
    RepoIndex,
    RepoSignals,
    ScoreBreakdown,
)

logger = logging.getLogger(__name__)


# --- Plugin Interfaces ---


class ArtifactGeneratorPlugin(ABC):
    """Base class for custom artifact generators."""

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
        """
        Determine if this artifact should be generated for the given repo.

        Args:
            index: Repository file index
            signals: Extracted signals about the repo

        Returns:
            True if this artifact is relevant for the repo
        """
        ...

    @abstractmethod
    def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
        """
        Generate the prompt for artifact creation.

        Args:
            index: Repository file index
            signals: Extracted signals about the repo
            context: Prepared context string

        Returns:
            Complete prompt for the LLM
        """
        ...

    def score_artifact(self, index: RepoIndex, signals: RepoSignals) -> ScoreBreakdown:
        """
        Score this artifact for planning prioritization.

        Override to customize scoring logic.
        """
        return ScoreBreakdown(
            reusability=5.0,
            time_saved=5.0,
            leverage=5.0,
            context_cost=5.0,
            gap_weight=5.0,
            total_score=0,
        )

    def post_process(self, content: str) -> str:
        """
        Post-process generated content.

        Override to add custom transformations.
        """
        return content


class SignalDetectorPlugin(ABC):
    """Base class for custom signal detection."""

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
        """
        Detect signals from repository index.

        Args:
            index: Repository file index

        Returns:
            Dictionary of detected signals
        """
        ...


class SecretPatternPlugin(ABC):
    """Base class for custom secret detection patterns."""

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
        """
        Validate a potential match.

        Override to add custom validation logic.
        Returns True if this is a real secret, False for false positive.
        """
        return True


class PostProcessorPlugin(ABC):
    """Base class for content post-processors."""

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
    def process(self, content: str, family: ArtifactFamily, context: dict[str, Any]) -> str:
        """
        Process generated content.

        Args:
            content: Generated content
            family: Artifact family
            context: Additional context (job info, signals, etc.)

        Returns:
            Processed content
        """
        ...


# --- Plugin Registry ---


@dataclass
class PluginInfo:
    """Information about a loaded plugin."""

    name: str
    type: str  # artifact_generator, signal_detector, secret_pattern, post_processor
    source: str  # file path or module name
    description: str = ""
    enabled: bool = True


@dataclass
class PluginRegistry:
    """Central registry for all plugins."""

    artifact_generators: list[ArtifactGeneratorPlugin] = field(default_factory=list)
    signal_detectors: list[SignalDetectorPlugin] = field(default_factory=list)
    secret_patterns: list[SecretPatternPlugin] = field(default_factory=list)
    post_processors: list[PostProcessorPlugin] = field(default_factory=list)

    _plugin_info: list[PluginInfo] = field(default_factory=list)

    def register_artifact_generator(self, plugin: ArtifactGeneratorPlugin) -> None:
        """Register an artifact generator plugin."""
        self.artifact_generators.append(plugin)
        self.artifact_generators.sort(key=lambda p: -p.priority)
        self._plugin_info.append(PluginInfo(
            name=plugin.name,
            type="artifact_generator",
            source="code",
            description=plugin.description,
        ))
        logger.info(f"Registered artifact generator: {plugin.name}")

    def register_signal_detector(self, plugin: SignalDetectorPlugin) -> None:
        """Register a signal detector plugin."""
        self.signal_detectors.append(plugin)
        self.signal_detectors.sort(key=lambda p: -p.priority)
        self._plugin_info.append(PluginInfo(
            name=plugin.name,
            type="signal_detector",
            source="code",
            description=plugin.description,
        ))
        logger.info(f"Registered signal detector: {plugin.name}")

    def register_secret_pattern(self, plugin: SecretPatternPlugin) -> None:
        """Register a secret pattern plugin."""
        self.secret_patterns.append(plugin)
        self._plugin_info.append(PluginInfo(
            name=plugin.name,
            type="secret_pattern",
            source="code",
            description=plugin.description,
        ))
        logger.info(f"Registered secret pattern: {plugin.name}")

    def register_post_processor(self, plugin: PostProcessorPlugin) -> None:
        """Register a post-processor plugin."""
        self.post_processors.append(plugin)
        self.post_processors.sort(key=lambda p: p.priority)
        self._plugin_info.append(PluginInfo(
            name=plugin.name,
            type="post_processor",
            source="code",
            description=plugin.description,
        ))
        logger.info(f"Registered post processor: {plugin.name}")

    def list_plugins(self) -> list[PluginInfo]:
        """List all registered plugins."""
        return self._plugin_info.copy()

    def get_generators_for_family(self, family: ArtifactFamily) -> list[ArtifactGeneratorPlugin]:
        """Get all generators for a specific family."""
        return [g for g in self.artifact_generators if g.family == family]


# Global registry instance
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (mainly for testing)."""
    global _registry
    _registry = None


# --- Plugin Loading ---


def load_plugin_from_file(path: Path) -> list[Any]:
    """
    Load plugins from a Python file.

    The file should define classes that extend the plugin base classes.

    Args:
        path: Path to Python file

    Returns:
        List of loaded plugin instances
    """
    if not path.exists():
        raise FileNotFoundError(f"Plugin file not found: {path}")

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    plugins = []
    registry = get_registry()

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type):  # It's a class
            try:
                if issubclass(obj, ArtifactGeneratorPlugin) and obj is not ArtifactGeneratorPlugin:
                    instance = obj()
                    registry.register_artifact_generator(instance)
                    plugins.append(instance)
                elif issubclass(obj, SignalDetectorPlugin) and obj is not SignalDetectorPlugin:
                    instance = obj()
                    registry.register_signal_detector(instance)
                    plugins.append(instance)
                elif issubclass(obj, SecretPatternPlugin) and obj is not SecretPatternPlugin:
                    instance = obj()
                    registry.register_secret_pattern(instance)
                    plugins.append(instance)
                elif issubclass(obj, PostProcessorPlugin) and obj is not PostProcessorPlugin:
                    instance = obj()
                    registry.register_post_processor(instance)
                    plugins.append(instance)
            except TypeError:
                # Abstract class, skip
                pass

    return plugins


def load_plugins_from_directory(directory: Path) -> list[Any]:
    """
    Load all plugins from a directory.

    Args:
        directory: Directory containing plugin files

    Returns:
        List of all loaded plugin instances
    """
    if not directory.exists():
        logger.warning(f"Plugin directory not found: {directory}")
        return []

    plugins = []
    for path in directory.glob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            loaded = load_plugin_from_file(path)
            plugins.extend(loaded)
            logger.info(f"Loaded {len(loaded)} plugins from {path}")
        except Exception as e:
            logger.error(f"Failed to load plugin {path}: {e}")

    return plugins


# --- Decorator-based Registration ---


def artifact_generator(
    name: str,
    family: ArtifactFamily,
    description: str = "",
    priority: int = 0,
) -> Callable:
    """
    Decorator for creating simple artifact generators.

    Usage:
        @artifact_generator("my-generator", ArtifactFamily.DOCS)
        def my_generator(index, signals, context):
            return "prompt for generation"
    """
    def decorator(func: Callable[[RepoIndex, RepoSignals, str], str]) -> ArtifactGeneratorPlugin:
        class DecoratedGenerator(ArtifactGeneratorPlugin):
            @property
            def name(self) -> str:
                return name

            @property
            def family(self) -> ArtifactFamily:
                return family

            @property
            def description(self) -> str:
                return description

            @property
            def priority(self) -> int:
                return priority

            def should_generate(self, index: RepoIndex, signals: RepoSignals) -> bool:
                return True  # Override if needed

            def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
                return func(index, signals, context)

        instance = DecoratedGenerator()
        get_registry().register_artifact_generator(instance)
        return instance

    return decorator


def secret_pattern(
    name: str,
    pattern: str,
    description: str = "",
    severity: str = "medium",
) -> Callable:
    """
    Decorator for creating simple secret patterns.

    Usage:
        @secret_pattern("my-pattern", r"MY_SECRET_\\w+", severity="high")
        def validate_my_pattern(match):
            return len(match) > 10
    """
    def decorator(func: Callable[[str], bool] | None = None) -> SecretPatternPlugin:
        class DecoratedPattern(SecretPatternPlugin):
            @property
            def name(self) -> str:
                return name

            @property
            def pattern(self) -> str:
                return pattern

            @property
            def description(self) -> str:
                return description

            @property
            def severity(self) -> str:
                return severity

            def validate_match(self, match: str) -> bool:
                if func is not None:
                    return func(match)
                return True

        instance = DecoratedPattern()
        get_registry().register_secret_pattern(instance)
        return instance

    if callable(pattern):
        # Used without arguments
        return decorator(None)
    return decorator


# --- Built-in Plugin Examples ---


class ArchitectureDocGenerator(ArtifactGeneratorPlugin):
    """Example built-in generator for architecture documentation."""

    @property
    def name(self) -> str:
        return "architecture-doc"

    @property
    def family(self) -> ArtifactFamily:
        return ArtifactFamily.DOCS

    @property
    def description(self) -> str:
        return "Generates architecture overview documentation"

    @property
    def priority(self) -> int:
        return 10

    def should_generate(self, index: RepoIndex, signals: RepoSignals) -> bool:
        # Generate for larger projects
        return index.total_files > 20

    def get_prompt(self, index: RepoIndex, signals: RepoSignals, context: str) -> str:
        return f"""Generate an architecture overview document for this codebase.

Repository: {signals.repo_name}
Primary Language: {signals.primary_language or 'Unknown'}
Frameworks: {', '.join(f.name for f in signals.frameworks[:5])}

Based on the codebase context below, create a comprehensive architecture document that covers:
1. High-level system overview
2. Key components and their responsibilities
3. Data flow and interactions
4. Technology stack rationale
5. Design patterns used

Context:
{context}

Output the document in Markdown format."""


# Register built-in plugins on import
def _register_builtins() -> None:
    """Register built-in plugins."""
    registry = get_registry()
    registry.register_artifact_generator(ArchitectureDocGenerator())


# Auto-register builtins
_register_builtins()
