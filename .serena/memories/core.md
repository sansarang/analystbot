# AnalystBot Core

Sports-analysis Telegram chatbot. Numbers from official APIs (statsapi.mlb.com, The Odds API, API-Football), opinions from deep search (Perplexity sonar-pro, Grok Live Search), verdicts from Claude (JUDGE_MODEL, extended thinking).

Status: pre-implementation. Only env scaffolding exists (CLAUDE.md, docker-compose.yml, .mcp.json). No source code yet.

Planned layout (from CLAUDE.md — authoritative spec, read it before building):
- `app/collectors/` — numeric data collection
- `app/research/` — deep-search opinion gathering
- `app/engine/` — value / consensus / parlay / judge
- `app/pipeline.py`, `app/bot/`, `app/scheduler.py`, `app/grader.py`
- `db/schema.sql`, `mock_data/`, `tests/`

Project-wide invariants:
- NO automated bet execution, ever.
- LLM-produced numbers must be cross-checked against API numbers; API wins on conflict.
- Missing API key → fall back to mock mode using `mock_data/`, never crash.
- DB stores UTC (timestamptz); KST conversion only at display layer.
- Formulas: ev = p*odds - 1; half-Kelly staking capped at 5% bankroll; p_final = 0.45*p_model + 0.30*p_market + 0.25*p_claude.

Stack details: `mem:tech_stack`. Runnable commands: `mem:suggested_commands`. Code style rules: `mem:conventions`. Definition-of-done checks: `mem:task_completion`.
