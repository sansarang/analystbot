"""🔴🔴 **§6-2 질의 생성** — 현지어 + 영어 · 별칭 전부 · 원천 지정 먼저.

> 언어: 리그·대회 **현지어 + 영어 필수** · 별칭(현지 표기·로마자·약칭) 전부 ·
> 사실 종류별 틀(`config/search_terms/<언어>.yaml`) · 원천 지정(`site:`)으로
> **S·A 를 먼저** · 기간은 킥오프 전 72시간(결장·라인업) / 14일(감독·장기 부상).
> 계약 **QY1**: 현지어가 없으면 **실패**(질의를 만들지 않는다) ·
> **QY2**: 질의 로그(목록·결과 수) **미기록 실패**.

🔴 **왜** — 기준선(2026-10-13): 결장 재현율 **16.3%** 인데 버린 문서의 **52.9%**
   가 신원이고 그 중 **잘못 버림은 1%** 다. 즉 **엉뚱한 문서를 많이 긁어오고**
   맞는 기사는 **애초에 못 찾는다** → 질의가 손실의 뿌리다.
🔴 낱말·원천·별칭은 **표에서만** 온다(사본 금지): `config/search_terms/*.yaml` ·
   `config/sources/*.yaml` · `discover.aliases_of`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TERMS = Path(__file__).resolve().parents[3] / "config/search_terms"

#: 🔴 사실 종류 — 지시서 §6-2 그대로
KINDS: tuple[str, ...] = ("absence", "return", "expected_xi", "presser",
                          "rotation", "coach", "national")

#: 🔴 기간(시간) — 결장·라인업은 72시간 · 감독·장기 부상은 14일
HOURS = {"absence": 72, "return": 72, "expected_xi": 72, "presser": 72,
         "rotation": 72, "coach": 336, "national": 336}

#: 🔴 영어는 **언제나** 더한다(지시: 현지어 + 영어 필수)
ENGLISH = "en"

#: 🔴 **어느 대상에 무엇을 묻나** — 선수에게 "새 감독"을 묻지 않는다(실측에서
#   `Leandro Damiao new manager` 같은 질의가 나왔다 · 계약이 그 자리를 센다)
TARGETS = {
    "absence": ("team", "player"),
    "return": ("team", "player"),
    "expected_xi": ("team",),
    "presser": ("team", "coach"),
    "rotation": ("team", "coach"),
    "coach": ("team", "coach"),
    "national": ("team", "player"),
}


@lru_cache(maxsize=32)
def terms(lang: str) -> dict:
    """🔴 그 언어의 낱말 표. 없으면 **빈 표**(그 언어 질의를 안 만든다)."""
    import yaml
    path = TERMS / f"{str(lang or '').lower()}.yaml"
    if not path.exists():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


@dataclass
class Log:
    """🔴🔴 **QY2** — 질의 로그. 비어 있으면 사유가 **미기록**이라고 말한다."""

    _rows: list[dict] = field(default_factory=list)

    def note(self, q: str, *, hits: int) -> None:
        """🔴 결과 수를 적는다 — 같은 질의 줄이 **있으면 고치고** 없으면 더한다.

        ⚠️ 질의는 **만들 때** 먼저 적히고(결과 0) 던진 **뒤에** 수가 채워진다.
           그래서 더하기만 하면 같은 질의가 **두 줄**이 된다(실측: 계약이 잡았다).
        """
        for one in self._rows:
            if str(one.get("q")) == str(q):
                one["hits"] = int(hits)
                return
        self._rows.append({"q": str(q), "hits": int(hits)})

    def rows(self) -> list[dict]:
        return list(self._rows)

    def summary(self) -> str:
        if not self._rows:
            return "🔴 **질의 로그 미기록** — 질의·결과 수를 적지 않았다(QY2)"
        hits = sum(int(r["hits"]) for r in self._rows)
        return (f"질의 {len(self._rows)}개 · 결과 {hits}건"
                f"(0건 질의 {sum(1 for r in self._rows if not r['hits'])}개)")


def _langs(league: str) -> tuple[list[str], str]:
    """🔴 그 리그의 **현지어 + 영어**. 현지어 표가 없으면 빈 목록(QY1)."""
    from app.core.search import sources as _sr
    said = [str(x).lower() for x in (_sr.table(league).get("lang") or [])]
    local = [x for x in said if x != ENGLISH and terms(x)]
    if not local:
        return [], (f"🔴 **현지어 낱말 표가 없다**(`{league}` · 표의 lang "
                    f"{said or '없다'}) — 질의를 만들지 않는다(QY1)")
    return [*local, ENGLISH], f"언어 {[*local, ENGLISH]}"


def _names(name: str) -> list[str]:
    """🔴 팀 별칭 — `discover.aliases_of` 하나가 든다(현지 표기 포함)."""
    from app.core import discover as _d
    got = [str(x).strip() for x in _d.aliases_of(name) if str(x or "").strip()]
    out: list[str] = []
    for one in got:
        if one not in out:
            out.append(one)
    return out[:4]


def _plain_en(league: str, teams: dict, kinds: list[str]) -> list[dict]:
    """🔴 영어 일반 질의 — 상한에 눌려도 **영어는 남긴다**(지시: 영어 필수)."""
    words = terms(ENGLISH)
    out: list[dict] = []
    for kind in kinds:
        for word in list(words.get(kind) or [])[:1]:
            for side in ("home", "away"):
                for nm in teams[side][:1]:
                    out.append({"q": f"{nm} {word}", "lang": ENGLISH,
                                "kind": kind, "hours": HOURS.get(kind, 72),
                                "grade": "", "target": f"{side}:{nm}"})
    return out


def build(*, league: str, home: str, away: str, players: list[str],
          coach: str, kinds=("absence", "expected_xi"),
          log: "Log | None" = None,
          cap: int | None = None) -> tuple[list[dict], str]:
    """🔴🔴 질의 목록. 한 줄: `{q, lang, kind, hours, grade, target}`.

    🔴 **원천 지정(`site:`)이 먼저**다 — S·A 도메인에 대고 묻고, 그 다음 일반 질의.
    ⚠️ 현지어 낱말 표가 없으면 **빈 목록 + 사유**다(QY1).
    """
    from app.core.search import sources as _sr
    langs, why = _langs(league)
    if not langs:
        return [], why
    said_kinds = [k for k in kinds if k in KINDS]
    if not said_kinds:
        return [], f"🔴 아는 사실 종류가 없다({kinds})"
    teams = {"home": _names(home), "away": _names(away)}
    out: list[dict] = []
    # ── ① 원천 지정 질의(S → A)
    for grade in ("S", "A"):
        for one in _sr.rows_of(league, grade):
            dom = str(one.get("domain") or "")
            lang = str(one.get("lang") or langs[0]).lower()
            words = terms(lang)
            for kind in said_kinds:
                word = (list(words.get(kind) or []) or [""])[0]
                if not word:
                    continue
                for side in ("home", "away"):
                    for nm in teams[side][:2]:
                        out.append({
                            "q": f"site:{dom} {nm} {word}",
                            "lang": lang, "kind": kind,
                            "hours": HOURS.get(kind, 72), "grade": grade,
                            "target": f"{side}:{nm}"})
    # ── ② 일반 질의 — 현지어·영어 · 팀 별칭 · 선수 · 감독
    for lang in langs:
        words = terms(lang)
        if not words:
            continue
        for kind in said_kinds:
            for word in list(words.get(kind) or [])[:2]:
                for side in ("home", "away"):
                    for nm in teams[side][:2]:
                        out.append({"q": f"{nm} {word}", "lang": lang,
                                    "kind": kind,
                                    "hours": HOURS.get(kind, 72),
                                    "grade": "", "target": f"{side}:{nm}"})
                if "player" in TARGETS.get(kind, ()):
                    for who in [str(p) for p in (players or [])][:5]:
                        out.append({"q": f"{who} {word}", "lang": lang,
                                    "kind": kind,
                                    "hours": HOURS.get(kind, 72),
                                    "grade": "", "target": f"player:{who}"})
                if coach and "coach" in TARGETS.get(kind, ()):
                    out.append({"q": f"{coach} {word}", "lang": lang,
                                "kind": kind, "hours": HOURS.get(kind, 336),
                                "grade": "", "target": f"coach:{coach}"})
    # 🔴🔴 **§6-9 비용 상한** — 표의 `per_match_query_cap` 을 넘으면 **S·A 원천
    #    지정 질의만** 남긴다(지시서: *"상한 초과 시 S·A 원천만"*).
    said_cap = (int(_sr.table(league).get("per_match_query_cap") or 0)
                if cap is None else int(cap))
    said_cut = ""
    if said_cap and len(out) > said_cap:
        was = len(out)
        first = [q for q in out if q["grade"]][:said_cap]
        out = first if first else out[:said_cap]
        # 🔴🔴 **영어는 필수다**(지시: 현지어 + 영어 필수) — 상한을 지키면서도
        #    영어 질의를 **적어도 몇 개** 남긴다. ⚠️ 두 요구가 부딪히는 자리이고,
        #    *"상한 때문에 영어가 사라졌다"* 는 쪽이 더 나쁜 손실이다.
        if not any(q["lang"] == ENGLISH for q in out):
            room = max(1, said_cap // 4)
            said_en = [q for q in (_plain_en(league, teams, said_kinds))][:room]
            out = out[:max(0, said_cap - len(said_en))] + said_en
            said_cut = (f" · 🔴 **상한 {said_cap} 초과({was}개) → 원천 지정"
                        f"(S·A) + 영어 {len(said_en)}개로 자름**")
        else:
            said_cut = (f" · 🔴 **상한 {said_cap} 초과({was}개) → 원천 지정"
                        f"(S·A)만 {len(out)}개 남겼다**")
    if log is not None:
        for one in out:
            log.note(one["q"], hits=0)   # 🔴 결과 수는 부르는 쪽이 채운다
    return out, (f"{why}{said_cut} · 질의 {len(out)}개"
                 f"(원천 지정 {sum(1 for q in out if q['grade'])}개 · "
                 f"일반 {sum(1 for q in out if not q['grade'])}개 · "
                 f"종류 {sorted(set(q['kind'] for q in out))})")
