# AnalystBot Core

Sports-analysis Telegram chatbot. Numbers from official APIs (statsapi.mlb.com, The Odds API, API-Football), opinions from deep search (Perplexity sonar-pro, Grok Live Search), verdicts from Claude (JUDGE_MODEL).

Status: v1 implemented and tested (42 tests + 2 live-key skips). CLAUDE.md is the authoritative spec.

Layout (as built):
- `app/collectors/` — `base.py` (BaseAPIClient: httpx, 3-retry exp backoff, mock fallback), `mlb.py` (schedule/pitchers/standings/finals + upsert), `odds.py` (h2h/spreads/totals → odds_snapshots), `football.py`
- `app/research/` — `perplexity.py` (expert picks → JSON parse w/ 1 retry → normalize → expert_picks, odds attached from DB not LLM), `grok.py` (live briefing), `normalize.py` (freeform pick → `h2h:<team>` / `spreads:<team>:<line>` / `totals:Over|Under:<line>` — shared with grader)
- `app/engine/` — `value.py` (ev/kelly/ensemble/heuristic p_model), `consensus.py` (ledger roi_90d → weight 0.2–2.0), `parlay.py` (2–4 legs, +EV only, no same-game), `judge.py` (Anthropic SDK, adaptive thinking + strict `verdict` tool; forced tool_choice retry w/o thinking; model-ladder fallback on 404; deterministic mock)
- `app/pipeline.py` — schedule upsert → (stats ∥ odds ∥ research) gather → ensemble → predictions insert (ev>threshold) → report (Sonnet live / template mock) → Redis cache 30m key `report:{sport}:{date}`
- `app/bot/main.py` — aiogram 3.x Router; `--simulate "<text>"` CLI; 4096-char split; intent parse (Haiku structured output live / regex mock)
- `app/scheduler.py` — KST cron: 04:00 prefetch, 30m odds snapshot, 13:00 grade yesterday
- `app/grader.py` — grades canonical picks (ML/spread/total incl. push; draw = ML loss); expert_ledger is a VIEW (auto-updates)

Invariants (unchanged): NO bet execution; API numbers win over LLM; missing key → mock via `mock_data/` (FORCE_MOCK=true forces all; tests set it in conftest); UTC in DB, KST display only.

Formulas: ev = p*odds - 1; half-Kelly cap 5%; p_final = 0.45*p_model + 0.30*p_market + 0.25*p_claude (weights in config).

Gotchas: asyncpg date params need `date` objects not strings; games are matched by schedule ext_ids (not KST date) since MLB games cross the KST midnight; The Odds API team names must equal statsapi names for snapshot matching.

Stack details: `mem:tech_stack`. Commands: `mem:suggested_commands`. Style: `mem:conventions`. Done-checks: `mem:task_completion`.
