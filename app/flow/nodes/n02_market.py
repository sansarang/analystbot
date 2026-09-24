"""[v1.4 STEP 3] ② 시장값 — 배당을 **마진 제거 확률**로 바꾼다.

🔴 `p`(devig)와 `required`(1/배당)를 **필드로 분리한다.** 섞으면 ⑪의 edge 가
   늘 마진만큼 양수로 나와 거짓 픽이 된다(지시문 STEP 3 "흔한 오류").
🔴 야구는 `devig_2way`, 축구는 `devig_3way` 만 부른다.
⚠️ 배당이 없으면 `p=None` · `market_missing=True`. 확률을 지어내지 않는다.
⚠️ 파생(총점·팀토탈·핸디)은 **원배당 그대로** 싣는다 — ⑪이 쓴다.
"""
from __future__ import annotations

import logging

from app.flow import rules as R

from app.flow.odds_math import devig_2way, devig_3way

logger = logging.getLogger(__name__)

NODE = "n02_market"

#: 이름표 붙은 스냅샷만 본다. 기준선 규칙의 원본은 `odds_move.BASELINE_ORDER` 다.
_SQL = """
    SELECT o.market, o.side, o.line, o.odds, o.snap_tag, o.provider, o.captured_at
      FROM odds_snapshots o
     WHERE o.game_id = $1
     ORDER BY o.captured_at DESC
"""


def _minute(ts):
    """`captured_at` → **분 단위**로 끊은 시각. 문자열도 받는다.

    🔴 쪽마다 따로 INSERT 라 같은 벌이 마이크로초로 어긋난다 — 그대로 묶으면
       전 벌이 반쪽이 된다.
    """
    import datetime as _dt

    if isinstance(ts, str):
        try:
            ts = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(ts, _dt.datetime):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.UTC)
    return ts.astimezone(_dt.UTC).replace(second=0, microsecond=0)


async def _changes(state, ctx) -> list:
    """[MOV-C] 이 경기와 같은 종목·날짜의 **시각 붙은 변화**.

    🔴 Go 크롤러가 쌓는다 — 라인업·선발(`crawl:<종목>:<날짜>:changes`)과
       뉴스(`crawl:news_<리그>:<날짜>:changes`) 둘 다 읽는다.
    ⚠️ **흐름은 지금까지 이것을 한 번도 안 읽었다**(`app/flow/` 참조 0건).
       만들어 놓고 안 이은 자리였다.
    ⚠️ 못 읽으면 빈 목록이다 — 귀인이 `unobserved` 가 되고, 그건 "자금"과
       **다른 말**이다(찾아보지 않았다는 뜻).
    """
    if "changes" in (ctx.inject or {}):
        return list((ctx.inject or {}).get("changes") or [])
    redis = getattr(ctx, "redis", None)
    if redis is None:
        return []
    try:
        from app.collectors.crawler_feed import load_changes

        code = _news_code(state)
        day = str(state.kickoff_utc or "")[:10]
        out = []
        for key in (code, f"news_{code}"):
            # 🔴 [KEY-1 2026-09-24] **상한을 올린다.** 기본 50 인데 뉴스는
            #    하루 300건 넘게 쌓인다(실측 mlb 317 · npb 295 · kbo 274).
            #    최근 50건만 보면 이 경기 기사가 그 안에 없어 **전건 0** 이
            #    된다 — 실측으로 14경기 전부 "이 경기 0" 이었다.
            #    ⚠️ 창(`move.window_min`)이 어차피 시각으로 거른다.
            out.extend(await load_changes(
                redis, key, day,
                limit=int(R.get("move.changes_limit", 400))) or [])
        return out
    except Exception as exc:
        logger.warning("[flow:n02] 변화 조회 실패 game=%s: %s", state.game_id, exc)
        return []


