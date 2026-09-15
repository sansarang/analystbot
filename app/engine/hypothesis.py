"""[U5 2026-09-15] 가설 생성 H1 — 검색 **전에** 무엇을 찾을지 정한다.

🔴 **이것이 페이블 순서의 핵심이다.** 지금까지는 수집이 need 와 무관하게 전부
   돌았고, 그래서 S6(확인 판정)이 "무엇을 확인해야 하는가"를 몰랐고 S9(구조 픽)
   가 "무엇이 충족됐나"로 고를 수 없었다.

게이트가 방향을 정하고, 방향이 need 를 정한다:

    시장 과대   시장이 그쪽을 높게 본다  → **반대편을 세울 근거**를 찾는다
    가치 의심   우리가 높게 본다        → **우리 쪽을 무너뜨릴 근거**를 찾는다
                                          (못 찾으면 사전값이 틀린 것이다)
    동의        승패는 볼 것이 없다      → **파생(U/O·핸디)** need 만
    보드 고정   need 없음 — 수집도 하지 않는다

⚠️ **순수 함수 모듈이다.** DB·HTTP 를 부르지 않는다(`gate.py` 와 같은 규칙).
⚠️ need 이름은 **S5 가 수집하는 항목 이름과 같아야 한다.** 두 이름표를 만들면
   U7 이 영영 못 맞춘다 — 아래 `FIELDS` 가 그 원본이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 S5 추출 스키마와 **같은 이름**이다. 여기서 새 이름을 만들지 않는다.
#   (`satellite.extract_game_facts` 가 채우는 칸)
FIELDS = ("out", "doubt", "xi_status", "xi", "bench_notable",
          "last3", "midweek", "notes")

#: 방향. 게이트 side 를 그대로 쓴다(home·draw·away) — 사본 금지.
HOME, DRAW, AWAY = "home", "draw", "away"

#: 문턱. **빅매치는 3** — 자료가 많아 우연 일치가 쉽다.
SUFFICIENT_DEFAULT = 2
SUFFICIENT_BIGMATCH = 3


@dataclass(frozen=True)
class Need:
    """찾을 것 하나. `field` 는 S5 항목 이름, `side` 는 어느 팀인가."""
    field: str
    side: str
    why: str

    @property
    def key(self) -> str:
        return f"{self.side}.{self.field}"


@dataclass(frozen=True)
class Hypothesis:
    direction: str | None
    need: tuple = field(default_factory=tuple)
    sufficient_count: int = SUFFICIENT_DEFAULT
    reason: str = ""

    def as_dict(self) -> dict:
        return {"direction": self.direction,
                "need": [{"field": n.field, "side": n.side, "why": n.why}
                         for n in self.need],
                "sufficient_count": self.sufficient_count,
                "reason": self.reason}


def _other(side: str | None) -> str | None:
    """반대편. 무승부는 반대편이 없다 — None 이다."""
    return {HOME: AWAY, AWAY: HOME}.get(side or "")


#: 승패 need 표(실행판 3-1). 🔴 **축구·야구가 다른 것은 필드 이름뿐**이다 —
#  규칙은 같다. 종목으로 분기문을 늘리지 않는다.
_SOCCER_OUT = ("out", "doubt", "bench_notable")
_SOCCER_LOAD = ("midweek", "last3")
_BASEBALL_OUT = ("out", "doubt")
_BASEBALL_LOAD = ("last3",)


def build(gate_label: str, *, sport: str, side: str | None = None,
          bigmatch: bool = False, gap_pp: float | None = None) -> Hypothesis:
    """게이트 → 가설. 🔴 **여기서 확률을 만들지 않는다.**

    `gate_label` 은 `gate.AGREE|OVER|DOUBT|BOARD` 중 하나다 — 문자열을 여기
    베껴 적지 않고 `gate` 에서 가져온다.
    """
    from app.engine import gate as G

    sp = (sport or "").lower()
    out_fields = _SOCCER_OUT if sp == "soccer" else _BASEBALL_OUT
    load_fields = _SOCCER_LOAD if sp == "soccer" else _BASEBALL_LOAD
    suff = SUFFICIENT_BIGMATCH if bigmatch else SUFFICIENT_DEFAULT

    if gate_label == G.BOARD:
        # 🔴 없는 것을 찾지 않는다. 수집도 하지 않는다.
        return Hypothesis(None, (), suff,
                          "사전값 또는 시장이 없다 — 찾을 것이 없다")

    if gate_label == G.AGREE:
        # 승패는 볼 것이 없다. 파생만 본다.
        need = (Need("last3", HOME, "득점 환경(U/O)"),
                Need("last3", AWAY, "득점 환경(U/O)"))
        return Hypothesis(None, need, suff,
                          "사전값과 시장이 같다 — 승패 대신 파생만 본다")

    if gate_label == G.OVER:
        # 시장이 `side` 를 높게 본다 → **반대편을 세울 근거**.
        mine = _other(side)
        if mine is None:
            return Hypothesis(None, (), suff,
                              f"시장 과대인데 방향이 {side!r} 다 — 반대편이 없다")
        need = tuple(Need(f, side, f"시장이 높게 본 {side} 쪽 약점")
                     for f in out_fields + load_fields)
        need += tuple(Need(f, mine, f"반대편 {mine} 를 세울 근거")
                      for f in out_fields)
        return Hypothesis(mine, need, suff,
                          f"시장이 {side} 를 {abs(gap_pp or 0):.1f}%p 높게 본다 — "
                          f"{mine} 를 세울 근거를 찾는다")

    if gate_label == G.DOUBT:
        # 우리가 `side` 를 높게 본다 → **우리 쪽을 무너뜨릴 근거**.
        need = tuple(Need(f, side or HOME, f"우리가 높게 본 {side} 쪽 결장·피로")
                     for f in out_fields + load_fields)
        opp = _other(side)
        if opp:
            need += tuple(Need(f, opp, f"{opp} 가 생각보다 강할 근거")
                          for f in out_fields)
        return Hypothesis(side, need, suff,
                          f"우리가 {side} 를 {abs(gap_pp or 0):.1f}%p 높게 본다 — "
                          "무너뜨릴 근거를 못 찾으면 사전값이 틀린 것")

    logger.warning("[hypothesis] 모르는 게이트 라벨 %r — 찾을 것 없음", gate_label)
    return Hypothesis(None, (), suff, f"알 수 없는 게이트: {gate_label!r}")


def need_keys(h: Hypothesis) -> list[str]:
    """`["home.out", "away.midweek", …]`. U6 가 수집을 좁힐 때 쓴다."""
    return [n.key for n in h.need]


# ═══════════════ [U7 2026-09-15] 확인 판정 H2
#
# 🔴 왜: `confirmed/refuted/unknown` 이 없어서 지금은 **자료가 많으면 픽**이
#    된다. U5 가 need 를 만들고 U6 가 그것만 모으게 했는데, 모은 것이 가설을
#    세웠는지 무너뜨렸는지 판정하는 자리가 비어 있었다.
# 🔴 `unknown 과반 → 보드` 가 원칙 4·11 의 구현이다. 모르는 것이 절반을 넘으면
#    픽을 내지 않는다.
#
# ⚠️ U6 의 `fill_schema` 가 만든 구분이 이 판정의 전제다:
#      값이 있다(truthy) → confirmed   찾았다
#      값이 [] / False   → refuted     봤는데 없다
#      값이 None         → unknown     안 봤다 / 소스가 없다
#    `[]` 를 unknown 으로 읽으면 "결장 0명"이라는 **정보**를 모른다고 치게 되고,
#    멀쩡한 경기가 보드로 간다.

CONFIRMED, REFUTED, UNKNOWN = "confirmed", "refuted", "unknown"


def _verdict_of(value) -> str:
    """한 칸의 판정. 🔴 None 과 빈 값을 **구분**한다."""
    if value is None:
        return UNKNOWN
    if value is False or (hasattr(value, "__len__") and len(value) == 0):
        return REFUTED
    return CONFIRMED


def _unknown_ratio() -> float:
    """미상 과반 기준. ⚠️ U13 에서 `config/rules.yaml` 로 옮긴다."""
    try:
        from app.config import get_settings

        return float(get_settings().unknown_board_ratio)
    except Exception:
        return 0.5


def confirm(h: Hypothesis, collected: dict | None) -> dict:
    """가설 + 수집 → `{confirmed[], refuted[], unknown[], sufficient, board}`.

    `collected` 는 `{"home": {필드: 값}, "away": {...}}` — U6 추출 8칸 모양.

    🔴 `sufficient` 는 confirmed 수가 문턱 이상인가다. need 가 **비어 있으면
       무조건 False** — 아무것도 안 찾고 픽이 나가면 안 된다.
    🔴 `board` 는 unknown 이 과반인가다.
    ⚠️ 순수 함수다. DB·HTTP 를 부르지 않는다.
    """
    box = collected or {}
    buckets: dict[str, list] = {CONFIRMED: [], REFUTED: [], UNKNOWN: []}
    for n in h.need:
        # 🔴 **그 팀 칸만** 본다. 상대편 값을 내 근거로 읽으면 반대 방향
        #    근거가 내 근거가 된다.
        side_box = box.get(n.side) or {}
        buckets[_verdict_of(side_box.get(n.field))].append(n.key)

    total = len(h.need)
    n_conf = len(buckets[CONFIRMED])
    n_unk = len(buckets[UNKNOWN])
    sufficient = bool(total) and n_conf >= int(h.sufficient_count)
    board = (n_unk / total) > _unknown_ratio() if total else True

    out = {CONFIRMED: buckets[CONFIRMED], REFUTED: buckets[REFUTED],
           UNKNOWN: buckets[UNKNOWN], "sufficient": sufficient,
           "board": board, "need_n": total,
           "sufficient_count": int(h.sufficient_count)}
    logger.info("[confirm] need %d → 확인 %d · 반증 %d · 미상 %d "
                "· 문턱 %d · 충족 %s · 보드 %s",
                total, n_conf, len(buckets[REFUTED]), n_unk,
                h.sufficient_count, sufficient, board)
    return out
