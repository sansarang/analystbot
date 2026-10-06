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

from app.core.schema import (XI, Coach, Doc, Facts, MatchRef, Missing,
                             Player)


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


def xi_of(team_key: str, raw: object, *, source_url: str = "",
          missing: list[Missing] | None = None) -> XI:
    """🔴 어댑터의 XI 모양 → `schema.XI`. ⚠️ 모르면 `state="none"`(지어내지 않는다).

    🔴 축구 완성 지시서 §2:
      · `players` 는 **이름+포지션+등번호**(`lineup` 칸)
      · `confirmed` 는 **경기 페이지의 확정 표식**만(`lineup_state`)
      · 예상 명단에 **결장 명단 선수가 있으면 그 선수를 빼고** `conflict` 사유를 남긴다
        (⚠️ 실측 온두라스–자메이카: 결장자가 든 예상 명단이 돌았다)
    """
    box = dict(raw or {}) if isinstance(raw, dict) else {}
    rows = [dict(x) for x in (box.get("lineup") or []) if isinstance(x, dict)]
    players = names_of(box.get("players") or box.get("starters"))
    if rows and not players:
        players = [str(r.get("name") or "") for r in rows if r.get("name")]
    said = str(box.get("lineup_state") or "").strip().lower()
    if said in ("confirmed", "predicted", "none"):
        state = said
    elif box.get("confirmed"):
        # 🔴 **옛 어댑터 꼴**(`confirmed: True`) — 그것도 **경기 페이지**가 준 표식이다
        #    (NPB·KBO·ESPN 파서가 그 칸을 쓴다). ⚠️ 기사에서 온 것은 이 칸을 쓰지
        #    않는다 — §2 가 *"확정은 경기 페이지의 확정 표식만"* 이라 못 박았다.
        state = "confirmed"
    else:
        # ⚠️ 표식이 없으면 **확정이라고 적지 않는다**(fail-closed · §2 금지 항목)
        state = "predicted" if players else "none"
    # 🔴 **결장자가 예상 명단에 있으면 뺀다** — 그 사실을 사유로 남긴다
    gone = {str(m.name).strip().lower() for m in (missing or [])}
    conflicts: list[str] = []
    if gone and state != "confirmed":
        keep_rows, keep_names = [], []
        for name in players:
            if str(name).strip().lower() in gone:
                conflicts.append(f"⚠️ 제외: {name}(결장 명단)")
                continue
            keep_names.append(name)
        for r in rows:
            if str(r.get("name") or "").strip().lower() in gone:
                continue
            keep_rows.append(r)
        players, rows = keep_names, keep_rows
    return XI(team=team_key, state=state,                 # type: ignore[arg-type]
              formation=(_text(box.get("formation")) or None),
              players=players,
              bench=names_of(box.get("bench") or box.get("subs")),
              lineup=[Player(name=str(r.get("name") or ""),
                             pos=str(r.get("pos") or ""),
                             number=(int(r["number"])
                                     if isinstance(r.get("number"), int)
                                     else None))
                      for r in rows if r.get("name")],
              source_url=str(source_url or box.get("source_url") or ""),
              fetched_at=_utc(box.get("fetched_at")),
              conflicts=conflicts)


def missing_of(raw: object, *, source_url: str = "",
               source: str = "page") -> list[Missing]:
    """🔴 어댑터의 결장 명단 → `schema.Missing` 목록(§2).

    ⚠️ 기사에서 온 것은 `source="article"` 이다 — s5 가 그때 **등급을 한 단계 낮춘다**.
    """
    allowed = set(Missing.model_fields["reason"].annotation.__args__)  # type: ignore[union-attr]
    out: list[Missing] = []
    for row in (raw or []) if isinstance(raw, (list, tuple)) else ():
        box = dict(row) if isinstance(row, dict) else {}
        name = _text(box.get("name"))
        if not name:
            continue
        said = str(box.get("reason") or "other")
        out.append(Missing(
            name=name, pos=str(box.get("pos") or ""),
            reason=(said if said in allowed else "other"),  # type: ignore[arg-type]
            returns=str(box.get("returns") or ""),
            source_url=str(source_url or ""),
            source=("article" if source == "article" else "page")))
    return out


