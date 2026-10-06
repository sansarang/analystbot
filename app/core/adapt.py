"""🔴🔴 **v6 §2 — 기존 부품 출력 → `schema` 타입. 변환은 여기서만.**

지시서 §2: *"기존 부품은 `import` 해서 쓰되, 기존 부품이 dict 를 돌려주면
`app/core/adapt.py` 의 변환 함수 **한 곳**에서 schema 타입으로 바꾼다(부품 내부는
건드리지 않는다)."*

══════════════════════════════════════════════════════════════════
🔴 왜 **한 곳**인가
══════════════════════════════════════════════════════════════════

⚠️ 실사고 2026-10-04~06(결함 ①): 어댑터마다 `players` 가 dict 이거나 list 였고,
   `Game` 을 dict 로 아는 호출부가 있었고, 반증 폐기를 dict 로 읽어 **카드가
   죽었다**. 🔴 변환이 여러 곳에 있으면 한 곳이 칸을 빠뜨려도 안 보인다.
🔴 그래서 **이 파일이 유일한 통로**다 — `app/core/` 의 단계 함수는 dict 를 보지
   않는다(§7 정적 검사가 단계 서명에서 `dict`·`Any`·`tuple` 반환을 막는다).

⚠️ 지금은 **골격**이다(§8 1단계) — 2단계에서 s1·s2·s3 이 쓰는 변환을 채운다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.schema import XI, Doc, Facts, MatchRef


def _utc(v: object) -> datetime | None:
    """🔴 tz 있는 UTC 만 — 없으면 `None`(절대규칙 2 · §8-7).

    ⚠️ naive 를 조용히 UTC 로 가정하면 그 가정이 틀려도 아무 데도 안 적힌다.
    🔴 **글자도 받는다** — `readtext.extract` 는 발행일을 **문자열**로 돌려준다
       (`"2026-10-05"`·`"2026-10-05T09:00:00+00:00"`). ⚠️ 그것을 `datetime` 만
       받게 두면 날짜가 **조용히 사라진다**(실측: 이 변환 하나로 `Doc` 전부가
       `date_source="none"` 이 됐다).
    🔴 **날짜만 있으면 그 날 00:00 UTC** 로 본다 — 그 가정을 여기 적어 둔다
       (기사 발행일은 날짜까지만 아는 것이 흔하고, §5-3 창은 일 단위다).
    """
    from app import timefmt
    if isinstance(v, datetime):
        got = timefmt.aware(v)
        return got.astimezone(timezone.utc) if got is not None else None
    said = str(v or "").strip()
    if not said:
        return None
    try:
        parsed = datetime.fromisoformat(said.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # 🔴 날짜만 온 것이다 — UTC 자정으로 못 박고 그 사실을 여기 적는다
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _text(v: object) -> str:
    """🔴 사람이 읽을 이름만 꺼낸다 — **사전을 글자로 만들지 않는다.**

    ⚠️ 실사고 2026-10-02: fotmob `infoBox.Stadium` 이 사전이라 `str()` 로 감싸니
       `{'name': …, 'lat': …}` 가 그대로 `games.venue` 에 들어갔다.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("name", "leagueName", "shortName", "text"):
            got = v.get(k)
            if isinstance(got, str) and got.strip():
                return got.strip()
        return ""
    if isinstance(v, (list, tuple)):
        for x in v:
            got = _text(x)
            if got:
                return got
    return str(v).strip()


def names_of(raw: object) -> list[str]:
    """🔴 선수 이름들 — 어댑터가 **dict 든 list 든** 같은 꼴로 돌려준다.

    ⚠️ 실사고: NPB 가 `players` 를 dict 로 주고 fotmob 은 list 로 줬다 —
       그 차이를 **여기서만** 흡수한다.
    """
    if isinstance(raw, dict):
        return [n for n in (_text(v) for v in raw.values()) if n]
    if isinstance(raw, (list, tuple)):
        return [n for n in (_text(v) for v in raw) if n]
    got = _text(raw)
    return [got] if got else []


