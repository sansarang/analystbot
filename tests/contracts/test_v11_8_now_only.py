"""🔴🔴 **"현재 상태" 입구 — 재현 모드에서 확률 경로 금지** (사용자 지시 2026-10-12 2번).

> 2. "현재 상태" 입구 목록화(grep 목록에 없던 것): fotmob 결장 명단, 선수 시즌
> 누계(득점·도움·xG·출전 시간 → 공격 기여표·축0 가치·무기 비중), 순위표,
> 선수단 명부·등번호, 시장 가치, 선발 비율(30% 규칙).
>   각각: 경기 단위 자료에서 as_of까지 **재합산 가능 → 재합산으로 바꾼다** /
>   불가 → 재현 모드에서 **"현재 값 — 재현 불가" 표시**하고 **확률 경로에서 뺀다**.
> 계약 L2: 재현 모드에서 as_of 이후 값을 담을 수 있는 "현재 상태" 입구가
> **표시 없이 확률 경로에 들어가면 실패**.

🔴 목록과 판정(실측 2026-10-12):
  ① 결장 명단 `fotmob.missing_of` ← **그 경기 페이지**(as-of 정합) ✅
  ② 선수 시즌 누계 `fotmob.squad_stats`·`key_players_all` ← **현재 누계** 🔴
     → 경기별 `player_adv`(선수 xG/xA)·골 목록으로 **재합산 가능** → 그 길로 바꾼다
  ③ 순위표 `fotmob._tables` ← **현재 순위** 🔴 → 재현 불가(표시 + 확률 경로 밖)
  ④ 명부·등번호 `players_of`(경기 페이지) ✅ / `squad_names`(선수단 페이지) 🔴 표시용
  ⑤ 시장 가치 `_value_of` ← **그 경기 페이지의 `marketValue`** ✅ as-of 정합
  ⑥ 선발 비율(30% 규칙) ← `usual_starts` ← 경기 목록(as-of 걸림) ✅
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_now_only_list_exists_in_code() -> None:
    """🔴 목록이 **코드 상수**다 — 새 입구가 생기면 여기 더한다."""
    from app.core import asof
    assert set(asof.NOW_ONLY) >= {"player_stats", "standings", "squad_names"}


def test_each_entry_says_recountable_or_not() -> None:
    from app.core import asof
    for key, one in asof.NOW_ONLY.items():
        assert "재합산" in one or "재현 불가" in one, (key, one)


def test_l2_probability_path_refuses_now_only_in_replay() -> None:
    """🔴 L2 — 재현 모드에서 그 값이 **확률 경로**에 들어가면 막는다."""
    from app.core import asof
    ok, why = asof.may_use("standings", replay=True)
    assert ok is False and "재현 불가" in why
    ok2, why2 = asof.may_use("standings", replay=False)
    assert ok2 is True, why2


def test_as_of_safe_entries_pass() -> None:
    """✅ 그 경기 페이지에서 오는 값은 재현에서도 쓴다(시장 가치·결장 명단)."""
    from app.core import asof
    for key in ("player_value", "missing"):
        ok, _why = asof.may_use(key, replay=True)
        assert ok is True, key


def test_card_marks_now_only_values() -> None:
    """🔴 표시 — 카드가 *"현재 값 — 재현 불가"* 를 적는다."""
    said = _src("app/core/asof.py")
    assert "현재 값 — 재현 불가" in said


def test_axis0_value_comes_from_the_match_page() -> None:
    """🔴 ⑤ — 축0 의 선수 가치는 **그 경기 페이지**다(현재 값이 아니다).

    ⚠️ 실측 2026-10-12: `s2_facts` 가 `values_of(그 경기 XI·lineup)` 로 모은다 —
       선수단 페이지(현재 누계)가 아니다. 그래서 as-of 재현에서도 정합이다.
    """
    said = _src("app/core/stages/s2_facts.py")
    i = said.index("values: dict[str, float] = {}")
    seg = said[i:i + 400]
    assert "raw_xi" in seg and "values_of" in seg, seg[:200]
    assert "squad_stats" not in seg