def coach_of(raw: object) -> Coach | None:
    """🔴 감독(§2). ⚠️ 이름이 없으면 `None` — 빈 감독을 만들지 않는다."""
    if isinstance(raw, dict):
        name = _text(raw.get("name"))
        return Coach(name=name, since=str(raw.get("since") or ""),
                     interim=bool(raw.get("interim"))) if name else None
    name = _text(raw)
    return Coach(name=name) if name else None


def facts_of(raw: dict, *, xi: dict[str, XI] | None = None,
             match_format: str = "unknown",
             sources: list[str] | None = None,
             missing: dict[str, list[Missing]] | None = None,
             coach: dict[str, Coach] | None = None,
             player_pos: dict[str, str] | None = None,
             squad: dict[str, list[str]] | None = None,
             gaps: list[str] | None = None) -> Facts:
    """🔴 구조 사실 묶음 → `schema.Facts`. ⚠️ 없는 칸은 **빈 것**으로 둔다.

    🔴 축구 완성 지시서 §2 의 칸을 **더해서** 받는다(이름 바꾸기·빼기 금지).
    """
    box = dict(raw or {})
    fmt = str(match_format or "unknown")
    allowed = set(Facts.model_fields["match_format"].annotation.__args__)  # type: ignore[union-attr]
    return Facts(
        standings=dict(box.get("standings") or {}),
        recent=dict(box.get("recent") or {}),
        h2h=dict(box.get("h2h") or {}),
        xi=dict(xi or {}),
        missing=dict(missing or {}),
        coach=dict(coach or {}),
        last_xi=dict(box.get("last_xi") or {}),
        schedule=dict(box.get("schedule") or {}),
        player_pos=dict(player_pos or {}),
        squad={k: [str(x) for x in v] for k, v in (squad or {}).items()},
        match_format=(fmt if fmt in allowed else "unknown"),  # type: ignore[arg-type]
        extra_time=box.get("extra_time"),
        leg=box.get("leg"),
        sources=[str(x) for x in (sources or box.get("sources") or [])],
        # 🔴 **못 받은 칸을 이름으로**(§2) — 블록 1 이 칸별로 적는다
        gaps=[str(x) for x in (gaps or [])])


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


def _parts(name: str) -> frozenset[str]:
    """🔴 `absence_def` 와 `def_absence` 를 같은 것으로 보는 **이름 꼴** 비교."""
    return frozenset(x for x in str(name).split("_") if x)


def catalog_type(kind: str) -> str:
    """🔴🔴 **유형군 이름 → 카탈로그 유형 이름.** 못 옮기면 **빈 글자**다.

    ══════════════════════════════════════════════════════════════════
    🔴 실측 2026-10-06 — **이름이 두 표에서 갈려 있었다**
    ══════════════════════════════════════════════════════════════════

    `subtask_groups.yaml` 의 `kinds` 20개 중 **7개가 카탈로그에 없다**:

        absence_def · absence_att · lineup_rotation · coach_intent ·
        individual_title · regression · team_stats

    ⚠️ 그런데 **방향·무게·검색 낱말을 아는 쪽은 카탈로그**(`variable_types.yaml`)다.
       🔴 그래서 카탈로그에 없는 이름을 `type` enum 으로 모델에 주면, 돌아온 변수는
          방향 규칙을 못 찾아 **전부 `both`**(방향 없음)가 된다 — 실측으로 그랬다.

    옮기는 길은 **둘뿐이고 둘 다 이미 있는 표다**(지어내지 않는다 · #4):
      ① `rules.v5_names()` — 지시문 이름 → §4 이름(`lineup_rotation` →
         `squad_rotation`)
      ② **이름 꼴**이 같은 것(`absence_def` ↔ `def_absence`) — 낱말 집합이 **똑같을
         때만** 잇는다. 뜻으로 추측하지 않는다.
    🔴 그 둘로도 못 옮기는 이름은 **버리고 이름으로 남긴다**(#3 조용한 0 금지) —
       `absence_att`·`coach_intent`·`individual_title`·`team_stats`·`regression`.
       ⚠️ 어디에 붙일지는 **사용자가 정한다**(카탈로그에 유형을 더할지, 유형군의
          이름을 고칠지) — 내가 고르면 그것은 지어낸 규칙이다.
    """
    from app import rules
    cat = rules.variable_types()
    said = str(kind)
    if said in cat:
        return said
    moved = rules.v5_names().get(said, "")
    if moved and moved in cat:
        return moved
    want = _parts(said)
    for name in sorted(cat):
        if _parts(name) == want:
            return name
    return ""


