"""🔴🔴 **"코드는 알고 모델은 모르는 칸"을 0개로** — 사용자 지시 2026-10-05.

> `done` 스키마 **전수 점검**. 코드가 변수 하나를 받아들이는 데 필요한 **모든
> 칸**(team 열쇠, type, direction_hint, claim, quote, url, published_at, lang,
> tier 등)을 표로 뽑고, 각 칸이 **(1) 프롬프트에 설명돼 있는지 (2) 스키마
> `required` 에 있는지 (3) enum이면 enum으로 막혀 있는지** 세 열로 보고해라.
> 빠진 칸은 이번 재실행 결과와 상관없이 **지금 채우고 계약을 건다.**
> **"코드는 알고 모델은 모르는 칸"을 0개로 만드는 게 목적이다.**

══════════════════════════════════════════════════════════════════
🔴 왜 — 같은 병이 **세 번** 났다
══════════════════════════════════════════════════════════════════

```
§1-1   본문을 안 넘겨 인용 대조 실패          12줄 → 0개
카탈로그 유형 목록을 안 말해 겹침 0개          18개가 전부 카탈로그 밖
hint   `direction_hint` 목록을 안 말해        10·16줄 → 0개
```

🔴 전부 **코드가 아는 것을 모델에게 안 알려 주고 그 답을 버린** 꼴이다.
⚠️ 그래서 목록을 손으로 세지 않는다 — **코드에서 뽑아** 비교한다(사본 금지).
"""
from __future__ import annotations

import dataclasses
import inspect
import re

import pytest


def _needed() -> tuple[str, ...]:
    """🔴 코드가 **읽는** 칸 — `_vars_from` 의 `row.get("…")` 에서 뽑는다.

    ⚠️ 손으로 적지 않는다 — 코드가 바뀌면 이 목록이 **따라온다**.
    """
    from app import agentloop
    src = inspect.getsource(agentloop)
    i = src.index("def _vars_from")
    return tuple(sorted(set(re.findall(
        r'row\.get\("([a-z_]+)"', src[i:i + 2600]))))


def _schema_vars() -> dict:
    """🔴 `done` 스키마의 **변수 한 줄** 정의."""
    from app import agentloop

    def walk(o):
        if isinstance(o, dict):
            if o.get("type") == "object" and "direction_hint" in (
                    o.get("properties") or {}):
                return o
            for v in o.values():
                got = walk(v)
                if got:
                    return got
        if isinstance(o, list):
            for v in o:
                got = walk(v)
                if got:
                    return got
        return None
    return walk(agentloop.output_schema()) or {}


#: 🔴 그 칸을 프롬프트가 **무슨 말로** 설명하나. ⚠️ 칸 이름 **또는** 그 뜻이다
#   (프롬프트는 한국어로 *"작동 설명 1문장"* 이라고 적는다 — `claim` 이 아니다).
MEANS: dict = {
    "id": ("변수마다", "번호"), "type": ("유형",), "team": ("team",),
    "direction_hint": ("direction_hint",), "claim": ("작동 설명", "1문장"),
    "quote": ("인용",), "url": ("출처 URL", "URL"),
    "published_at": ("발행 시각",), "lang": ("lang", "언어"),
    "conflict": ("conflict", "충돌"), "reverified": ("재검증", "reverified"),
}


def test_audit_코드가_읽는_칸이_스키마에_다_있다():
    """🔴🔴 **빠진 칸 0개** — 코드가 읽는데 스키마에 없으면 모델이 못 낸다."""
    props = set((_schema_vars().get("properties") or {}))
    missing = [k for k in _needed() if k not in props]
    assert not missing, (
        f"🔴 코드가 읽는데 스키마에 **없는 칸**: {missing} — 모델은 그 칸을 "
        f"모르고, 코드는 그것이 없다고 변수를 버린다")


def test_audit_전부_required_다():
    """🔴 하나라도 빠지면 모델이 **안 내도 되는** 칸이 된다."""
    box = _schema_vars()
    req = set(box.get("required") or [])
    missing = [k for k in _needed() if k not in req]
    assert not missing, f"🔴 `required` 에 없는 칸: {missing}"


@pytest.mark.parametrize("field", sorted(_needed()))
def test_audit_프롬프트가_그_칸을_설명한다(field):
    """🔴🔴 **모델이 모르면 쓸 수 없다** — 세 번 다친 그 자리다."""
    from app import agentloop
    said = agentloop.system_prompt()
    words = MEANS.get(field, (field,))
    assert any(w in said for w in words), (
        f"🔴 프롬프트가 `{field}` 를 **설명하지 않는다**(찾은 말: {words}) — "
        f"코드는 그 칸을 읽는데 모델은 모른다")


def test_audit_값이_정해진_칸은_enum_으로_막는다():
    """🔴 설명만으로는 모자라다 — **스키마가 강제**해야 한다(세 번의 교훈).

    ⚠️ 어느 칸이 *"값이 정해진 칸"* 인가는 **코드가 검사하는 칸**이다 —
       `agentschema` 가 값을 보고 터뜨리는 칸(사본 금지: 그 목록을 여기 안 적는다).
    """
    from app import agentloop, agentschema
    src = inspect.getsource(agentschema)
    props = _schema_vars().get("properties") or {}
    # 🔴 `agentschema` 가 **검사하는** 칸을 찾는다(`not in <목록>` 꼴)
    checked = set(re.findall(r"self\.([a-z_]+) not in ([A-Z_]+)", src))
    assert checked, "🔴 값 검사가 **하나도 없다** — 그러면 막을 것도 없다"
    for field, listname in checked:
        got = props.get(field) or {}
        assert got.get("enum"), (
            f"🔴 `{field}` 는 코드가 **값을 검사하는 칸**(`{listname}`)인데 "
            f"스키마가 **enum 으로 안 막는다** — 모델이 아무 값이나 쓰고 그 "
            f"변수는 전부 버려진다(실측 2026-10-05: 10·16줄 → 0개)")
        want = set(getattr(agentschema, listname, ()) or ())
        assert set(got["enum"]) == want, (field, got["enum"], sorted(want))


