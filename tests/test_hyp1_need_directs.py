"""HYP-1 계약 — **가설이 수집을 지휘한다** (페이블 순서의 핵심).

🔴 `hypothesis.py` 머리말: "이것이 페이블 순서의 핵심이다. 지금까지는 수집이
   need 와 무관하게 전부 돌았고, 그래서 S6 이 무엇을 확인해야 하는가를 몰랐다."

실측 2026-09-17 — 그 배선이 통째로 없었다:
   need_keys()·apply_need()  운영 호출 0건 · extract_game_facts(need=…) 인자만
   있고 본문 미사용 · 유일한 호출부가 need 를 안 넘김 · _DUE_SQL 이 가설 미조회.

⚠️ **지휘는 "무엇을 찾을지 말해 주는 것"이지 "찾은 것을 버리는 것"이 아니다.**
   need 밖 칸을 비우면 ANL-5 로 넣은 `notes`("고종욱 1군 말소.")가 사라진다.
"""
import inspect

import pytest

from app.collectors import satellite as SAT
from app.engine import hypothesis as HY

H = {"direction": "away",
     "need": [{"field": "out", "side": "home", "why": "x"},
              {"field": "doubt", "side": "away", "why": "x"}],
     "sufficient_count": 2, "reason": ""}
BLOCKS = [("http://a", "본문")]


# ── 가설이 내려간다

def test_원장에서_가설을_읽는다():
    assert "hypothesis" in SAT._DUE_SQL


def test_수집_루프가_가설을_싣는다():
    src = inspect.getsource(SAT.run) if hasattr(SAT, "run") else ""
    if not src:
        import pathlib
        src = pathlib.Path(SAT.__file__).read_text(encoding="utf-8")
    assert '"hypothesis": (r.get("hypothesis")' in src


def test_gather가_need를_넘긴다():
    assert "need=_need_of(jg)" in inspect.getsource(SAT.gather)


@pytest.mark.parametrize("raw", [H, __import__("json").dumps(H)])
def test_가설에서_need를_만든다(raw):
    assert SAT._need_of({"hypothesis": raw}) == ["home.out", "away.doubt"]


def test_가설이_없으면_None이다():
    """🔴 빈 목록(보드 고정)과 None(가설 없음)은 다르다 — 굶기지 않는다."""
    for jg in ({}, {"hypothesis": None}, {"hypothesis": ""}):
        assert SAT._need_of(jg) is None


def test_가설이_깨져도_수집이_안_죽는다():
    """🔴 옛 행·스키마 미적용에서 사이클이 통째로 죽으면 안 된다."""
    assert SAT._need_of({"hypothesis": "{이건 JSON 이 아니다"}) is None
    assert SAT._need_of({"hypothesis": {"need": [{"side": "home"}]}}) is None


# ── 프롬프트가 지휘한다

def test_프롬프트가_찾을_것을_말한다():
    p = SAT._extract_prompt("H", "A", BLOCKS, ["home.out", "away.doubt"])
    assert "우선 찾는 것" in p
    assert "home.out" in p and "away.doubt" in p


def test_가설이_없으면_프롬프트가_종전과_같다():
    """🔴 반대 위험 — 안 받은 경기의 수집을 바꾸지 않는다."""
    base = SAT._extract_prompt("H", "A", BLOCKS)
    assert SAT._extract_prompt("H", "A", BLOCKS, None) == base
    assert SAT._extract_prompt("H", "A", BLOCKS, []) == base
    assert "우선 찾는 것" not in base


def test_찾은_것을_버리지_않는다():
    """🔴 스키마 8칸을 그대로 다 요구한다 — need 밖 칸을 지우면 ANL-5 가 무효가 된다."""
    from app.engine.scout_config import EXTRACT_SCHEMA

    p = SAT._extract_prompt("H", "A", BLOCKS, ["home.out"])
    for k in EXTRACT_SCHEMA:
        assert f'"{k}"' in p, k
    assert "다른 칸도" in p


def test_apply_need를_안_부른다():
    """🔴 설계 결정 — 칸 비우기는 잇지 않는다(분석 입력이 도로 좁아진다)."""
    body = inspect.getsource(SAT.gather) + inspect.getsource(SAT.extract_game_facts)
    assert "apply_need(" not in body


# ── 사본 금지 · 비용

def test_키_모양을_손으로_안_적었다():
    """🔴 `home.out` 은 `Need.key` 가 원본이다.

    ⚠️ **코드 줄만 본다.** 머리말의 예시(`["home.out", …]`)를 위반으로 세면
       설명을 못 쓰게 된다 — 오늘만 다섯 번째 같은 함정이다.
    """
    lines = [ln for ln in inspect.getsource(SAT._need_of).splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    body = "\n".join(lines).split('"""')[-1]      # 머리말 제외
    assert "n.key" in body
    assert '"home.' not in body and '"away.' not in body
    assert HY.Need("out", "home", "").key == "home.out"


def test_콜_수가_안_는다():
    """🔴 프롬프트에 한 줄 더할 뿐이다 — 호출은 경기당 1콜 그대로."""
    src = inspect.getsource(SAT.extract_game_facts)
    assert src.count("_complete_free(") == 1
