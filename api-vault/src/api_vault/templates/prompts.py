"""
Prompt templates for all artifact types.

Each template includes:
- Clear instructions for the specific artifact
- Self-check rubric to ensure quality
- Structured output format requirements
"""

from dataclasses import dataclass


@dataclass
class PromptTemplate:
    """A prompt template for artifact generation."""

    id: str
    name: str
    system_prompt: str
    user_prompt_template: str


# System prompt shared across all templates
BASE_SYSTEM_PROMPT = """You are a senior software engineer creating documentation artifacts for a software project.

CRITICAL RULES:
1. Only describe what you can verify from the provided context
2. When information is missing, explicitly state "UNKNOWN - verify by..." or "NOT FOUND IN CONTEXT"
3. Never hallucinate file paths, function names, or implementation details
4. Use concrete examples from the provided code when available
5. Be specific and actionable, not generic

Your output should be professional, accurate, and immediately useful to developers working on this project."""


PROMPT_TEMPLATES: dict[str, PromptTemplate] = {
    # Documentation templates
    "runbook": PromptTemplate(
        id="runbook",
        name="RUNBOOK.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create a comprehensive RUNBOOK.md for this project based on the following context:

{context}

---

Generate a RUNBOOK.md with these sections:

## Prerequisites
- List required software with versions (only what you can verify from config files)
- List environment variables needed (only from .env.example or config)

## Quick Start
- Step-by-step commands to get the project running
- Use actual commands from package.json, Makefile, or similar

## Development Setup
- How to install dependencies
- How to configure the environment
- How to run in development mode

## Building
- Build commands and options
- Output artifacts and locations

## Testing
- How to run tests
- Test configuration details

## Common Tasks
- Frequently needed commands
- Development workflow tips

## Self-Check Rubric
At the end, include a self-assessment:
- [ ] All commands are from actual config files, not assumed
- [ ] Prerequisites list versions from lock files/configs
- [ ] Unknown items are marked as "VERIFY: ..."
- [ ] No hallucinated file paths or commands

Format: Clean markdown with code blocks for all commands.""",
    ),
    "troubleshooting": PromptTemplate(
        id="troubleshooting",
        name="TROUBLESHOOTING.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create a TROUBLESHOOTING.md guide based on the following project context:

{context}

---

Generate a TROUBLESHOOTING.md with these sections:

## Common Issues

For each issue, use this format:
### Issue: [Problem Description]
**Symptoms:** What the user sees
**Cause:** Why this happens (if known from context)
**Solution:** Step-by-step fix
**Prevention:** How to avoid in future

Cover these categories:
1. Setup/Installation issues
2. Build/Compilation errors
3. Runtime errors
4. Configuration problems
5. Dependency conflicts

## Environment-Specific Issues
- Development environment problems
- CI/CD pipeline issues (if applicable)
- Docker/container issues (if applicable)

## Debugging Tips
- How to enable debug logging
- Useful debugging commands
- Where to find logs

## Getting Help
- How to report issues
- What information to include

## Self-Check Rubric
- [ ] Issues are based on actual project structure, not generic
- [ ] Solutions reference real files and configs from context
- [ ] Unknown solutions are marked as "VERIFY: ..."

Format: Clear markdown with code examples.""",
    ),
    "architecture": PromptTemplate(
        id="architecture",
        name="ARCHITECTURE_OVERVIEW.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create an ARCHITECTURE_OVERVIEW.md based on the following project context:

{context}

---

Generate an architecture document with these sections:

## Overview
- One paragraph describing what this system does
- Primary technologies used (from detected frameworks)

## System Architecture
- High-level component diagram (ASCII art)
- Main modules/packages and their responsibilities
- Only describe components you can verify from file structure

## Directory Structure
```
project/
├── [describe actual structure from context]
```

## Key Components
For each major component:
### [Component Name]
- **Location:** [actual file/folder path]
- **Responsibility:** [what it does]
- **Dependencies:** [what it imports/uses]

## Data Flow
- How data moves through the system
- Request/response lifecycle (if applicable)

## External Dependencies
- List external services/APIs used
- Database connections (type only, no credentials)

## Design Decisions
- Notable patterns used (only if evident from code)
- Trade-offs visible in the architecture

## Self-Check Rubric
- [ ] All file paths exist in the provided structure
- [ ] Component descriptions match actual code
- [ ] No assumed architecture patterns not in evidence

Format: Markdown with ASCII diagrams where helpful.""",
    ),
    # Security templates
    "threat_model": PromptTemplate(
        id="threat_model",
        name="THREAT_MODEL.md",
        system_prompt=BASE_SYSTEM_PROMPT + """

For security analysis, use the STRIDE methodology:
- Spoofing: Can attackers impersonate users/systems?
- Tampering: Can data be modified in transit/storage?
- Repudiation: Can actions be denied without proof?
- Information Disclosure: Can sensitive data leak?
- Denial of Service: Can availability be affected?
- Elevation of Privilege: Can users gain unauthorized access?""",
        user_prompt_template="""Create a THREAT_MODEL.md based on the following project context:

{context}

---

Generate a threat model document with these sections:

## System Overview
- Brief description of what the system does
- Trust boundaries identified

## Assets
- Data assets (what data is stored/processed)
- System assets (infrastructure components)

## Threat Actors
- Who might attack this system
- Their capabilities and motivations

## STRIDE Analysis

### Spoofing
- Identified threats
- Current mitigations (from code)
- Recommendations

### Tampering
[Same structure]

### Repudiation
[Same structure]

### Information Disclosure
[Same structure]

### Denial of Service
[Same structure]

### Elevation of Privilege
[Same structure]

## Attack Surface
- Entry points identified in code
- External interfaces

## Security Controls (Current)
- Authentication mechanisms found
- Authorization patterns found
- Input validation found
- Logging/monitoring found

## Recommendations
Prioritized security improvements

## Self-Check Rubric
- [ ] Threats are specific to this codebase, not generic
- [ ] Current controls reference actual code patterns
- [ ] Recommendations are actionable for this stack

Format: Markdown with clear prioritization.""",
    ),
    "security_checklist": PromptTemplate(
        id="security_checklist",
        name="SECURITY_CHECKLIST.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create a SECURITY_CHECKLIST.md based on the following project context:

{context}

---

Generate a security checklist tailored to this project:

## Pre-Deployment Checklist

### Authentication & Authorization
- [ ] [Stack-specific auth checks]
- [ ] Session management configured securely
- [ ] Password policies enforced (if applicable)

### Data Protection
- [ ] Sensitive data encrypted at rest
- [ ] TLS/HTTPS enforced for data in transit
- [ ] PII handling compliant with requirements

### Input Validation
- [ ] All user inputs validated
- [ ] SQL injection prevention
- [ ] XSS prevention
- [ ] CSRF tokens implemented (if web)

### Dependencies
- [ ] No known vulnerable dependencies
- [ ] Dependency audit completed
- [ ] Lock files committed

### Secrets Management
- [ ] No hardcoded secrets
- [ ] Environment variables for sensitive config
- [ ] Secrets rotation process defined

### Logging & Monitoring
- [ ] Security events logged
- [ ] No sensitive data in logs
- [ ] Alerting configured for security events

### Infrastructure
- [ ] Minimal permissions configured
- [ ] Firewall rules reviewed
- [ ] Container security (if applicable)

## Framework-Specific Checks
[Add checks specific to detected frameworks]

## Verification Steps
How to verify each checklist item

## Self-Check Rubric
- [ ] Checklist items are relevant to detected stack
- [ ] Generic items are marked as conditional
- [ ] Verification steps are concrete

Format: Markdown checklist with verification guidance.""",
    ),
    "auth_notes": PromptTemplate(
        id="auth_notes",
        name="AUTHZ_AUTHN_NOTES.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create AUTHZ_AUTHN_NOTES.md based on the following project context:

{context}

---

Document the authentication and authorization system:

## Overview
- Authentication method(s) used
- Authorization model

## Authentication Flow
1. [Step-by-step auth flow based on code]
2. ...

### User Registration (if applicable)
- Process description
- Validation requirements

### Login Process
- Credential handling
- Session/token creation

### Session Management
- Session storage mechanism
- Expiration policies
- Refresh mechanism

## Authorization Model
- Role definitions (if found)
- Permission structure
- Resource access patterns

## Security Features
- Rate limiting
- Account lockout
- MFA (if present)

## Integration Points
- External auth providers (if any)
- SSO/OAuth flows (if applicable)

## Code References
- Key files handling auth
- Middleware/decorators used

## Known Limitations
- Security considerations
- Areas for improvement

## Self-Check Rubric
- [ ] Flow descriptions match actual code
- [ ] File references are verified
- [ ] Unknown mechanisms marked clearly

Format: Technical markdown with code references.""",
    ),
    # Testing templates
    "golden_path_tests": PromptTemplate(
        id="golden_path_tests",
        name="GOLDEN_PATH_TEST_PLAN.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create a GOLDEN_PATH_TEST_PLAN.md based on the following project context:

{context}

---

Create a test plan covering critical user journeys:

## Overview
- Testing strategy summary
- Test framework to use (based on project)

## Golden Path Scenarios

### Scenario 1: [Primary User Journey]
**Preconditions:**
- Required setup state

**Steps:**
1. [Specific action]
2. [Specific action]
...

**Expected Results:**
- [Verifiable outcome]

**Test Implementation:**
```[language]
// Suggested test structure
```

### Scenario 2: [Secondary Journey]
[Same structure]

[Continue for 5-7 critical paths]

## Edge Cases
- Important boundary conditions
- Error scenarios to test

## Integration Points
- External service mocks needed
- Test data requirements

## Test Environment
- Required configuration
- Database seeding needs

## Coverage Goals
- Critical paths that must be covered
- Acceptance criteria

## Self-Check Rubric
- [ ] Scenarios reflect actual application functionality
- [ ] Test code uses project's test framework
- [ ] No assumptions about unverified features

Format: Actionable test plan with code examples.""",
    ),
    "minimum_tests": PromptTemplate(
        id="minimum_tests",
        name="MINIMUM_TESTS_SUGGESTION.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create MINIMUM_TESTS_SUGGESTION.md based on the following project context:

{context}

---

Suggest minimum viable test coverage:

## Current Test Status
- Existing tests found: [from context]
- Test framework: [detected or suggested]

## Priority 1: Critical Tests
Tests that must exist for production readiness:

### [Function/Module Name]
**Why:** [Criticality reason]
**Test Type:** Unit/Integration/E2E
**Suggested Test:**
```[language]
// Test implementation
```

[3-5 critical tests]

## Priority 2: Important Tests
Tests that should exist:
[5-7 additional tests]

## Priority 3: Nice to Have
Tests for edge cases and polish:
[Additional suggestions]

## Test Infrastructure Needs
- Mocking requirements
- Test database setup
- CI integration suggestions

## Quick Wins
- Easiest tests to add first
- Maximum value for minimum effort

## Self-Check Rubric
- [ ] Suggested tests are for real functions/modules
- [ ] Code examples use correct syntax for project
- [ ] Priorities based on actual code criticality

Format: Prioritized list with code examples.""",
    ),
    # API templates
    "endpoint_inventory": PromptTemplate(
        id="endpoint_inventory",
        name="ENDPOINT_INVENTORY.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create an ENDPOINT_INVENTORY.md based on the following project context:

{context}

---

Document all API endpoints:

## API Overview
- Base URL pattern
- API version (if applicable)
- Authentication required

## Endpoints

### [HTTP Method] [Path]
**Description:** What this endpoint does
**Authentication:** Required/Optional/None
**Request:**
```json
{{
  "param": "type and description"
}}
```
**Response:**
```json
{{
  "field": "type and description"
}}
```
**Status Codes:**
- 200: Success
- 400: Bad request
- ...
**Example:**
```bash
curl -X [METHOD] [URL]
```

[Document all found endpoints]

## Common Headers
- Required headers for all requests

## Error Response Format
- Standard error structure

## Rate Limiting
- Limits if found in code

## Self-Check Rubric
- [ ] All endpoints found in route files documented
- [ ] Request/response shapes from actual code
- [ ] No assumed endpoints

Format: API documentation markdown.""",
    ),
    "openapi_draft": PromptTemplate(
        id="openapi_draft",
        name="openapi_draft.json",
        system_prompt=BASE_SYSTEM_PROMPT + """

Output ONLY valid JSON. No markdown, no explanation, just the OpenAPI JSON document.""",
        user_prompt_template="""Create an OpenAPI 3.0 specification based on the following project context:

{context}

---

Generate a valid OpenAPI 3.0 JSON document that describes the API.

Requirements:
1. Include only endpoints found in the code
2. Use proper JSON schema for request/response bodies
3. Include realistic examples based on code
4. Mark unknown fields with "VERIFY" in description
5. Output ONLY the JSON, no markdown wrapper

The JSON should include:
- openapi: "3.0.3"
- info with title, version, description
- servers array
- paths with all endpoints
- components/schemas for data models
- security schemes if auth is detected""",
    ),
    # Observability templates
    "logging_conventions": PromptTemplate(
        id="logging_conventions",
        name="LOGGING_CONVENTIONS.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create LOGGING_CONVENTIONS.md based on the following project context:

{context}

---

Define logging conventions for this project:

## Overview
- Current logging library (from dependencies)
- Log levels used

## Log Levels

### DEBUG
- When to use
- Example: `logger.debug("...")`

### INFO
- When to use
- Example with structure

### WARNING
- When to use
- Example

### ERROR
- When to use
- Error context to include

## Structured Logging Format
```json
{{
  "timestamp": "ISO8601",
  "level": "INFO",
  "message": "description",
  "context": {{}}
}}
```

## Context Fields
Standard fields to include:
- request_id
- user_id (if applicable)
- [others based on project]

## Sensitive Data
- Fields to never log
- Masking patterns

## Log Locations
- Where logs go
- Rotation policy (if found)

## Examples by Scenario
### API Request
```[language]
// Logging example
```

### Error Handling
```[language]
// Logging example
```

## Self-Check Rubric
- [ ] Uses project's actual logging library
- [ ] Examples match code patterns found
- [ ] Sensitive data handling is specific

Format: Convention guide with examples.""",
    ),
    "metrics_plan": PromptTemplate(
        id="metrics_plan",
        name="METRICS_PLAN.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create METRICS_PLAN.md based on the following project context:

{context}

---

Define a metrics and monitoring strategy:

## Overview
- Monitoring tools detected/suggested
- Key performance indicators

## Application Metrics

### Request Metrics
- request_count (Counter)
- request_duration (Histogram)
- request_size (Histogram)

### Business Metrics
[Suggest based on application type]

### Resource Metrics
- memory_usage
- cpu_usage
- connection_pool_size

## Instrumentation Guide

### [Framework] Specific
```[language]
// How to add metrics
```

## Alerting Thresholds
| Metric | Warning | Critical |
|--------|---------|----------|
| ... | ... | ... |

## Dashboard Suggestions
- Key graphs to create
- Important correlations

## Health Checks
- Liveness check design
- Readiness check design

## Self-Check Rubric
- [ ] Metrics are relevant to this application type
- [ ] Instrumentation uses project's stack
- [ ] Thresholds are reasonable defaults

Format: Actionable metrics plan.""",
    ),
    # Product templates
    "ux_copy_bank": PromptTemplate(
        id="ux_copy_bank",
        name="UX_COPY_BANK.md",
        system_prompt=BASE_SYSTEM_PROMPT,
        user_prompt_template="""Create UX_COPY_BANK.md based on the following project context:

{context}

---

Create a UI copy reference guide:

## Overview
- Application type
- Target audience
- Tone guidelines

## Common UI Elements

### Buttons
| Action | Copy | Context |
|--------|------|---------|
| Submit | "Save Changes" | Form completion |
| ... | ... | ... |

### Form Labels
| Field | Label | Helper Text |
|-------|-------|-------------|
| ... | ... | ... |

### Error Messages
| Error Type | Message | Recovery Action |
|------------|---------|-----------------|
| Validation | "Please enter a valid email" | Show format hint |
| Network | "Unable to connect. Please try again." | Retry button |
| ... | ... | ... |

### Success Messages
| Action | Message |
|--------|---------|
| ... | ... |

### Empty States
| Screen | Message | CTA |
|--------|---------|-----|
| ... | ... | ... |

## Microcopy Guidelines
- Placeholder text patterns
- Tooltip conventions
- Loading state messages

## Accessibility
- Screen reader considerations
- ARIA label patterns

## Self-Check Rubric
- [ ] Copy reflects application's actual features
- [ ] Tone is consistent throughout
- [ ] Error messages are helpful and specific

Format: Reference guide with tables.""",
    ),
}


def get_prompt_template(template_id: str) -> PromptTemplate | None:
    """
    Get a prompt template by ID.

    Args:
        template_id: Template identifier

    Returns:
        PromptTemplate or None if not found
    """
    return PROMPT_TEMPLATES.get(template_id)


def list_templates() -> list[str]:
    """
    List all available template IDs.

    Returns:
        List of template IDs
    """
    return list(PROMPT_TEMPLATES.keys())


def render_prompt(template_id: str, context: str) -> tuple[str, str] | None:
    """
    Render a prompt template with context.

    Args:
        template_id: Template identifier
        context: Repository context string

    Returns:
        Tuple of (system_prompt, user_prompt) or None if template not found
    """
    template = get_prompt_template(template_id)
    if template is None:
        return None

    user_prompt = template.user_prompt_template.format(context=context)
    return template.system_prompt, user_prompt
