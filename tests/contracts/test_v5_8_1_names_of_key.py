"""🔴🔴 **이름표가 든 이름을 흘리지 않는다** — §8-1 · §4-1.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (고치고도 **효과가 0 이었다**)
══════════════════════════════════════════════════════════════════

`_SHAPES["mlb"]` 를 고쳐 공식 API 의 짧은 이름을 받게 했고, 이름표가 그것을
**실제로 들었다**:

```
reg.teams["team:000338"].all_names()
  → ['Milwaukee Brewers', 'mlb:158', 'Brewers', '브루어스', '밀워키 브루어스']
teamref.key_of("Brewers") → team:000338 ✅
```

🔴 그런데 **쓰는 곳에는 안 닿았다**:

```
_names_of_key("team:000338") → ['Milwaukee Brewers', '밀워키 브루어스']
                                🔴 'Brewers' 가 **없다**
→ 거부된 질의 7건 중 **0건이 섰다**
```

⚠️ 까닭: `_names_of_key` 가 `label_of(k, lang)` 로 **언어마다 대표 이름 하나**만
   꺼냈다. 🔴 이름표가 `names['en']` 에 세 개를 들고 있는데 **첫 개만** 썼다.

🔴 **이것이 이 저장소가 반복해 다친 자리다**(CLAUDE.md #2) — 판정 함수는
   고쳤는데 **그것을 쓰는 곳**은 그대로였다. 돌연변이 22건이 같은 병으로
   통과했다. 그래서 이 계약은 함수가 아니라 **효과**를 잰다.
"""
from __future__ import annotations

import pytest


def test_v5_8_1_이름표가_든_이름을_다_돌려준다():
    """🔴 `all_names` 에 있는 것이 `_names_of_key` 에 **다** 있어야 한다."""
    from app import teamref
    from app.analyze import _names_of_key
    reg = teamref.registry()
    bad: list[str] = []
    for key, ref in list(reg.teams.items())[:400]:
        got = set(_names_of_key(key))
        for name in ref.all_names():
            # 🔴 외부 id(`mlb:158`)는 **이름이 아니다** — 그것만 빼고 다 있어야 한다
            if teamref.is_code(name) or ":" in name:
                continue
            if name not in got:
                bad.append(f"{key}: `{name}` 가 빠졌다(돌려준 것 {sorted(got)})")
    assert not bad, (
        "🔴🔴 **이름표가 든 이름을 흘린다** — 에이전트·문지기가 그 이름을 "
        "못 본다:\n  " + "\n  ".join(bad[:6]))


def test_v5_8_1_외부_id_는_이름이_아니다():
    """🔴 `mlb:158`·`fdorg:103` 을 **검색어로 쓰면** 쓰레기가 돌아온다."""
    from app.analyze import _names_of_key
    from app import teamref
    reg = teamref.registry()
    for key in list(reg.teams)[:400]:
        for name in _names_of_key(key):
            assert ":" not in name, (
                f"🔴 `{key}` 가 **외부 id** `{name}` 를 이름으로 돌려준다 — "
                f"검색어가 되면 아무 데도 없는 글자다")


def test_v5_8_1_영어가_먼저다():
    """🔴 §4-2 — 검색 순서가 그 순서다. ⚠️ 첫 이름이 **대표 영문명**이어야 한다."""
    from app import teamref
    from app.analyze import _names_of_key
    key, _ = teamref.key_of("Milwaukee Brewers")
    if not key:
        pytest.skip("이름표에 MLB 명단이 없다 — 캐시를 받아야 한다")
    got = _names_of_key(key)
    assert got and got[0] == teamref.label_of(key, "en"), got


@pytest.mark.parametrize("query,want", [
    # 🔴 **게이트 2 에서 실제로 거부된 질의들**이다(실측 2026-10-04 · g2_mlb.log)
    ("Brewers Padres NLDS Game 1 2026 MLB.com recap", True),
    ("Brewers win NLDS Game 1 Padres October 3 2026", True),
    ("Padres win NLDS Game 1 Brewers October 3 2026", True),
    # ══════════════════════════════════════════════════════════════
    # ⚠️ 아래 둘은 **거부가 맞다** — 처음 `True` 로 적었고 그것이 틀렸다
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 §4-1 이 세는 것은 **다섯 요소**(팀·상대·대회·종목 낱말·날짜)다.
    #     선수 이름·`rotation`·`Game 1` 은 그 다섯에 **없다** — 좁히는 느낌이
    #     들어도 규칙이 세는 칸이 아니다.
    #  ⚠️ 내 기대를 맞추려고 문지기를 느슨하게 하지 않는다 — 그러면 §4-1 이
    #     막으려던 쓰레기 86% 가 돌아온다(실측 2026-10-04).
    #
    #  `San Diego Padres 2026 rotation …`  → 팀 하나 · 대회 없음 · 날짜 없음
    ("San Diego Padres 2026 rotation starters Robert Suarez Michael King",
     False),
    # ══════════════════════════════════════════════════════════════
    # 🔴 **이것은 이제 선다** — 결정 ⑤ (2026-10-04)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 처음 `False` 로 적었다: *"팀 하나 + 날짜(상대·대회 없음)"*.
    #  🔴 **그 판단이 틀렸다** — `NLDS` 가 **대회**다. 결정 ⑤가 라운드 이름을
    #     설정 데이터로 넣었고, 이제 team + competition + when = **3** 이다.
    #  ✅ 그것이 ⑤가 노린 바로 그 효과다(게이트2 2판에서 이 질의가 거부됐다).
    ("Brewers NLDS Game 1 win Oct 3 2026 Jacob Misiorowski", True),
])
def test_v5_8_1_거부됐던_질의가_선다(query, want):
    """🔴🔴 **효과를 잰다** — 함수를 고쳐도 쓰는 곳에서 안 변하면 안 고친 것이다.

    ⚠️ 실측 2026-10-04: 이름표를 고친 **뒤에도 7건 중 0건**이 섰다.
    """
    from app import agentloop, querygate, teamref
    from app.analyze import _names_of_key
    hk, _ = teamref.key_of("Milwaukee Brewers")
    ak, _ = teamref.key_of("San Diego Padres")
    if not (hk and ak):
        pytest.skip("이름표에 MLB 명단이 없다 — 캐시를 받아야 한다")

    class _Inp:
        home_names = tuple(_names_of_key(hk))
        away_names = tuple(_names_of_key(ak))
        competition = "MLB"

    class _Holder:
        inp = _Inp()

    parts = agentloop.Tools._parts(_Holder(), query)
    n, got = querygate.count_parts(query, parts=parts)
    ok = n >= querygate.MIN_PARTS
    assert ok is want, (
        f"🔴 `{query[:52]}` → 요소 {n}개({got}) · 기대 "
        f"{'통과' if want else '거부'} · 선언 {parts}")
