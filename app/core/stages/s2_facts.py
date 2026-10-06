"""🔴🔴 **v6 s2 — 구조 사실.** `MatchRef → Facts`(§5).

지시서 §5 s2: *"기존 어댑터 호출 → `adapt.py` 에서 `Facts` 로. 어댑터마다 다른
모양(`players` dict/list 등)은 **여기서만** 흡수. `match_format` 은 대회명·라운드
정보로 정하고 모르면 `unknown`."*

⚠️ 없으면 `None`·빈 것이다 — **지어내지 않는다**(§3).
"""
from __future__ import annotations

from typing import Any

from app.core import adapt
from app.core.schema import XI, DropReason, Facts, MatchRef
from app.core.state import RunState


async def run(ref: MatchRef, *, state: RunState, net: Any = None,
              search: Any = None) -> Facts:
    """🔴 그 경기의 구조 사실. ⚠️ 실패해도 **빈 `Facts`** 를 돌려준다(§5)."""
    box: dict[str, Any] = {}
    xi: dict[str, XI] = {}
    sources: list[str] = []
    try:
        got = await _depth(ref, net=net, search=search)
    except Exception as exc:                                # noqa: BLE001
        state.drop("s2", DropReason.NO_DOC, f"깊이 소스가 터졌다: {exc!r}")
        got = []
    for fact in got:
        qid = str(getattr(fact, "question_id", "") or "")
        val = getattr(fact, "value", None)
        if not isinstance(val, dict):
            continue
        tail = qid.rpartition(":")[2]
        url = str(getattr(fact, "source", "") or "")
        if url:
            sources.append(url)
        if tail == "standings":
            box.setdefault("standings", {}).update(val)
        elif tail == "form":
            team = str(getattr(fact, "team", "") or "")
            if team:
                box.setdefault("recent", {})[team] = dict(val)
        elif tail == "h2h":
            box.setdefault("h2h", {}).update(val)
        elif tail in ("lineup", "xi") and val.get("team"):
            key = _key_of(ref, str(val.get("team")))
            if key:
                xi[key] = adapt.xi_of(key, val, source_url=url)
    # 🔴 **형식은 표가 정한다**(대회명·라운드) — 모르면 `unknown`(지어내지 않는다)
    fmt, why = _format_of(ref)
    state.note(f"s2 형식 — {why}")
    return adapt.facts_of(box, xi=xi, match_format=fmt,
                          sources=sorted(set(sources)))


def _key_of(ref: MatchRef, name: str) -> str:
    """🔴 이름 → 그 경기의 **두 열쇠 중 하나**. ⚠️ 못 가리면 빈 글자."""
    from app import teamref
    got, _why = teamref.key_of(name)
    if got in (ref.home, ref.away):
        return str(got)
    low = name.strip().lower()
    if low and low == ref.home_name.strip().lower():
        return ref.home
    if low and low == ref.away_name.strip().lower():
        return ref.away
    return ""


def _format_of(ref: MatchRef) -> tuple[str, str]:
    """🔴 경기 형식 — `scenarios.match_format` 표가 든다(사본 금지)."""
    from app import scenarios
    got, why = scenarios.match_format(round_note="",
                                      competition=ref.competition)
    return str(got), str(why)


async def _depth(ref: MatchRef, *, net: Any, search: Any) -> list:
    """🔴 깊이 소스 — `ext_id` 가 가리키는 공식 경로. ⚠️ 없으면 빈 목록."""
    from app import cells, matchkey
    from app.collect import fotmob
    src = matchkey.source_of(ref.id)
    if src != "fotmob" or net is None:
        return []
    url = f"{fotmob.BASE}/match/{matchkey.id_of(ref.id)}"
    got = await net.get(url)
    if not getattr(got, "ok", False):
        return []
    out: list = []
    for name in (ref.home_name, ref.away_name):
        q = cells.Question(cells.Q_LINEUP, ref.id, team=name,
                           league=ref.competition,
                           deadline=ref.kickoff_utc)
        out += list(fotmob.parse_context(got, q) or [])
    return out
