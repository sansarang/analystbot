"""카드 판정 블록 — 사람이 읽는 형태의 계약.

🔴 실측 2026-09-07 실카드(`card:mlb:2026-09-06`)에서 드러난 여섯 결함:
   ① 문장이 잘렸다 — "…홈 확률을 0.50" 에서 끝났다(300자 상한)
   ② 근거 3개가 뭉개졌다 — "…득실 흐름은 홈 쪽 자료4: Washington…"
   ③ 팀 이름이 두 언어 — 제목 "LA 다저스", 본문 "Los Angeles Dodgers"
   ④ 내부 용어 — "신뢰도 medium", "근거 지지 축 없음"
   ⑤ 양쪽 승률을 둘 다 — 54.0% / 46.0% 는 같은 정보
   ⑥ 전개·분기점·예상점수·발생확률이 카드에 하나도 없었다
"""

import pytest

from app.engine.card import verdict_block


def _jg(**kw):
    base = {
        "home": "Los Angeles Dodgers", "away": "Washington Nationals",
        "p_claude": 0.56, "starts_at_kst": "2026-09-07 11:10",
        "judge_confidence": "medium",
        "matchup": {
            "우세": "home",
            "전개": {"분기점": "Wrobleski가 5이닝을 넘기는가",
                    "예상점수": {"홈": 5, "원정": 3}},
            "결론": {"판단": "선발 이닝 소화력이 이 경기를 가릅니다."},
            "변수": ["조기 강판 — 발생 시 원정 방향 약 6%p · 발생 확률 48% · "
                    "현재 p에 3%p 기반영 · 근거 자료14"],
            "추가확인": ["투구수 제한 여부(구단 미공개)"]},
    }
    base.update(kw)
    return base


def _text(jg):
    return "\n".join(verdict_block(jg))


# ═══════════════ ① 잘리지 않는다

def test_판단_서술이_통째로_실린다():
    """🔴 300자 상한이 문장 중간을 잘랐다. 자르지 않는다."""
    long = "가" * 800 + " 끝문장이다."
    jg = _jg()
    jg["matchup"]["결론"]["판단"] = long
    assert long in _text(jg), "판단이 잘렸다"


def test_근거를_이어붙이지_않는다():
    """🔴 `" ".join(근거)` 가 앞뒤 문장을 구분 없이 붙였다."""
    jg = _jg()
    jg["matchup"]["근거"] = ["자료1: 첫 근거", "자료4: 둘째 근거"]
    t = _text(jg)
    assert "첫 근거 자료4" not in t
    # 카드는 `근거` 가 아니라 `결론.판단` 을 쓴다 — 감사용 문장은 싣지 않는다.
    assert "자료4: 둘째 근거" not in t


# ═══════════════ ②③ 한 언어 · 내부 용어 금지

def test_팀_이름이_한_언어로만_나온다():
    t = _text(_jg())
    assert "LA 다저스" in t and "워싱턴 내셔널스" in t
    assert "Los Angeles Dodgers" not in t
    assert "Washington Nationals" not in t


@pytest.mark.parametrize("banned", ["medium", "high", "low",
                                    "지지 축", "실데이터", "판정 승률"])
def test_내부_용어가_새지_않는다(banned):
    assert banned not in _text(_jg())


def test_확신도는_사람_말로_나온다():
    assert "확신도 보통" in _text(_jg())


# ═══════════════ ④ 한쪽만 — 반대편은 같은 정보다

def test_우세팀_확률만_적는다():
    t = _text(_jg())
    assert "LA 다저스 우세 56%" in t
    assert "44%" not in t, "반대편 확률까지 적었다"


def test_원정_우세면_원정_이름으로_적는다():
    jg = _jg(p_claude=0.44)
    jg["matchup"]["우세"] = "away"
    assert "워싱턴 내셔널스 우세 56%" in _text(jg)


def test_박빙이면_박빙이라_적는다():
    jg = _jg(p_claude=0.53)
    jg["matchup"]["우세"] = "박빙"
    assert "박빙" in _text(jg)


# ═══════════════ ⑤ 전개·분기점·발생확률이 실린다

def test_예상점수는_원정_홈_순서다():
    """카드 표기가 `원정 @ 홈` 이므로 점수도 같은 순서여야 한다
    (실사고 2026-08-27: 순서가 뒤집혀 정반대로 읽혔다)."""
    assert "예상 3-5" in _text(_jg())


def test_갈림길과_발생확률이_실린다():
    t = _text(_jg())
    assert "갈림길 — Wrobleski가 5이닝을 넘기는가" in t
    assert "발생 확률 48%" in t
    assert "원정 쪽으로 6%p" in t


def test_발생확률이_없으면_미확인이라_적는다():
    """⚠️ 자료14 가 답을 못 준 변수의 확률을 카드가 지어내지 않는다."""
    jg = _jg()
    jg["matchup"]["변수"] = ["조기 강판 — 발생 시 원정 방향 약 6%p · "
                             "현재 p에 3%p 기반영 · 근거 자료10"]
    t = _text(jg)
    assert "발생 확률은 미확인" in t
    assert "발생 확률 " not in t.replace("발생 확률은 미확인", "")


def test_확인_불가를_밝힌다():
    """모르는 것을 밝히는 것도 정보다."""
    assert "확인 불가 — 투구수 제한 여부(구단 미공개)" in _text(_jg())


# ═══════════════ ⑥ 없는 것을 만들지 않는다

def test_판정이_없으면_빈_블록이다():
    assert verdict_block({"home": "A", "away": "B"}) == []
    assert verdict_block({}) == []


def test_전개가_없어도_깨지지_않는다():
    jg = _jg()
    jg["matchup"].pop("전개")
    t = _text(jg)
    assert "LA 다저스 우세 56%" in t
    assert "갈림길" not in t and "예상" not in t


def test_판단이_비면_그_줄을_만들지_않는다():
    jg = _jg()
    jg["matchup"]["결론"] = {}
    t = _text(jg)
    assert "갈림길" in t          # 나머지는 살아 있다
    assert t.count("\n\n") <= 2   # 빈 줄만 남기지 않는다


def test_파이프라인이_이_블록을_쓴다():
    src = open("app/pipeline.py", encoding="utf-8").read()
    assert "from app.engine.card import verdict_block" in src
    assert 'f"  판정 근거: {str(g[\'verdict\'])[:300]}"' not in src, \
        "옛 잘림 렌더러가 남아 있다"
