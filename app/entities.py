"""별칭 사전 접근자 — **현지 이름 · 감독 · 현지 매체**(사용자 기술 지시 2026-10-03).

> 내가 잘 찾는 이유의 절반은 팀을 **공식명이 아니라 현지 매체가 부르는 이름**으로
> 치기 때문이다 … **감독·주장·핵심 선수 이름도 검색어가 된다.**

🔴 원본은 `config/entities.yaml` 이다 — 이 파일은 **읽기만** 한다(사본 금지).
⚠️ **선언한 팀만** 이긴다. 없으면 빈 값이고 호출부가 종전 경로로 간다 — 그 사실이
   사유로 남아야 한다(#3 조용한 0 금지).
"""
from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)

ENTITIES = "config/entities.yaml"


@functools.lru_cache(maxsize=None)
def _table() -> dict:
    from app import rules
    return dict((rules._load(ENTITIES).get("teams") or {}))


def _row(team: str) -> dict:
    """그 팀의 선언. 🔴 **이름이 정확히 맞아야** 한다 — 부분 일치로 넓히지 않는다.

    ⚠️ 넓히면 `Korea` 가 `South Korea W` 를 집는다(남녀가 섞인다). 표기가 갈리는
       문제는 `aliases` 로 푸는 것이고, 표 조회를 느슨하게 해서 푸는 것이 아니다.
    """
    return dict(_table().get(str(team or "").strip()) or {})


def aliases_of(team: str, *, lang: str = "") -> list[str]:
    """🔴 그 팀의 **현지 별칭**. `lang` 을 주면 그 언어만, 없으면 전부.

    ⚠️ 공식명은 **넣지 않는다** — 호출부가 공식명 질의를 따로 던진다.
    """
    box = (_row(team).get("aliases") or {})
    if lang:
        return [str(x) for x in (box.get(str(lang)) or [])]
    out: list[str] = []
    for got in box.values():
        for x in (got or []):
            if str(x) not in out:
                out.append(str(x))
    return out


