"""🔴🔴 **리그 자동 등록** — 사용자 결정 2026-10-10 §1·§3.

> 모든 경기를 찾아 분석까지 해야 한다. **리그 수동 선언·상한 방식을 자동 등록으로
> 바꾼다.**

🔴 쓰는 자리는 `data/leagues_auto/{competition_key}.json` **하나**다 — 코드도
   config 도 아니다(§1 둘째 줄). ⚠️ `config/leagues.yaml` 은 *"기준 모델·분할
   규칙·특수 처리가 필요한 리그"* 만 남는다(지금 7개 그대로).

🔴 **필수 칸이 하나라도 없으면 등록 실패**다(§1 셋째 줄):
   출처(fotmob 리그 id·URL) · 확인일 · 나라(ccode) · 팀 목록 출처 · 언어(CLDR).
⚠️ 언어는 **CLDR 에서 받는다**(`babel`) — 손으로 적지 않는다(사용자 지시 2026-10-03).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
#: 🔴 저장 자리 — `data/` 다(코드·config 아님 · §1)
STORE = ROOT / "data" / "leagues_auto"
#: 🔴 §1 — **이 칸이 다 있어야** 등록이다. 하나라도 없으면 실패.
NEED: tuple[str, ...] = ("competition_key", "source", "checked_at", "ccode",
                         "teams_from", "langs", "teams")
#: 🔴 §3 — 기준을 *"약하다"* 고 적는 경기 수(사용자가 적은 30)
WEAK_AT = 30


def _wnow() -> datetime:
    """🔴 "지금" — `app/window.now_utc` 하나다(§4 `--as-of` 가 고정한다)."""
    from app import window as _w
    return _w.now_utc()


def path_of(key: str) -> Path:
    """🔴 그 리그의 파일 — 열쇠의 `:` 를 `_` 로 바꾼다(파일 이름이 된다)."""
    said = str(key or "").replace(":", "_").replace("/", "_")
    return STORE / f"{said or 'unknown'}.json"


def load(key: str) -> dict:
    """🔴 등록된 리그. ⚠️ 없으면 **빈 표**다(지어내지 않는다)."""
    p = path_of(key)
    if not p.is_file():
        return {}
    try:
        return dict(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return {}


def langs_of(ccode: str) -> list[str]:
    """🔴🔴 §3 — 나라 → **CLDR 공식 언어** + 영어. 손으로 적지 않는다.

    🔴 실측 2026-10-10(babel CLDR `territory_languages`):
       `AR→es` · `TR→tr` · `IT→it` · `AU→en` · `SG→en,zh,ms` · `VN→vi` · `TH→th`
       — 사용자가 적은 것과 **그대로 맞는다**.
    ⚠️ fotmob 은 세 글자(`ARG`)를 준다 — CLDR 은 두 글자(`AR`)다. 🔴 그 변환도
       **표에서** 한다(`pycountry` 가 없으면 앞 두 글자로 떨어지지 않는다 — 그러면
       빈 목록이고 등록이 실패한다 · 조용히 틀리지 않는다).
    """
    out, _why = langs_with_why(ccode)
    return out


def langs_with_why(ccode: str) -> tuple[list[str], str]:
    """🔴🔴 `(언어들, 왜)` — **왜를 함께** 돌려준다(#3 조용한 0 금지).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **fotmob 의 나라 코드는 FIFA 코드다 — CLDR 은 ISO 만 안다**
    ══════════════════════════════════════════════════════════════════

    실측 2026-10-10(스위스 수퍼리그 FC Zürich–Thun 실행): fotmob 이 `ccode:
    "SUI"` 를 줬고 등록이 *"필수 칸이 없다: ['langs']"* 로 **실패했다.**
    🔴 `babel` 의 `global.dat` **전수 조사**로 확인했다 — 16개 표 어디에도 `SUI`
       가 없다(`territory_aliases["CHE"] → ['CH']` 는 있다). 즉 CLDR 은 FIFA
       코드를 **모른다**.

    ⚠️ 그래서 **표를 손으로 짓지 않는다**(사본 금지 · 추측 금지). 대신:
      ① 두 글자면 CLDR 에 바로 묻는다.
      ② 세 글자면 CLDR `territory_aliases`(ISO 3→2)로 바꿔 묻는다.
      ③ 그래도 안 되면 **영어만** 쓰고 **그 까닭을 이름으로 남긴다** — 등록을
         막지 않는다(막으면 그 리그 경기를 **아예 못 본다**).
    🔴 ③ 이 걸린 코드는 `questions/2026-10-10_fifa_ccode_vs_cldr.md` 에 실측으로
       쌓는다 — 기억이 아니라 측정으로 자란다.
    """
    cc = str(ccode or "").strip().upper()
    if not cc:
        return ["en"], "🔴 나라 코드가 비었다 — 영어만"
    # 🔴🔴 §1-5 — **ISO 국가가 아닌 축구협회 넷**은 언어를 바로 적었다
    said = fifa_table().get("langs") or {}
    if cc in said:
        out = [str(x) for x in (said[cc] or [])] or ["en"]
        return out, f"§1-5 — `{cc}` 는 ISO 국가가 아닌 축구협회다 → {out}"
    two = cc if len(cc) == 2 else _alpha2(cc)
    if not two:
        miss = (fifa_table().get("unmatched") or {}).get(cc)
        where = (f"`{FIFA_CONF}` 가 **못 맞춘 코드**다(`unmatched`)" if miss
                 else f"`{FIFA_CONF}` 에 **없는 코드**다")
        return ["en"], (f"🔴 `{cc}`" + (f"({miss})" if miss else "")
                        + f" 를 ISO 로 못 바꿨다 — {where} · 영어만으로 "
                        f"찾는다(현지어 기사를 놓친다)")
    try:
        import babel.core as bc
        box = (bc.get_global("territory_languages") or {}).get(two) or {}
    except Exception:                                       # noqa: BLE001
        return ["en"], f"🔴 babel 을 못 읽었다(`{two}`) — 영어만"
    off = sorted(((k, float(v.get("population_percent") or 0))
                  for k, v in box.items() if v.get("official_status")),
                 key=lambda x: -x[1])
    out = [k for k, _p in off][:3]
    if not out:
        return ["en"], f"🔴 CLDR 이 `{two}` 의 공식 언어를 모른다 — 영어만"
    if "en" not in out:
        out.append("en")       # 🔴 영어는 늘 더한다(§3: "그 언어 + 영어")
    return out, f"CLDR — `{cc}`→`{two}` 공식 언어 {out}"


#: 🔴🔴 §1-5 — **FIFA 코드 → ISO** 표. 도구가 만들고 사람이 손대지 않는다.
FIFA_CONF = "data/fifa_to_iso.yaml"


def fifa_table() -> dict:
    """🔴 `data/fifa_to_iso.yaml` — 출처·확인일이 머리에 적혀 있다(§1-5).

    🔴 만든 도구는 `tools/build_fifa_iso.py` 다 — **손으로 늘리지 않는다**
       (CLAUDE.md #1). ⚠️ 파일이 없으면 **빈 표**이고 그 사실이 사유에 남는다.
    """
    from app import rules
    try:
        return dict(rules._load(FIFA_CONF) or {})
    except Exception:                                       # noqa: BLE001
        return {}


def _alpha2(cc3: str) -> str:
    """🔴🔴 세 글자 코드 → ISO 두 글자. 못 바꾸면 **빈 글자**(지어내지 않는다).

    | 순서 | 어디서 |
    |---|---|
    | ① | **`data/fifa_to_iso.yaml`**(§1-5 · 공개 목록 → CLDR 로 맞춘 233개) |
    | ② | CLDR `territory_aliases`(ISO3→ISO2 · 표에 없는 코드를 메운다) |

    🔴 ① 이 먼저인 까닭: fotmob 이 주는 것은 **FIFA 코드**이고 그 표가 그것을
       안다(`SUI`→`CH`). ⚠️ CLDR 은 FIFA 를 모른다(babel 전수 조사 2026-10-10).
    ⚠️ **앞 두 글자를 떼지 않는다** — `AUS`→`AU` 는 맞지만 `CHE`→`CH` 는 그
       방식으로 틀린다. 표가 답이다.
    """
    said = str(cc3 or "").strip().upper()
    got = str((fifa_table().get("iso") or {}).get(said) or "").strip().upper()
    if len(got) == 2:
        return got
    try:
        import babel.core as bc
        box = (bc.get_global("territory_aliases") or {}).get(said)
    except Exception:                                       # noqa: BLE001
        return ""
    for x in (box or []):
        one = str(x).strip().upper()
        if len(one) == 2:
            return one
    return ""


def baseline_of(rows: list[dict]) -> dict:
    """🔴🔴 §3 — 그 리그 **이번 시즌 결과**로 기준 출발점.

    > 자체 Elo 가 없으면 … 홈승·무·원정승 비율과 **경기당 총골**을 계산해
    > 출발점으로. 경기 수가 **30경기 미만이면 "기준 약함"** 표시.
    """
    n = len(rows or [])
    if not n:
        return {"n": 0, "weak": True, "why": "끝난 경기가 0건이다"}
    home = sum(1 for r in rows if int(r["home_score"]) > int(r["away_score"]))
    draw = sum(1 for r in rows if int(r["home_score"]) == int(r["away_score"]))
    goals = sum(int(r["home_score"]) + int(r["away_score"]) for r in rows)
    return {"n": n,
            "share_home_draw_away": [round(home / n, 4), round(draw / n, 4),
                                     round((n - home - draw) / n, 4)],
            "goals_per_match": round(goals / n, 3),
            "weak": n < WEAK_AT,
            "why": (f"이번 시즌 끝난 경기 {n}건으로 셌다"
                    + (f" — 🔴 **기준 약함**({WEAK_AT}경기 미만)" if n < WEAK_AT
                       else ""))}


def build(*, competition_key: str, meta: dict, teams: list[str],
          baseline: dict, seen: list[str] | None = None,
          teams_from: str = "", when: date | None = None,
          ) -> tuple[dict, str]:
    """🔴🔴 §1 — 등록할 표를 **만든다**. `(표, 사유)` · 필수 칸이 없으면 `({}, 사유)`.

    ⚠️ **실패를 조용히 넘기지 않는다** — 사유에 무엇이 없는지 이름으로 적는다.
    """
    lid = meta.get("league_id")
    ccode = str(meta.get("ccode") or "")
    said = {
        "competition_key": str(competition_key or ""),
        # 🔴 출처 — **리그 id 와 주소 둘 다**(§1 셋째 줄)
        "source": {"fotmob_league_id": lid, "url": str(meta.get("url") or "")},
        # 🔴 확인일도 **고정 시계**를 따른다(§4 — 재현 모드에서 날짜가 흔들리면
        #    그 등록 파일이 매 실행 달라진다)
        "checked_at": str((when or _wnow().date()).isoformat()),
        "ccode": ccode,
        # 🔴 팀 목록 출처 — 이미 만든 통로 이름 그대로(§3 첫 줄)
        # 🔴 팀 목록을 **어디서** 받았나 — 순위표냐 일정이냐가 다르다(컵대회)
        "teams_from": str(teams_from or (f"fotmob:{lid}" if lid else "")),
        "langs": langs_of(ccode),
        # 🔴 §3 — 언어를 **어떻게 정했나**. FIFA 코드라 영어만 쓴 경우가 여기 남는다
        "langs_why": langs_with_why(ccode)[1],
        "teams": sorted(set(str(x) for x in (teams or []) if str(x).strip())),
        "name": str(meta.get("name") or ""),
        "season": str(meta.get("season") or ""),
        # 🔴 §3 — 대회 형식(조가 여럿이면 조별) · 분할은 순위표 구역이 말한다
        "format": ("group" if int(meta.get("groups") or 0) > 1 else "league"),
        "zones": dict(meta.get("zones") or {}),
        "baseline": dict(baseline or {}),
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **경기 페이지가 적는 글자 그대로**(실사고 2026-10-10)
        # ══════════════════════════════════════════════════════════════
        #
        #  엘살바도르 `Primera Division - Apertura` 가 **스페인 라리가**
        #  `league:PD` 로 붙었다 — 그 줄의 `football_data_names` 에
        #  `Primera Division` 이 있어 **품는 일치**가 걸렸다.
        #  🔴 카드 쪽은 리그 id 없이 **대회 글자만** 받는다. 그래서 그 글자를
        #     여기 **그대로** 담아 두고, 열쇠 판정이 **정확 일치**로 먼저 본다 —
        #     정확 일치는 품는 일치보다 **센 증거**다.
        "seen": sorted({str(x).strip() for x in (seen or [])
                        if str(x).strip()}),
    }
    miss = [k for k in NEED if not said.get(k)]
    if miss:
        return {}, f"🔴 등록 실패 — 필수 칸이 없다: {miss}"
    return said, (f"등록 준비 — `{said['competition_key']}` · {ccode} · "
                  f"언어 {said['langs']} · 팀 {len(said['teams'])} · "
                  f"{said['baseline'].get('why')}")


def save(box: dict) -> tuple[Path | None, str]:
    """🔴 파일로 쓴다. ⚠️ 필수 칸을 **다시 본다** — 만든 쪽을 믿지 않는다."""
    miss = [k for k in NEED if not dict(box).get(k)]
    if miss:
        return None, f"🔴 등록 실패 — 필수 칸이 없다: {miss}"
    STORE.mkdir(parents=True, exist_ok=True)
    p = path_of(str(box["competition_key"]))
    p.write_text(json.dumps(box, ensure_ascii=False, indent=2, sort_keys=True)
                 + "\n", encoding="utf-8")
    return p, f"등록했다 — {p.relative_to(ROOT)}"


def registered() -> list[str]:
    """🔴 등록된 리그 열쇠들 — 계약이 *"자동 등록 경로를 통과했나"* 를 본다(§1)."""
    if not STORE.is_dir():
        return []
    out: list[str] = []
    for p in sorted(STORE.glob("*.json")):
        try:
            got = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        key = str(dict(got).get("competition_key") or "")
        if key:
            out.append(key)
    return out


def short_of(key: str) -> str:
    """🔴 자동 등록 열쇠 → **짧은 이름**(`league:KL1` → `KL1`).

    계약이 *"자동 등록한 리그가 손 선언에도 있나"* 를 볼 때 쓴다(§1) — 두 쪽의
    이름 모양이 다르므로 한 곳에서 맞춘다.
    """
    said = str(key or "")
    return said.split(":", 1)[1] if ":" in said else said


def line(key: str) -> str:
    """🔴🔴 §4 — 카드·보고가 적는 **등록 한 줄**: 나라·언어·팀 수·기준 상태.

    > 각 경기마다: 자동 등록 파일 · 검색 언어 · 라인업 출처 · 기준 상태를 적는다.

    ⚠️ 등록이 없으면 **그 사실**을 적는다 — 빈 글자로 조용히 넘기지 않는다(#3).
    """
    box = load(key)
    if not box:
        return f"🆕 자동 등록 없음 — `{short_of(key)}`"
    base = dict(box.get("baseline") or {})
    said = (f"🆕 **자동 등록** `{short_of(key)}` · {box.get('ccode')} · "
            f"언어 {box.get('langs')} · 팀 {len(box.get('teams') or [])} · "
            f"확인일 {box.get('checked_at')} · 기준 "
            + ("🔴 **약함**" if base.get("weak") else "✅")
            + f"({base.get('n')}경기)")
    # 🔴 언어를 **영어만으로 떨어진 까닭**은 숨기지 않는다(#3)
    why = str(box.get("langs_why") or "")
    if why.startswith("🔴"):
        said += f"\n   ⚠️ 검색 언어 — {why}"
    return said


def report() -> str:
    """🔴 `/상태` 가 적는 **등록된 리그 전부** — 상한이 없어졌으니 수가 보여야 한다.

    ⚠️ 수동 선언 상한(7개)을 걷은 뒤로는 **이 목록이 유일한 눈**이다(§1).
    """
    keys = registered()
    if not keys:
        return "🆕 자동 등록된 리그 0개 — 아직 아무 경기도 새 리그를 안 열었다"
    return (f"🆕 자동 등록된 리그 {len(keys)}개\n"
            + "\n".join(line(k) for k in keys))


def key_by_name(said: str) -> str:
    """🔴🔴 **대회 글자 → 자동 등록 열쇠**. 없으면 `""`.

    ⚠️ 실사고 2026-10-10: 등록은 됐는데 카드가 *"대회를 알아보지 못했다"* 를
       띄웠다 — `s2b` 는 `MatchRef.competition`(**글자** `Serie B`)만 주고 리그
       id 를 안 주기 때문이다. 🔴 그래서 **이름으로도** 찾는다.
    🔴 대조는 `competition._norm` 하나다(사본 금지) — 거기서 글자를 다듬는다.
    """
    from app.core import competition as comp
    want = comp._norm(said)
    if not want:
        return ""
    # 🔴 **긴 이름부터** 본다 — 손 표와 같은 규칙이다(`serie a` 가
    #    `serie a - brazil` 을 가로채지 않게 · `competition.key_of` ③).
    cand: list[tuple[int, str]] = []
    for key in registered():
        box = load(key)
        for word in (str(box.get("name") or ""), short_of(key),
                     *[str(x) for x in (box.get("seen") or [])]):
            low = comp._norm(word)
            if not low:
                continue
            # 🔴 **품는 검사**다 — 실측 2026-10-10: 등록 이름은
            #    `Segunda Federación` 인데 경기 페이지는
            #    `Segunda Federacion - Group 2` 라고 적는다(조 이름이 붙는다).
            if low == want or low in want:
                cand.append((len(low), key))
    if not cand:
        return ""
    cand.sort(key=lambda x: -x[0])
    # 🔴 **가장 긴 일치가 여럿이면 고르지 않는다** — 이름이 나라를 넘어 겹친다
    best = cand[0][0]
    keys = {k for n, k in cand if n == best}
    if len(keys) > 1:
        logger.info("[autoleague] 🔴 `%s` 가 자동 등록 %d곳에 같은 길이로 "
                    "걸린다 — 고르지 않는다 %s", said, len(keys), sorted(keys))
        return ""
    return cand[0][1]


def key_by_seen(said: str) -> str:
    """🔴🔴 **경기 페이지 글자와 정확히 같은** 자동 등록 열쇠. 없으면 `""`.

    ⚠️ 실사고 2026-10-10: 손 표의 `football_data_names`(`Primera Division`)가
       엘살바도르 리그 글자(`Primera Division - Apertura`)를 **품어서** 그 경기가
       라리가로 붙었다. 🔴 **정확 일치가 품는 일치를 이긴다** — 그 순서를
       `competition.key_of` 가 지킨다(여기는 재료만 준다).
    """
    from app.core import competition as comp
    want = comp._norm(said)
    if not want:
        return ""
    hit = {key for key in registered()
           for word in (load(key).get("seen") or [])
           if comp._norm(word) == want}
    if len(hit) == 1:
        return hit.pop()
    if hit:
        # 🔴🔴 **애매하면 고르지 않는다**(실사고 2026-10-10 두 번째): 스위스와
        #    인도네시아가 둘 다 `Super League` 다. 인도네시아 경기가 **스위스
        #    리그**로 붙어 기준·홈 이점이 통째로 남의 것이 됐다.
        #  🔴 빈 글자를 주면 카드가 *"대회를 알아보지 못했다"* 를 띄우고 등급을
        #     보류한다 — **그 쪽이 맞다**(틀린 기준으로 판정하는 것보다 낫다).
        logger.info("[autoleague] 🔴 `%s` 가 자동 등록 %d곳에 걸린다 — "
                    "고르지 않는다 %s", said, len(hit), sorted(hit))
    return ""