def _news_code(state) -> str:
    """Go 크롤러가 쌓는 키의 코드 — **`kbo`·`npb`·`mlb`·`soccer`**.

    🔴 [KEY-1 2026-09-24] **여기가 틀려서 기사 886건을 한 건도 못 읽었다.**
    ```
    Go 가 쌓은 것   crawl:news_mlb:2026-09-24:changes  317건
    ②가 찾던 것     crawl:news_baseball:…              0건
    ```
    원인 둘 다 내 잘못이다:
      ① `code_for(league, sport)` 인데 **인자를 바꿔** 불렀다
         → `code_for('baseball','MLB')` = `'baseball'`
      ② ⑤에 이미 `_sport_code` 가 있는데 여기 **새로 지었다**(사본)

    🔴 그래서 짓지 않고 **⑤의 것을 그대로 쓴다.** 두 노드가 같은 답을
       내야 하고, 계약이 그 일치를 잠근다.
    ⚠️ 야구는 리그(`mlb`), 축구는 종목(`soccer`)이다 — 특례가 아니라
       `games.sport` 열의 실제 값이 그렇게 생겼다.
    """
    from app.flow.labels import sport_code

    return sport_code(state)


async def _rows(state, ctx) -> list:
    if "odds_rows" in (ctx.inject or {}):
        return list(ctx.inject["odds_rows"] or [])
    if ctx.pool is None:
        return []
    try:
        gid = int(state.game_id)
    except (TypeError, ValueError):
        return []
    try:
        return [dict(r) for r in await ctx.pool.fetch(_SQL, gid)]
    except Exception as exc:
        logger.warning("[flow:n02] 배당 조회 실패 game=%s: %s", state.game_id, exc)
        return []


def _sets(rows, home: str, away: str) -> list:
    """시각별 **완전한 h2h 한 벌** → `[(시각, 홈확률)]`, 오래된 것부터.

    🔴 [MOV-H 2026-09-23] 개장가를 뽑으려면 시각별로 갈라야 한다. 종전
       `_h2h` 는 "가장 최근 한 벌"만 냈다.
    🔴 **`impossible_set` 을 여기서도 지난다.** ODD-S 게이트는 앞으로 들어올
       것만 막고, 이미 쌓인 244행(kbo 145 · npb 94 · mlb 5)은 DB 에 남아
       있다. 거르지 않으면 **깨진 호가가 개장가로 뽑힌다.**
       판정은 `odds_math.impossible_set` 하나가 한다 — 사본 금지.
    🔴 **시각을 분 단위로 묶는다.** 적재가 쪽마다 따로 INSERT 해서 같은 벌의
       `captured_at` 이 **마이크로초 단위로 어긋난다**(실측 2026-09-23:
       `15:13:42.665749`(home) vs `15:13:42.672699`(away)). 정확히 같은 값으로
       묶으면 전 벌이 반쪽이 되어 **이동이 조용히 0** 이 된다.
       ⚠️ 실데이터로 돌려 보고서야 알았다 — 단위 계약이 두 쪽에 같은 시각을
          주는 바람에 통과했었다(거짓 픽스처).
    ⚠️ 반쪽 벌(한 쪽만 온 시각)은 세지 않는다. 확률을 만들 수 없다.
    """
    from app.flow.odds_math import devig_2way, devig_3way, impossible_set

    # (분, 쪽) → 그 분에 관측된 배당들. 한 쪽에 값이 둘 이상이면 **모호**다.
    seen: dict = {}
    for r in rows:
        if (r.get("market") or "") != "h2h":
            continue
        ts = _minute(r.get("captured_at"))
        if ts is None:
            continue
        side = str(r.get("side") or "")
        key = ("home" if side == home else
               "away" if side == away else
               "draw" if side.lower() in ("draw", "무", "tie") else None)
        if key is None:
            continue
        try:
            seen.setdefault(ts, {}).setdefault(key, set()).add(round(float(r["odds"]), 4))
        except (TypeError, ValueError):
            continue

    out = []
    for ts, sides in sorted(seen.items()):
        # 🔴 [ODD-2 2026-09-23] **한 분에 서로 다른 두 벌이 들어온다.** 실측:
        #    ```
        #    g1774 15:13:42  한화 1.65 / 롯데 2.20   마진 1.061 (한화 우세)
        #          15:13:42  한화 2.10 / 롯데 1.74   마진 1.051 (롯데 우세)
        #    ```
        #    둘 다 마진이 정상이고 `snap_tag` 도 같다(태그 없음) — 가릴 수
        #    없다. 아무 쪽이나 고르면 다음 분에 반대 벌이 뽑혀 **±12%p 가짜
        #    이동**이 생긴다(kbo·npb 증분 자기상관 ρ₁ −0.58 의 정체).
        #    ⚠️ **고르지 않고 버린다.** 모르는 것을 골라 쓰면 그게 곧 거짓
        #       귀인이 되고, "이유 미상은 없다"가 거짓말이 된다.
        if any(len(v) > 1 for v in sides.values()):
            continue
        q = {k: next(iter(v)) for k, v in sides.items()}
        if impossible_set(list(q.values())):
            continue
        if {"home", "draw", "away"} <= set(q):
            ph = devig_3way(q["home"], q["draw"], q["away"])[0]
        elif {"home", "away"} <= set(q):
            ph = devig_2way(q["home"], q["away"])[0]
        else:
            continue
        out.append((ts, round(ph, 4)))
    return out