def coach_of(team: str, facts: list | None = None) -> tuple[str, str]:
    """🔴 감독 이름과 **어디서 왔나**. 못 알면 `("", 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 **자료가 선언을 이긴다**
    ══════════════════════════════════════════════════════════════════

    감독은 바뀐다. 그래서 그 경기 자료(fotmob 라인업의 `coach`·npb 명단)가 이름을
    주면 **그것을 먼저** 쓰고, 없을 때만 yaml 을 본다.
    ⚠️ 실측 2026-10-03(콜롬비아 vs 파라과이): fotmob 이 `coach=None` 을 줬다 —
       그때 yaml 이 `Néstor Lorenzo`·`Gustavo Alfaro` 를 댄다.
    """
    for f in (facts or []):
        v = f.value if isinstance(getattr(f, "value", None), dict) else {}
        if not v or str(v.get("team") or "") != str(team or ""):
            continue
        got = str(v.get("coach") or "").strip()
        if got:
            return got, "경기 자료"
    # 🔴 §8-2 — `coach` 가 문자열일 수도 dict 일 수도 있고, 학습한 것도 본다
    row = coach_row(team)
    if row.get("name"):
        return row["name"], str(row.get("source") or f"선언({ENTITIES})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **감독 미상은 탈락 사유가 아니다**(§8-2 [#11])
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04: 이 줄이 카드에 두 번 떴고 사다리 ③(*"감독명 + 회견"*)이
    #     통째로 안 돌았다. 🔴 모르면 **그 자리표만 비우고 나머지 각도는 돈다** —
    #     사유 코드(§8-6)를 **붙이지 않는다**(탈락이 아니다).
    return "", (f"⚠️ `{team}` 의 감독을 **아직 모른다** — 그 각도만 건너뛴다"
                f"(§8-2: 탈락 사유가 아니다). 공식 명단이나 첫 검색이 채운다")


def outlets_of(team: str) -> list[str]:
    """🔴 그 팀의 **현지 매체 도메인**. 없으면 빈 목록(전역 목록으로 간다)."""
    return [str(x) for x in (_row(team).get("outlets") or []) if str(x).strip()]


def names_of(team: str) -> list[str]:
    """🔴 귀속 검사에 쓸 **그 팀을 가리키는 모든 이름**(공식명 + 별칭).

    ⚠️ `verify.mentions_team` 은 한 번에 하나만 보므로, 호출부가 이 목록을 돌린다.
    """
    out = [str(team or "").strip()] if str(team or "").strip() else []
    for a in aliases_of(team):
        if a not in out:
            out.append(a)
    return out


def langs_of(team: str) -> list[str]:
    """🔴🔴 그 팀의 **별칭이 선언된 언어들**(사용자 기술 지시 2026-10-03).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이것이 필요한가 — 실측 2026-10-03
    ══════════════════════════════════════════════════════════════════

    파라과이 별칭 `Albirroja` 를 `es` 로 선언했는데 검색 언어가 `en` 뿐이라
    **그 별칭이 한 번도 안 던져졌다.** 선언이 있는데 안 쓰이는 것이 가장 나쁘다.

    🔴 **별칭을 그 언어로 선언한 것 자체가** *"이 팀 기사는 그 언어로 나온다"* 는
       뜻이다. 그래서 검색 언어 목록에 **자동으로 들어간다** — 같은 사실을
       `search_langs.yaml` 에 또 적지 않는다(사본 금지).
    """
    return [str(k) for k in (_row(team).get("aliases") or {}) if str(k).strip()]


# 🔴 `declared()` 는 두지 않았다 — 계약이 **그 팀을 직접** 묻는 것이 더 뜻이 있고
#    (`aliases_of("Jamaica")`), 안 이어진 공개 함수는 없는 코드보다 나쁘다.

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **v5 §8-2 — 엔티티 표의 여섯 칸** [#11]
# ══════════════════════════════════════════════════════════════════
#
#  > `entities.yaml` 에 팀마다 `coach`(**이름·부임일·출처**), `captain`,
#  > `home_venue`, `country`, `league`, `langs` 를 둔다. 감독 이름은 공식
#  > 명단에서 채우고, 비어 있으면 에이전트가 첫 검색에서 채워
#  > `learned_from:<경기ID>` 로 적는다.
#  > **감독 이름 미상이 변수 탈락 사유가 되지 않는다.**
#
#  🔴 왜 — 실측 2026-10-04(밀워키 vs 샌디에이고) 카드 원문:
#
#      세포 감독:Milwaukee Brewers: `Milwaukee Brewers` 의 감독을 모른다
#      세포 감독:San Diego Padres:  같다
#
#  ⚠️ 그 줄이 두 번 떴고 사다리 ③(*"감독명 + 회견"*)이 **통째로 안 돌았다.**
#     🔴 감독 이름 하나가 없어서 그 유형의 변수가 영영 0 이 된다.

#: 🔴 §8-2 가 이름 댄 칸. ⚠️ 팀마다 손으로 지키면 갈린다 — **한 곳**에 적는다.
#   `aliases`·`outlets`·`source` 는 v4 에서 쓰던 칸이고 §8-2 가 지우지 않았다.
FIELDS: tuple[str, ...] = ("coach", "captain", "home_venue", "country",
                           "league", "langs", "aliases", "outlets", "source")

#: 🔴 학습한 값이 **어디서 왔나**. ⚠️ 출처 없이 채우면 지어낸 것과 구분되지 않는다.
LEARNED_KEY = "learned_from"

#: 🔴 학습한 감독이 사는 곳. ⚠️ `entities.yaml`(사용자가 적는 것)과 **섞지 않는다**
#   — 섞으면 사용자가 적은 것과 봇이 주운 것을 못 가린다.
LEARNED_COACHES = "var/learned_coaches.json"


def coach_row(team: str) -> dict:
    """🔴🔴 그 팀의 감독 — **이름·부임일·출처**를 든 dict.

    ⚠️ 기존 선언 열여섯 팀이 `coach: 이름` **문자열**이다. 🔴 손으로 전부 고치지
       않는다(사본 금지) — 읽는 쪽이 **두 꼴을 받는다.** 문자열이면 `since` 는
       비고 `source` 는 그 팀의 `source` 줄에서 온다.
    🔴 **학습한 것이 선언보다 뒤다** — 사용자가 적은 것이 봇이 주운 것보다 낫다.
    """
    row = _row(team)
    got = row.get("coach")
    if isinstance(got, dict):
        out = {"name": str(got.get("name") or "").strip(),
               "since": got.get("since"),
               "source": str(got.get("source") or row.get("source") or "")}
        if got.get(LEARNED_KEY):
            out[LEARNED_KEY] = got[LEARNED_KEY]
        return out
    if isinstance(got, str) and got.strip():
        return {"name": got.strip(), "since": None,
                "source": str(row.get("source") or f"선언({ENTITIES})")}
    # 🔴 선언에 없으면 **학습한 것**을 본다(그 사실을 출처가 말한다)
    return _learned_coach(team)


def _learned_coach(team: str) -> dict:
    """⚠️ 봇이 주운 감독. 🔴 없으면 **빈 dict** — 지어내지 않는다."""
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / LEARNED_COACHES
    if not p.is_file():
        return {}
    try:
        box = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.info("[entities] 학습 감독 파일을 못 읽었다: %r", exc)
        return {}
    got = box.get(str(team or "").strip())
    return dict(got) if isinstance(got, dict) else {}





# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **세 칸은 손으로 적지 않는다** — 시스템이 이미 안다
# ══════════════════════════════════════════════════════════════════
#
#  §8-2 가 `country`·`league`·`langs` 를 요구한다. ⚠️ 그런데 그 셋은 **이미**
#  시스템에 있다:
#
#      league    이름표(`teamref`)가 리그 명단에서 받아 둔다
#      country   이름표의 나라 코드(`iso:MK`·`fa:SCO`)
#      langs     🔴 `resolve.nation_langs`(Babel CLDR) 또는 리그 언어
#
#  🔴 그것을 yaml 에 옮겨 적으면 **사본**이 되고, 이적·승강 때마다 한 발 늦는다
#     (CLAUDE.md #1 · 2026-09-27 에 같은 병으로 여섯 번 놓쳤다).
#  ⚠️ 그래서 **선언이 있으면 선언이 이기고, 없으면 시스템에서 꺼낸다.**
#     §8-2 의 요구는 *"표에 둔다"* 이고 그 표를 **읽는 문**이 이것이다.


def profile(team: str) -> dict:
    """🔴 §8-2 의 여섯 칸을 **채워서** 돌려준다. 각 칸의 **출처도 함께.**

    ⚠️ 빈 칸은 `None` 이고 그 사실이 `_why` 에 남는다(#3 조용한 0 금지).
    """
    row = _row(team)
    out: dict = {"team": team, "_why": {}}

    def put(name: str, value, why: str) -> None:
        out[name] = value
        out["_why"][name] = why

    # ── coach (이름·부임일·출처)
    cr = coach_row(team)
    put("coach", cr or None,
        str(cr.get("source") or "") if cr else "선언·자료·학습에 없다")
    # ── captain · home_venue · outlets · aliases — **선언만**이다(사실이라 지어내지 않는다)
    for name in ("captain", "home_venue", "outlets", "aliases"):
        got = row.get(name)
        put(name, got if got else None,
            f"선언({ENTITIES})" if got else f"`{ENTITIES}` 에 없다")
    # ── league · country · langs — 🔴 **시스템에서 꺼낸다**(위 머리글)
    if row.get("league"):
        put("league", row["league"], f"선언({ENTITIES})")
    else:
        put("league", _league_of(team) or None, "이름표(리그 명단)")
    if row.get("country"):
        put("country", row["country"], f"선언({ENTITIES})")
    else:
        code = _country_of(team)
        put("country", code or None,
            "이름표의 나라 코드" if code else "나라 코드가 없다(클럽이다)")
    if row.get("langs"):
        put("langs", list(row["langs"]), f"선언({ENTITIES})")
    else:
        got, why = _langs_of(team, out.get("league") or "")
        put("langs", list(got) or None, why)
    return out


def _league_of(team: str) -> str:
    """⚠️ 이름표가 그 팀의 리그를 안다(리그 명단에서 받아 둔다)."""
    try:
        from app import teamref
        key, _ = teamref.key_of(team)
        ref = teamref.registry().teams.get(key) if key else None
        return str(getattr(ref, "league", "") or "")
    except Exception as exc:                            # noqa: BLE001
        logger.info("[entities] 리그를 못 읽었다(%s): %r", team, exc)
        return ""


def _country_of(team: str) -> str:
    """🔴 이름표가 담아 둔 **나라 코드**(`iso:MK`·`fa:SCO`). 클럽이면 빈 값."""
    try:
        from app import teamref
        key, _ = teamref.key_of(team)
        ref = teamref.registry().teams.get(key) if key else None
        if ref is None:
            return ""
        for box in ref.names.values():
            for nm in box:
                if teamref.is_code(nm) and nm.split(":", 1)[0] in ("iso", "fa"):
                    return nm
        return ""
    except Exception as exc:                            # noqa: BLE001
        logger.info("[entities] 나라 코드를 못 읽었다(%s): %r", team, exc)
        return ""


def _langs_of(team: str, league: str) -> tuple[tuple[str, ...], str]:
    """🔴 §4-2 — 대표팀은 Babel likely-subtag, 클럽은 **리그의 현지어**."""
    try:
        from app import resolve
        got, why = resolve.nation_langs(team)
        if got:
            return got, f"Babel CLDR — {why}"
    except Exception as exc:                            # noqa: BLE001
        logger.info("[entities] 나라 언어를 못 읽었다(%s): %r", team, exc)
    if league:
        try:
            from app import league_index as LI
            got = tuple(LI.langs_of(league) or ())
            if got:
                return got, f"리그 명부({league})"
        except Exception as exc:                        # noqa: BLE001
            logger.info("[entities] 리그 언어를 못 읽었다(%s): %r", league, exc)
    # 🔴 별칭이 선언된 언어도 *"그 언어로 기사가 나온다"* 는 뜻이다(v4)
    got = tuple(langs_of(team))
    if got:
        return got, f"별칭 선언 언어({ENTITIES})"
    return (), "언어를 못 알았다 — 리그도 나라 코드도 별칭도 없다"