def xi_of(team_key: str, raw: object, *, source_url: str = "") -> XI:
    """🔴 어댑터의 XI 모양 → `schema.XI`. ⚠️ 모르면 `state="none"`(지어내지 않는다)."""
    box = dict(raw or {}) if isinstance(raw, dict) else {}
    players = names_of(box.get("players") or box.get("starters"))
    confirmed = bool(box.get("confirmed"))
    state = "confirmed" if confirmed else ("predicted" if players else "none")
    return XI(team=team_key, state=state,
              formation=(_text(box.get("formation")) or None),
              players=players, bench=names_of(box.get("bench") or box.get("subs")),
              source_url=str(source_url or box.get("source_url") or ""))


def facts_of(raw: dict, *, xi: dict[str, XI] | None = None,
             match_format: str = "unknown",
             sources: list[str] | None = None) -> Facts:
    """🔴 구조 사실 묶음 → `schema.Facts`. ⚠️ 없는 칸은 **빈 것**으로 둔다."""
    box = dict(raw or {})
    fmt = str(match_format or "unknown")
    allowed = set(Facts.model_fields["match_format"].annotation.__args__)  # type: ignore[union-attr]
    return Facts(
        standings=dict(box.get("standings") or {}),
        recent=dict(box.get("recent") or {}),
        h2h=dict(box.get("h2h") or {}),
        xi=dict(xi or {}),
        match_format=(fmt if fmt in allowed else "unknown"),  # type: ignore[arg-type]
        extra_time=box.get("extra_time"),
        sources=[str(x) for x in (sources or box.get("sources") or [])])


def doc_of(*, doc_id: str, url: str, body: str, subtask: str,
           title: str = "", lang: str = "en", tier: str = "aggregator",
           published_at: object = None, date_source: str = "none") -> Doc:
    """🔴 받아 둔 문서 → `schema.Doc`. **본문과 날짜가 한 몸**이다(§3).

    ⚠️ 날짜가 없으면 `date_source="none"` 이고, 불변식 9 가 *"그 Doc 을 근거로 한
       변수가 없다"* 를 센다 — 즉 **빈칸이 조용히 통과하지 않는다.**
    """
    when = _utc(published_at)
    allowed_src = set(Doc.model_fields["date_source"].annotation.__args__)  # type: ignore[union-attr]
    allowed_tier = set(Doc.model_fields["tier"].annotation.__args__)  # type: ignore[union-attr]
    src = str(date_source or "none")
    return Doc(
        id=str(doc_id), url=str(url),
        domain=(str(url).split("/")[2] if str(url).count("/") >= 2 else ""),
        tier=(tier if tier in allowed_tier else "aggregator"),  # type: ignore[arg-type]
        lang=str(lang or "en"), title=str(title or ""), body=str(body or ""),
        published_at=when,
        # 🔴 날짜가 없으면 출처도 `none` 이다 — 둘이 어긋나지 않게 **여기서** 맞춘다
        date_source=((src if src in allowed_src else "none")  # type: ignore[arg-type]
                     if when is not None else "none"),
        subtask=str(subtask))  # type: ignore[arg-type]


def ref_of(raw: Any, *, competition_short: str, openworld: bool = False
           ) -> MatchRef | None:
    """🔴 기존 `matchref.MatchRef` → `schema.MatchRef`. 못 만들면 `None`.

    ⚠️ 킥오프가 tz 없으면 **만들지 않는다** — 그 값으로 창을 자르면 경기를 잃는다.
    """
    kick = _utc(getattr(raw, "kickoff_utc", None))
    home, away = str(getattr(raw, "home_id", "") or ""), \
        str(getattr(raw, "away_id", "") or "")
    if kick is None or not (home and away):
        return None
    sport = str(getattr(raw, "sport", "") or "soccer")
    allowed = set(MatchRef.model_fields["sport"].annotation.__args__)  # type: ignore[union-attr]
    return MatchRef(
        id=str(getattr(raw, "key", "") or ""),
        sport=(sport if sport in allowed else "soccer"),  # type: ignore[arg-type]
        competition=str(getattr(raw, "competition", "") or ""),
        competition_short=str(competition_short or ""),
        home=home, away=away,
        home_name=str(getattr(raw, "home", "") or ""),
        away_name=str(getattr(raw, "away", "") or ""),
        kickoff_utc=kick, venue=str(getattr(raw, "venue", "") or ""),
        langs=[str(x) for x in (getattr(raw, "langs", None) or ())],
        openworld=bool(openworld))
