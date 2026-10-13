"""🔴🔴 **§2-1 시즌 표기**(통합 지시서 2026-10-13 밤).

> 모든 경기에 `season_id` · 팀별 **"이번 시즌 리그 경기 수"** 를 `as_of` 기준으로.

🔴 달력 규칙의 원본은 **`config/season_rules.yaml` 하나**다 — 코드에 달력을 박지
   않는다(리그가 바꾸면 그 파일만 고친다). ⚠️ 표에 없는 리그는 **빈 글자 + 사유**다
   (연도를 지어내지 않는다 · #4).
🔴 **SE1** — `season_id` 없는 경기가 폼·Elo 계산에 들어가면 **실패**다. 그 자리를
   막는 문이 `require` 이고, 부르는 쪽(§3 입력 어댑터)이 그것을 지난다.
🔴 **L1** — 경기 수는 `as_of` **이전**만 센다(문은 `fotmob.before_as_of` 하나).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: 🔴 규칙 표가 사는 곳(원본 하나)
PATH = Path(__file__).resolve().parents[2] / "config/season_rules.yaml"


@lru_cache(maxsize=1)
def rules() -> dict:
    """🔴 `{리그: [{from, kind, start_month}]}` — 없으면 **빈 표**다."""
    import yaml
    if not PATH.exists():
        logger.error("[season] 규칙 표가 없다: %s", PATH)
        return {}
    got = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    return {str(k): list(v or []) for k, v in dict(got).items()}


def _when(when: object) -> date | None:
    if isinstance(when, datetime):
        return when.date()
    if isinstance(when, date):
        return when
    said = str(when or "")[:10]
    try:
        return date.fromisoformat(said)
    except ValueError:
        return None


def id_of(*, league: str, when: object) -> tuple[str, str]:
    """🔴🔴 그 경기의 `season_id` 와 사유. 모르면 `("", 🔴 사유)`."""
    at = _when(when)
    if at is None:
        return "", f"🔴 날짜를 못 읽었다({when!r})"
    rows = rules().get(str(league or ""))
    if not rows:
        return "", (f"🔴 `{league}` 은 **달력 규칙 표에 없다**"
                    f"(`config/season_rules.yaml`) — 시즌을 지어내지 않는다")
    said = [r for r in rows
            if str(dict(r).get("from") or "9999-12") <= at.strftime("%Y-%m")]
    if not said:
        return "", (f"🔴 `{league}` 의 규칙이 {at.isoformat()} 보다 **뒤에서만** "
                    f"시작한다(표를 고쳐야 한다)")
    one = dict(said[-1])
    kind = str(one.get("kind") or "")
    if kind == "calendar":
        return str(at.year), f"단일 연도(calendar · 규칙 {one.get('from')})"
    if kind == "autumn_spring":
        start = int(one.get("start_month") or 7)
        year = at.year if at.month >= start else at.year - 1
        return (f"{year}/{(year + 1) % 100:02d}",
                f"추춘제(start_month {start} · 규칙 {one.get('from')})")
    return "", f"🔴 `{league}` 규칙의 `kind` 를 모른다({kind!r})"


def tag(rows: list[dict], *, league_key: str = "league",
        when_key: str = "utc") -> list[dict]:
    """🔴 줄마다 `season_id`·`season_why` 를 붙인다(모르면 빈 글자)."""
    out: list[dict] = []
    for one in list(rows or []):
        said = dict(one)
        got, why = id_of(league=str(said.get(league_key) or ""),
                         when=said.get(when_key))
        said["season_id"] = got
        said["season_why"] = why
        out.append(said)
    return out


def require(rows: list[dict]) -> str:
    """🔴🔴 **SE1** — `season_id` 없는 줄이 있으면 **사유**(없으면 빈 글자).

    ⚠️ 조용히 넘기지 않는다 — 부르는 쪽이 이 글자를 보고 **멈추거나 적는다**.
    """
    bad = [one for one in list(rows or [])
           if not str(dict(one).get("season_id") or "").strip()]
    if not bad:
        return ""
    said = {str(dict(x).get("league") or "?") for x in bad}
    return (f"🔴 **SE1 — `season_id` 없는 경기 {len(bad)}건**"
            f"(리그 {sorted(said)}) · 폼·Elo 에 넣지 않는다")


def games_of(rows: list[dict], *, team: str, as_of, league: str = "",
             ) -> tuple[int, str]:
    """🔴🔴 그 팀의 **이번 시즌 리그 경기 수**(`as_of` 이전). `(수, 사유)`.

    🔴 "이번 시즌"은 `as_of` 의 `season_id` 다 — 경기 목록의 시즌과 **그것**을 맞춘다.
    """
    from app.collect import fotmob as fm
    want, why = id_of(league=str(league or ""), when=as_of)
    if not want:
        return 0, why
    said = fm.before_as_of(tag(list(rows or [])), as_of=as_of, key="utc")
    got = [r for r in said
           if str(r.get("season_id") or "") == want
           and str(team) in (str(r.get("home") or ""), str(r.get("away") or ""))]
    return len(got), (f"이번 시즌 `{want}` 리그 **{len(got)}경기**"
                      f"(as-of 이전 · {why})")
