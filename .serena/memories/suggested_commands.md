# Suggested Commands

- `docker compose up -d` — start PostgreSQL 16 + Redis 7 (Docker runs via colima on this Mac; if daemon unreachable: `colima start`)
- `uvicorn app.main:app --reload` — FastAPI dev server
- `python -m app.bot` — Telegram bot (polling)
- `pytest` — full test suite; `pytest tests/<file> -x -q` for fast single-file runs
- DB inspection: prefer postgres MCP direct SQL; CLI fallback `docker exec -it analystbot-postgres psql -U analyst -d analystbot`
- Redis inspection: redis MCP; CLI fallback `docker exec -it analystbot-redis redis-cli`

Darwin note: BSD userland (`sed -i ''`, no GNU flags on grep/find).
