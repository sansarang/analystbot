# Task Completion Checklist

- `pytest` must pass; new features require accompanying tests in `tests/` (no test → not done).
- No linter/formatter/type-checker configured yet; when introduced (likely ruff/mypy), update this memory with exact commands.
- If schema changed: update `db/schema.sql` and verify via postgres MCP query against the running container.
