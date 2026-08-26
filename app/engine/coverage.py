"""[A-4단계] 종목별 **수집 가능 범위**를 한 곳에 선언한다.

없는 것을 억지로 만드는 것보다 없다고 말하는 것이 낫다 — 이 프로젝트의 기본 규율.

KBO·NPB에서 전문가 픽은 **수집하지 않는다.** 실측(2026-08-27, 캐시된 research):
  KBO expert_picks 0/5 · NPB 1/6 (그마저 "NPBアナリスト A" 같은 익명)
  MLB 10/15 · 축구 3/3  ← 영어권에는 실제로 존재한다
한국어 매체에 KBO 전문가 픽이 **정형화된 형태로 존재하지 않는다.** 그동안
수집된 것도 대부분 "전적 미상 — 0.5표"였고, 검증되지 않은 픽은 축으로서
가치가 낮았다.

⚠️ 축이 3개에서 2개로 줄었으므로 **문턱이 높아져야 한다.**
   종전에는 `axes_n >= 2`였는데, KBO에서 전문가 축이 항상 꺼져 있으면
   그 조건이 **우연히** data+model을 요구하게 된다. 우연에 기대지 않고
   명시한다 — 살아 있는 축이 **전부** 같은 방향일 때만 추천 자격을 준다.
"""

# 종목별로 **수집하지 않는** 필드. 카드에 "미수집"으로 정직하게 표기된다.
UNCOLLECTED: dict[str, tuple[str, ...]] = {
    "kbo": ("expert_picks", "umpire", "fan_sentiment", "counter_evidence"),
    "npb": ("expert_picks", "umpire", "fan_sentiment", "counter_evidence"),
    "mlb": (),
    "soccer": (),
}

# 사람이 읽을 이름
FIELD_KR = {
    "expert_picks": "전문가 픽",
    "umpire": "주심 성향",
    "fan_sentiment": "팬 여론",
    "counter_evidence": "반대 근거 수집",
}

# 전문가 픽이 없으면 전문가 축도 없다.
_AXIS_OF_FIELD = {"expert_picks": "expert"}
ALL_AXES = ("data", "expert", "model")


def uncollected(sport: str) -> tuple[str, ...]:
    return UNCOLLECTED.get(sport, ())


def available_axes(sport: str) -> tuple[str, ...]:
    """그 종목에서 **실제로 살아 있는** 근거 축."""
    dead = {_AXIS_OF_FIELD[f] for f in uncollected(sport) if f in _AXIS_OF_FIELD}
    return tuple(a for a in ALL_AXES if a not in dead)


def qualifies_axes(sport: str, axes: dict) -> bool:
    """추천 자격의 축 조건.

    · 축이 온전한 종목(MLB·축구) — 종전대로 **2축 이상**
    · 축이 줄어든 종목(KBO·NPB) — **살아 있는 축이 전부** 같은 방향
      (한 축이라도 비면 추천하지 않고 마켓 보드만 보여준다)
    """
    avail = available_axes(sport)
    if len(avail) < len(ALL_AXES):
        return bool(avail) and all(axes.get(a) for a in avail)
    n = sum(1 for a in avail if axes.get(a))
    if axes.get("expert_strong"):
        n += 1
    return n >= 2


def coverage_note(sport: str) -> str:
    """카드에 붙일 한 줄. 수집하는 것이 다 있으면 빈 문자열.

    ⚠️ 사용자가 **이 픽이 어떤 근거 위에 있는지** 알아야 한다.
       축이 줄어든 사실을 숨기면 같은 신호등이 다른 무게를 갖게 된다.
    """
    miss = uncollected(sport)
    if not miss:
        return ""
    names = " · ".join(FIELD_KR.get(f, f) for f in miss)
    n = len(available_axes(sport))
    return f"ℹ️ {names} 미수집 — {n}축 판정"
