"""② **재검색 루프** 계약 (사용자 설계 2026-10-02).

> ② 빗나가면 각도를 바꾼다 — 프리뷰 → 감독 회견 → 현지 매체 → 현지어
> **관련 0건이면 다음 템플릿**
> (봇: 예산 3회, 늘리면 엔진 정지 전례 / 나: 경기당 2~4회 + 각도 전환)
"""
from __future__ import annotations

import asyncio
import inspect

from app import cells, rules
from app.blackboard import Blackboard, Fact
from app.net import Fetched, Net
from tests._helpers import strip_docs


def _cell(n_sources: int, hit_at: int | None, angles: int):
    """검색 소스 `n_sources` 개 중 `hit_at` 번째만 사실을 낸다."""
    calls: list[str] = []

    def _mk(i: int):
        def _parse(payload, q):
            calls.append(f"s{i}")
            if hit_at is not None and i == hit_at:
                return [Fact(question_id=q.id, value={"x": i}, hardness="hard")]
            return []
        # 🔴 **v5 §4-1 문지기**(2026-10-04): 질의가 **세 요소 이상**이어야
        #    던져진다. ⚠️ 대역 질의(`q0`)는 한 요소라 막힌다 — 이 시험의 요점은
        #    **각도 전환**이고 문지기가 아니다. 🔴 그래서 조각을 선언으로 준다.
        return cells.Source(f"검색:{i}", "search", query=f"q{i}",
                            parts={"team": "A", "opponent": "B",
                                   "when": f"lineup{i}"},
                            parse=_parse, lang="en")

    cell = cells.Cell(cells.Question(cells.Q_COUNTER, "L:팀:2026-10-02",
                                     team="팀", league="L"),
                      [_mk(i) for i in range(n_sources)],
                      budget=cells.Budget(searches=n_sources, fetches=4,
                                          angles=angles))

    class _Search:
        available = True

        async def query(self, text, **k):
            return [type("H", (), {"url": f"https://x/{text}", "title": "t",
                                   "snippet": "s", "publisher": "p",
                                   "published_at": None, "body": ""})()]

    net = Net()

    async def _get(url, **k):
        return Fetched(url, True, 200, "<html>x</html>")

    net.get = _get                                  # type: ignore[assignment]
    state = asyncio.run(cell.run(net, Blackboard(), search=_Search(),
                                 scores=None))
    return state, cell, calls


def test_빗나가면_다음_각도로_간다():
    """🔴 관련 0건이면 **다음 템플릿**을 던진다."""
    _state, cell, calls = _cell(4, hit_at=3, angles=4)
    # 🔴 네 각도를 다 던졌고 **마지막에서 맞혔다** — 빗나간 것은 셋이다
    assert len(calls) == 4, calls
    assert cell.budget.used_angles == 3, cell.budget.used_angles
    assert cell.budget.out_of_angles is False


def test_맞히면_남은_각도를_쓰지_않는다():
    """🔴 **맞힌 각도는 세지 않는다.** 전 판 예산은 검색 횟수만 셌다."""
    _state, cell, calls = _cell(4, hit_at=0, angles=4)
    assert calls == ["s0"], calls
    assert cell.budget.used_angles == 0, "맞혔는데 각도를 썼다"
    assert cell.budget.out_of_angles is False


def test_각도_예산이_끊으면_사유가_다르다():
    """🔴 끊길 때 **사유가 셋으로 갈린다**: 각도 소진 ≠ 검색 횟수 ≠ 시간 초과.

    ⚠️ 한 사유로 적으면 *"무엇을 늘려야 하는가"* 를 모른다.
    """
    _state, cell, calls = _cell(6, hit_at=None, angles=2)
    # 🔴 **`max_angles` 는 "빗나가도 되는 횟수"다** — 첫 시도는 전환이 아니다.
    #    그래서 던진 각도는 `angles + 1` 이고 남은 소스 셋은 **안 던진다.**
    #    ⚠️ 이 뜻을 흐리면 "4개 템플릿인데 왜 3개만 돌았나"를 영영 못 센다.
    assert len(calls) == 3, calls
    assert cell.budget.used_angles == 2
    assert cell.budget.out_of_angles is True
    assert any("각도 소진" in t for t in cell.tried), cell.tried
    assert any("안 던졌다" in t for t in cell.tried), cell.tried
    # 🔴 요약 줄이 각도를 **따로** 적는다 — 이 수가 상한을 정하는 자료다
    spent = cell.budget.spent
    assert "빗나간 각도 2/2" in spent and "각도 예산 소진" in spent, spent
    assert "검색" in spent and "열기" in spent


def test_상한을_yaml_이_정한다():
    """🔴 숫자를 코드에 박지 않는다 — **실제 테스트로 정한다**(사용자 지시).

    ⚠️ 그래서 yaml 이 *"미정 — 실제 테스트로 정한다"* 를 적어 둔다.
    """
    pol = rules.catalog_policy()
    assert int(pol["max_angles"]) >= 2
    assert "실제 테스트" in str(pol.get("measured")), pol
    src = strip_docs(inspect.getsource(cells.budget_for))
    assert "catalog_policy" in src
    # 🔴 값이 코드에 박혀 있지 않나
    assert str(pol["max_angles"]) not in src
    assert cells.budget_for(3, fetches=2).angles == int(pol["max_angles"])


def test_직접_주소_소스는_각도를_쓰지_않는다():
    """🔴 각도는 **검색**의 개념이다. 공식 API 가 0건을 내는 것은 "각도가 틀렸다"가
    아니라 "그 자료가 없다"다 — 그것으로 각도를 깎으면 검색이 시작도 못 한다."""
    src = strip_docs(inspect.getsource(cells.Cell.run))
    at = src.index("take_angle()")
    head = src[max(0, at - 400):at]
    assert 'src.kind == "search"' in head, head[-200:]