def move_of(rows, home: str, away: str) -> dict:
    """개장 → 현재 **홈 기준** 이동. 🔴 못 재면 `move_pp` 는 **None** 이다.

    ⚠️ 0 과 모름은 다른 말이다(MOV-1 이 적은 규약). 한 벌뿐이면 "안 움직였다"
       가 아니라 "모른다"다.
    """
    pts = _sets(rows, home, away)
    if not pts:
        return {"move_pp": None, "n_snaps": 0, "open_home": None,
                "now_home": None, "since": None}
    if len(pts) == 1:
        return {"move_pp": None, "n_snaps": 1, "open_home": pts[0][1],
                "now_home": pts[0][1], "since": pts[0][0]}
    return {"move_pp": round((pts[-1][1] - pts[0][1]) * 100, 2),
            "n_snaps": len(pts), "open_home": pts[0][1],
            "now_home": pts[-1][1], "since": pts[0][0]}


async def _with_causes(state, ctx, rows) -> dict:
    """[MOV-C 3·4단계] 이동에 **원인**과 **개장 괴리**를 붙인다.

    사용자 2026-09-23: "배당률 분석은 **초기부터** 분석이 이루어져야 한다".
    종전 ②는 "현재 시장 확률" 한 줄만 냈다 — 개장가가 왜 그랬는지, 어디로
    얼마나 왜 움직였는지는 **아무 노드도 하지 않았다**(⑪이 끝에서 검증만).

    🔴 `open_gap_pp` = 개장 홈확률 − 우리 사전값 홈확률. ③ 게이트는 **현재**
       시장과만 비교한다. 개장과도 비교하면 둘이 갈린다:
         처음부터 달랐다   → 실력 평가 차이(우리 Elo 가 다르게 본다)
         움직여서 달라졌다 → 개장 뒤 무슨 일이 있었다 → `causes` 가 답한다
    ⚠️ **싣기만 한다.** ③의 판정(라벨·stop)은 바꾸지 않는다.
    ⚠️ ①은 여전히 시장을 보지 않는다 — 페이블식 순서의 선은 ①과 ② 사이다.
    """
    from app.flow import attribution as A

    mv = move_of(rows, state.home, state.away)
    pri = getattr(state, "n01_prior", None) or {}
    ph = pri.get("p_home")
    if mv.get("open_home") is not None and ph is not None:
        try:
            mv["open_gap_pp"] = round((float(mv["open_home"]) - float(ph)) * 100, 2)
        except (TypeError, ValueError):
            mv["open_gap_pp"] = None
    else:
        mv["open_gap_pp"] = None

    chgs = await _changes(state, ctx)
    # 🔴 [NWS-D] **기사의 호재·악재를 여기서 정한다.** ②가 제목과 팀을 이미
    #    갖고 있으므로 ⑤가 자료를 다시 긁을 필요가 없다. ⑤는 이것을 증거
    #    한 줄로 옮기기만 한다.
    #    ⚠️ 이동을 못 재도(`move_pp` None) 기사 방향은 낼 수 있다 — 배당이
    #       안 움직였다고 부상이 없는 것은 아니다.
    mv["news_dir"] = A.news_dir(chgs, (state.home, state.away))
    if mv.get("move_pp") is None:
        mv["causes"] = None
        return mv
    bag = A.explain(_sets(rows, state.home, state.away), chgs,
                    teams=(state.home, state.away))
    mv["causes"] = bag
    if bag.get("moves"):
        logger.info("[flow:n02] game=%s %s", state.game_id, A.summary(bag))
    return mv


