"""
Prompt templates for artifact generation.

Each template is a parameterized prompt that gets filled with
repository context to generate high-quality, repo-specific artifacts.
"""

from api_vault.templates.prompts import (
    PROMPT_TEMPLATES,
    get_prompt_template,
    list_templates,
    render_prompt,
)

__all__ = [
    "PROMPT_TEMPLATES",
    "get_prompt_template",
    "list_templates",
    "render_prompt",
]
