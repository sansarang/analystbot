"""단계 4 계약 — **필수 8건**의 정의가 정본과 같나, 그리고 측정이 정직한가.

🔴 **이 파일은 점수를 잠그지 않는다.** 점수는 라이브 웹이 정하고 날마다 바뀐다 —
   그것을 계약으로 박으면 웹이 바뀔 때마다 빨개지고, 그러면 아무도 안 본다.
   잠그는 것은 **정의와 정직성**이다:

   · 8건의 정의가 v4 §9 와 **글자까지** 같나 (사본 금지)
   · 날짜를 모르는 건이 **이름으로** 남나 (조용한 0 금지)
   · 검색이 죽었을 때 측정이 **"무효"라고 말하나** (거짓 측정 금지)

측정 자체는 `tools/measure_stage4.py` 이고 결과는 `logs/stage4/` 에 남는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
V4 = (ROOT / "docs" / "fable" / "inbox" / "2026-09-29_v4.md").read_text(
    encoding="utf-8")
CASES = yaml.safe_load(
    (ROOT / "config" / "stage4_essential8.yaml").read_text(encoding="utf-8"))


def _origin_items() -> list[str]:
    """v4 §9 의 **필수 8건** 원문 항목. 🔴 정본에서 읽는다 — 베끼지 않는다.

    ⚠️ 뽑은 수를 **8과 대조**한다. 정규식이 항목을 빠뜨리면 계약이 "7건만 확인
       했다"고 조용히 통과할 수 있다 — 이 저장소가 `h2h_pattern` 을 놓쳐 13유형을
       12로 센 것과 같은 병이다.
    """
    sec = V4.split("**단계 4 필수 8건")[1].split("**병렬 가능**")[0]
    got = [t.strip() for t in re.split(r"[①②③④⑤⑥⑦⑧]", sec)[1:] if t.strip()]
    assert len(got) == 8, f"정본에서 {len(got)}개만 뽑았다 — 정규식이 빠뜨린다"
    return got


# ══════════════════════════════════════════════════════════════════
# 🔴 사본 금지 — 정의가 정본과 같나
# ══════════════════════════════════════════════════════════════════

def test_8건이_정본과_글자까지_같다():
    """🔴 항목 문구를 손으로 바꿔 적으면 그것이 사본이고, 정본이 바뀔 때 안 따라간다."""
    want = _origin_items()
    have = [CASES["items"][i]["origin"] for i in sorted(CASES["items"])]
    assert len(have) == 8, f"yaml 에 {len(have)}건이 있다"
    for i, (w, h) in enumerate(zip(want, have), 1):
        assert h == w, f"{i}번: yaml={h!r}\n     정본={w!r}"


def test_유형이_v4_4절_유형표에_있는_것이다():
    """🔴 `var_type` 은 §4 유형 13종 중 하나여야 한다 — 새 유형을 지어내지 않는다."""
    from app import rules as R
    known = set(R.variable_types())
    for i, case in CASES["items"].items():
        assert case["var_type"] in known, (i, case["var_type"], sorted(known))


def test_정본_낱말이_정본_문구에서_왔다():
    """🔴 `origin_terms` 는 **정본 항목 문구 안에 실재하는 낱말**이어야 한다.

    ⚠️ 내가 덧붙인 로마자(`extra_terms`)와 갈라 둔 이유가 이것이다 — 채점이
       "정본이 댄 낱말"을 기준으로 삼아야 시험이 정직하다. 여기 아무 낱말이나
       넣으면 시험을 내가 고쳐 쓰는 것이 된다.
    """
    for i, case in CASES["items"].items():
        origin = case["origin"]
        for t in case.get("origin_terms") or []:
            assert t in origin, (
                f"{i}번: `{t}` 가 정본 문구에 없다 — 지어낸 낱말이다\n"
                f"     정본: {origin!r}")


def test_덧붙인_낱말은_정본_낱말과_겹치지_않는다():
    """⚠️ 겹치면 채점에서 "정본 낱말로 통과"와 "내 낱말로 통과"가 구분되지 않는다."""
    for i, case in CASES["items"].items():
        o = set(case.get("origin_terms") or [])
        e = set(case.get("extra_terms") or [])
        assert not (o & e), (i, sorted(o & e))


# ══════════════════════════════════════════════════════════════════
# 🔴 조용한 0 금지 — 모르는 것이 이름으로 남나
# ══════════════════════════════════════════════════════════════════

def test_날짜를_모르는_건이_비어_있다():
    """🔴 **정본이 날짜를 대지 않는 건은 `day` 를 비운다** — 지어내지 않는다(§11-3).

    실측 2026-09-30: 3건(모리야스·마리보르–고리차·램버트)이 그렇다. 정본은 그
    셋의 경기 날짜를 어디에서도 대지 않는다 → 측정에서 **"못 잼"** 으로 빠지고
    보고에 이름으로 남는다.

    ⚠️ 이 계약이 잠그는 것은 *"3건이다"* 가 아니라 *"비어 있으면 비어 있다고
       한다"* 다 — 날짜가 확인되면 채우고 이 계약은 그대로 통과한다.
    """
    for i, case in CASES["items"].items():
        day = case.get("day")
        assert day is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)), (
            f"{i}번 day={day!r} — 비우거나 ISO 날짜여야 한다")
        if day is not None:
            # 🔴 날짜를 채웠으면 **정본의 어디에서 왔는지** 주석이 있어야 한다
            raw = (ROOT / "config" / "stage4_essential8.yaml").read_text(
                encoding="utf-8")
            line = next(ln for ln in raw.splitlines()
                        if f"day: {day}" in ln)
            assert "#" in line, (
                f"{i}번: 날짜 {day} 의 출처 주석이 없다 — 어디서 왔는지 적어라")


def test_모르는_것마다_왜_어려운지_적혀_있다():
    """🔴 8건 전부 `why_hard` 가 있어야 한다.

    ⚠️ 점수만 남기면 다음 세션이 **무엇을 고쳐야 하는지** 모른다. 어려운 이유가
       곧 고칠 자리다(§19-b-6 이 사유를 요구하는 것과 같은 규약).
    """
    for i, case in CASES["items"].items():
        assert (case.get("why_hard") or "").strip(), f"{i}번에 why_hard 가 없다"


# ══════════════════════════════════════════════════════════════════
# 🔴 거짓 측정 금지 — 검색이 죽었으면 "무효"라고 말한다
# ══════════════════════════════════════════════════════════════════

def test_검색이_죽으면_미발견이_아니라_무효다():
    """🔴 **이 계약이 이번 세션의 가장 값진 자리다.**

    실측 2026-09-30: 측정 도구의 첫 판이 전 질의 0건을 *"미발견"* 으로 채점해
    **0/8** 을 냈다. 원인은 봇이 아니라 **SearXNG 엔진 전부 정지**였다(내 라이브
    측정이 요청 과다를 유발했다). 그 숫자를 보고하면 **거짓 측정**이고, 그것을
    근거로 설계를 고치려 들게 된다(조용한 0 금지 · §11-3 추측 금지).
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "measure_stage4", ROOT / "tools" / "measure_stage4.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    case = {"origin": "x", "origin_terms": ["없는낱말"], "extra_terms": [],
            "reach": [["없는낱말"]]}
    got = m.score_one(case, [], [], [])
    # 채점 함수 자체는 "도달X" 를 낸다 — 무효 판정은 호출부가 얹는다
    assert got["도달"] == "X" and got["변환"] == "X"
    assert "도달X" in got["verdict"]
    # 🔴 그 호출부에 무효 판정이 **실재하는지** 본다
    src = (ROOT / "tools" / "measure_stage4.py").read_text(encoding="utf-8")
    assert '"측정 무효"' in src, "검색이 죽었을 때 무효로 찍는 자리가 없다"
    assert "backend_alive" in src, "정지 엔진 이름을 낼 자리가 없다"


