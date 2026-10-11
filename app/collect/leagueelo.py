"""🔴🔴 **리그별 자체 Elo** — football-data.org 과거 결과로 **우리가 계산한다**.

사용자 승인 2026-10-06(5차) ③:

> football-data.org 과거 결과로 **리그별 자체 Elo** 를 계산해 저장(하루 1회 갱신),
> 같은 순서형 로짓을 **리그 경기**로 적합. **clubelo 칸은 dead 로 둔다.**

## 왜 우리가 계산하나

🔴 clubelo 는 **죽었다**(실측 2026-10-06: `Fixtures API deactivated` · 502). 그런데
   `football-data.org` 는 **키만으로 과거 결과를 다 준다**(실측: `PL/2025` 380경기 ·
   `PL/2024` 380경기 · `PD/2025` 380경기). 결과가 있으면 Elo 는 **계산할 수 있다** —
   남의 수를 빌리지 않는다.

## 계산 규칙 — 손으로 고른 수가 **둘뿐**이다

| 수 | 값 | 어디서 |
|---|---|---|
| `K` | 20 | `config/league_elo.yaml` — 축구 Elo 의 통용값 |
| 시작 등급 | 1500 | 같은 표 — **모든 팀이 같다**(차이만 뜻을 가진다) |

⚠️ 홈 보정은 **여기서 안 넣는다** — ① 의 순서형 로짓이 홈 개최 경기로만 적합돼
   절단점이 그것을 머금고 있다(`config/base_model.yaml`). 🔴 두 번 세지 않는다.
🔴 그래서 이 파일이 내는 것은 **순수한 전력 차**이고, 홈 효과는 ① 이 더한다.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
#: 🔴 저장 자리 — `var/` 다(커밋하지 않는다 · 하루 1회 갱신)
STORE = ROOT / "var" / "league_elo"
CONF = "config/league_elo.yaml"


def table() -> dict:
    """🔴 설정표 — `K`·시작 등급·대회 목록·시즌 수. 코드에 숫자를 안 적는다."""
    from app import rules
    return dict(rules._load(CONF) or {})


def _rows(matches: list[dict]) -> list[tuple[datetime, str, str, int, int]]:
    """🔴 football-data 응답 → `(시각, 홈, 원정, 홈골, 원정골)`. ⚠️ 못 읽은 줄은 버린다."""
    out = []
    for m in matches:
        try:
            when = datetime.fromisoformat(str(m["utcDate"]).replace("Z", "+00:00"))
            # 🔴 절대규칙 2 — **시간대 없는 값은 받지 않는다**(naive 가 새면 날짜가
            #    기계 시간대로 조용히 바뀐다). football-data 는 `Z` 로 주지만 **확인한다**.
            if when.tzinfo is None:
                continue
            ft = (m.get("score") or {}).get("fullTime") or {}
            home, away = int(ft["home"]), int(ft["away"])
            a = str((m.get("homeTeam") or {}).get("name") or "").strip()
            b = str((m.get("awayTeam") or {}).get("name") or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if a and b:
            out.append((when, a, b, home, away))
    return sorted(out, key=lambda r: r[0])


def compute(matches: list[dict], *, k: float, start: float
            ) -> tuple[dict[str, float], list[dict]]:
    """🔴🔴 Elo 를 **시간 순으로** 굴린다. `(최종 등급표, 적합용 줄들)`.

    🔴 적합용 줄은 **경기 전 등급**을 담는다 — 그것이 ① 의 입력(`dr`)이고, 경기 후
       등급으로 적합하면 **결과를 보고 맞히는 것**이 된다(누설).
    ⚠️ 골 차는 안 쓴다(`K` 하나) — 골 차 가중은 수를 더 고르게 만들고, 그 수를
       우리가 재지 않았다.
    """
    rate: dict[str, float] = {}
    rows: list[dict] = []
    for when, home, away, hg, ag in _rows(matches):
        ra = rate.setdefault(home, start)
        rb = rate.setdefault(away, start)
        we = 1.0 / (10.0 ** (-(ra - rb) / 400.0) + 1.0)
        got = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        rows.append({"when": when.date().isoformat(), "home": home, "away": away,
                     "home_elo": round(ra, 2), "away_elo": round(rb, 2),
                     "outcome": (2 if hg > ag else (1 if hg == ag else 0))})
        rate[home] = ra + k * (got - we)
        rate[away] = rb - k * (got - we)
    return {t: round(v, 2) for t, v in rate.items()}, rows


def fotmob_table() -> dict:
    """🔴 fotmob 으로 받을 리그 표 — `config/league_elo.yaml` 의 `fotmob` 칸."""
    return dict(table().get("fotmob") or {})


async def fetch_fotmob(net, comp: str, *, state=None
                       ) -> tuple[list[dict], str]:
    """🔴🔴 **fotmob 결과로 그 리그를 받는다**(사용자 지시 2026-10-09 ③).

    > K리그1·J1 자체 Elo: football-data 에 **없는 리그**는 fotmob 경기 결과로
    > 자체 Elo 를 굴린다.

    `(football-data 와 같은 꼴의 경기들, 사유)`.

    🔴 **꼴을 맞춰 돌려준다** — `_rows()`·`compute()` 를 **그대로** 쓴다(사본 금지
       · #1). 그래서 Elo 계산 규칙이 리그마다 갈리지 않는다.
    ⚠️ 끝난 경기만 싣는다(`finished` · 스코어가 있는 줄).
    🔴 시즌은 주소 인자다 — 실측 2026-10-09: `?season=2025` 가 228경기를 줬고
       인자 없이는 **현재 시즌**(198경기 · 끝난 180)을 준다.
    """
    from app.collect import fotmob as fm
    box = fotmob_table()
    said = dict((box.get("competitions") or {}).get(comp) or {})
    lid, slug = said.get("id"), str(said.get("slug") or "")
    if not lid or not slug:
        return [], f"`{comp}` 가 fotmob 표에 없다"
    seasons = [str(x) for x in (box.get("seasons") or [])]
    out: list[dict] = []
    hows: list[str] = []
    for season in seasons:
        url = f"{fm.BASE}/leagues/{lid}/matches/{slug}"
        got = await net.get(url, params={"season": season})
        if not getattr(got, "ok", False):
            hows.append(f"{season}: HTTP {getattr(got, 'status', '?')}")
            continue
        j = fm.payload(getattr(got, "text", "") or "")
        if not j:
            hows.append(f"{season}: 페이로드가 없다")
            continue
        rows = _fotmob_matches(j)
        out += rows
        hows.append(f"{season}: {len(rows)}경기")
    # 🔴 **같은 경기가 두 번 올 수 있다** — 시즌 인자가 안 먹는 해는 현재 시즌을
    #    되돌려준다(실측: 인자 없는 호출과 겹친다). ⚠️ 겹치면 Elo 가 그 경기를 두
    #    번 세어 등급이 부풀어 오른다 → **경기 번호로 하나만 남긴다**.
    seen: set[str] = set()
    uniq = []
    for m in out:
        mid = str(m.get("id") or "")
        if mid and mid in seen:
            continue
        if mid:
            seen.add(mid)
        uniq.append(m)
    if len(uniq) != len(out):
        hows.append(f"중복 {len(out) - len(uniq)}경기 뺐다")
    if state is not None:
        state.note(f"리그Elo(fotmob) `{comp}` {len(uniq)}경기 — {' · '.join(hows)}")
    return uniq, " · ".join(hows)


def _fotmob_matches(j: dict) -> list[dict]:
    """🔴 fotmob 리그 페이지 → **football-data 꼴**의 끝난 경기들.

    ⚠️ 칸 이름을 football-data 에 맞춘다(`utcDate`·`score.fullTime`·`homeTeam`) —
       그래야 `_rows()` 가 분기 없이 읽는다(#1 사본 금지 · #2 배선).
    """
    import re as _re
    box = ((j.get("props") or {}).get("pageProps") or {})
    rows = ((box.get("fixtures") or {}).get("allMatches")
            or ((box.get("overview") or {}).get("matches") or {}).get("allMatches")
            or [])
    out = []
    for m in rows:
        if not isinstance(m, dict):
            continue
        st = m.get("status") or {}
        if not st.get("finished") or st.get("cancelled"):
            continue
        got = _re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(st.get("scoreStr") or ""))
        if not got:
            continue
        out.append({"id": str(m.get("id") or ""),
                    "utcDate": str(st.get("utcTime") or ""),
                    "score": {"fullTime": {"home": int(got.group(1)),
                                           "away": int(got.group(2))}},
                    "homeTeam": {"name": str((m.get("home") or {}).get("name") or "")},
                    "awayTeam": {"name": str((m.get("away") or {}).get("name") or "")}})
    return out


def path_of(comp: str, *, when: date | None = None) -> Path:
    """🔴 그 대회의 **그날** 파일. ⚠️ 날짜가 바뀌면 새로 받는다(하루 1회 갱신)."""
    day = (when or datetime.now(timezone.utc).date()).isoformat()
    return STORE / day / f"{comp}.json"


def load(comp: str, *, when: date | None = None) -> dict:
    """🔴 저장해 둔 등급표. ⚠️ 없으면 **빈 표**다(있는 척하지 않는다)."""
    p = path_of(comp, when=when)
    if not p.is_file():
        return {}
    try:
        return dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def save(comp: str, box: dict, *, when: date | None = None) -> Path:
    p = path_of(comp, when=when)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(box, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


async def fetch(net, comp: str, seasons: list[str], *, state=None
                ) -> tuple[list[dict], str]:
    """🔴 그 대회의 **끝난 경기**를 시즌별로 받는다. `(경기들, 사유)`.

    ⚠️ 키가 없으면 빈 목록이다 — football-data 는 `X-Auth-Token` 없이 **403** 이다
       (실측 2026-10-06).
    """
    from app.collect import fdorg
    key = fdorg.api_key()
    if not key:
        return [], "football-data 키가 없다(`FOOTBALL_DATA_KEY` 비었다)"
    out: list[dict] = []
    hows: list[str] = []
    for season in seasons:
        url = f"https://api.football-data.org/v4/competitions/{comp}/matches"
        got = await net.get(url, params={"season": season, "status": "FINISHED"},
                            headers={"X-Auth-Token": key})
        # 🔴🔴 **분당 한도에 걸린다** — football-data 무료 티어는 분당 10회다.
        #    ⚠️ 실측 2026-10-06: 9대회 × 3시즌(27요청)을 한 번에 던져 FL1·DED 가
        #       통째로 빠졌다. 그런데 하나씩 부르면 **둘 다 온다**(305·306경기).
        #    🔴 그래서 429 면 `Retry-After` 만큼 **기다렸다가 한 번 더** 부른다.
        if getattr(got, "status", 0) == 429:
            wait = _retry_after(getattr(got, "headers", {}) or {})
            if state is not None:
                state.note(f"리그Elo `{comp}` 분당 한도 — {wait}초 기다린다")
            await asyncio.sleep(wait)
            got = await net.get(url,
                                params={"season": season, "status": "FINISHED"},
                                headers={"X-Auth-Token": key})
        if not getattr(got, "ok", False):
            hows.append(f"{season}: HTTP {getattr(got, 'status', '?')}")
            continue
        try:
            box = json.loads(getattr(got, "text", "") or "{}")
        except ValueError:
            hows.append(f"{season}: JSON 이 아니다")
            continue
        said = [m for m in (box.get("matches") or []) if isinstance(m, dict)]
        out += said
        hows.append(f"{season}: {len(said)}경기")
    return out, " · ".join(hows)


async def refresh(net, *, when: date | None = None, state=None
                  ) -> tuple[dict[str, dict], list[dict]]:
    """🔴🔴 **하루 1회 갱신** — 대회마다 받아 Elo 를 굴리고 저장한다.

    `({대회: 등급표}, 적합용 줄들)`. ⚠️ 이미 그날 파일이 있으면 **받지 않는다**.
    """
    box = table()
    k = float(box.get("k") or 20.0)
    start = float(box.get("start") or 1500.0)
    seasons = [str(s) for s in (box.get("seasons") or [])]
    out: dict[str, dict] = {}
    rows: list[dict] = []
    # 🔴🔴 **통로가 둘이다**(사용자 지시 2026-10-09 ③) — football-data 가 주는
    #    리그와, 그것이 **안 주는** 리그(fotmob 으로 받는다). ⚠️ 표가 어느 쪽인지
    #    말한다 — 코드에 리그 이름을 박지 않는다.
    # 🔴🔴 **통로는 대회 표가 말한다**(사용자 지시 2026-10-09(4차) §1) —
    #    `baseline.elo` 가 `fotmob` 인 리그가 fotmob 통로다. ⚠️ 종전에는 이 파일의
    #    `fotmob:` 칸만 봤다 — 그러면 통로 목록이 **두 곳**에 산다(#1 사본 금지).
    from app.core import competition as _comp
    via_fotmob = {str(c) for c in
                  ((fotmob_table().get("competitions") or {}).keys())}
    for _key, _row in _comp.rows().items():
        if str(_comp.elo_source(_key).get("elo") or "") == "fotmob":
            via_fotmob.add(_comp.short_key(_key))
    for comp in ([str(c) for c in (box.get("competitions") or [])]
                 + sorted(via_fotmob)):
        got = load(comp, when=when)
        if got.get("ratings"):
            out[comp] = got
            rows += list(got.get("fit_rows") or [])
            if state is not None:
                state.note(f"리그Elo `{comp}` 그날 파일 적중 — "
                           f"{len(got['ratings'])}팀")
            continue
        if comp in via_fotmob:
            matches, how = await fetch_fotmob(net, comp, state=state)
        else:
            matches, how = await fetch(net, comp, seasons, state=state)
        if not matches:
            if state is not None:
                state.note(f"리그Elo `{comp}` 못 받았다 — {how}")
            continue
        rate, fit_rows = compute(matches, k=k, start=start)
        said = {"competition": comp, "ratings": rate, "fit_rows": fit_rows,
                "matches": len(matches),
                # 🔴 어느 통로로 받았는지 **파일에 남긴다** — 카드의 출처 줄이
                #    이것을 적는다(`football-data` 와 `fotmob` 을 섞어 말하지 않는다)
                "via": ("fotmob" if comp in via_fotmob else "football-data"),
                "seasons": ([str(x) for x in (fotmob_table().get("seasons") or [])]
                            if comp in via_fotmob else seasons),
                "k": k,
                "start": start, "built_at": datetime.now(timezone.utc).isoformat()}
        save(comp, said, when=when)
        out[comp] = said
        rows += fit_rows
        logger.info("[리그Elo] %s %d팀 · %d경기(%s)", comp, len(rate),
                    len(matches), how)
        if state is not None:
            state.note(f"리그Elo `{comp}` {len(rate)}팀 · {len(matches)}경기({how})")
    return out, rows


def all_comps(*, when: date | None = None) -> list[str]:
    """🔴🔴 **등급을 찾을 대회 목록** — 표 + **쌓인 파일에서 자란다**.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **실사고 2026-10-10** — 자체 Elo 를 만들어 두고 못 찾았다
    ══════════════════════════════════════════════════════════════════

    `config/league_elo.yaml` 의 `competitions` 는 football-data 리그 아홉뿐이다.
    🔴 그런데 K리그1·J1 은 **fotmob 결과로 자체 Elo 를 만들어** `var/league_elo/`
       에 쌓아 두고 있었다(`KL1.json` — 14팀 · 1516.95 …).
    ⚠️ `rating_of` 가 그 목록만 봐서 **`Gangwon FC` 를 못 찾았다** — 그래서 보정
       폼(§1)이 Elo 보정을 아예 못 했다. 🔴 `comps=['KL1']` 로 직접 부르면
       **찾는다**(1544.97) — 즉 자료는 있고 **목록이 좁았다**.

    🔴 그래서 **쌓인 파일에서 자라게** 한다(#1 손으로 유지하는 목록은 한 발 늦는다).
    ⚠️ 표의 순서를 **먼저** 둔다 — 같은 팀이 두 대회에 있으면 오래 측정된 쪽이다.
    """
    said = [str(c) for c in (table().get("competitions") or [])]
    try:
        # 🔴 **그날 파일이 있는 대회를 더한다** — 경로는 `path_of` 하나가 안다
        box = path_of("x", when=when).parent
        for one in sorted(box.glob("*.json")):
            if one.stem not in said:
                said.append(one.stem)
    except Exception:                                       # noqa: BLE001
        pass
    return said


def rating_of(team: str, *, comps: list[str] | None = None,
              when: date | None = None) -> tuple[float | None, str]:
    """🔴 그 팀의 리그 Elo. `(등급, 사유)` — ⚠️ 못 찾으면 `(None, 사유)`.

    🔴 이름은 football-data 표기다(`Liverpool FC`) — 우리 열쇠와 **별칭표**로 잇는다.
    """
    from app import teamref
    key, _ = teamref.key_of(team)
    names = {team.lower()}
    if key:
        box = teamref.registry().teams.get(key)
        if box is not None:
            names |= {n.lower() for v in box.names.values() for n in v}
    for comp in (comps or all_comps(when=when)):
        box_file = load(comp, when=when)
        said = box_file.get("ratings") or {}
        # 🔴 **통로를 지어내지 않는다** — 등급 파일의 `via` 가 말한다(지시
        #    2026-10-09 ③). ⚠️ 종전엔 `football-data 결과로 계산` 이 **박혀** 있어
        #    fotmob 으로 받은 J1·K리그1 카드에 거짓 출처가 찍혔다(실측 2026-10-09:
        #    가시마 1671.66 의 사유가 `football-data` 라고 적혔다).
        via = str(box_file.get("via") or "football-data")
        # 🔴🔴 **대조 입구 하나로 한 칸 더**(사용자 지시 2026-10-11 ⑤)
        #  ⚠️ 실측 2026-10-11(엘체–셀타): 등급 파일의 열쇠는 `RC Celta de Vigo` 인데
        #     봇이 쥔 이름은 fotmob 의 `Celta Vigo` 였다 — 글자 그대로도, ` fc` 를
        #     걷어도 안 맞아 **기준 열이 통째로 비었다**(카드: *"Elo 를 못 받았다"*).
        #  🔴 그래서 `discover.same_any`(느슨한 대조)로 한 번 더 본다 — 이름을
        #     손으로 늘리지 않는다(#1 사본 금지).
        from app.core import discover as _dc
        got_names = sorted(names)
        for nm, val in said.items():
            if (nm.lower() in names
                    or nm.lower().replace(" fc", "") in names
                    or _dc.same_any(nm, got_names, loose=True)):
                return float(val), f"{comp} 자체 Elo({via} 결과로 계산)"
    return None, f"`{team}` 이 리그 Elo 표에 없다(대회 파일을 받았나 보라)"


#: 🔴 분당 한도에 걸렸을 때 기본 대기(초) — ⚠️ 머리말이 말해 주면 **그 수**를 쓴다
RETRY_WAIT_SEC = 61


def _retry_after(head: dict) -> int:
    """🔴 `Retry-After` 머리말 → 초. ⚠️ 없으면 `RETRY_WAIT_SEC`(분당 한도라 1분)."""
    try:
        got = int(str(head.get("retry-after") or "").strip())
    except ValueError:
        return RETRY_WAIT_SEC
    return max(1, min(300, got))
