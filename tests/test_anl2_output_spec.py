"""ANL-2 계약 — 분석 프롬프트가 **출력 형식을 말한다.**

🔴 실측 2026-09-17 운영: 분석 대상 6건 전부 실패 · `main_axis` 0/13.
   한 번 불러 원문을 보니 **마크다운 산문**이었다(1033자):
     '제공해주신 분석 데이터를 바탕으로 … ### [경기 정보] …'
   `analyze.build_input` 에는 출력 지시가 **한 줄도 없었다.**
   JSON 을 내라고 말한 적 없이 JSON 이 아니라고 버리고 있었다.

🔴 실측 A/B (같은 모델·같은 자료·연속 호출):
     지시문 없음 → 산문 785자 → JSON ❌
     지시문 있음 → 311자      → **JSON ✅ 칸 10개**
                                결정축='주전결장 및 코드 보정' · 방향='홈 상향'

🔴 함정 — `l1` 이 `build_input` 을 **검사 기준으로도** 쓴다. 지시문이 섞이면
   "근거가 입력의 사실인가"를 스키마 이름으로 때워도 통과하고, 숫자 검사의
   기준도 넓어진다. 그래서 **기본값은 종전 그대로**이고 실제 호출만 붙인다.
"""
import inspect
import pathlib

import pytest

from app.engine import analyze as AN

BLK = {"home": "H", "away": "A", "league": "MLB", "p_market": 0.55,
       "gap_pp": -7.9, "gate": "시장 과대", "adj_pp": {"주전결장": -1.5},
       "p_code": 0.67, "kickoff_kst": "09-18 08:10",
       "home_facts": {"out": ["X"]}, "away_facts": {}}


# ── 지시문이 붙는다

def test_JSON만_내라고_말한다():
    assert "JSON" in AN.build_input(BLK, with_schema=True)


def test_마크다운을_금지한다():
    """🔴 실측 응답이 마크다운이었다."""
    assert "백틱" in AN.build_input(BLK, with_schema=True)


@pytest.mark.parametrize("key", AN.SCHEMA)
def test_칸_이름을_전부_알려준다(key):
    assert key in AN.build_input(BLK, with_schema=True)


def test_라벨_표를_알려준다():
    p = AN.build_input(BLK, with_schema=True)
    for lab in AN.DIRECTIONS + AN.MARKET_VIEWS:
        assert lab in p, lab


def test_l1이_반려하는_규칙을_미리_말한다():
    """🔴 반려 사유를 말해 주지 않으면 통과할 수 없는 시험이다.
    실측: 숫자 금지를 말한 뒤 다음 반려가 '배당이 있다' 였다."""
    p = AN.build_input(BLK, with_schema=True)
    for k in AN.NO_NUM_KEYS:
        assert k in p
    for w in AN.REASON_BANNED:
        assert w in p


# ── 🔴 반대 위험 — l1 의 기준이 안 바뀐다

def test_기본값은_종전_그대로다():
    """🔴 `l1` 이 이 결과를 검사 기준으로 쓴다 — 글자 하나 바뀌면 안 된다."""
    base = AN.build_input(BLK)
    assert "JSON" not in base
    assert not any(k in base for k in AN.SCHEMA)
    assert base.endswith("[missing] 없음")


def test_l1이_자료_블록만_본다():
    src = inspect.getsource(AN.l1)
    assert "build_input(blk)" in src
    assert "with_schema" not in src


def test_지시문에_숫자가_없다():
    """🔴 숫자가 들어가면 `l1` 의 '입력에 있는 숫자만' 기준이 넓어진다."""
    import re

    assert not re.search(r"\d", AN.output_spec())


# ── 사본 금지

def test_칸_이름을_손으로_안_적었다():
    src = inspect.getsource(AN.output_spec)
    assert "SCHEMA" in src and "DIRECTIONS" in src and "MARKET_VIEWS" in src
    for k in AN.SCHEMA:
        assert f'"{k}"' not in src, k


def test_숫자금지_목록이_한_곳이다():
    """🔴 `l1` 과 지시문이 같은 상수를 본다 — 손으로 두 벌 적으면 사본이다."""
    assert "NO_NUM_KEYS" in inspect.getsource(AN.l1)
    assert "REASON_BANNED" in inspect.getsource(AN.l1)
    assert AN.NO_NUM_KEYS == ("결정축", "결정축_근거", "반대축")


def test_문장이_되고_있는_판정_프롬프트와_같다():
    """🔴 이 문장은 `prompts.py` 에서 베꼈다 — 거기서 바뀌면 여기가 사본이 된다."""
    pr = pathlib.Path("app/engine/prompts.py").read_text(encoding="utf-8")
    assert AN.JSON_ONLY in pr


def test_run이_지시문을_붙여_묻는다():
    assert "build_input(blk, with_schema=True)" in inspect.getsource(AN.run)


def test_L1_반려가_원장을_막지_않는다():
    """🔴 JSON 만 오면 결정축·시장판단은 남는다 — L1 은 품질 신호지 실패가 아니다.
    이 성질 때문에 ANL-2 하나로 `analyze_failed` 6/6 이 풀린다."""
    src = inspect.getsource(AN.run)
    tail = src.split("ok1, why1 = l1(", 1)[1]
    # ⚠️ **뜻으로 잰다.** 처음에 호출 한 줄을 글자 그대로 박았더니 ANL-3 이
    #    같은 줄의 `model=` 만 바꿨는데 계약이 깨졌다 — 뜻은 그대로인데.
    assert "to_ledger(parsed" in tail, "반려 뒤 원장 기록이 사라졌다"
    assert "failed=True" not in tail, "L1 반려를 실패로 적고 있다"
