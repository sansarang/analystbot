"""[ELO-N] 축구 사전값이 없어 가설이 안 섰다 — **이름이 안 맞았다.**

사용자 2026-09-22: "축구 가설이 왜 안 서는게 많은지 검토하고 수정해라"

🔴 실측:
```
n03_gate (축구 45경기)  보드고정 35 · 동의 6 · 가치의심 3 · 시장과대 1
멈춤 사유               "사전값이 없다 — 보드 고정"
missing: ["Tottenham Hotspur FC", "Aston Villa FC"]
         ["CA Osasuna", "Rayo Vallecano de Madrid"]
         ["Bologna FC 1909", "Torino FC"]
사전값 있음/없음:  야구 99/8 · **축구 12/33**
```
`config/elo_names.yaml` 대조표에 최근 14일 홈팀이 대거 빠져 있다 —
EPL 15 · 라리가 17 · 세리에A 20 · 분데스 14 · J1 10 · 덴마크 7팀.

ALI-1 이 이미 겪은 자리다 — "`Como 1907` 은 0건, `Como` 는 나온다."
"""
from __future__ import annotations

import inspect

from app.models import soccer_elo as SE


# ── 간추리기 ────────────────────────────────────────────────────────

def test_법인격과_창단연도를_뗀다():
    """🔴 이름이 아니라 **형식**이다."""
    assert SE.slim("Tottenham Hotspur FC") == "tottenham hotspur"
    assert SE.slim("Bologna FC 1909") == "bologna"
    assert SE.slim("CA Osasuna") == "osasuna"
    assert SE.slim("AS Monaco FC") == "monaco"


def test_악센트_규칙을_다시_짓지_않았다():
    """🔴 원본은 `fotmob.norm`(치환표 `team_name_map.yaml`)이다.
    `ø`·`æ`·`ß` 는 NFKD 로 안 풀린다(FMR-1)."""
    src = inspect.getsource(SE.slim)
    assert "from app.collectors.fotmob import norm" in src
    assert "unicodedata" not in src, "정규화를 여기서 다시 짰다"
    assert SE.slim("Brøndby IF") == "brondby"


def test_빈_정규화는_안_맞춘다():
    """🔴 D26 — `norm('박건우') → ''`. 빈 키로 맞추면 **전부 서로 일치**한다."""
    assert SE.slim("박건우") == ""
    assert SE._slim_index(["박건우", "김도영"]) == {}


def test_법인격만_있는_이름을_비우지_않는다():
    """⚠️ 토큰이 전부 지워지면 원래 정규화 이름을 쓴다."""
    assert SE.slim("AS") == "as"
    assert SE.slim("FC") == "fc"


def test_모호하면_둘_다_버린다():
    """🔴 `Al Ahli` 는 사우디·카타르·UAE 에 실재한다. 조용히 하나를 고르면
    그게 D15 가 오탐을 세 번 낸 자리다."""
    idx = SE._slim_index(["Al Ahli FC", "Al Ahli SC", "Bologna FC 1909"])
    assert "al ahli" not in idx, idx
    assert idx.get("bologna") == "Bologna FC 1909"


def test_같은_이름이_두_번_와도_버리지_않는다():
    """⚠️ 반대 위험 — 같은 문자열이 중복이면 모호가 아니다."""
    idx = SE._slim_index(["Bologna FC", "Bologna FC"])
    assert idx.get("bologna") == "Bologna FC"


# ── 느슨 매칭 ───────────────────────────────────────────────────────

_RATINGS = {"I1": {"Bologna": 1520.0, "Torino": 1480.0},
            "E0": {"Tottenham": 1600.0, "Aston Villa": 1550.0}}


def test_대조표가_먼저_이긴다(monkeypatch):
    """🔴 사람이 정한 것을 규칙이 덮지 않는다."""
    monkeypatch.setattr(SE, "_elo_names",
                        lambda: {"세리에A": {"Bologna FC 1909": "Torino"}})
    out = SE.ratings_loose("세리에A", ["Bologna FC 1909"], _RATINGS)
    # 대조표가 Torino 로 지목했으면 그 값이다(정규화로 Bologna 를 덮지 않는다)
    assert out["Bologna FC 1909"] == 1480.0


def test_못_찾은_팀만_정규화로_맞춘다(monkeypatch):
    monkeypatch.setattr(SE, "_elo_names", lambda: {"세리에A": {}})
    out = SE.ratings_loose("세리에A", ["Bologna FC 1909", "Torino FC"],
                           _RATINGS)
    assert out == {"Bologna FC 1909": 1520.0, "Torino FC": 1480.0}


def test_리그_밖에서_찾지_않는다(monkeypatch):
    """🔴 종전 규약 — 리그 간 비교가 되면 안 된다."""
    monkeypatch.setattr(SE, "_elo_names", lambda: {"세리에A": {}})
    out = SE.ratings_loose("세리에A", ["Tottenham Hotspur FC"], _RATINGS)
    assert out == {}, out


def test_모호한_팀은_안_붙는다(monkeypatch):
    monkeypatch.setattr(SE, "_elo_names", lambda: {"세리에A": {}})
    r = {"I1": {"Al Ahli FC": 1500.0, "Al Ahli SC": 1400.0}}
    assert SE.ratings_loose("세리에A", ["Al Ahli"], r) == {}


def test_팀_목록이_없으면_종전과_같다(monkeypatch):
    """⚠️ 되돌릴 길 — DB 를 못 읽으면 대조표 정확 일치만이다."""
    monkeypatch.setattr(SE, "_elo_names",
                        lambda: {"세리에A": {"Bologna FC 1909": "Bologna"}})
    assert SE.ratings_loose("세리에A", [], _RATINGS) == \
        SE.ratings_for_league("세리에A", _RATINGS)


def test_레이팅_풀이_없으면_빈_결과(monkeypatch):
    monkeypatch.setattr(SE, "_elo_names", lambda: {"세리에A": {}})
    assert SE.ratings_loose("세리에A", ["Bologna FC 1909"], {}) == {}


# ── 배선 ────────────────────────────────────────────────────────────

def test_캐시를_채우는_쪽이_느슨_매칭을_쓴다():
    """🔴 `n01_prior` 는 한 줄도 안 건드린다 — 캐시를 채우는 쪽만 고친다."""
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(SE.publish_ratings).splitlines())
    assert "ratings_loose" in src
    assert "_league_teams" in src


def test_팀_목록_조회가_최근_경기만_본다():
    """⚠️ 전 시즌을 긁으면 개명 전 이름까지 들어온다."""
    assert "30 days" in SE._TEAMS_SQL and "7 days" in SE._TEAMS_SQL
    assert "sport='soccer'" in SE._TEAMS_SQL


def test_흐름이_pool_을_넘긴다():
    """🔴 배선의 끝 — pool 이 없으면 DB 표기를 못 읽어 종전과 같다."""
    from app.flow import bridge as B

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(B).splitlines())
    assert "ensure_soccer_elo(redis, soccer_want, pool=pool)" in src
    assert "publish_ratings(redis, lgs, day, pool=pool)" in src
