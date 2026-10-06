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
    """🔴🔴 **공식 깊이 소스** — 어느 어댑터가 아나는 `ingest.context_of` 가 정한다.

    ⚠️ 주소를 여기 적지 않는다(§2 · 사본 금지) — 종목마다 다른 경로를 손으로 적으면
       리그가 늘 때 한 발 늦는다. 🔴 `ingest.context_of(리그, ext_id)` 하나가 그
       라우팅의 원본이다.
    ⚠️ **어댑터가 깊이를 안 주는 리그가 있다**(KBO 는 `sources_context` 가 빈
       목록이다 — 그 API 가 예고 선발·라인업을 안 준다). 그때는 빈 목록이 **정직한
       상태**다(있는 척하는 함수를 두지 않는다 · CLAUDE.md #2).
    """
    from app.collect import ingest
    if net is None:
        return []
    fn = ingest.context_of(ref.competition, ref.id)
    if not callable(fn):
        return []
    try:
        raw = fn(ref.id)
    except Exception:                                       # noqa: BLE001
        return []
    # 🔴 **부품이 무엇을 돌려줄지 타입으로 모른다** — `Iterable` 인지 확인하고 센다.
    #    ⚠️ 모르는 것을 `list()` 에 넣으면 strict 가 맞게 막는다(그 자리가 ① 결함의
    #       뿌리다 — "받는 쪽이 꼴을 믿었다").
    srcs: list[Any] = list(raw) if isinstance(raw, (list, tuple)) else []
    out: list = []
    for src in srcs:
        url = str(getattr(src, "url", "") or "")
        parse = getattr(src, "parse", None)
        if not (url and callable(parse)):
            continue
        got = await net.get(url)
        if not getattr(got, "ok", False):
            continue
        for name in (ref.home_name, ref.away_name):
            # 🔴 `cells` 를 보는 곳은 `adapt` 하나다(⑤ 정적 검사)
            q = adapt.lineup_question(ref, name)
            try:
                said = parse(got, q)
            except Exception:                               # noqa: BLE001
                continue
            if isinstance(said, (list, tuple)):
                out += list(said)
    return out