def test_측정이_간격을_둔다():
    """🔴 연달아 던지면 업스트림 엔진이 정지한다 — 그 상태로 잰 값은 무효다.

    ⚠️ 실측 2026-09-30: 간격 없이 돌려 `brave`·`duckduckgo`·`google cse` 를 전부
       정지시켰고, 30분 넘게 안 풀렸다. §19-f 의 "우회 없음"과 같은 결의 문제다 —
       상대 서버에 예의를 지키는 것이 측정의 전제다.
    """
    src = (ROOT / "tools" / "measure_stage4.py").read_text(encoding="utf-8")
    assert "THROTTLE_SEC" in src
    assert "asyncio.sleep(THROTTLE_SEC)" in src


def test_측정이_원문과_다른_점을_밝힌다():
    """🔴 §9 는 *"경기 전 시점 웹(카세트)"* 을 요구하고, 그 웹은 남아 있지 않다.

    오늘 웹에서 재는 것이 원문과 어떻게 다른지 도구 머리글에 적혀 있어야 한다 —
    안 적으면 다음 세션이 이 수치를 "원문대로 쟀다"고 읽는다.
    """
    src = (ROOT / "tools" / "measure_stage4.py").read_text(encoding="utf-8")
    assert "경기 전 시점 웹" in src
    assert "오늘 웹" in src


