"""1단계 — MLB 라인업 재판정이 KBO처럼 같은 research 칸을 채운다.

실측 2026-08-29 아침 카드: lineup_status=confirmed 인데 today_nine n=0,
상태 카드 5칸 미수집, λ trace는 있는데 '핵심 지표 전무'가 붙었다.
원인은 폴링 타순이 research에 안 들어가고, 재판정 번들에 순위·폼이 없고,
_compute_picks가 Statcast를 sanitize 복사본에만 얹은 것이다.
"""

import json

import pytest

from app.collectors.lineups import apply_lineup_poll_to_research
from app.collectors.mlb import load_ctx, save_ctx
from app.config import Settings
from app.engine.lineup_diff import attach_lineup_view
from app.pipeline import load_source_bundle, merge_source_data
from app.research.validate import sanitize_research


class _FakeRedis:
    def __init__(self, store=None):
        self.store = store or {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v
        return True

    async def lrange(self, k, a, b):
        return []


def _orders(prefix: str) -> list[str]:
    return [f"{prefix}{i}" for i in range(9)]


def _poll(**over):
    payload = {
        "status": "confirmed",
        "starters": {"home": "Yoshinobu Yamamoto", "away": "Dylan Cease"},
        "orders": {"home": _orders("H"), "away": _orders("A")},
        "notes": [], "injuries": {},
    }
    payload.update(over)
    return payload


def test_poll_copies_nine_names_into_research():
    """폴링 confirmed + 타순 9명 → today_nine n=9. 스냅샷 우회에 의존하지 않는다."""
    research: dict = {}
    jg = {"home": "Los Angeles Dodgers", "away": "San Diego Padres", "sport": "mlb"}
    filled = apply_lineup_poll_to_research(research, jg, _poll())
    assert "home_lineup.order" in filled and "away_lineup.order" in filled
    assert research["home_lineup"]["order"].startswith("H0-")
    assert research["home_pitcher"]["name"] == "Yoshinobu Yamamoto"
    jg["research"] = research
    attach_lineup_view(jg, "mlb")
    assert jg["today_nine"]["home"]["n"] == 9
    assert jg["today_nine"]["away"]["n"] == 9


def test_poll_does_not_write_partial_order():
    """9명 미만은 타순을 쓰지 않는다 — 부분 명단을 확정처럼 남기지 않는다."""
    research: dict = {}
    jg: dict = {}
    apply_lineup_poll_to_research(research, jg, _poll(
        orders={"home": ["A", "B", "C"], "away": _orders("A")}))
    assert "home_lineup" not in research
    assert research["away_lineup"]["order"].startswith("A0-")


def test_poll_order_wins_over_crawler_snapshot():
    """크롤러 스냅샷이 옛 타순이어도 이번 폴링 9명이 이긴다."""
    jg = {"home": "Los Angeles Dodgers", "away": "San Diego Padres",
          "home_pitcher": "Old H", "away_pitcher": "Old A", "game_id": 1}
    snap = {f"{jg['away']}@{jg['home']}": {
        "home_pitcher": "Old H", "away_pitcher": "Old A",
        "lineup_home": "-".join(_orders("OldH")),
        "lineup_away": "-".join(_orders("OldA")),
    }}
    research: dict = {}
    merge_source_data(research, jg, "mlb", {"crawler": snap})
    apply_lineup_poll_to_research(research, jg, _poll())
    assert research["home_lineup"]["order"].startswith("H0-")
    assert research["home_pitcher"]["name"] == "Yoshinobu Yamamoto"


@pytest.mark.asyncio
async def test_mlb_ctx_roundtrip_keeps_int_game_ids():
    """JSON 왕복 뒤에도 absences/weather 키가 int여야 _merge_mlb가 찾는다."""
    r = _FakeRedis()
    await save_ctx(r, "2026-08-29", {
        "standings": {"Los Angeles Dodgers": {"rank": 1}},
        "form": {"Los Angeles Dodgers": {"results_l3": "WWL"}},
        "era": {"Yoshinobu Yamamoto": 2.50},
        "weather": {410: {"text": "기온 22도", "dome": False}},
        "absences": {410: {"lineup": {"confirmed": True}}},
    })
    ctx = await load_ctx(r, "2026-08-29")
    assert ctx["standings"]["Los Angeles Dodgers"]["rank"] == 1
    assert ctx["form"]["Los Angeles Dodgers"]["results_l3"] == "WWL"
    assert ctx["era"]["Yoshinobu Yamamoto"] == 2.50
    assert 410 in ctx["weather"] and 410 in ctx["absences"]


@pytest.mark.asyncio
async def test_load_source_bundle_mlb_includes_standings_form():
    """재판정 번들에 슬레이트와 같은 순위·폼이 있어야 카드 칸이 찬다."""
    r = _FakeRedis()
    await save_ctx(r, "2026-08-29", {
        "standings": {"Los Angeles Dodgers": {"rank": 1, "w": 80, "l": 50}},
        "form": {"Los Angeles Dodgers": {"results_l3": "WWL", "score_games": 3}},
        "era": {}, "weather": {}, "absences": {},
    })
    bundle = await load_source_bundle(r, "mlb", "2026-08-29")
    assert bundle["standings"]["Los Angeles Dodgers"]["rank"] == 1
    assert bundle["form"]["Los Angeles Dodgers"]["results_l3"] == "WWL"


def test_sanitize_keeps_statcast_lambda_fields():
    """sanitize가 xwOBA를 버리면 번들 없는 재계산에서 λ가 죽는다."""
    clean, dropped = sanitize_research({
        "home_pitcher": {"name": "Yoshinobu Yamamoto", "era_season": 2.50,
                         "xwoba_allowed": 0.280},
        "away_pitcher": {"name": "Dylan Cease", "era_season": 3.80,
                         "xwoba_allowed": 0.310},
        "home_offense": {"xwoba_30d": 0.340, "ops": 0.780},
        "away_offense": {"xwoba_30d": 0.310},
        "league_baselines": {"xwoba": 0.320, "xwoba_allowed": 0.320},
    }, "mlb")
    assert clean["home_offense"]["xwoba_30d"] == 0.340
    assert clean["home_pitcher"]["xwoba_allowed"] == 0.280
    assert clean["league_baselines"]["xwoba"] == 0.320
    assert "home_offense.xwoba_30d" not in dropped


def test_compute_picks_writes_statcast_onto_jg_research():
    """enrich가 sanitize 복사본만 채우면 카드가 빈다 — jg.research에도 얹는다."""
    from app.pipeline import _compute_picks

    jg = {
        "game_id": 1, "sport": "mlb", "status": "scheduled",
        "home": "Los Angeles Dodgers", "away": "San Diego Padres",
        "home_pitcher": "Yoshinobu Yamamoto", "away_pitcher": "Dylan Cease",
        "starts_at_kst": "08/29 10:10", "league": "MLB",
        "p_claude": 0.55, "judge_confidence": "medium",
        "market_probs": {}, "best_odds": {}, "alt_markets": [],
        "expert_picks": [], "stats": {}, "research": {},
    }
    bundle = {
        "offense": {
            "Los Angeles Dodgers": {"xwoba_30d": 0.340},
            "San Diego Padres": {"xwoba_30d": 0.310},
        },
        "pitchers": {
            "Yoshinobu Yamamoto": {"xwoba_allowed": 0.280, "era_season": 2.50},
            "Dylan Cease": {"xwoba_allowed": 0.310, "era_season": 3.80},
        },
        "bullpen": {}, "parks": {}, "league": {"xwoba": 0.320},
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb", bundle)
    assert jg["research"]["home_offense"]["xwoba_30d"] == 0.340
    assert jg["research"]["away_pitcher"]["xwoba_allowed"] == 0.310
    assert jg.get("lam") and jg["lam"]["home"] > 0
    assert "핵심 지표(타선·선발) 전무" not in (jg.get("lambda_missing") or [])


def test_rejudge_merge_then_poll_fills_today_nine_and_standings():
    """재판정 순서: 번들 병합 + 폴링 타순 → 카드가 읽는 칸이 같이 찬다."""
    jg = {
        "home": "Los Angeles Dodgers", "away": "San Diego Padres",
        "home_pitcher": "Yoshinobu Yamamoto", "away_pitcher": "Dylan Cease",
        "game_id": 1, "sport": "mlb",
        "stats": {"home_pitcher_era": 2.50, "away_pitcher_era": 3.80},
    }
    research: dict = {}
    apply_lineup_poll_to_research(research, jg, _poll())
    merge_source_data(research, jg, "mlb", {
        "offense": {"Los Angeles Dodgers": {"xwoba_30d": 0.340}},
        "pitchers": {"Yoshinobu Yamamoto": {"xwoba_allowed": 0.280}},
        "bullpen": {"Los Angeles Dodgers": {"bp_pitches_3d": 210}},
        "standings": {"Los Angeles Dodgers": {"rank": 1, "w": 80, "l": 50, "d": 0}},
        "form": {"Los Angeles Dodgers": {"results_l3": "WWL", "score_games": 3}},
        "weather": {},
    })
    apply_lineup_poll_to_research(research, jg, _poll())
    jg["research"] = research
    attach_lineup_view(jg, "mlb")
    assert jg["today_nine"]["home"]["n"] == 9
    assert research["home_standing"]["rank"] == 1
    assert research["home_usage"]["results_l3"] == "WWL"
    assert research["home_usage"]["bp_pitches_3d"] == 210
    assert research["home_offense"]["xwoba_30d"] == 0.340
    assert json.dumps(research["home_lineup"]["order"])  # 직렬화 가능


def _mlb_both_sides_bundle():
    return {
        "offense": {
            "Los Angeles Dodgers": {"xwoba_30d": 0.340},
            "San Diego Padres": {"xwoba_30d": 0.310},
        },
        "pitchers": {
            "Yoshinobu Yamamoto": {"xwoba_allowed": 0.280, "throws": "R"},
            "Dylan Cease": {"xwoba_allowed": 0.310, "throws": "R"},
        },
        "bullpen": {
            "Los Angeles Dodgers": {"bp_pitches_3d": 210},
            "San Diego Padres": {"bp_pitches_3d": 180},
        },
        "standings": {
            "Los Angeles Dodgers": {"rank": 1, "w": 80, "l": 50, "d": 0, "win_pct": 0.615},
            "San Diego Padres": {"rank": 2, "w": 75, "l": 55, "d": 0, "win_pct": 0.577},
        },
        "form": {
            "Los Angeles Dodgers": {
                "score_games": 3, "results_l3": "WWL", "runs_l3": 15,
                "runs_allowed_l3": 9, "runs_per_game_l3": 5.0,
            },
            "San Diego Padres": {
                "score_games": 3, "results_l3": "LWW", "runs_l3": 12,
                "runs_allowed_l3": 11, "runs_per_game_l3": 4.0,
            },
        },
        "weather": {},
    }


def test_mlb_rejudge_research_fills_all_five_card_cells():
    """카드 칸 정의는 그대로 두고, 공급이 양 팀 5칸을 채워야 한다.

    모름 허용(MAX_UNKNOWN=2)을 늘리지 않는다. 칸을 채우면 2단이 다시 돈다.
    """
    from app.engine.card import CELL_KEYS, MAX_UNKNOWN, build_card

    jg = {
        "home": "Los Angeles Dodgers", "away": "San Diego Padres",
        "game_id": 1, "sport": "mlb",
        "stats": {"home_pitcher": "Yoshinobu Yamamoto", "away_pitcher": "Dylan Cease",
                  "home_pitcher_era": 2.50, "away_pitcher_era": 3.80},
    }
    research: dict = {}
    apply_lineup_poll_to_research(research, jg, _poll())
    merge_source_data(research, jg, "mlb", _mlb_both_sides_bundle())
    apply_lineup_poll_to_research(research, jg, _poll())
    card = build_card(jg, research)
    assert card["unknown"] == []
    assert card["judgeable"] is True
    assert len(card["unknown"]) <= MAX_UNKNOWN
    for side in ("home", "away"):
        for key in CELL_KEYS:
            assert card[side][key]["known"], f"{side}.{key} 미수집: {card[side][key]}"
    assert "Yamamoto" in card["home"]["starter"]["facts"][0]
    assert "타순 9명" in " ".join(card["home"]["batting"]["facts"])
    assert "210구" in " ".join(card["home"]["bullpen"]["facts"])
    assert "WWL" in " ".join(card["home"]["recent3"]["facts"])
    assert "1위" in card["home"]["weight"]["facts"][0]


def test_merge_mlb_starter_name_from_stats_when_jg_empty():
    """헤더는 stats.home_pitcher를 쓰는데 카드는 research 이름을 본다."""
    from app.engine.card import build_side

    jg = {"home": "Los Angeles Dodgers", "away": "San Diego Padres",
          "game_id": 1, "stats": {"home_pitcher": "Yoshinobu Yamamoto",
                                  "away_pitcher": "Dylan Cease",
                                  "home_pitcher_era": 2.50, "away_pitcher_era": 3.80}}
    research: dict = {}
    merge_source_data(research, jg, "mlb", {
        "pitchers": {"Yoshinobu Yamamoto": {"xwoba_allowed": 0.280}},
        "weather": {},
    })
    home = build_side(research, "home")
    assert home["starter"].known
    assert "Yamamoto" in home["starter"].facts[0]
    assert jg["home_pitcher"] == "Yoshinobu Yamamoto"


def test_compute_picks_without_dist_does_not_keep_old_trace():
    """이전 λ 트레이스를 남기고 '핵심 지표 전무'만 붙이면 카드가 모순된다."""
    from app.pipeline import _compute_picks

    jg = {
        "game_id": 1, "sport": "mlb", "status": "scheduled",
        "home": "Los Angeles Dodgers", "away": "San Diego Padres",
        "starts_at_kst": "08/29 10:10", "league": "MLB",
        "p_claude": 0.55, "judge_confidence": "medium",
        "market_probs": {}, "best_odds": {}, "alt_markets": [],
        "expert_picks": [], "stats": {}, "research": {},
        "lambda_trace": ["홈 타선 xwOBA 0.340 → ×1.05"],
        "lambda_missing": [],
        "lam": {"home": 4.5, "away": 4.2},
    }
    _compute_picks(Settings(_env_file=None), [jg], "mlb", None)
    assert jg.get("lambda_trace") == []
    assert jg.get("lam") is None
    assert jg.get("lambda_missing") == ["핵심 지표(타선·선발) 전무"]
    assert not any(c["market"] == "totals" for c in (jg.get("market_board") or []))
