"""npb.jp 팀 타격 → λ home_offense. 라이브 HTTP 없음."""
from app.collectors.npb_stats import (
    HIT_HEADER,
    PIT_HEADER,
    fetch_team_stats,
    league_baselines,
    merge_into_research,
    parse_table,
)
from app.config import Settings
from app.engine.scoring import mlb_lambdas


def _tbl(header, row):
    th = "<tr>" + "".join(f"<th>{h}</th>" for h in header) + "</tr>"
    td = "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    return f"<table>{th}{td}</table>"


# 실측 2026-08-28 tmb_c / tmp_c 한신 행 (헤더·값 길이만 맞추면 된다)
_HIT_HANSHIN = [
    "阪神", ".247", "114", "4299", "3789", "423", "936", "143", "10", "102",
    "1405", "402", "58", "22", "82", "26", "347", "24", "55", "970", "78",
    ".371", ".317",
]
_HIT_HAWKS = [
    "ソフトバンク", ".258", "115", "4458", "3891", "561", "1002", "177", "19",
    "120", "1577", "512", "62", "11", "58", "36", "407", "20", "46", "863",
    "63", ".410", ".333",
]
_PIT_HANSHIN = [
    "阪神", "2.90", "114", "64", "49", "36", "71", "92", "8", "15", "16",
    ".566", "4150", "1011", "895", "94", "260", "15", "34", "916", "17", "1",
    "360", "326",
]
_PIT_HAWKS = [
    "ソフトバンク", "3.20", "115", "70", "40", "30", "80", "100", "5", "10",
    "8", ".636", "4200", "1020", "900", "80", "250", "10", "30", "900", "10",
    "0", "400", "360",
]


class _Client:
    async def get(self, path):
        if path.endswith("tmb_c.html"):
            return _tbl(HIT_HEADER, _HIT_HANSHIN)
        if path.endswith("tmb_p.html"):
            return _tbl(HIT_HEADER, _HIT_HAWKS)
        if path.endswith("tmp_c.html"):
            return _tbl(PIT_HEADER, _PIT_HANSHIN)
        if path.endswith("tmp_p.html"):
            return _tbl(PIT_HEADER, _PIT_HAWKS)
        raise AssertionError(path)


def test_header_mismatch_rejects_rows():
    bad = _tbl(HIT_HEADER, _HIT_HANSHIN).replace("出塁率", "OBP")
    rows, _ = parse_table(bad, HIT_HEADER)
    assert rows == []


def test_parse_obp_from_measured_shape():
    rows, hdr = parse_table(_tbl(HIT_HEADER, _HIT_HANSHIN), HIT_HEADER)
    assert hdr[-2:] == ["長打率", "出塁率"]
    assert rows[0]["チーム"] == "阪神"
    assert rows[0]["出塁率"] == ".317"


async def test_fetch_maps_odds_names_and_computes_ops():
    teams = await fetch_team_stats(_Client(), year=2026)
    assert set(teams) == {"Hanshin Tigers", "Fukuoka SoftBank Hawks"}
    h = teams["Hanshin Tigers"]
    assert h["window"] == "season"
    assert h["obp"] == 0.317
    assert h["slg"] == 0.371
    assert h["ops"] == 0.688          # 표에 OPS 컬럼 없음 — 합산만
    assert h["team_era"] == 2.90
    assert "woba" not in h


def test_league_baselines_from_collected_not_mlb_constant():
    teams = {"Hanshin Tigers": {"obp": 0.317, "ops": 0.688, "slg": 0.371},
             "Fukuoka SoftBank Hawks": {"obp": 0.333, "ops": 0.743, "slg": 0.410}}
    base = league_baselines(teams)
    assert base["obp"] == 0.325
    assert "woba" not in base


def test_merge_overwrites_llm_and_keeps_yahoo_era():
    teams = {"Yomiuri Giants": {"obp": 0.297, "ops": 0.651, "slg": 0.354,
                                "team_era": 3.10},
             "Hanshin Tigers": {"obp": 0.317, "ops": 0.688, "slg": 0.371}}
    jg = {"home": "Yomiuri Giants", "away": "Hanshin Tigers"}
    research = {"home_offense": {"obp_30d": 0.999, "woba_30d": 0.400},
                "home_pitcher": {"name": "戸郷翔征", "era_season": 2.80}}
    filled = merge_into_research(research, jg, teams)
    assert research["home_offense"]["obp_30d"] == 0.297
    assert "woba_30d" not in research["home_offense"]
    assert research["home_pitcher"]["era_season"] == 2.80
    assert "league_baselines" in filled
    assert research["home_bullpen"]["era"] == 3.10


def test_obp_path_makes_npb_lambda_usable():
    teams = {"Yomiuri Giants": {"obp": 0.297, "ops": 0.651, "slg": 0.354},
             "Hanshin Tigers": {"obp": 0.317, "ops": 0.688, "slg": 0.371}}
    jg = {"home": "Yomiuri Giants", "away": "Hanshin Tigers"}
    research = {"home_pitcher": {"era_season": 2.80},
                "away_pitcher": {"era_season": 3.10}}
    merge_into_research(research, jg, teams)
    lam = mlb_lambdas(jg, research, Settings(_env_file=None), sport="npb")
    assert lam.usable
    assert any("OBP" in t for t in lam.trace)
    assert research["home_offense"]["obp_30d"] == 0.297