# ══════════════════════════════════════════════════════════════════
# 측정용 시계 — 🔴 운영에 새지 않는다
# ══════════════════════════════════════════════════════════════════

def test_측정용_시계가_운영에_새지_않는다():
    """🔴 `CASSETTE_AS_OF` 는 **명시적일 때만** 듣는다. 비면 진짜 지금이다.

    ⚠️ 이 값이 운영에 남으면 봇이 과거 시각으로 돌면서 오래된 기사를 오늘 것으로
       읽는다 — M13 을 기계로 재현하는 셈이다.
    """
    import os
    from datetime import datetime, timedelta, timezone

    from app import cassette
    kst = timezone(timedelta(hours=9))
    os.environ.pop(cassette.AS_OF_ENV, None)
    os.environ.pop(cassette.MODE_ENV, None)
    assert cassette.reference_now().date() == datetime.now(kst).date()

    os.environ[cassette.AS_OF_ENV] = "2026-09-28"
    try:
        assert cassette.reference_now().date().isoformat() == "2026-09-28"
        # 🔴 오타는 **무시하고 진짜 지금** — 조용히 엉뚱한 날짜로 가지 않는다
        os.environ[cassette.AS_OF_ENV] = "엉망"
        assert cassette.reference_now().date() == datetime.now(kst).date()
    finally:
        os.environ.pop(cassette.AS_OF_ENV, None)


def test_시계를_옮겨도_검증이_느슨해지지_않는다():
    """🔴 기준 시각만 옮긴다 — 그 시각에서 **오래된 기사는 여전히 거부**된다.

    ⚠️ 실측: 시계를 09-29 로 세웠을 때 33일 지난 기사가 그대로 떨어졌다.
    """
    import os
    from datetime import datetime, timedelta, timezone

    from app import cassette, verify
    kst = timezone(timedelta(hours=9))
    os.environ[cassette.AS_OF_ENV] = "2026-09-29"
    try:
        now = cassette.reference_now()
        ok = {"title": "스타멘 발표", "tier": verify.TIER_PRIMARY,
              "published_at": datetime(2026, 9, 29, 12, 0, tzinfo=kst)}
        assert verify.check_article(ok, now).ok
        old = dict(ok, published_at=datetime(2026, 8, 27, 12, 0, tzinfo=kst))
        assert not verify.check_article(old, now).ok, "오래된 기사가 통과했다"
    finally:
        os.environ.pop(cassette.AS_OF_ENV, None)


# ══════════════════════════════════════════════════════════════════
# 🔴 도달은 **낱말이 아니라 사실**이다 — 오늘 가장 값진 정정
# ══════════════════════════════════════════════════════════════════

