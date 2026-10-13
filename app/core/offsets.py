"""🔴🔴 **§5-3 리그 오프셋 · 대회 홈 이점** — 지시서 2026-10-13 밤 셋째.

> 핵심 문제: 서로 다른 리그 팀이 만난다 → 리그 안에서 잰 Elo·폼은 리그 사이에
> 비교가 안 된다.
> (a) 리그 강도 보정: 대륙 대회의 리그 간 맞대결 결과(as_of 이전, 최근 3시즌)로
>     리그별 오프셋을 추정 → **팀 점수 = 리그 내 Elo + 리그 오프셋**.
>     판 `data/league_offsets/<대륙>/<as_of>.yaml`(리그별 값·표본 수·구간).
>     리그 간 맞대결 표본 **< 20경기** 인 리그 → 오프셋 ⬜ + 🔴.
> (c) 홈 이점: **그 대회 자체 실측**(최근 3시즌 · 대회별 판). 국내 리그 홈 이점을
>     **빌리지 않는다**. 중립 경기 → 홈 이점 **0**.

🔴 **CC1** — 국내 리그 홈 이점·Elo 를 **오프셋 없이** 대륙 대회에 쓰면 실패.
🔴 **CC2** — 오프셋 계산에 `as_of` **이후** 경기를 쓰면 실패(판 고르기는
   `versions.pick_file` 하나다 · 사본 금지).
🔴 **CC3** — 중립 경기에 홈 이점을 적용하면 실패.
⚠️ 이 파일은 **읽기만** 한다 — 판을 적는 것은 도구(`tools/fit_offsets.py`)다
   (`app/` 은 yaml 을 쓰지 않는다).
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 판이 사는 곳 — `data/league_offsets/<대륙>/<날짜>.yaml`
BOX = ROOT / "data/league_offsets"

#: 🔴 대회 홈 이점 판 — `data/comp_home/<대회 열쇠>/<날짜>.yaml`
HOME_BOX = ROOT / "data/comp_home"

#: 🔴🔴 리그 간 맞대결이 이보다 적으면 **오프셋을 내지 않는다**(§5-3-a)
MIN_GAMES = 20


def plate_of(*, confederation: str, as_of) -> tuple[dict, str]:
    """🔴 그 대륙의 오프셋 판(`as_of` **이전** 최신 · CC2). `(판, 사유)`."""
    from app.core import versions as _v
    said = str(confederation or "").strip().upper()
    if not said:
        return {}, "🔴 **대륙을 모른다** — 오프셋 판을 고를 수 없다"
    path, why = _v.pick_file(BOX / said, as_of=as_of, ext="yaml")
    if path is None:
        return {}, why
    import yaml
    got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(got), why


def of(league: str, *, confederation: str, as_of) -> tuple[float | None, str]:
    """🔴🔴 그 리그의 **오프셋**(Elo 점수 단위). 표본 미달이면 `None` + 🔴.

    🔴 §5-3-a: *"리그 간 맞대결 표본 < 20경기인 리그 → 오프셋 ⬜ + 🔴(그 팀이 낀
       경기는 레이팅 비교 미산출)"*.
    """
    box, why = plate_of(confederation=confederation, as_of=as_of)
    if not box:
        return None, why
    rows = dict(box.get("leagues") or {})
    one = rows.get(str(league or ""))
    if not isinstance(one, dict):
        return None, (f"🔴 **오프셋 없다** — `{league}` 가 판에 없다({why} · "
                      f"적힌 리그 {len(rows)}개)")
    n = int(one.get("n") or 0)
    if n < MIN_GAMES:
        return None, (f"🔴 **표본 미달** — `{league}` 리그 간 맞대결 {n}경기 "
                      f"(< {MIN_GAMES}) → 오프셋 ⬜ · 그 팀이 낀 경기는 "
                      f"레이팅 비교 **미산출**")
    try:
        got = float(one["value"])
    except (KeyError, TypeError, ValueError):
        return None, f"🔴 `{league}` 오프셋 값을 못 읽었다({one!r})"
    said_band = one.get("band")
    return got, (f"오프셋 {got:+.1f}(표본 {n}경기"
                 + (f" · 95% {float(said_band[0]):+.1f}~"
                    f"{float(said_band[1]):+.1f}"
                    if isinstance(said_band, (list, tuple))
                    and len(said_band) == 2 else "")
                 + f") · {why}")


def score_of(*, elo: float | None, league: str, confederation: str,
             as_of) -> tuple[float | None, str]:
    """🔴🔴 **CC1** — 대륙 대회의 팀 점수 = 리그 내 Elo **+ 리그 오프셋**.

    🔴 오프셋이 없으면 **점수도 없다**(국내 Elo 를 그대로 쓰지 않는다 · 손값 금지).
    """
    if elo is None:
        return None, "🔴 리그 내 Elo 가 없다 — 대회 점수를 못 만든다"
    got, why = of(league, confederation=confederation, as_of=as_of)
    if got is None:
        return None, (f"🔴 **대회 점수 미산출** — 오프셋이 없으면 국내 Elo 를 "
                      f"그대로 쓰지 않는다(CC1) · {why}")
    return float(elo) + got, f"리그 내 Elo {float(elo):.0f} {why}"


def home_of(key: str, *, as_of, stage: str = "") -> tuple[float | None, str]:
    """🔴🔴 **그 대회 자체** 홈 이점 배율. 중립 경기면 **1.0**(= 이점 0 · CC3).

    🔴 **CC1** — 국내 리그 홈 이점을 빌리지 않는다. 그 대회 판이 없으면 `None`
       이고, 카드는 그 칸을 **미산출**로 적는다.
    """
    from app.core import competition as _cp
    from app.core import versions as _v
    said_key = str(key or "")
    neutral, why_n = _cp.neutral_of(said_key, stage=str(stage or ""))
    if neutral is True:
        # 🔴 **CC3** — 중립이면 홈 이점이 **없다**(배율 1.0)
        return 1.0, f"🔴 중립 경기 — 홈 이점 **0**(배율 1.0) · {why_n}"
    path, why = _v.pick_file(HOME_BOX / said_key.replace(":", "_"),
                             as_of=as_of, ext="yaml")
    if path is None:
        return None, (f"🔴 **대회 홈 이점 판이 없다** — 국내 리그 값을 빌리지 "
                      f"않는다(CC1) · {why}")
    import yaml
    box = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        got = float(dict(box)["home_mul"])
        n = int(dict(box).get("n") or 0)
    except (KeyError, TypeError, ValueError):
        return None, f"🔴 그 판에서 `home_mul` 을 못 읽었다({path.name})"
    return got, f"대회 홈 이점 ×{got:.3f}(표본 {n}경기 · {why})"
