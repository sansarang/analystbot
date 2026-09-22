"""[LE-1b] 역사 배당 적재 — football-data.co.uk.

🔴 **왜 필요한가.** 우리 DB 배당은 **한 달치뿐**이다(실측 2026-09-22:
   MLB 8/22~ · KBO·NPB 9/2~ · 축구 8/23~). walk-forward(LE-2)를 돌릴 길이가
   없다. 이 CSV 에는 4시즌 · 개별 북 8개 · **개장/마감**이 다 있다.

🔴 **`games`·`odds_snapshots` 를 건드리지 않는다.** `odds_snapshots.game_id` 는
   `games(id)` 를 참조하므로 역사 경기를 넣으려면 `games` 에 19,289행을
   만들어야 한다 — **D32 가 겪은 사고**다(소급이 타국 동명 리그를 끌어와
   `games` 오염 750행, 백업 뜨고 삭제).
"""
from __future__ import annotations

import pytest

import tools.backfill_history as B

#: 실측 헤더(`data/elo/csv/D1_2223.csv` · 2026-09-22)에서 그대로 떼 온 한 행.
ROW = {
    "Div": "E0", "Date": "05/08/2022", "HomeTeam": "Crystal Palace",
    "AwayTeam": "Arsenal", "FTHG": "0", "FTAG": "2", "FTR": "A",
    "B365H": "3.60", "B365D": "3.50", "B365A": "2.05",
    "B365CH": "4.00", "B365CD": "3.60", "B365CA": "1.90",
    "PSH": "3.70", "PSD": "3.55", "PSA": "2.08",
    "PSCH": "4.09", "PSCD": "3.66", "PSCA": "1.93",
    "AvgH": "3.58", "AvgD": "3.48", "AvgA": "2.04",
    "AvgCH": "3.95", "AvgCD": "3.58", "AvgCA": "1.91",
    "B365>2.5": "1.90", "B365<2.5": "1.90",
    "B365C>2.5": "1.95", "B365C<2.5": "1.85",
    # 🔴 빈 칸 — 북마다 제공 범위가 다르다
    "BWH": "", "BWD": "", "BWA": "",
    # 🔴 배당이 아닌 값(1 이하)
    "IWH": "0", "IWD": "1.00", "IWA": "-1",
}


def _by(rows, book, phase, market="h2h"):
    return {sd: od for bk, ph, mk, _, sd, od in rows
            if bk == book and ph == phase and mk == market}


def test_개장과_마감을_구분한다():
    """🔴 `C` 가 붙은 컬럼이 마감이다. 섞이면 LE-4 의 목표(`p_close−p_open`)가
    통째로 거짓이 된다."""
    rows = B.prices_of(ROW, ("h2h",))
    assert _by(rows, "B365", "open") == {"home": 3.60, "draw": 3.50, "away": 2.05}
    assert _by(rows, "B365", "close") == {"home": 4.00, "draw": 3.60, "away": 1.90}
    # 피나클도 들어온다 — LE-3 의 '참 확률' 후보다
    assert _by(rows, "PS", "close")["home"] == 4.09


def test_빈_칸은_행을_만들지_않는다():
    """⚠️ 없는 값을 0 이나 평균으로 채우면 '이 북이 그 가격을 냈다'가 거짓이 된다."""
    rows = B.prices_of(ROW, ("h2h",))
    assert _by(rows, "BW", "open") == {}, "빈 칸으로 행을 만들었다"


def test_배당이_1_이하면_버린다():
    """🔴 소수배당은 1 보다 크다. 0·1·음수는 배당이 아니다."""
    rows = B.prices_of(ROW, ("h2h",))
    assert _by(rows, "IW", "open") == {}, f"{_by(rows, 'IW', 'open')}"


def test_총점은_라인을_싣는다():
    """⚠️ 라인 없는 총점 배당은 무의미하다."""
    rows = B.prices_of(ROW, ("totals",))
    tot = [(bk, ph, sd, ln, od) for bk, ph, mk, ln, sd, od in rows if mk == "totals"]
    assert tot, "총점을 안 읽었다"
    assert all(ln == 2.5 for _, _, _, ln, _ in tot)
    assert {sd for _, _, sd, _, _ in tot} == {"over", "under"}


def test_마켓을_고를_수_있다():
    """⚠️ 핸디는 아직 안 싣는다(LE-5 보류) — 범위를 코드가 아니라 인자로 정한다."""
    assert all(mk == "h2h" for _, _, mk, _, _, _ in B.prices_of(ROW, ("h2h",)))
    assert B.prices_of(ROW, ()) == []


def test_적재기가_운영표를_건드리지_않는다():
    """🔴 **D32 재발 방지.** `games`·`odds_snapshots` 에 쓰지 않는다."""
    import inspect

    src = inspect.getsource(B)
    for banned in ("INSERT INTO games", "INSERT INTO odds_snapshots",
                   "UPDATE games", "DELETE FROM games"):
        assert banned not in src, f"운영 표에 쓴다: {banned}"
    assert "history_matches" in src and "history_prices" in src


def test_멱등이다():
    """⚠️ 두 번 돌려도 중복이 없어야 롤백이 안전하다(영향지도 ④)."""
    import inspect

    src = inspect.getsource(B)
    assert src.count("ON CONFLICT") >= 2, "멱등 보장이 없다"
    assert "DO NOTHING" in src


def test_다운로드를_다시_짓지_않았다():
    """🔴 원본은 `soccer_elo.download_csvs` 다(사본 금지)."""
    import inspect

    src = inspect.getsource(B)
    assert "download_csvs" in src
    assert "httpx" not in src, "다운로드를 여기서 다시 짰다"
    assert "football-data.co.uk" == B.SOURCE


def test_Elo_파서를_건드리지_않았다():
    """🔴 `soccer_elo._parse_csv` 는 Elo 용이라 **북별 배당을 버린다.**
    고치면 Elo 가 깨지므로 여기서 따로 읽는다 — 그 사실을 잠근다."""
    import inspect

    from app.models import soccer_elo as SE

    assert "_market_probs_from_row" in inspect.getsource(SE._parse_csv), (
        "Elo 파서가 바뀌었다 — LE-1b 가 따로 읽는 이유가 아직 유효한지 보라")


def test_실제_캐시를_읽는다():
    """⚠️ 픽스처만으로는 컬럼 이름이 맞는지 모른다 — 실파일로 확인한다."""
    files = B.csv_files()
    if not files:
        pytest.skip("CSV 캐시가 없다(운영 볼륨에만 있을 수 있다)")
    path, season, code = files[0]
    rows = B.read_file(path, season, ("h2h", "totals"))
    assert rows, f"{path} 에서 한 경기도 못 읽었다"
    have = [r for r in rows if r["prices"]]
    assert have, "가격을 한 줄도 못 읽었다 — 컬럼 이름이 바뀌었다"
    r = have[0]
    assert r["home"] and r["away"] and r["date"]
    phases = {ph for _, ph, _, _, _, _ in r["prices"]}
    assert phases == {"open", "close"}, phases
