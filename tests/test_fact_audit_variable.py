"""FA-2 — L1 오탐 2유형의 계약. **감시층만 바뀐다. 판정은 불변이다.**

🔴 (a) **변수 문장의 조건절은 가정이지 인용이 아니다.**
   형식의 원본은 `prompts.MATCHUP` [변수 형식]:
       "<리스크 서술> — 발생 시 <홈|원정> 방향 약 N%p · … · 근거 <자료 번호>"
   `발생 시` **앞**이 가정, **뒤**가 실재 주장이다. 종전 코드는 그 위험을
   주석으로 인지만 하고 두었다(`_THRESHOLD` 가 `↑↓+` 만 본다) — `미만`·`이상`
   을 문장 단위로 빼면 자료10 인용이 함께 빠지기 때문이었다. 같은 문장의
   **다른 자리**라는 것이 열쇠였다.

🔴 (b) **표본 크기는 그 값 앞에서 가장 가까운 표기를 쓴다.**
   실측 game=1734: "로건은 최근 5경기 … 김진욱은 최근 2경기 9이닝 11실점"
   에서 11실점의 표본이 5 로 잡혀, 합계 재계산이 `vals[:5]`(합 19)만 보고
   정답 `vals[:2]`(4+7=11)을 건너뛰었다. **판정이 맞았는데 환각으로 찍혔다.**

전후 측정(운영, 2026-09-11): 오탐 5건 해소 · 신규 mismatch 0 ·
verified 86→69. 줄어든 22건 **전부** 변수 조건절(설명 안 됨 0건)이고,
그 수는 이제 `condition_n` 으로 남는다.
"""

import pytest

from app.engine import fact_audit as fa

# 자료4 구조 그대로. home 선발 r=[4,7,1,6,1] · innings=[4.667,4.333,6.0,5.0,5.0]
PROMPT = """
4. 양팀 오늘 선발투수의 최근 등판 기록: {"home": {"선발등판": [
 {"opponent": "Hanwha Eagles", "innings": 4.667, "r": 4, "date": "2026-09-04"},
 {"opponent": "LG Twins", "innings": 4.333, "r": 7, "date": "2026-08-29"},
 {"opponent": "Doosan Bears", "innings": 6.0, "r": 1, "date": "2026-08-21"},
 {"opponent": "NC Dinos", "innings": 5.0, "r": 6, "date": "2026-08-14"},
 {"opponent": "Samsung Lions", "innings": 5.0, "r": 1, "date": "2026-07-31"}]},
 "away": {"선발등판": [
 {"opponent": "Kia Tigers", "innings": 6.0, "r": 4, "date": "2026-09-05"},
 {"opponent": "Samsung Lions", "innings": 5.667, "r": 4, "date": "2026-08-29"},
 {"opponent": "SSG Landers", "innings": 6.0, "r": 0, "date": "2026-08-23"}]}}
10. 변수 대장: {"이닝분포": {"최장": 1.0, "p25": 4.0, "p50": 5.0}}
"""
NAMES = {"김진욱": "home", "로건": "away", "이준기": "away"}


def _units(claims):
    return {(c["unit"], c["value"]) for c in claims}


# ═══════════════ (a) 조건절은 빼고, 근거부는 남긴다

def test_조건절의_가정값은_감사하지_않는다():
    """실측 game=1735 · 1736 이 이 자리였다."""
    v = {"변수": ["원정 선발 이준기가 3이닝 미만으로 조기 강판 — 발생 시 홈 "
                  "방향 약 +5%p · 근거 자료10 이닝분포 최장 1.0이닝"]}
    got = _units(fa.extract_claims(v, NAMES))
    assert ("ip", 3.0) not in got, got


def test_같은_문장의_근거부는_계속_대조한다():
    """🔴 반대 위험 — 근거까지 빼면 감시가 변수 문장을 통째로 못 본다."""
    v = {"변수": ["원정 선발 이준기가 3이닝 미만으로 조기 강판 — 발생 시 홈 "
                  "방향 약 +5%p · 근거 자료10 이닝분포 최장 1.0이닝"]}
    got = _units(fa.extract_claims(v, NAMES))
    assert ("ip", 1.0) in got, got


def test_변수_근거부의_거짓_수치는_여전히_잡힌다():
    """(a) 규칙이 변수 문장을 감사 면제구역으로 만들면 안 된다."""
    v = {"변수": ["선발 조기 강판 — 발생 시 홈 방향 약 4%p · 근거 자료4 "
                  "직전등판 9.9이닝 4실점"]}
    res = fa.audit(v, PROMPT, names=NAMES)
    assert res["mismatch_n"] == 1, res
    assert res["mismatch_detail"][0]["claimed"] == 9.9


