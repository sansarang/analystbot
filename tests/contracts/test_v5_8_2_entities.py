"""🔴🔴 **v5 §8-2 — 엔티티 표.** 감독 미상이 **탈락 사유가 되지 않는다**. [#11]

§8-2 원문:

> `entities.yaml` 에 팀마다 `coach`(이름·부임일·출처), `captain`, `home_venue`,
> `country`, `league`, `langs` 를 둔다. 감독 이름은 공식 명단에서 채우고,
> 비어 있으면 에이전트가 첫 검색에서 채워 `learned_from:<경기ID>` 로 적는다.
> **감독 이름 미상이 변수 탈락 사유가 되지 않는다.** [#11]

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04(밀워키 vs 샌디에이고)
══════════════════════════════════════════════════════════════════

```
세포 감독:Milwaukee Brewers: `Milwaukee Brewers` 의 감독을 모른다 — 선언에도
                              자료에도 없다
세포 감독:San Diego Padres:  같다
```
⚠️ 그 줄이 카드에 두 번 떴고, `coach` 를 자리표로 쓰는 카탈로그 질의(사다리 ③
   *"감독명 + 회견"*)가 **통째로 안 돌았다.** 🔴 감독 이름 하나가 없어서 그
   유형의 변수가 영영 0 이 된다 — §8-2 가 그것을 막는다.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 🔴 §8-2 가 이름 댄 **여섯 칸**
WANT = ("coach", "captain", "home_venue", "country", "league", "langs")


def test_v5_8_2_선언에_여섯_칸_규격이_있다():
    """🔴 칸 이름을 **한 곳**에 적어 둔다 — 팀마다 손으로 지키면 갈린다."""
    from app.entities import FIELDS
    assert set(WANT) <= set(FIELDS), sorted(FIELDS)


def test_v5_8_2_coach가_이름_부임일_출처를_든다():
    """🔴 §8-2 — `coach`(**이름·부임일·출처**). ⚠️ 이름만 있으면 낡은 것을 못 가린다.

    실측 2026-10-03: `entities.yaml` 의 `coach: Néstor Lorenzo` 는 **문자열**이라
    *"언제부터"* 와 *"어디서 왔나"* 가 없었다. 감독은 바뀌는데 그 사실을 못 센다.
    """
    from app.entities import coach_row
    got = coach_row("Jamaica")
    assert got.get("name"), got
    for k in ("name", "since", "source"):
        assert k in got, (k, sorted(got))


def test_v5_8_2_문자열_coach도_읽힌다():
    """⚠️ 기존 선언 열여섯 팀이 `coach: 이름` **문자열**이다 — 깨뜨리지 않는다.

    🔴 손으로 전부 고치지 않는다(사본 금지) — 읽는 쪽이 두 꼴을 받는다.
    """
    from app import rules
    from app.entities import coach_row
    raw = rules._load("config/entities.yaml")["teams"]
    plain = [t for t, v in raw.items() if isinstance((v or {}).get("coach"), str)]
    assert plain, "문자열 꼴 선언이 하나도 없다 — 이 계약이 공허하다"
    for t in plain[:3]:
        got = coach_row(t)
        assert got.get("name"), (t, got)
        # ⚠️ 출처는 그 팀의 `source` 줄에서 온다(문자열 꼴에는 `since` 가 없다)
        assert got.get("source"), (t, got)


def test_v5_8_2_감독_미상이_탈락_사유가_아니다():
    """🔴🔴 §8-2 의 알맹이 [#11].

    ⚠️ 실측 2026-10-04: 감독을 모른다는 사유가 카드에 두 번 떴고, 사다리 ③
       (*"감독명 + 회견"*)이 **통째로 안 돌았다.**
    🔴 모르면 **그 자리표만 비우고 나머지 각도는 돈다.**
    """
    from app.entities import coach_of
    name, why = coach_of("없는팀 FC")
    assert name == "", (name, why)
    # 🔴 **사유가 §8-6 enum 이 아니다** — 탈락이 아니므로 사유가 없다
    from app.reasons import Reason
    assert not any(r.value in why for r in Reason), (
        f"🔴 감독 미상이 **탈락 사유 코드**로 적혔다: {why}")
    # 🔴 그리고 그 사실이 **못 쟀다**로 남는다(#3 조용한 0 금지)
    assert "모른다" in why or "없다" in why, why




def _types() -> set[str]:
    from app import rules
    return set(rules.variable_types())






# ══════════════════════════════════════════════════════════════════
# 🔴 §8-2 의 여섯 칸을 **채워서** 돌려주나
# ══════════════════════════════════════════════════════════════════


def test_v5_8_2_profile이_여섯_칸을_다_든다():
    """🔴 빈 칸도 **이름으로** 있어야 한다 — 없으면 호출부가 `KeyError` 로 터진다."""
    from app.entities import profile
    got = profile("Jamaica")
    for k in WANT:
        assert k in got, (k, sorted(got))
        assert k in got["_why"], f"🔴 `{k}` 의 출처가 없다"
        # 🔴🔴 **비어 있으면 없는 것과 같다**(2026-10-04 돌연변이 H 가 그 자리로
        #    통과했다 — 칸은 있고 값이 빈 문자열이었다).
        assert str(got["_why"][k] or "").strip(), (
            f"🔴 `{k}` 의 출처가 **비었다** — 그러면 못 쟀는지 없는지 모른다")


def test_v5_8_2_세_칸은_손으로_적지_않는다():
    """🔴🔴 `country`·`league`·`langs` 는 **시스템이 이미 안다.**

    ⚠️ yaml 에 옮겨 적으면 **사본**이 되고 이적·승강 때마다 한 발 늦는다
       (CLAUDE.md #1 · 2026-09-27 에 같은 병으로 여섯 번 놓쳤다).
    🔴 실측 2026-10-04 — 선언에 그 셋이 **한 줄도 없는데** 채워진다:
         LG Twins         league KBO    langs ['ko','en']  ← 이름표·리그 명부
         North Macedonia  country iso:MK  langs ['mk','en'] ← Babel CLDR
    """
    from app import rules
    from app.entities import profile
    raw = rules._load("config/entities.yaml")["teams"]
    for t in raw:
        assert not ({"country", "league", "langs"} & set(raw[t] or {})), (
            f"🔴 `{t}` 가 그 셋을 **손으로** 적었다 — 사본이 된다")
    kbo = profile("LG Twins")
    assert kbo["league"] == "KBO" and "이름표" in kbo["_why"]["league"]
    assert kbo["langs"] == ["ko", "en"] and "리그" in kbo["_why"]["langs"]
    mk = profile("North Macedonia")
    assert mk["country"] == "iso:MK" and "나라 코드" in mk["_why"]["country"]
    assert mk["langs"] == ["mk", "en"] and "CLDR" in mk["_why"]["langs"]


def test_v5_8_2_모르는_칸은_None이고_까닭이_남는다():
    """#3 조용한 0 금지 — *"없다"* 와 *"아직 안 쟀다"* 를 가른다."""
    from app.entities import profile
    got = profile("없는팀 FC")
    assert got["langs"] is None
    assert "못 알았다" in got["_why"]["langs"], got["_why"]["langs"]
    assert got["country"] is None
    assert "클럽" in got["_why"]["country"], got["_why"]["country"]




def test_v5_8_2_학습이_선언을_못_덮는다(monkeypatch):
    """🔴 사용자가 적은 것이 봇이 주운 것보다 낫다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    첫 판은 학습 값을 **만들지 않고** 그냥 선언을 읽었다. 그러니 *"학습을 먼저
    본다"* 로 뒤집은 돌연변이도 **읽을 학습이 없어** 초록이었다.
    🔴 그래서 학습이 **다른 이름을 들고 있는 상태**를 만들어 놓고 본다.
    """
    from app import entities
    monkeypatch.setattr(
        entities, "_learned_coach",
        lambda team: {"name": "주운 감독", "since": None,
                      "source": "학습 — fotmob:1", "learned_from": "fotmob:1"})
    # 🔴 선언이 있는 팀 — **선언이 이긴다**
    got = entities.coach_row("Jamaica")
    assert got["name"] == "Rudolph Speid", got
    assert "학습" not in str(got.get("source") or ""), got
    # 🔴 선언이 **없는** 팀 — 그때는 학습이 쓰인다(기능이 죽지 않았다)
    none = entities.coach_row("없는팀 FC")
    assert none["name"] == "주운 감독", none
    assert none.get("learned_from") == "fotmob:1", none
