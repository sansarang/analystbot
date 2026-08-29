"""당일 NPB last-3 라이브 검증. npb_last3_verified 는 바꾸지 않는다.

실행: PYTHONPATH=. uv run python tools/verify_npb_form.py
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter

from app.collectors.npb_form import fetch_recent_form
from app.collectors.yahoo_npb import YahooNPBClient, parse_finals, score_card_html
from app.pipeline import today_kst


FIELDS = (
    "starter_ip", "starter_r", "starter_pitches", "bullpen_count",
    "runs", "hits", "hr", "bb", "k", "errors",
    "opponent_rank", "opponent_win_pct",
)


def _report(form: dict) -> dict:
    teams = len(form)
    games = [row for pkt in form.values() for row in (pkt.get("games") or [])]
    n = len(games)
    ip_ok = sum(1 for g in games if g.get("starter_ip") is not None)
    r_ok = sum(1 for g in games if g.get("starter_r") is not None)
    missing = Counter()
    for g in games:
        for f in FIELDS:
            if g.get(f) is None and f != "bullpen_count":
                missing[f] += 1
        if "bullpen_count" not in g:
            missing["bullpen_count"] += 1
    return {
        "teams": teams,
        "game_rows": n,
        "starter_ip_ok": ip_ok,
        "starter_r_ok": r_ok,
        "starter_ip_rate": (ip_ok / n) if n else 0.0,
        "starter_r_rate": (r_ok / n) if n else 0.0,
        "missing_field_counts": dict(missing),
        "per_team": {
            team: {
                "n": pkt.get("score_games"),
                "results": pkt.get("results_l3"),
                "games": pkt.get("games") or [],
            }
            for team, pkt in form.items()
        },
    }


async def markup_check(client: YahooNPBClient, date: str) -> dict:
    """예정 HTML을 parse_finals 하면 0건이어야 한다. 종료일만 점수가 붙는다."""
    html_today = score_card_html(await client.schedule(date))
    finals_today = parse_finals(html_today)
    from datetime import date as date_cls, timedelta

    yday = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    html_yday = score_card_html(await client.schedule(yday))
    finals_yday = parse_finals(html_yday)
    return {
        "today": date,
        "today_finals_parsed": len(finals_today),
        "yesterday": yday,
        "yesterday_finals_parsed": len(finals_yday),
        "today_has_preview_or_scheduled": (
            "(予)" in html_today or "試合前" in html_today or "予告" in html_today
        ),
        "today_has_finished_marker": "試合終了" in html_today,
        "yesterday_has_finished_marker": "試合終了" in html_yday,
    }


async def main() -> None:
    date = today_kst()
    client = YahooNPBClient()
    form = await fetch_recent_form(date, client)
    report = _report(form)
    markup = await markup_check(client, date)
    out = {
        "date": date,
        "npb_last3_verified_unchanged": True,
        "form": report,
        "markup": markup,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
