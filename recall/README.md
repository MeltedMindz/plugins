# Recall

Your codebase finally has a memory.

A Claude Code plugin + MCP server that automatically captures architectural decisions, stores them in a searchable database, and exposes them for natural language queries.

## Features

- **Auto-detection** - PostToolUse hooks detect architectural decisions as you code
- **Quick capture** - Prompts for a "why" explanation when decisions are detected
- **Full-text search** - SQLite + FTS5 for fast, fuzzy searching
- **MCP integration** - Query decisions via natural language
- **Export formats** - JSON, Markdown, and ADR (Architecture Decision Records)

## Commands

| Command | Description |
|---------|-------------|
| `/decision [reason]` | Manually record a decision |
| `/decisions` | List recent decisions |
| `/decision-search [query]` | Search past decisions |
| `/decision-link` | Link a decision to a git commit |

## MCP Tools

| Tool | Description |
|------|-------------|
| `query_decisions` | Search decisions with natural language |
| `add_decision` | Record a new decision |
| `get_decision` | Get details of a specific decision |
| `link_commit` | Link a decision to a git commit |
| `list_projects` | List all projects with decisions |
| `export_decisions` | Export decisions to JSON, Markdown, or ADR format |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `decisions://recent` | Recent decisions across all projects |
| `decisions://project/{path}` | Decisions for a specific project |
| `decisions://file/{path}` | Decisions related to a specific file |

## Installation

### Claude Code Plugin

```bash
# Copy to your project
cp -r recall/.claude-plugin your-project/
cp -r recall/commands your-project/
cp -r recall/hooks your-project/
cp -r recall/agents your-project/
cp -r recall/scripts your-project/
```

### MCP Server

```bash
cd recall/mcp-server
npm install
npm run build

# Add to claude_desktop_config.json
```

See [INSTALL.md](./INSTALL.md) for detailed instructions.

## How It Works

1. **Detection** - Hooks watch for file changes that indicate architectural decisions (new configs, dependency changes, structural refactors)

2. **Capture** - When detected, you're prompted to explain the "why" behind the decision

3. **Storage** - Decisions are stored in SQLite with full-text search indexing

4. **Query** - Use commands or MCP tools to search and retrieve past decisions

## Example

```
You: /decision Using Redis for session storage instead of JWT

Recall: Decision recorded.
  - Type: Infrastructure
  - Confidence: HIGH
  - Project: my-app
  - Linked files: src/config/session.ts

You: Why did we choose Redis for sessions?

Claude (via MCP): Based on the recorded decision from Jan 15:
  "Using Redis for session storage instead of JWT"
  - Allows session invalidation on logout
  - Scales horizontally with Redis cluster
  - Avoids JWT token size issues with large payloads
```

## Structure

```
recall/
├── .claude-plugin/       # Plugin manifest
├── commands/             # Slash commands
├── hooks/                # PostToolUse detection
├── agents/               # decision-helper AI agent
├── scripts/              # Detection logic
├── mcp-server/           # MCP server
│   └── src/
│       ├── tools/        # MCP tools (modular)
│       ├── resources/    # MCP resources
│       ├── prompts/      # MCP prompts
│       └── db/           # SQLite + FTS5
├── INSTALL.md
├── SECURITY.md
└── EXAMPLES.md
```

## License

MIT
