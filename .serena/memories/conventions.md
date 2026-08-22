# Conventions

- Edit symbol-wise via Serena (`find_symbol` → `replace_symbol_body`); never rewrite whole files. Check cross-module deps (collectors/research/engine) with `find_referencing_symbols` before changing signatures.
- Every external HTTP call: exponential backoff, 3 retries, explicit timeout (httpx).
- Async-first: httpx.AsyncClient, aiogram 3.x async handlers.
- All timestamps stored UTC (timestamptz); convert to KST only for user-facing display.
- Each API-key-dependent module must have a mock-mode path reading from `mock_data/`.
- Never emit LLM numeric values directly; cross-validate against API-sourced numbers first.
