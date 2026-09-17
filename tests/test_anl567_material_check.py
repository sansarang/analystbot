"""ANL-5·6·7 계약 — ①재료 ②검사 ③기록.

실측 2026-09-17 (오늘 밤 게이트 3건 · 운영):
  ① 원장에 p_prior 0.68 이 있는데 blk 은 **하드코딩 None**,
     추출이 notes="고종욱 1군 말소." 를 받아 놨는데 build_input 이 **안 읽었다.**
     → 모델이 본 입력이 **6줄**. L1 반려 2/3 사유가 "입력 블록에 없는 사실".
  ② 빈 근거는 검사를 **건너뛰어 통과**하고, 조사 하나에 구체적인 근거가 반려됐다.
     → 운영에서 결정축 **'홈 사실'** 이 L1·L2 를 다 통과했다.
  ③ 반려 **사유**는 남기는데 **대상 문장**이 안 남아, 원인을 결정축으로 대신 쟀다.
"""
import inspect
import re

import pytest

from app.engine import analyze as AN
from app.engine import pick_ledger as PL

FACTS = {"out": ["고종욱"], "xi_status": "predicted",
         "notes": "고종욱 1군 말소.", "doubt": ["나성범"],
         "source": "https://www.koreabaseball.com/x", "published": "2026-09-16"}
BLK = {"home": "Kia Tigers", "away": "Kiwoom Heroes", "league": "KBO",
       "p_market": 0.6156, "gap_pp": 6.75, "gate": "가치 의심", "adj_pp": {},
       "p_code": 0.68, "kickoff_kst": "x",
       "home_facts": FACTS, "away_facts": {}}
FULL = {"결정축": "x", "결정축_방향": "홈 하향", "반대축": "y",
        "시장_판단": "적정", "시장_판단_이유": "", "구조_후보": [],
        "불확실": "", "근거_수": 1}


def _l1(reason):
    return AN.l1({**FULL, "결정축_근거": reason}, BLK)


# ══ ANL-5 · 재료

def test_수집한_notes가_들어간다():
    assert "1군 말소" in AN.build_input(BLK)


def test_출전의문이_들어간다():
    assert "나성범" in AN.build_input(BLK)


def test_없으면_줄이_안_는다():
    """🔴 '없음'을 쓰면 없는 사실이 있어 보인다."""
    t = AN.build_input({**BLK, "home_facts": {"out": ["고종욱"]}})
    assert "출전의문" not in t


def test_URL을_안_넣는다():
    """⚠️ 출처 링크는 판단 재료가 아니라 잡음이다."""
    assert "koreabaseball.com" not in AN.build_input(BLK)


def test_p_prior를_원장에서_읽는다():
    src = inspect.getsource(PL.record_confirm_and_analysis)
    assert '"p_prior": None' not in src, "하드코딩 None 이 남아 있다"
    sel = src.split("SELECT", 1)[1].split("FROM pick_ledger", 1)[0]
    assert "p_prior" in sel, "원장에서 읽지도 않는다"


# ══ ANL-6 · 검사

def test_빈_근거는_반려된다():
    """🔴 종전에는 **통과**했다 — 내용이 없을수록 유리했다."""
    assert _l1("")[0] is False
    assert _l1("홈")[0] is False


def test_조사가_붙어도_인용으로_본다():
    """🔴 한국어는 조사가 붙는다 — `결장` 과 `결장으로` 는 같은 사실이다."""
    assert _l1("고종욱의 결장으로 타선 운영에 차질이 생겼다")[0] is True


def test_수집한_notes를_인용하면_통과한다():
    assert _l1("말소된 선수가 있어 타선이 약해졌다")[0] is True


def test_입력에_없는_사실은_반려된다():
    """🔴 **반대 위험** — 느슨하게만 만들면 검사가 통째로 무의미해진다."""
    ok, why = _l1("원정팀 감독이 어제 사임했고 구단이 매각 협상 중이다")
    assert ok is False and "없는 사실" in why


def test_라벨만_따라_쓰면_반려된다():
    """🔴 `src` 를 렌더된 글자로 만들면 `[원정 사실]` 의 '원정' 에 걸려 통과한다."""
    assert "원정" not in AN.fact_words(BLK)
    assert "경기" not in AN.fact_words(BLK)


def test_사실_낱말은_값에서만_나온다():
    fw = AN.fact_words(BLK)
    assert "고종욱" in fw and "말소" in fw and "나성범" in fw
    assert not any("koreabaseball" in w for w in fw)


def test_칸_이름을_손으로_안_적었다():
    src = inspect.getsource(AN.fact_words)
    assert "EXTRACT_SCHEMA" in src
    for k in ("out", "doubt", "last3", "notes"):
        assert f'"{k}"' not in src, k


def test_숫자_검사는_안_바뀌었다():
    """🔴 숫자는 렌더된 [숫자] 줄에 있다 — 기준이 바뀌면 안 된다."""
    src = inspect.getsource(AN.l1)
    assert "blk_text = build_input(blk)" in src
    assert "blk_text.replace" in src
    bad = AN.l1({**FULL, "결정축_근거": "고종욱 결장",
                 "시장_판단_이유": "우리는 88% 로 본다"}, BLK)
    assert bad[0] is False and "없는 숫자" in bad[1]


def test_칸_누락과_라벨_검사는_그대로다():
    assert AN.l1({"결정축": "x"}, BLK)[0] is False
    assert AN.l1({**FULL, "결정축_방향": "이상한값",
                  "결정축_근거": "고종욱 결장"}, BLK)[0] is False


# ══ ANL-7 · 기록

def test_검사_대상_문장이_남는다():
    r = AN.check_row(False, "없는 사실", True, "", [], None,
                     reason="고종욱 결장으로 타선이 약해졌다")
    assert r["reason"] == "고종욱 결장으로 타선이 약해졌다"


def test_실패_가지는_None이다():
    """🔴 근거 자체가 없다 — 빈 문자열로 채우지 않는다."""
    assert AN.check_row(None, None, None, None, [], "JSON 이 아니다")["reason"] is None
    assert AN.check_row(True, "", True, "", [], None, reason="  ")["reason"] is None


def test_run이_근거를_싣는다():
    assert 'reason=parsed.get("결정축_근거")' in inspect.getsource(AN.run)


def test_새_칸을_만들지_않았다():
    """🔴 자리표를 또 늘리면 PA-23 의 사고 자리가 하나 더 생긴다."""
    n = max(int(x) for x in re.findall(r"\$(\d+)", PL._ANALYZE_SAVE))
    assert n == 10


@pytest.mark.parametrize("fn", [AN.l1, AN.l2])
def test_검사_자체는_안_바꿨다(fn):
    assert "check_row" not in inspect.getsource(fn)