def names_of_key(key: object) -> list[str]:
    """🔴 그 팀을 가리키는 **모든 이름**(공식명·별칭) — 열쇠를 받는다.

    🔴 **`app/analyze.py` 에서 옮겨 왔다**(§8 5단계 삭제 · 2026-10-06). 변환은
       `adapt` 한 곳이라는 §2 규칙에 맞는 자리다 — 열쇠 → 이름은 변환이다.
    ⚠️ §8-1 — 인자는 **열쇠**다(이름이 아니다). 이름을 인자로 받으면 그 함수가 또
       하나의 해석 지점이 된다.
    """
    from app import entities, teamref
    k = str(key or "")
    if not k:
        return []
    # 🔴 **영어 대표명이 맨 앞**이다 — 검색 순서가 그 순서다(§4-2).
    got = [teamref.label_of(k, lang) for lang in ("en", "ko", "ja", "es")]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이름표가 든 것을 전부 꺼낸다**(실측 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전은 `label_of(k, lang)` **넷**뿐이었다 — 그것은 언어마다 **대표
    #     이름 하나**다. 🔴 이름표는 `names['en']` 에 여럿을 든다:
    #
    #       reg.teams["team:000338"].all_names()
    #         → ['Milwaukee Brewers', 'mlb:158', 'Brewers', '브루어스', …]
    #       _names_of_key(…)  →  ['Milwaukee Brewers', '밀워키 브루어스']
    #                             🔴 **'Brewers' 를 흘렸다**
    #
    #  🔴 그래서 공식 API 의 짧은 이름을 받게 고쳐도 **효과가 0 이었다** —
    #     에이전트 질의 7건이 그대로 `query_too_bare` 로 거부됐다.
    #     ⚠️ 판정 함수를 고치고 **쓰는 곳을 안 고친** 그 병이다(CLAUDE.md #2).
    ref = teamref.registry().teams.get(k)
    if ref is not None:
        got += ref.all_names()
    # 🔴 별칭은 `entities` 가 든다(현지 매체가 부르는 이름 · 사본 금지)
    got += list(entities.names_of(got[0] if got else ""))
    out: list[str] = []
    for n in got:
        # 🔴 **외부 id 는 이름이 아니다**(`mlb:158`·`fdorg:103`) — 이름표가
        #    별칭으로 들고 있지만 검색어로 쓰면 아무 데도 없는 글자다.
        if not n or ":" in n or teamref.is_code(n):
            continue
        if n not in out:
            out.append(n)
    return out

def lineup_question(ref: MatchRef, team_name: str) -> Any:
    """🔴🔴 **어댑터에 넘길 질문 꼴** — `cells` 를 보는 곳은 **이 파일 하나**다.

    사용자 지시 2026-10-06(2차) ⑤:

    > `cells`: 지금 삭제하지 않는다. 대신 `app/core/` 에서는 **`adapt.py` 만 `cells`
    > 를 import 할 수 있게** 정적 검사를 건다.

    ⚠️ 어댑터(`collect/*`)는 `cells.Question` 꼴로 묻는다 — 그 타입을 지우려면 수집층
       전부를 다시 써야 한다(계약 34개). 🔴 그래서 **경계를 여기 하나로 좁힌다**:
       단계(`s2`)는 이 함수만 부르고 `cells` 를 모른다.
    """
    from app import cells
    return cells.Question(cells.Q_LINEUP, ref.id, team=team_name,
                          league=ref.competition, deadline=ref.kickoff_utc)
