"""[MOV-1] 배당 이동 분석 (Part 1 / Phase 1-B).

배당이 **어디로, 왜** 움직이는지를 사전값 산출 전에 읽는다. 라인업 발표
직후 돈이 어느 쪽으로 갔는지가 시장이 그 뉴스를 어떻게 평가했는지를 알려준다.

🔴 **라인 이동(`move_line_hcp`·`move_line_ou`)은 만들지 않았다.** 지시문
   허가 범위가 "핸디·U/O 라인이 크롤에 없으면 멈추고 보고"라고 정했고,
   Phase 1 실측에서 없는 것이 확인됐다(oddsportal `handicapValue` 0건 ·
   theodds 08-27 정지). 원자료가 없는 칸을 만들면 영원히 NULL 인 칸이 되고,
   그 칸이 있다는 사실이 "재고 있다"는 착각을 만든다.

🔴 **소스를 섞어 계산하지 않는다**(지시문 1-B-1). 북마다 마진이 달라
   소스를 건너뛰면 이동이 아니라 **소스 차이**를 잰다.
⚠️ 순수 함수 모듈이다. DB·HTTP 를 부르지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

NEWS = "news"
MONEY = "money"
CONTRA = "contra"
NONE = "none"

#: 이동으로 치는 최소 폭(%p). 지시문 1-B-2.
MOVE_MIN_PP = 2.0
#: 뉴스와 **반대**로 이만큼 움직이면 취소 사유다. 지시문 1-B-3.
CONTRA_MIN_PP = 3.0

#: 기준선 우선순위. `triggers.KINDS` 와 **같은 이름**을 쓴다.
BASELINE_ORDER = ("open", "pre", "lineup", "late", "close")


@dataclass(frozen=True)
class Move:
    label: str
    move_pp: float | None
    reason: str


def move_pp(now, prev) -> float | None:
    """확률 이동(%p). 🔴 한쪽이라도 없으면 **None** — 0 이 아니다.

    "안 움직였다"와 "모른다"는 다른 말이고, 0 으로 읽으면 둘이 같아진다.
    """
    if now is None or prev is None:
        return None
    return round((float(now) - float(prev)) * 100, 2)


def moved(pp) -> bool:
    return pp is not None and abs(float(pp)) >= MOVE_MIN_PP


def series(snaps: list[dict], provider: str) -> list[dict]:
    """한 소스의 스냅샷만. 🔴 소스를 건너뛰면 마진 차를 이동으로 읽는다."""
    return [s for s in (snaps or []) if s.get("provider") == provider]


def baseline(snaps: list[dict]) -> dict | None:
    """괴리 기준선. `open` 이 있으면 그것, 없으면 **가장 이른** 스냅샷."""
    if not snaps:
        return None
    by = {s.get("snap_tag"): s for s in snaps}
    for tag in BASELINE_ORDER:
        if tag in by:
            return by[tag]
    return snaps[0]


def move_between(snaps: list[dict], now_tag: str, prev_tag: str,
                 *, provider: str | None = None, key: str = "p_home"):
    """두 시점 사이 이동. 한쪽이 없으면 None. 소스를 지정하면 그 안에서만."""
    rows = series(snaps, provider) if provider else list(snaps or [])
    by = {s.get("snap_tag"): s for s in rows}
    a, b = by.get(now_tag), by.get(prev_tag)
    if a is None or b is None:
        return None
    return move_pp(a.get(key), b.get(key))


def classify(*, move_pp: float | None, news: dict | None) -> Move:
    """이동 + 뉴스 방향 → 원인. **코드 규칙이다. LLM 을 부르지 않는다.**

    ⚠️ 딥서치가 없는 경기(`news is None`)는 `money`/`none` 만 나온다 —
       근거 없이 `news` 를 붙이면 확증이 거짓으로 선다.
    """
    if not moved(move_pp):
        return Move(NONE, move_pp, "이동이 임계 미만이다")
    pp = float(move_pp)
    if not news:
        return Move(MONEY, pp,
                    f"{abs(pp):.1f}%p 이동 — 뉴스 근거 없음(딥서치 미실행 또는 무소득)")
    # 이동 부호: 양수면 홈 쪽으로 갔다는 뜻이다.
    toward = "home" if pp > 0 else "away"
    want = str(news.get("direction") or "")
    why = str(news.get("why") or "").strip()
    if toward == want:
        return Move(NEWS, pp, f"{abs(pp):.1f}%p {toward} 쪽 이동 — 뉴스와 같다: {why}")
    if abs(pp) >= CONTRA_MIN_PP:
        return Move(CONTRA, pp,
                    f"{abs(pp):.1f}%p {toward} 쪽 이동 — 뉴스({want})와 **반대**: {why}")
    return Move(MONEY, pp, f"{abs(pp):.1f}%p {toward} 쪽 이동 — 뉴스와 다르나 폭이 작다")


def confirm(label: str, *, adj_pp: float | None, move_pp: float | None) -> int:
    """`news` 이동이 코드 가감과 **같은 방향**이면 확증(+1). 크기는 안 바꾼다.

    지시문 1-B-4 ②. 확증은 플래그일 뿐 확률을 움직이지 않는다.
    """
    if label != NEWS or adj_pp is None or move_pp is None:
        return 0
    return 1 if (float(adj_pp) >= 0) == (float(move_pp) >= 0) else 0


def cancels(label: str) -> bool:
    """`contra` 면 픽·구조 픽을 취소한다(지시문 1-B-4 ④)."""
    return label == CONTRA