def _h2h(rows, home: str, away: str) -> dict:
    """가장 최근 h2h 한 벌. `side` 는 **팀 이름**이다(0-b 실측)."""
    out: dict = {}
    for r in rows:
        if (r.get("market") or "") != "h2h":
            continue
        side = str(r.get("side") or "")
        key = ("home" if side == home else
               "away" if side == away else
               "draw" if side.lower() in ("draw", "무", "tie") else None)
        if key and key not in out:
            out[key] = float(r["odds"])
    return out


def _derivatives(rows, home: str, away: str) -> dict:
    """총점·핸디·팀토탈 원배당. **가공하지 않는다.**"""
    der: dict = {"total": {}, "ah": [], "team_total_home": {},
                 "team_total_away": {}}
    for r in rows:
        m, side = (r.get("market") or ""), str(r.get("side") or "")
        line = None if r.get("line") is None else float(r["line"])
        odds = float(r["odds"])
        low = side.lower()
        if m == "totals":
            if "over" in low and "over" not in der["total"]:
                der["total"].update({"line": line, "over": odds})
            elif "under" in low and "under" not in der["total"]:
                der["total"].update({"line": line, "under": odds})
        elif m == "spreads":
            der["ah"].append({"line": line, "side": side, "odds": odds})
        elif m in ("team_totals", "team_total"):
            slot = ("team_total_home" if home and home in side else
                    "team_total_away" if away and away in side else None)
            if slot:
                key = "over" if "over" in low else "under"
                der[slot].setdefault("line", line)
                der[slot].setdefault(key, odds)
    return der


async def run(state, ctx):
    """② 시장값."""
    rows = await _rows(state, ctx)
    odds = _h2h(rows, state.home, state.away)
    sport = (state.sport or "").lower()

    have = ({"home", "draw", "away"} <= set(odds) if sport == "soccer"
            else {"home", "away"} <= set(odds))
    if not have:
        logger.info("[flow:n02] game=%s 배당 없음 — 시장 없음", state.game_id)
        state.n02_market = {"odds": odds or {}, "p": None, "required": None,
                            "derivatives": _derivatives(rows, state.home, state.away),
                            "move": await _with_causes(state, ctx, rows),
                            "market_missing": True}
        return state

    mv = await _with_causes(state, ctx, rows)

    if sport == "soccer":
        ph, pd, pa = devig_3way(odds["home"], odds["draw"], odds["away"])
        p = {"home": round(ph, 4), "draw": round(pd, 4), "away": round(pa, 4)}
    else:
        ph, pa = devig_2way(odds["home"], odds["away"])
        p = {"home": round(ph, 4), "draw": None, "away": round(pa, 4)}

    state.n02_market = {
        "odds": odds, "p": p,
        # 🔴 요구확률은 **따로** 둔다. `p` 와 같은 자리에 넣지 않는다.
        "required": {k: round(1.0 / v, 4) for k, v in odds.items()},
        "derivatives": _derivatives(rows, state.home, state.away),
        # 🔴 [MOV-H] 개장 → 현재 이동. ④가 이것을 가설에 접목한다.
        "move": mv,
        "market_missing": False,
    }
    logger.info("[flow:n02] game=%s p_home %.3f · p_away %.3f%s",
                state.game_id, p["home"], p["away"],
                f" · draw {p['draw']:.3f}" if p.get("draw") else "")
    return state
