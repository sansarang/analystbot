"""SOC-2 — 축구 3-way(홈승·무·원정승). **야구는 한 글자도 안 바뀐다.**

사용자 지시 2026-09-12: 축구 파이프라인을 야구와 동일하게.

🔴 왜. `apply_winner` 는 **팀 이름 하나**를 받아 홈/원정에 맞춘다:

     w = verdict["승자"];  hit_h, hit_a = _name_hits(w, home), _name_hits(w, away)
     if hit_h == hit_a:  → 판정을 버린다

   축구는 무승부가 정상 결과인데 **표현할 칸이 없다.** "무"를 승자로 주면
   두 팀 다 안 맞아 `False` 가 되고 판정이 통째로 버려진다.

⚠️ **반대 위험이 크다.** `apply_winner` 는 야구 v2·v3 가 쓴다. 3-way 를
   더하면서 2-way 동작이 한 글자라도 바뀌면 그게 P0 다. 계약의 절반이 그것이다.

🔴 그리고 **판정을 버리는 길을 지우면 안 된다** — 실측 2026-09-11: gemini 가
   경기에 없는 `KT Wiz` 를 4회 중 1회 냈다. 고쳐 쓰지 않고 버리는 것이 맞다.
"""

import pytest

from app.engine import matchup as MU


def _jg(sport="kbo"):
    return {"game_id": 1, "sport": sport,
            "home": "Doosan Bears", "away": "NC Dinos"}


def _soc():
    return {"game_id": 2, "sport": "soccer", "league": "K리그1",
            "home": "Daejeon Citizen", "away": "Pohang Steelers"}


# ═══════════════ ① 야구 회귀 0 — 2-way 는 그대로

def test_야구는_승자_이름_그대로다():
    jg = _jg()
    assert MU.apply_winner(jg, {"승자": "Doosan Bears", "확신": "중"}) is True
    assert jg["winner"] == "Doosan Bears"
    assert jg["matchup"]["승자"] == "Doosan Bears"


def test_야구는_결과_칸이_생기지_않는다():
    """🔴 2-way 원장에 없던 키가 생기면 카드·감사가 그것을 읽는다."""
    jg = _jg()
    MU.apply_winner(jg, {"승자": "NC Dinos"})
    assert "결과" not in jg["matchup"]


def test_경기의_팀이_아니면_여전히_버린다():
    """🔴 실측 2026-09-11: gemini 가 경기에 없는 팀을 4회 중 1회 냈다."""
    jg = _jg()
    assert MU.apply_winner(jg, {"승자": "KT Wiz"}) is False
    assert "winner" not in jg


def test_야구에서_무는_받지_않는다():
    """야구에 무승부 판정은 없다 — 들어오면 버린다."""
    jg = _jg()
    assert MU.apply_winner(jg, {"결과": "무"}) is False


# ═══════════════ ② 축구 3-way

def test_홈승을_홈팀으로_읽는다():
    jg = _soc()
    assert MU.apply_winner(jg, {"결과": "홈승", "확신": "중"}) is True
    assert jg["winner"] == "Daejeon Citizen"
    assert jg["matchup"]["결과"] == "홈승"


def test_원정승을_원정팀으로_읽는다():
    jg = _soc()
    assert MU.apply_winner(jg, {"결과": "원정승"}) is True
    assert jg["winner"] == "Pohang Steelers"


def test_무는_승자가_없다():
    """🔴 무승부는 **정상 결과**다 — 판정 실패가 아니다."""
    jg = _soc()
    assert MU.apply_winner(jg, {"결과": "무", "확신": "하"}) is True
    assert jg["matchup"]["결과"] == "무"
    assert jg["winner"] is None
    assert jg["matchup"]["승자"] is None


def test_모르는_결과는_버린다():
    """🔴 지어낸 라벨을 통과시키면 카드가 거짓을 말한다."""
    for bad in ("승", "draw", "", "홈", None):
        jg = _soc()
        assert MU.apply_winner(jg, {"결과": bad}) is False, bad


def test_축구도_팀_이름으로_올_수_있다():
    """🔴 종전 경로 호환 — `승자` 로 오면 종전처럼 처리한다."""
    jg = _soc()
    assert MU.apply_winner(jg, {"승자": "Daejeon Citizen"}) is True
    assert jg["winner"] == "Daejeon Citizen"


def test_서술과_확신은_3way에서도_실린다():
    jg = _soc()
    MU.apply_winner(jg, {"결과": "무", "확신": "상", "서술": "양 팀 다 결장이 많다."})
    assert jg["matchup"]["확신"] == "상"
    assert jg["matchup"]["서술"] == "양 팀 다 결장이 많다."


# ═══════════════ ③ 카드 — 무를 판정 실패로 적지 않는다

def test_카드가_무를_판정으로_센다():
    """🔴 `_render_card_v3` 는 `winner` 로 판정 여부를 센다. 무는 winner 가
    없으므로 그대로 두면 **"판정 실패"로 나간다**(SRCH-5 P0 와 같은 결함)."""
    from app import pipeline as P

    g = {"game_id": 1, "sport": "soccer", "league": "K리그1",
         "status": "scheduled", "home": "Daejeon Citizen",
         "away": "Pohang Steelers", "home_kr": "대전", "away_kr": "포항",
         "starts_at_kst": "2026-09-12T19:00:00+09:00",
         "winner": None,
         "matchup": {"결과": "무", "승자": None, "확신": "중"},
         "order_v3": {"자료": [], "갈림길목록": [], "질문": [], "DB본것": [],
                      "DB판정": "확인", "승자변경": False, "DB사유": ""}}
    out = P._render_card({"sport": "soccer", "date": "2026-09-12",
                          "games": [g], "picks": [], "recommended": [],
                          "combos": {}})
    assert "판정 실패" not in out
    assert "무승부" in out or "무" in out.split(P.DETAIL_SEP)[0]


def test_경기별_카드가_무를_적는다():
    from app.engine import form_card as FC

    jg = {"game_id": 1, "sport": "soccer", "league": "K리그1",
          "home": "Daejeon Citizen", "away": "Pohang Steelers",
          "winner": None,
          "matchup": {"결과": "무", "승자": None, "확신": "중",
                      "서술": "양 팀 다 결장이 많다."},
          "order_v3": {"자료": [], "갈림길목록": [], "질문": [], "DB본것": [],
                       "승자변경": False, "DB사유": ""}}
    out = FC.render_search_card(jg, "soccer")
    assert "무승부" in out
    assert "양 팀 다 결장이 많다." in out
