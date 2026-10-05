"""🔴🔴 **결정 ③ — 에이전트가 켜져 있으면 세포는 검색하지 않는다**.

사용자 결정 2026-10-04:

> 세포 검색은 **끈다**. v5에서 세포는 **계획기가 아니라 장부**다. 에이전트가
> 켜져 있으면 세포는 **검색하지 않고 커버리지 기록만** 한다. 지금 세포가 먼저
> 돌며 시간을 먹고 `query_too_bare` 26건을 만드는 건 **폐기할 경로에 비용을
> 쓰는 것**이다. 이걸 끄면 경기당 실행 시간도 크게 준다.

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-04 (게이트2 2판) — 세포가 만든 폐기
══════════════════════════════════════════════════════════════════

```
MLB  queries:23 → query_too_bare **26**
KBO  queries:37 → query_too_bare **65**
```

⚠️ 그 질의들은 **세포 것**이다(에이전트 것은 따로 세며 34/20 · 24/21 이었다).
🔴 그것을 *"고쳤다"* 가 아니라 **"그 경로를 끊었다"** 로 적는다.
"""
from __future__ import annotations


def test_dec3_에이전트가_켜지면_세포가_안_던진다():
    """🔴 끄는 문이 **있고**, 그 문이 `AGENT_ENABLED` 를 본다."""
    from app import cells
    assert hasattr(cells, "may_search"), (
        "🔴 세포 검색을 끄는 문이 없다 — `cells.may_search()` 를 만들어라")
    assert cells.may_search(agent_on=True)[0] is False
    # ⚠️ 에이전트가 **꺼져 있으면** 종전대로 검색한다(퇴로를 남긴다)
    assert cells.may_search(agent_on=False)[0] is True


def test_dec3_사유가_글로_남는다():
    """🔴 **조용한 0 금지**(#3) — *"안 찾았다"* 와 *"찾았는데 0건"* 은 다르다."""
    from app import cells
    ok, why = cells.may_search(agent_on=True)
    assert ok is False
    assert "장부" in why or "에이전트" in why, why


def test_dec3_커버리지는_계속_쌓인다():
    """🔴🔴 *"검색하지 않고 **커버리지 기록만** 한다"* — 장부는 계속 쓴다.

    ⚠️ 검색을 끄면서 칸 기록까지 멈추면 카드가 **빈 상태표**를 낸다 — 그것은
       "못 쟀다"를 "없다"로 바꾸는 것이다(#3).
    """
    import inspect

    from app import cells
    from tests._helpers import strip_docs
    # ⚠️ 문은 **검색 소스 입구**(`_try`)에 있다 — `run` 은 소스를 돌리는 루프다.
    #    🔴 처음 `Cell.run` 을 봤고 그것이 빗나갔다(자리를 안 재고 적었다).
    body = strip_docs(inspect.getsource(cells.Cell._try))
    assert "may_search" in body, (
        "🔴 세포의 검색 입구가 그 문을 **안 본다**(#2 배선)")
    # 🔴🔴 끈 뒤에도 **각도 기록**이 남아야 한다 — §7-5 R5(*"자료 부족"* 선언
    #    자격)의 재료다. ⚠️ 검색을 끄면서 그 수까지 멈추면 R5 가 자격 없이
    #    돌거나 영영 못 돈다.
    after = body.split("may_search", 1)[1].split("take_search", 1)[0]
    assert "funnel.angle" in after, (
        "🔴 검색을 끄면서 **각도 기록까지** 멈췄다 — R5 가 자격을 잃는다")


def test_dec3_깔때기가_끊긴_것을_이름으로_적는다():
    """🔴 깔때기의 `queries` 칸이 **0 이 아니라 사유**를 들어야 한다."""
    from app import reasons
    assert hasattr(reasons.Reason, "CELL_SEARCH_OFF"), (
        "🔴 `Reason.CELL_SEARCH_OFF` 가 없다 — 끊은 경로를 **이름으로** 남겨라")
    got = reasons.Reason.CELL_SEARCH_OFF
    assert got.fix_where == "없음", got.fix_where
    assert got.kind == "none", got.kind


def test_dec3_설정이_아니라_에이전트_스위치를_본다():
    """🔴 새 스위치를 만들지 않는다 — `AGENT_ENABLED` **하나**가 원본이다.

    ⚠️ 스위치를 둘로 두면 *"에이전트는 켜고 세포 검색도 켠"* 상태가 생기고,
       그것이 바로 사용자가 끄라고 한 **중복 비용**이다.
    """
    import inspect

    from app import cells
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(cells.may_search))
    assert "CELL_SEARCH" not in body, (
        "🔴 세포 검색용 **새 스위치**를 만들었다 — `AGENT_ENABLED` 하나로 "
        "갈려야 한다(스위치가 둘이면 중복 비용이 되살아난다)")
