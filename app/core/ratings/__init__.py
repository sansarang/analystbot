"""🔴🔴 **바닥 점수 — 후보 셋의 공통 틀**(지시서 2026-10-12 엔진 교체 §2).

> 공통 인터페이스:
>   `rate(matches_before_as_of, params)` → `RatingTable{team_id: {home, away,
>   overall}, as_of, n_matches}`
>   `prob_input(home_id, away_id, table)` → `diff`(숫자 하나)

🔴 왜 셋인가 — Elo 는 **골 차를 안 본다**(5-0 과 1-0 이 같다). ELOg 는 골 차로
   K 를 키우고, pi-ratings 는 **홈·원정 점수를 따로** 든다. 어느 것이 나은지는
   **백필이 말한다**(§1 판정 규칙) — 코드가 고르지 않는다.
🔴 학습률은 **판 파일**에서 온다(`data/ratings_params/<리그>/<as_of>.yaml`) —
   손값이면 계약 R2 가 빨개진다. ⚠️ 판이 없으면 `provisional` 로 표시하고 그
   사실을 카드가 적는다(조용한 임시값 금지).
🔴 누설 금지(R1) — `rate` 는 `as_of` **이전** 경기만 본다. 문은 하나다
   (`fotmob.before_as_of`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: 🔴 판 파일이 사는 곳 — `data/<표>/<열쇠>/<as_of>.yaml`(지시 §0)
TABLE = "ratings_params"

#: ⚠️ 판이 없을 때 쓰는 **임시값** — 그 사실을 `why` 가 말한다(§0 손값 금지)
FALLBACK: dict[str, dict] = {
    "elo": {"k": 20.0, "start": 1500.0},
    "elog": {"k0": 10.0, "lam": 1.0, "start": 1500.0},
    "pi": {"lam": 0.06, "gamma": 0.5, "start": 0.0},
}


@dataclass
class Params:
    """🔴 학습률 한 묶음 — 어디서 왔는지(`ver`·`why`)를 **함께** 든다."""

    name: str
    values: dict
    ver: str = ""
    provisional: bool = False
    why: str = ""

    def __getitem__(self, key: str) -> float:
        return float(self.values[key])

    def get(self, key: str, default: float = 0.0) -> float:
        got = self.values.get(key)
        return float(default if got is None else got)


@dataclass
class RatingTable:
    """🔴 `{팀: {home, away, overall}}` + `as_of` + 센 경기 수."""

    teams: dict = field(default_factory=dict)
    as_of: object = None
    n_matches: int = 0
    kind: str = ""
    params_ver: str = ""

    def of(self, team: str) -> tuple[float, str]:
        """🔴 그 팀의 `overall`. **표에 없으면 리그 하위 25%** + 사유(§2)."""
        box = dict(self.teams or {}).get(str(team))
        if box:
            return float(box["overall"]), ""
        said = sorted(float(v["overall"]) for v in (self.teams or {}).values())
        if not said:
            return 0.0, "🔴 **신규 팀 초기값** — 등급표가 비었다"
        got = said[max(0, len(said) // 4)]
        return got, (f"🔴 **신규 팀 초기값** — 표에 없다(승격·신생) → 리그 하위 "
                     f"25% {got:.2f}")


def load_params(name: str, *, league: str, as_of=None,
                strict: bool = False) -> Params:
    """🔴🔴 **R2** — 학습률은 **판 파일**에서 온다. 없으면 `strict` 면 예외다.

    🔴 판을 읽는 곳은 `app/core/versions.py` **하나다**(사본 금지 · walk-forward).
    ⚠️ 느슨한 호출은 `FALLBACK` 을 주되 `provisional=True` 와 🔴 사유를 단다 —
       카드·보고가 그 글자를 그대로 적는다.
    """
    said = str(name)
    if said not in FALLBACK:
        raise ValueError(f"🔴 모르는 바닥 점수다: `{said}`")
    from app.core import versions as _v
    box = _v.path_of(TABLE, f"{said}/{_slug(league)}")
    try:
        got, why = _v.pick(box, as_of=as_of) if as_of is not None else ({}, "")
    except ValueError as exc:
        got, why = {}, str(exc)
    if not as_of:
        why = "🔴 `as_of` 를 안 넘겼다 — 판을 고를 수 없다(L3)"
    if got:
        return Params(name=said, values=dict(got), ver=str(why),
                      provisional=False, why=why)
    if strict:
        raise ValueError(f"🔴 **R2 위반** — `{said}`·`{league}` 학습률 판이 없다"
                         f"({why}) · 손값으로 돌리지 않는다")
    return Params(name=said, values=dict(FALLBACK[said]), ver="",
                  provisional=True,
                  why=f"🔴 **임시 학습률**(판 없음 — {why}) · `tools/fit_ratings.py` "
                      f"로 적합해야 한다")


def _slug(league: str) -> str:
    """🔴 대회 열쇠를 **파일 이름**으로(`league:KL1` → `league_KL1`)."""
    return str(league or "unknown").replace(":", "_").replace("/", "_")


def rows_of(matches: list[dict], *, as_of) -> list[tuple]:
    """🔴🔴 **R1 — 문은 하나다.** `as_of` 이전 경기만 `(시각, 홈, 원정, 홈골, 원정골)`.

    🔴 거르는 함수는 `fotmob.before_as_of` 다(사본 금지) — 폼·골 시간·Elo 가
       **같은 문**을 지난다.
    ⚠️ 골이 없는 줄(미래·취소)은 버린다. 시각이 없는 줄도 버린다.
    """
    from app.collect import fotmob as fm
    said = fm.before_as_of(list(matches or []), as_of=as_of, key="utc")
    out = []
    for m in said:
        hg, ag = m.get("hg"), m.get("ag")
        home, away = str(m.get("home") or ""), str(m.get("away") or "")
        if hg is None or ag is None or not home or not away:
            continue
        out.append((str(m.get("utc")), home, away, int(hg), int(ag)))
    return sorted(out, key=lambda r: r[0])
