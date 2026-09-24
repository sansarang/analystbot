"""[D61-3] 죽은 코드 — **계약이 초록이라 살아 있는 것처럼 보였다.**

사용자 2026-09-24: "전부다 하나씩 수정해라..수정후 다시 확인해라"

🔴 실측(2026-09-24) — `app/` 안에서 부르는 곳이 0이었다:
```
n05_evidence.starter_side_of   운영 0 · 계약 6   ← direction.starter_direction 이 대체
state.get_node                 운영 0 · 계약 0
odds_free.backfill_open_tags   운영 0 · 계약 0   ← 소급 대상 0쌍(완료)
```
CLAUDE.md §배선: "만든 것은 반드시 부르는 곳이 있어야 한다. 없으면 만들지
마라. **안 이어진 코드는 없는 코드보다 나쁘다** — 있는 줄 알고 아무도 다시
안 본다."

⚠️ `State.from_json` 은 **남긴다.** 살아 있는 `to_json`(`flow/run.py:39` 이
   노드마다 스냅샷을 쓴다)의 짝이고, 없애면 읽는 쪽마다 손으로 되살리는
   **사본**이 생긴다. 왕복 계약이 `tests/pipeline/test_skeleton.py` 에 있다.
"""
from __future__ import annotations

from app.collectors import odds_free as OF
from app.flow import state as ST
from app.flow.nodes import n05_evidence as E


def test_대체된_함수는_남아_있지_않다():
    """🔴 `starter_direction` 이 쪽별로 방향을 낸다 — 옛 `{악재 주체: n}`
    표현은 ⑤ 어디에서도 쓰지 않는다."""
    assert not hasattr(E, "starter_side_of")
    from app.flow import direction as DIR
    assert hasattr(DIR, "starter_direction"), "대체본이 없다"


def test_쓰지_않는_getter_가_없다():
    assert not hasattr(ST.State, "get_node")


def test_끝난_소급_함수가_없다():
    """소급 대상 0쌍(실측 2026-09-24). `tag_open` 은 **살아 있다** —
    `store_rows` 가 매 적재마다 부른다."""
    assert not hasattr(OF, "backfill_open_tags")
    assert hasattr(OF, "tag_open"), "살아 있는 쪽까지 지웠다"


def test_짝이_있는_직렬화는_남긴다():
    """⚠️ 반대 위험 — 필요한 것까지 지우지 않았다."""
    assert hasattr(ST.State, "to_json") and hasattr(ST.State, "from_json")
    s = ST.State.new({"game_id": 1, "sport": "baseball", "league": "KBO",
                      "home": "KT Wiz", "away": "NC Dinos",
                      "kickoff_utc": "2026-09-24T08:00:00+00:00"})
    assert ST.State.from_json(s.to_json()).game_id == s.game_id
