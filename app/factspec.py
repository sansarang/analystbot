"""🔴🔴 **어댑터 통일 스키마** — v5 §8-3. #6 을 닫는 자리다.

> 모든 어댑터는 **같은 꼴**로 낸다. 어댑터 고유 칸
> (`home_goals/home_score`, `last5/recent`, `matches/window_games`)은
> **어댑터 안에서 변환하고 밖으로 나오지 않는다.**
> 계약: **어댑터 밖 코드에서 어댑터 고유 칸 이름이 보이면 실패.** [#6]

══════════════════════════════════════════════════════════════════
🔴 왜 — **같은 꼴 버그를 세 번** 맞았다 (2026-10-04)
══════════════════════════════════════════════════════════════════

```
① `last5` 를 내는 어댑터가 fotmob 하나      → 야구·하키 폼 변수 **0**
② `home_goals` 를 쓰는 어댑터가 fotmob 하나 → 야구·하키 맞대결 **0승 0패**
③ `window_games` 만 세고 `count` 를 안 봄   → 13경기를 **0경기**로
```
⚠️ 셋 다 **읽는 쪽**(`classify`)에 `or` 를 덧대 고쳤다. §11-1 이 금지한 그것이다:

> **증상 수정 금지** — 같은 꼴 버그가 두 번째로 나오면 그 자리를 고치지 말고
> **그 꼴을 막는 계약부터** 쓴다(칸 이름 불일치 → `Fact` 스키마 계약).

🔴 그래서 **정본 이름을 여기 한 곳**에 선언하고, 어댑터가 그 이름으로 내보낸다.
   읽는 쪽에 `or` 분기가 남아 있으면 계약이 빨개진다.

══════════════════════════════════════════════════════════════════
⚠️ `app/blackboard.Fact` 와 **다른 것**이다
══════════════════════════════════════════════════════════════════

```
blackboard.Fact   세포가 받은 **한 소스의 답**(질문 id·값·검증 재료)
factspec.Fact     🔴 어댑터가 내보내는 **구조 사실의 꼴**(§8-3)
```
🔴 §8-3 은 *"모든 어댑터가 같은 꼴로 낸다"* 를 요구하고, 그 꼴이 이것이다.
⚠️ 두 이름이 같아 헷갈리므로 이 모듈을 **거쳐서만** 쓴다(`factspec.Fact`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: 🔴 §8-3 `kind` — **여덟**뿐이다. ⚠️ 오타로 새 `kind` 가 생기면 그 사실이 샌다
#   (아무 분기도 그것을 안 받아 조용히 배경이 된다).
KINDS: tuple[str, ...] = ("result", "standing", "h2h", "starter",
                          "starter_stats", "lineup", "absence", "schedule")

#: 🔴 §8-3 `state` — 셋. ⚠️ 어댑터 원문은 `Final`·`OFF`·`완료` 로 갈린다 —
#   **그 변환이 어댑터 안에서** 끝나야 한다(그것이 이 선언의 요점이다).
STATES: tuple[str, ...] = ("final", "live", "scheduled")

#: 🔴🔴 **정본 칸 이름.** §8-3 의 `Fact` 가 이름 댄 것 + `payload` 안의 정본.
#
#  ⚠️ `payload` 안에도 정본이 있다 — 폼·맞대결이 거기 들어가고, 그 키가 갈리면
#     §8-3 의 뜻이 사라진다(바로 그 셋이 세 번 다친 자리다).
CANON: tuple[str, ...] = (
    # ── §8-3 `Fact` 의 칸
    "kind", "team", "opponent", "date_utc", "home_score", "away_score",
    "state", "payload", "source", "url", "hardness",
    # ── `payload` 안의 정본
    "last5",     # ['W','D','L',…] — 🔴 **어댑터가 계산해서** 낸다
    "recent",    # 최근 경기 행들(각 행이 `home_score`/`away_score`/`state`)
    "matches",   # 맞대결 경기 행들
    "count",     # 🔴 그 목록의 **개수**(`window_games` 가 아니다)
    "rest_days", "last_game", "games",
)

#: 🔴🔴 **어댑터 고유 칸** — 어댑터 **안에서만** 쓴다.
#
#  ⚠️ 이 목록은 §8-3 이 괄호로 이름 댄 셋에서 자랐다:
#     `home_goals/home_score` · `last5/recent` · `matches/window_games`
#  🔴 각 쌍에서 **정본을 고른 근거**:
#     `home_score`  — §8-3 의 `Fact` 가 그 이름을 쓴다(문서가 정했다)
#     `matches`     — 어댑터 넷(fdorg·mlb·nhl·fotmob)이 이미 쓴다(fotmob 만 `window`)
#     `count`       — 같은 이유(`window_games` 는 fotmob 하나다)
#     ⚠️ `last5`·`recent` 는 **쌍이 아니다** — 하나는 글자 수열이고 하나는 경기
#        행들이다. 🔴 둘 다 정본이고, **어댑터가 둘 다 낸다**(`last5` 는 자기
#        행에서 계산한다). 그래야 읽는 쪽에 꼴 분기가 안 남는다.
ADAPTER_ONLY: tuple[str, ...] = ("home_goals", "away_goals",
                                 "window", "window_games")


def _utc(when: object, *, where: str = "") -> datetime:
    """🔴 §8-3: *"반드시 tz 포함 — **naive 면 실패**."* ⚠️ 조용히 UTC 로 안 민다."""
    if not isinstance(when, datetime):
        raise ValueError(f"🔴 시각이 아니다{(' (' + where + ')') if where else ''}: "
                         f"{when!r}")
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(
            f"🔴 **시간대 없는 값**이다(§8-3·§8-7){(' (' + where + ')') if where else ''}"
            f": {when!r} — 서버 시간대가 조용히 끼어든다")
    return when.astimezone(timezone.utc)


def is_key(value: object) -> bool:
    """🔴 그것이 **팀 열쇠**인가(`team:000338`). ⚠️ 이름이면 거짓이다."""
    return isinstance(value, str) and value.startswith("team:")


@dataclass(frozen=True)
class Fact:
    """🔴 어댑터가 내보내는 **구조 사실 하나**(§8-3).

    ⚠️ `frozen` 이다 — 중간 단계가 슬그머니 고치면 그 자체가 이 병의 재발이다.
    """

    kind: str
    team: str | None
    opponent: str | None
    date_utc: datetime
    home_score: int | None
    away_score: int | None
    state: str
    payload: dict = field(default_factory=dict)
    source: str = ""
    url: str | None = None
    hardness: int = 0

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"🔴 모르는 `kind` 다: {self.kind!r} — "
                             f"§8-3 이 이름 댄 것은 {list(KINDS)}")
        if self.state not in STATES:
            raise ValueError(f"🔴 모르는 `state` 다: {self.state!r} — "
                             f"§8-3 이 이름 댄 것은 {list(STATES)}"
                             f"(어댑터 원문 `Final`·`OFF` 는 **어댑터 안에서** 바꾼다)")
        for name in ("team", "opponent"):
            got = getattr(self, name)
            if got is not None and not is_key(got):
                raise ValueError(
                    f"🔴 `{name}` 은 **팀 열쇠**(`team:000338`)여야 한다 — "
                    f"받은 것: {got!r}. 이름이 들어오면 1~3단계가 고친 병이 "
                    f"데이터 모델에서 되살아난다(§8-1)")
        # 🔴 `frozen` 이라 대입을 못 한다 — 검사만 하고 바꾸지 않는다
        _utc(self.date_utc, where=f"{self.kind}")

    @property
    def date_utc_checked(self) -> datetime:
        """⚠️ UTC 로 맞춘 사본. 🔴 원본을 고치지 않는다(`frozen`)."""
        return _utc(self.date_utc)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **어댑터가 쓰는 변환기** — §8-3 *"어댑터 안에서 변환한다"*
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 어댑터마다 적으면 또 갈린다(그것이 #6 이다). 🔴 그래서 변환은 **여기 하나**
#     이고 어댑터가 그것을 부른다 — `app/collect/` 안에서만 부른다.

#: 🔴 끝난 경기를 뜻하는 **어댑터 원문**. ⚠️ 실측으로 적은 것만:
#   MLB statsapi `abstractGameState` → `"Final"` · NHL `gameState` → `"OFF"`
FINAL_WORDS: tuple[str, ...] = ("final", "off", "완료", "종료")


