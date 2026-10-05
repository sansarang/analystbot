# 🔴🔴 **타입 검사는 pytest 밖이다** — 사용자 지시 2026-10-05 (4번)
#
# > pyright 는 pytest 밖으로: 별도 명령(`make typecheck`)으로, **커밋 전 한 번만.**
#
# ⚠️ 왜 — pyright 가 계약 안에서 매번 10초를 먹어 스위트를 늦췄다.

.PHONY: typecheck test test-slow

typecheck:          ## 🔴 커밋 전 한 번 — app/research 는 strict, 나머지 basic
	PYTHONPATH=. uv run pyright

test:               ## 🔴 빠른 스위트(slow 제외 · 병렬) — 목표 2분 이하
	PYTHONPATH=. uv run pytest -q

test-slow:          ## 🔴 실모델·pyright 계약 — 마감 직전 한 번
	PYTHONPATH=. uv run pytest -q -m slow
