# Architecture

JPS One uses a layered architecture.

```text
Frontend UI
API routes
Workflow orchestration
Agents
Connectors
Business domain
Knowledge / RAG
MCP tools
Skill playbooks
Observability and operations
```

## Layer Rules

- API validates and delegates.
- Workflow orchestrates long-running processes.
- Agent handles LLM reasoning and structured generation.
- Connector talks to external deterministic systems.
- Business owns JPS rules.
- Knowledge retrieves cited source material.
- MCP exposes agent-facing tools.
- Skill documents repeatable workflows.

## Migration Strategy

Use side-by-side migration:

1. Keep existing routes working.
2. Add JPS One foundation modules.
3. Move old code by responsibility.
4. Keep compatibility adapters until the frontend is migrated.
5. Run regression tests after each move.