def test_audit_tier_는_모델이_내지_않는다():
    """🔴 `tier`(도메인 등급)는 **코드가 정한다** — 모델이 내면 속일 수 있다.

    ⚠️ 그래서 스키마에 **없어야** 한다. 🔴 검증층은 `url` 로
       `domains.verdict` 를 불러 등급을 **스스로** 매긴다(§4-3).
    """
    props = set((_schema_vars().get("properties") or {}))
    assert "tier" not in props, (
        "🔴 모델이 `tier` 를 낸다 — 팁 사이트를 `official` 이라 적을 수 있다. "
        "등급은 `url` 로 코드가 정한다(§4-3)")
    from app import verifylayer
    body = inspect.getsource(verifylayer.verify_one)
    assert "domains" in body, "🔴 검증층이 등급을 **스스로 안 매긴다**"


def test_audit_AgentVar_칸과_스키마가_같다():
    """🔴 셋이 **한 목록**이어야 한다 — 하나가 늘면 나머지도 늘어야 한다."""
    from app import agentschema
    fields = {f.name for f in dataclasses.fields(agentschema.AgentVar)}
    props = set((_schema_vars().get("properties") or {}))
    assert fields == props, (
        f"🔴 `AgentVar` 와 스키마가 **어긋났다**: "
        f"AgentVar 만 {sorted(fields - props)} · 스키마만 {sorted(props - fields)}")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **돌연변이가 뚫은 둘을 메운다** (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  A01 `lang` 설명을 뺀다        ⚠️ **통과** — 치환이 다른 `lang` 글자를 남겼다
#  A03 `type` enum 을 뺀다       ⚠️ **통과** — `type` 은 코드가 **값을 검사하지
#                                 않아서** "값이 정해진 칸"으로 안 세어졌다
#
# 🔴 A03 이 더 중요하다: 카탈로그 밖 유형이 오면 §4 유형표의 방향·hardness
#    규칙이 **하나도 안 걸린다**(실측 2026-10-05: 겹침 0개). ⚠️ 그런데 코드는
#    그것을 **버리지도 않았다** — 조용히 통과시켰다.


def test_audit_A03_type_도_enum_으로_막힌다():
    """🔴🔴 **A03** — `type` enum 을 빼도 빨개져야 한다.

    ⚠️ 종전 계약은 *"코드가 값을 검사하는 칸"* 만 enum 을 요구했고, `type` 은
       그 검사가 **없어서** 빠져나갔다. 🔴 `type` 은 **카탈로그**가 정하는
       칸이다 — 그 목록이 enum 이어야 한다.
    """
    from app import agentloop
    props = _schema_vars().get("properties") or {}
    got = (props.get("type") or {}).get("enum")
    assert got, (
        "🔴 `type` 이 **enum 으로 안 막힌다** — 카탈로그 밖 이름이 오면 §4 "
        "유형표의 방향·hardness 규칙이 **하나도 안 걸린다**(실측: 겹침 0개)")
    assert set(got) == set(agentloop._catalog()), (
        sorted(set(got) ^ set(agentloop._catalog())))


def test_audit_A03_카탈로그_밖_유형은_버린다():
    """🔴 enum 으로 막고 **그래도 오면 버린다**(모델이 스키마를 어길 수 있다).

    ⚠️ 조용히 통과시키면 그 변수가 **규칙 없이** 판정층에 들어간다.
    """
    import datetime as dt

    from app import agentloop
    UTC = dt.timezone.utc
    inp = agentloop.AgentInput(
        match_key="f:1", home="team:1", away="team:2",
        home_names=("A",), away_names=("B",), competition="C",
        sport="soccer", kickoff_utc=dt.datetime(2026, 10, 4, tzinfo=UTC),
        venue="V", langs=("en",))
    box = {"variables": [{"id": "v1", "type": "form", "team": "team:1",
                          "direction_hint": "home", "claim": "x",
                          "quote": "y", "url": "https://x/a",
                          "published_at": "2026-10-04T06:00:00Z",
                          "lang": "en", "conflict": False,
                          "reverified": True}]}
    got, why = agentloop.parse_args(box, inp=inp)
    assert got == [], (
        f"🔴 카탈로그 밖 유형 `form` 이 **통과했다** — §4 규칙이 안 걸린다: "
        f"{why}")
    assert "type" in why or "카탈로그" in why, why


def test_audit_A01_lang_설명이_그_자리에_있다():
    """🔴 **A01** — 설명 줄을 지워도 빨개져야 한다.

    ⚠️ 종전 계약은 프롬프트 **전체**에서 `lang` 글자를 찾았다 — 다른 자리의
       `lang`(예: `"lang": src.lang` 같은 보기)이 그것을 메웠다.
    🔴 그래서 **그 설명이 말하는 것**을 본다: 두 글자 코드의 **보기**가 있나.
    """
    from app import agentloop
    said = agentloop.system_prompt()
    assert "`lang`" in said and "`en`" in said, (
        "🔴 `lang` 에 **무엇을 넣으라는** 설명이 없다 — 코드는 그 값을 쓴다"
        "(현지어 판정·검색 언어)")
    # 🔴 그리고 **기사의 언어**임을 말해야 한다(질의 언어가 아니다)
    assert "기사의 언어" in said, said[-400:]
