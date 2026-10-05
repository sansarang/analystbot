"""단계 4 계약 — **질문형 예산**(§12-d 를 질문형으로 분기).

사용자 결정 2026-10-01 → `docs/fable/questions/2026-10-01_question_mode.md`:
§0 절대 전제는 **지킨다**. 바꾸는 것은 §12-d 다 — 배치는 *경기별 고정*이지만
질문형은 경기가 하나라 **그 경기에 몰아줄 수 있다.**

🔴 **잠그는 것**

| 무엇 | 왜 |
|---|---|
| 세포 팩토리가 **전부** `budget_for` 를 거친다 | 한 곳이 `Budget(...)` 을 직접 만들면 그 세포만 질문형에서 얕게 돈다 — 조용히 |
| 세포 팩토리가 **전부** `mode` 를 받는다 | 받지 않는 팩토리는 질문형에서 배치 예산으로 돈다 |
| 질문형이 배치보다 **얕아지지 않는다** | 모드를 켜서 더 얕아지면 그것은 버그다 |
| 모르는 모드는 **거부된다** | 오타가 조용히 배치로 떨어지면 측정이 거짓말을 한다 |
| 예산이 끊기면 **사유가 남는다** | 못 찾은 것과 못 열어 본 것은 다르다(§19-b-6 · 조용한 0 금지) |
| 질문형은 **시간 상한**도 건다 | 개수만 올리면 한 세포에 7분이 걸린다 — 사용자가 기다린다 |
| 배치에는 시간 상한이 **없다** | 배치 개수는 작아 필요 없고, 걸면 슬레이트가 조용히 얕아진다 |

⚠️ **목록을 손으로 적지 않는다.** 팩토리 목록은 `app/searchcells.py` 에서 자란다 —
   `*_cell` 로 끝나는 공개 함수가 원본이다. 새 세포가 생기면 계약이 그것도 본다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app import cells, searchcells
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]


def _factories() -> dict:
    """🔴 **원본에서 자란다** — `*_cell` 공개 함수가 세포 팩토리다."""
    got = {n: f for n, f in inspect.getmembers(searchcells, inspect.isfunction)
           if n.endswith("_cell") and not n.startswith("_")
           and f.__module__ == "app.searchcells"}
    assert len(got) >= 5, f"세포 팩토리를 {len(got)}개만 찾았다 — 규칙을 보라"
    return got


def test_모드가_둘이고_오타는_거부된다():
    assert cells.MODES == (cells.SLATE, cells.DEEP, cells.ASK)
    # 🔴 모드마다 시간 상한이 **선언돼** 있어야 한다 — 빠뜨리면 KeyError 로 터지는
    #    것보다 여기서 빨개지는 것이 낫다
    assert set(cells.SECONDS_OF) == set(cells.MODES)
    with pytest.raises(ValueError):
        cells.budget_for(3, fetches=2, mode="질문형")      # 오타·번역어


def test_깊은_모드가_배치보다_얕아지지_않는다():
    """🔴 모드를 켜서 예산이 **줄면** 버그다. 모든 배치 깊이에서 본다."""
    for fetches in range(0, cells.DEEP_FETCHES + 5):
        slate = cells.budget_for(4, fetches=fetches)
        q = cells.budget_for(4, fetches=fetches, mode=cells.DEEP)
        assert q.fetches >= slate.fetches, (fetches, q.fetches, slate.fetches)
        assert q.searches == slate.searches, \
            "`searches` 는 소스 수다 — 모드가 건드릴 자리가 아니다"
    # 🔴 측정이 가리킨 자리 — 배치 3건에서 36건 중 3건만 열고 끊겼다
    assert cells.budget_for(4, fetches=3, mode=cells.DEEP).fetches \
        == cells.DEEP_FETCHES


def test_모든_세포_팩토리가_mode_를_받는다():
    missing = [n for n, f in _factories().items()
               if "mode" not in inspect.signature(f).parameters]
    assert missing == [], (
        f"질문형에서 배치 예산으로 도는 세포가 있다: {missing}")


def test_모든_세포_팩토리의_기본값이_배치다():
    """🔴 기본은 **배치**다 — 슬레이트가 조용히 깊어지면 엔진이 정지한다
    (실측 2026-09-30: 측정 한 번이 SearXNG 엔진 셋을 전부 정지시켰다).
    """
    for n, f in _factories().items():
        got = inspect.signature(f).parameters.get("mode")
        if got is None:
            continue        # 🔴 그것은 위 계약이 이름으로 보고한다
        assert got.default == cells.SLATE, f"{n}: 기본 모드가 `{got.default}` 다"


def test_세포가_Budget_을_직접_만들지_않는다():
    """🔴 `budget_for` 를 우회하면 그 세포만 질문형에서 얕게 돈다 — **조용히.**

    ⚠️ D46 — 독스트링·주석은 뺀 **코드만** 본다. 문서가 `Budget(` 를 *설명하는*
       것과 코드가 그것을 *부르는* 것은 다르다.
    """
    code = strip_docs((ROOT / "app" / "searchcells.py").read_text(
        encoding="utf-8"))
    calls = [n.func.id for n in ast.walk(ast.parse(code))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "Budget"]
    assert calls == [], (
        f"`Budget(` 를 {len(calls)}곳에서 직접 부른다 — `budget_for` 를 쓰라")


def test_예산이_끊기면_사유가_남는다():
    """🔴 *"검색 0건은 '없음'이 아니라 unknown"*(§19-b-6). 못 열어 본 것을
    못 찾은 것으로 적으면 측정이 거짓말을 한다 — 실측으로 한 번 그랬다.
    """
    code = strip_docs((ROOT / "app" / "cells.py").read_text(encoding="utf-8"))
    assert code.count("예산소진") >= 3, (
        "예산 소진 사유를 남기는 곳이 셋 미만이다 — 검색·본문 양쪽에 있어야 한다")
    b = cells.budget_for(1, fetches=1)
    assert b.take_fetch() is True and b.take_fetch() is False
    assert "열기 1/1" in b.spent


# ══════════════════════════════════════════════════════════════════
# 🔴 시간 — 개수만으로는 못 막는다
# ══════════════════════════════════════════════════════════════════


def test_사람이_기다리는_모드만_짧게_조인다():
    """🔴 실측 2026-10-01 이 만든 계약.

    열기 예산을 20으로 올리고 녹음을 돌렸더니 **8분 동안 카세트가 한 건도 안
    늘었다.** 산수:

        `MIN_INTERVAL_SEC` 2초 + `TIMEOUT_SEC` 20초 = 열기 한 건 최악 22초
        22초 × 20건 = 한 세포 **7분 20초** · 세포 여섯 = **44분**

    사용자가 *"예측해줘"* 하고 44분을 기다릴 수 없다.

    ⚠️ **배치에는 걸지 않는다.** 배치 개수(3·2·1)는 작아 필요가 없고, 걸면
       슬레이트가 조용히 얕아진다.
    """
    q = cells.budget_for(4, fetches=3, mode=cells.DEEP)
    assert q.seconds == cells.DEEP_SECONDS and q.seconds > 0
    assert cells.budget_for(4, fetches=3).seconds is None, \
        "배치에 시간 상한이 걸렸다 — 슬레이트가 조용히 얕아진다"
    # 🔴 상한이 **산수와 맞아야** 한다 — 20건 × 22초를 덮으면 안 막는 것이다
    worst = cells.DEEP_FETCHES * 22
    assert q.seconds < worst, (
        f"시간 상한 {q.seconds}초가 최악 {worst}초를 안 막는다")


def test_시간이_다하면_열기를_멈추고_사유를_남긴다():
    b = cells.budget_for(4, fetches=3, mode=cells.DEEP)
    assert b.take_fetch() is True
    b.started -= (b.seconds + 1)              # 🔴 시계를 앞당긴다
    assert b.take_fetch() is False, "시간이 다했는데 계속 연다"
    assert b.out_of_time is True
    # 🔴 사유가 **문장으로** 남아야 한다 — 이 문장이 블랙보드 unknown 으로 간다
    assert "시간 예산 소진" in b.spent, b.spent
    assert b.used_fetches < b.fetches, \
        "개수가 남았는데도 멈췄다는 사실이 `spent` 에 보여야 한다"


def test_시간이_다하면_검색도_멈춘다():
    """🔴 열기만 막으면 검색이 계속 돌아 시간이 또 흐른다."""
    b = cells.budget_for(4, fetches=3, mode=cells.DEEP)
    b.started -= (b.seconds + 1)
    assert b.take_search() is False and b.out_of_time is True


def test_배치_예산에는_시간_칸이_없는_채로_동작한다():
    """⚠️ `seconds=None` 이 **예외를 내지 않아야** 한다 — 배치가 멈춘다."""
    b = cells.budget_for(4, fetches=2)
    b.started -= 10_000
    assert b.take_fetch() is True and b.out_of_time is False
    assert "초" not in b.spent, f"배치 사유에 시간이 끼었다: {b.spent}"


def test_사전분석과_즉답이_시간으로만_갈린다():
    """★ 🔴 **구조 지시 2026-10-01** — 사용자가 못 박았다:

    > 기존에 **서버에서 분석을 하고 있다** .. 사용자가 경기를 질문을 한다 ..
    > 아까 내가 보여준 결과물대로 사용자에게 답변을 줘야 한다

    분석은 **미리** 서버가 한다. 그래서 깊은 분석은 **사람이 안 기다리는 경로**이고,
    거기서 시간을 조이면 깊이를 잃는다.

    ⚠️ 내 첫 판은 *"질문형이니 빨라야 한다"* 며 90초를 **깊은 분석에** 걸었다.
       그것이 틀린 전제였다 — 두 경로를 가른다.

    🔴 **깊이(열기 개수)는 같고 시간만 다르다.** 열기까지 줄이면 `ASK` 가 다른
       분석이 되어 버리고, 그러면 같은 질문에 두 가지 답이 생긴다.
    """
    deep = cells.budget_for(6, fetches=3, mode=cells.DEEP)
    ask = cells.budget_for(6, fetches=3, mode=cells.ASK)
    assert deep.fetches == ask.fetches == cells.DEEP_FETCHES, \
        "깊이가 모드마다 다르면 같은 질문에 두 답이 생긴다"
    assert deep.searches == ask.searches
    assert ask.seconds < deep.seconds, (
        "사람이 기다리는 경로가 서버 사전 분석보다 **짧아야** 한다")
    assert cells.budget_for(6, fetches=3).seconds is None, \
        "배치에 시간 상한이 걸렸다"


def test_사전분석_상한이_슬레이트_규모와_맞는다():
    """★ 🔴 **상한이 슬레이트를 못 돌면 "서버가 미리 분석한다"가 거짓이 된다.**

    실측 2026-10-01: 슬레이트 **31경기**(NHL 16 · MLB 8 · NPB 7, 오늘 이후).
    경기마다 도는 세포 **넷**(라인업·의도 × 두 팀).

    산수 (지금은 세포가 **직렬**이다):

        최악 한 경기 = 4 × `DEEP_SECONDS` = 20분
        31경기       = **10.3시간**        → 하루에 들어간다, 그러나 여유가 없다

    v4 §12-d 가 요구하는 **병렬**(*"경기별 검색은 병렬(경기당 독립 코루틴)"*)이면
    한 경기 최악 = 가장 느린 세포 = 5분 → 31경기 **2.6시간**.

    🔴 이 계약이 잠그는 것: `DEEP_SECONDS` 를 올리다가 **하루를 넘기지 못하게**.
       넘기면 분석이 못 끝난 경기를 사용자가 묻게 되고, 그것은 조용한 실패다.
    ⚠️ `31` 은 실측값이다 — 슬레이트가 커지면 이 수를 갱신하고 다시 재라.
    """
    games = 31                      # 실측 2026-10-01 (오늘 이후 슬레이트)
    cells_per_game = 4              # 라인업·의도 × 두 팀
    half_day = 12 * 3600
    serial = cells_per_game * cells.DEEP_SECONDS * games
    assert serial < half_day, (
        f"직렬 최악 {serial / 3600:.1f}시간 — 반나절을 넘긴다. 재분석(방아쇠)·"
        f"이틀치 슬레이트 몫이 없다. `DEEP_SECONDS` 를 낮추거나 세포를 병렬로")
    # 🔴 병렬이면 넉넉하다 — 그 격차가 §12-d 병렬 요구의 근거다
    assert cells.DEEP_SECONDS * games < serial / 2
