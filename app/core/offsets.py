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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **P1 — "리그 간 전력 차" 표시 줄**(수정 지시 2026-10-13 밤 P1)
# ══════════════════════════════════════════════════════════════════
#
#  > 판정: … 통과 전에는 카드에 **"리그 간 전력 차(표시만)"** 줄로만 낸다 —
#  > 확률 경로에 안 넣는다.
#
#  🔴 그래서 이 아래 함수들은 **글자만** 만든다(계약 CC4 가 확률 모듈에서 호출
#     0건을 센다). 확률은 여전히 대회 실측 득점·홈 배율만 쓴다.
#  ⚠️ 판 고르기 — 표시 줄은 **가장 최근 판**을 읽는다(그 수는 그 경기의 정보가
#     아니라 **지난 대회 맞대결의 성적표**이고 확률에 닿지 않는다). 확률에 쓰는
#     경로는 그대로 `pick_file`(as-of 이전)이다 — CC2 는 그쪽을 지킨다.

AUTO_ELO = ROOT / "data/league_elo_auto"


def league_of(team: str) -> tuple[str, str]:
    """🔴 그 팀의 **국내 리그 열쇠**(자동 등록 Elo 판들이 팀 목록을 든다)."""
    import yaml
    said = str(team or "").strip()
    if not said or not AUTO_ELO.is_dir():
        return "", "⬜ 자동 등록 Elo 판이 없다"
    low = said.lower()
    from app.core import competition as _cp
    for path in sorted(AUTO_ELO.glob("*.yaml")):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # 🔴 **대륙 대회 판은 국내 리그가 아니다** — 그 판이 섞이면 모든 팀이
        #    `league:ACLE` 소속으로 잡힌다(실측 2026-10-13: 그렇게 나왔다).
        said_key = str(got.get("league") or "")
        if _cp.kind_require(said_key)[0] == "club_continental":
            continue
        teams = {str(k).strip().lower(): float(v)
                 for k, v in dict(got.get("teams") or {}).items()}
        if low in teams:
            return str(got.get("league") or ""), (
                f"판 `{path.stem}`(경기 {got.get('n')} · 팀 {len(teams)})")
    return "", f"⬜ `{said}` 가 어느 자동 등록 판에도 없다"


def latest_plate(conf: str) -> tuple[dict, str]:
    """🔴 그 대륙의 **가장 최근** 오프셋 판(표시 전용 · 위 설명)."""
    box = BOX / str(conf or "").upper()
    # 🔴 **날짜 이름만** 센다 — `verify.yaml`(검증 ρ)이 섞이면 그것이 판으로
    #    잡힌다(실측 2026-10-13: 맞대결 수가 `None` 으로 찍혔다).
    rows = sorted(p for p in (box.glob("*.yaml") if box.exists() else [])
                  if __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
    if not rows:
        return {}, f"⬜ `{conf}` 오프셋 판이 없다"
    import yaml
    got = yaml.safe_load(rows[-1].read_text(encoding="utf-8")) or {}
    return dict(got), f"판 `{rows[-1].stem}`(맞대결 {got.get('n')}경기)"


def verify_said(conf: str) -> str:
    """🔴🔴 **검증 꼬리표**(후속 지시 2026-10-13 밤 1번) — 외부 순위와의 ρ.

    > 카드의 🌐 표시 줄은 **ρ ≥ 0.6 확인 전까지 🟡 "검증 전"** 꼬리표.

    🔴 판은 `data/league_offsets/<대륙>/verify.yaml` 이고
       `tools/offset_check.py` 가 적는다(외부 순위는 **받아서 읽는다**).
    """
    path = BOX / str(conf or "").upper() / "verify.yaml"
    if not path.exists():
        return " · 🟡 **검증 전**(외부 순위와의 ρ 를 아직 안 쟀다)"
    import yaml
    box = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rho = box.get("rho")
    if rho is None:
        return " · 🟡 **검증 전**(ρ 가 판에 없다)"
    if not bool(box.get("ok")):
        return (f" · 🟡 **검증 미달** — 외부 순위와 ρ {float(rho):.2f} < "
                f"{float(box.get('cut') or 0.6):.1f}(적합 방식을 의심한다)")
    return (f" · ✅ **검증** 외부 협회 순위와 스피어만 ρ **{float(rho):.2f}**"
            f"(짝 {int(box.get('pairs') or 0)}개)")


def gap_said(*, conf: str, home: str, away: str) -> str:
    """🔴🔴 카드 한 줄 — **리그 간 전력 차(표시만)**. 못 쟀으면 ⬜ + 사유."""
    box, why = latest_plate(conf)
    out = []
    vals: dict[str, float | None] = {}
    for name, side in ((home, "홈"), (away, "원정")):
        key, why_l = league_of(name)
        if not key:
            out.append(f"{side} **{name}** ⬜ {why_l}")
            vals[side] = None
            continue
        one = dict(dict(box.get("leagues") or {}).get(key) or {})
        n = int(one.get("n") or 0)
        if one.get("value") is None:
            out.append(f"{side} **{name}**(`{key}`) ⬜ 오프셋 미산출"
                       f"(리그 간 맞대결 {n}경기 < {MIN_GAMES})")
            vals[side] = None
            continue
        vals[side] = float(one["value"])
        out.append(f"{side} **{name}**(`{key}`) **{float(one['value']):+.0f}**"
                   f"(표본 {n}경기)")
    tail = ""
    if vals.get("홈") is not None and vals.get("원정") is not None:
        said_gap = float(vals["홈"]) - float(vals["원정"])  # type: ignore[arg-type]
        tail = (f" → **리그 간 전력 차 {said_gap:+.0f}점**"
                f"({'홈' if said_gap > 0 else '원정'} 리그가 높다)")
    else:
        tail = " → 🟡 **차를 못 센다**(한쪽 이상 ⬜)"
    return (" · ".join(out) + tail + f" · {why}"
            + verify_said(conf)
            + " · ⚠️ **표시만**(확률 경로에 안 들어간다 · P1 판정 전)")