@pytest.mark.parametrize("word", ["미만", "이상", "이하", "초과"])
def test_비교어_네_종류를_모두_잡는다(word):
    v = {"변수": [f"홈 선발이 5이닝 {word} — 발생 시 원정 방향 약 4%p · 근거 없음"]}
    assert ("ip", 5.0) not in _units(fa.extract_claims(v, NAMES))


def test_비교어가_없는_맨숫자는_인용일_수_있다():
    """🔴 "벤자민 50구 제한" 의 50 은 자료2 의 **사실**이다 — 빼면 안 된다."""
    v = {"변수": ["벤자민이 50구 제한으로 3이닝 강판 — 발생 시 원정 방향 약 "
                  "5%p · 근거 자료2"]}
    got = _units(fa.extract_claims(v, NAMES))
    assert ("ip", 3.0) in got, got


def test_발생_시_마커가_없으면_종전대로_감사한다():
    """형식을 안 지킨 문장은 **안전한 쪽**으로 — 종전처럼 본다."""
    v = {"근거": ["홈 선발은 5이닝 미만으로 무너졌다"]}
    assert ("ip", 5.0) in _units(fa.extract_claims(v, NAMES))


def test_근거_필드의_비교어는_빼지_않는다():
    """`근거` 는 관측 진술이다. 변수 형식이 아니면 조건절 규칙이 안 붙는다."""
    v = {"근거": ["로건은 최근 5경기 모두 5.2이닝 이상 소화했다 (자료4)"]}
    assert ("ip", 5.2) in _units(fa.extract_claims(v, NAMES))


# ═══════════════ (b) 합계 재계산이 표본을 제대로 고른다

def test_한_문장에_투수가_둘이면_가까운_표본을_쓴다():
    """실측 game=1734 — 11실점의 표본이 5 로 잡혀 재계산이 건너뛰어졌다."""
    line = ("선발 로건은 최근 5경기 모두 5.2이닝 이상 소화하며 안정적이나, "
            "김진욱은 최근 2경기 9이닝 11실점으로 부진 (자료4)")
    claims = {(c["unit"], c["value"]): c.get("n")
              for c in fa.extract_claims({"근거": [line]}, NAMES)}
    assert claims[("r", 11.0)] == 2, claims
    assert claims[("ip", 5.2)] == 5, claims


def test_합계_인용이_derived_로_인정된다():
    """4 + 7 = 11. 판정이 한 산수가 맞다."""
    line = ("선발 로건은 최근 5경기 모두 5.2이닝 이상 소화하며 안정적이나, "
            "김진욱은 최근 2경기 9이닝 11실점으로 부진 (자료4)")
    res = fa.audit({"근거": [line]}, PROMPT, names=NAMES)
    assert res["mismatch_n"] == 0, res.get("mismatch_detail")
    assert res["derived_n"] >= 1, res


def test_합계가_틀리면_여전히_잡힌다():
    """🔴 감지력 보존 — 정답만 인정하고 오답은 그대로 mismatch 다."""
    line = "김진욱은 최근 2경기 9이닝 12실점으로 부진 (자료4)"     # 정답 11
    res = fa.audit({"근거": [line]}, PROMPT, names=NAMES)
    assert res["mismatch_n"] == 1, res
    assert res["mismatch_detail"][0]["claimed"] == 12.0


def test_표본_표기가_앞에_없으면_종전대로_첫_표기를_쓴다():
    line = "9이닝 11실점을 허용했다 — 최근 2경기 기준"
    n = {(c["unit"], c["value"]): c.get("n")
         for c in fa.extract_claims({"근거": [line]})}
    assert n[("r", 11.0)] == 2


# ═══════════════ 조용한 손실 금지 — 뺀 것을 센다

def test_뺀_조건절의_수가_남는다():
    """🔴 감사 대상에서 빼는 것과 소리 없이 사라지는 것은 다르다."""
    v = {"변수": ["홈 선발이 5이닝 미만 4실점 이상으로 강판 — 발생 시 원정 "
                  "방향 약 5%p · 근거 없음 — 보수 반영"]}
    res = fa.audit(v, PROMPT, names=NAMES)
    assert res["condition_n"] == 2, res       # 5이닝 · 4실점
    assert res["mismatch_n"] == 0


def test_원장_컬럼과_로그에_실린다():
    src = open("app/engine/fact_audit.py", encoding="utf-8").read()
    assert "condition_n" in src.split("INSERT INTO judgement_audit")[1][:400]
    assert "조건절제외" in src
    schema = open("db/schema.sql", encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS condition_n" in schema


# ═══════════════ 감시층만 바뀐다

def test_판정_경로는_이_모듈을_읽지_않는다():
    """L1 은 발송 뒤에 도는 섀도다 — 되돌아가면 판정이 감시를 베낀 것이 된다."""
    import pathlib

    for path in ("app/engine/matchup.py", "app/engine/value_gate.py"):
        p = pathlib.Path(path)
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8")
        assert "is_variable_condition" not in body, path
