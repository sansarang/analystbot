# Tech Stack

- Python 3.12
- FastAPI (HTTP API), aiogram 3.x (Telegram bot), httpx async (all external HTTP)
- PostgreSQL 16 + Redis 7 via docker-compose (user/pass/db: analyst/analyst/analystbot, ports 5432/6379)
- APScheduler (odds snapshots, prefetch jobs), pytest
- LLM: Anthropic SDK (judge, model from JUDGE_MODEL env), Perplexity sonar-pro, xAI Grok Live Search
- aiogram 3.x / FastAPI / Anthropic SDK have frequent breaking API changes — verify usage via context7 MCP docs, don't code from memory.
- .env keys: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, PPLX_API_KEY, XAI_API_KEY, ODDS_API_KEY, APIFOOTBALL_KEY, JUDGE_MODEL.