def test_도달은_한_자료_안에_사실이_있을_때다():
    """🔴 **낱말 하나로 재면 거짓 양성이 난다.**

    ⚠️ 실측 2026-09-30: 처음에는 낱말 하나가 검색 결과에 있으면 도달로 셌고
       **4a 도달 5/5** 라고 보고했다. 자료를 열어 보니 거짓이었다:

       · ② 발베르데 → `발베르데·벤탄쿠르·누녜스가 **한국 땅을 밟습니다**` 가
         잡혔다. 그것은 **결장의 반대**다 — v4 §12 **M11**(명단 없이 "완전체"로
         씀)이 정확히 그 오류이고, 그것을 "도달"로 세면 봇이 같은 실수를 하도록
         채점하는 셈이다.
       · ⑧ 김상식 → **8월** 기자회견 기사 열두 건이 잡혔다. 이름만 있고 그
         인용(`전후반 두 플랜`)은 없다.

       🔴 정정 후 **2/5**. 이 저장소가 반복해 다친 "문자열 검사"의 또 다른 얼굴이다.

    🔴 처방: `reach` 묶음을 **각각에서 하나씩 같은 스니펫에** 요구한다.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "measure_stage4", ROOT / "tools" / "measure_stage4.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    case = {"reach": [["발베르데", "Valverde"], ["결장", "제외"]]}

    class _H:
        def __init__(self, body):
            self.title, self.snippet = "", body
            self.publisher = "x"

    # 🔴 반대 사실을 말하는 자료 — 도달이 **아니다**
    opposite = _H("9월 28일 서울월드컵경기장, 발베르데·벤탄쿠르가 한국 땅을 밟습니다")
    assert m.reached_fact(case, [opposite])[0] is False, (
        "결장의 반대를 말하는 자료를 도달로 셌다 — M11 재발 경로")

    # 🔴 두 요소가 **한 자료 안에** 있어야 도달이다
    split_a, split_b = _H("발베르데 소식"), _H("우루과이 결장자 명단")
    assert m.reached_fact(case, [split_a, split_b])[0] is False, (
        "두 자료에 흩어진 낱말을 도달로 셌다")

    real = _H("우루과이 발베르데, 일본전 명단 제외")
    ok, where = m.reached_fact(case, [real])
    assert ok and "발베르데" in where


def test_reach가_없는_건은_도달을_못_잰다():
    """🔴 `reach` 를 정의하지 않으면 **도달을 재지 않는다** — 통과시키지 않는다.

    ⚠️ 정의가 없는데 도달로 세면 시험을 내가 고쳐 쓰는 것이 된다.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "measure_stage4", ROOT / "tools" / "measure_stage4.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    class _H:
        title = "아무 말"
        snippet = "아무 말"
        publisher = "x"

    ok, why = m.reached_fact({}, [_H()])
    assert ok is False and "reach" in why


def test_부재를_재는_건에는_reach가_없다():
    """⚠️ `absent_from_lineup` 건은 **타순 표를 뽑았나**로 도달을 잰다 —
    낱말 묶음이 아니다. 둘을 같이 두면 어느 쪽으로 채점되는지 모호해진다.
    """
    for i, case in CASES["items"].items():
        if case.get("absent_from_lineup"):
            assert not case.get("reach"), (
                f"{i}번: 부재 채점과 reach 를 같이 뒀다 — 하나만 둬라")
        else:
            assert case.get("reach"), f"{i}번: reach 가 없다 — 도달을 못 잰다"


def test_표기_대응의_키가_정본_낱말이다():
    """🔴 `same_as` 의 **키는 반드시 `origin_terms` 안에** 있어야 한다.

    §10 계산법이 *"동일 사실을 보도한 다른 매체"* 를 인정하므로 표기 대응은
    정당하다 — 정본은 `스바나제`, 자료는 `Svanadze` 다. 🔴 다만 **아무 낱말이나
    대응으로 붙이면 시험을 내가 고쳐 쓰는 것**이므로 키를 정본에 묶는다.

    ⚠️ 실측 2026-09-30: 한국어 표기만으로 채점하면 transfermarkt 가 그 사실을
       정확히 줘도(`현재 감독 Ramaz Svanadze · 취임 일자 2026년 9월 26일`)
       **완벽한 파서가 0점**이다.
    """
    for i, case in CASES["items"].items():
        origin = set(case.get("origin_terms") or [])
        for key in (case.get("same_as") or {}):
            assert key in origin, (
                f"{i}번: `same_as` 키 `{key}` 가 origin_terms 에 없다 — "
                f"정본에 묶이지 않은 대응이다")


def test_표기_대응이_사실을_바꾸지_않는다():
    """⚠️ 대응은 **같은 사실의 다른 표기**여야 한다 — 다른 사실을 붙이면 안 된다.

    🔴 지금 잠그는 것은 하나다: 대응이 **다른 `origin_term` 과 겹치지 않는다.**
       겹치면 `사뇰` 을 찾고 `스바나제` 를 찾았다고 셀 수 있다.
    """
    for i, case in CASES["items"].items():
        origin = set(case.get("origin_terms") or [])
        for key, forms in (case.get("same_as") or {}).items():
            for f in forms:
                assert f not in (origin - {key}), (
                    f"{i}번: `{key}` 의 대응 `{f}` 가 다른 정본 낱말이다")
