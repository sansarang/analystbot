"""[리허설] 라인업 공시 **전** 재료로 파이프라인을 격리 완주시킨다.

🔴 프로브가 답하지 못한 A항(자료1·7·8)과 C항(판정)을 **실제로 채우는** 검증이다.
   프로브는 읽기만 했다. 이건 돌려본다 — 대신 **전부 격리 키 안에서**.

격리 (이 파일의 존재 이유):
  · Redis 는 `RehearsalRedis` 프록시가 **모든 키에 `rehearsal:` 을 붙인다.**
    실판정 캐시(`analysis:*`)·폼 캐시·L1 프롬프트 보관(`judge_prompt:*`)이
    전부 격리된다. 프롬프트 보관이 특히 중요하다 — 격리 안 하면 저녁
    L1 이 리허설 판정의 프롬프트를 진짜로 알고 대조한다.
  · 텔레그램 전송은 캡처한다. `pick_ledger`·`judgement_audit`·`judge_review`·
    `shadow_panel` 에 **한 줄도 쓰지 않는다.**
  · 종료 시 `rehearsal:*` 전부 삭제하고 남은 건수를 로그로 남긴다.

⚠️ `games` 스케줄 upsert 는 일어난다 — 15분 뒤 프리페치가 쓸 같은 데이터이고
   멱등이다. 그 외 DB 쓰기는 없다.
⚠️ **Claude 판정 호출은 유료다.** 7경기 = 폼 14콜 + 매치업 7콜. "유료 호출 0"
   은 web_search·The Odds API 기준이고, 판정 자체는 유료 경로 없이 못 돈다.
"""
from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)
L = logger.info
PREFIX = "rehearsal:"


class RehearsalRedis:
    """모든 키에 접두사를 붙이는 얇은 프록시. **쓰기가 실 키로 새지 않는다.**"""

    _KEYED = {"get", "set", "setex", "delete", "expire", "exists", "ttl",
              "hget", "hset", "hgetall", "hincrby", "hdel", "sadd", "smembers",
              "lpush", "rpush", "lrange", "incr", "incrby", "getset"}

    def __init__(self, inner):
        self._r = inner
        self.touched: set[str] = set()

    def __getattr__(self, name):
        fn = getattr(self._r, name)
        if name not in self._KEYED:
            return fn

        async def wrapped(key, *a, **kw):
            k = f"{PREFIX}{key}"
            self.touched.add(k)
            return await fn(k, *a, **kw)

        return wrapped

    async def aclose(self):
        return None            # 바깥이 닫는다 — 프록시가 닫지 않는다


async def _cleanup(inner) -> int:
    """`rehearsal:*` 전부 삭제. 반환 남은 건수(0 이어야 한다)."""
    n = 0
    try:
        keys = [k async for k in inner.scan_iter(f"{PREFIX}*", count=500)]
        for k in keys:
            await inner.delete(k)
            n += 1
        left = [k async for k in inner.scan_iter(f"{PREFIX}*", count=500)]
        L("[rehearsal] 격리 키 삭제 %d건 · 남은 %d건", n, len(left))
        return len(left)
    except Exception as exc:
        logger.error("[rehearsal] 격리 키 삭제 실패: %s", exc)
        return -1


# ═════════════════ 1단계. 크롤링 생존·신선도 ═════════════════

async def stage1(pool, sport: str, date: str) -> list[dict]:
    L("[rehearsal] ── 1단계 %s 소스 신선도·라인업 상태 ──", sport.upper())
    # ⚠️ `games` 에는 타순 컬럼이 **없다**(스키마 확인). 타순은 `lineup_events`
    #    (크롤러)·`lineups`(MLB)·리서치 캐시에 산다. 추측하지 말고 조인한다.
    rows = await pool.fetch(
        """SELECT g.id, g.home, g.away, g.starts_at, g.lineup_status, g.status,
                  g.home_pitcher, g.away_pitcher,
                  (SELECT count(*) FROM lineup_events e
                    WHERE e.game_id = g.id) AS ev_rows,
                  (SELECT max(jsonb_array_length(e.batting_order))
                     FROM lineup_events e WHERE e.game_id = g.id) AS ev_max
             FROM games g WHERE g.sport=$1 AND g.starts_at > now()
            ORDER BY g.starts_at""", sport)
    for r in rows:
        L("[rehearsal] game=%s %s @ %s start=%s lineup_status=%s "
          "선발 %s/%s · lineup_events %s행(최대 %s명)",
          r["id"], r["away"], r["home"],
          f"{r['starts_at']:%H:%M}Z", r["lineup_status"],
          r["away_pitcher"] or "-", r["home_pitcher"] or "-",
          r["ev_rows"], r["ev_max"])
    od = await pool.fetch(
        """SELECT provider, count(DISTINCT game_id) AS games,
                  round(extract(epoch FROM now() - max(captured_at))/60) AS age_min
             FROM odds_snapshots o JOIN games g ON g.id=o.game_id
            WHERE g.sport=$1 AND o.captured_at > now() - interval '12 hours'
            GROUP BY provider""", sport)
    for r in od:
        flag = " ⚠️나이 60분 초과" if (r["age_min"] or 0) > 60 else ""
        L("[rehearsal] 배당 %s — %s경기 · 최신 %s분 전%s",
          r["provider"], r["games"], r["age_min"], flag)
    if not od:
        L("[rehearsal] 배당 — 12시간 내 적재 0건")
    return [dict(r) for r in rows]


# ═════════════════ 2단계. 재료 조립 ═════════════════

#: 라인업 공시 **전에도 차 있어야** 하는 자료. 비면 결함이다.
REQUIRED_BEFORE_LINEUP = ("1박스", "7선발시즌", "8타선시즌", "9불펜")
#: 공시 전에는 비는 게 정상인 자료.
OK_TO_BE_EMPTY = ("3타순",)


def material_flags(jg: dict) -> dict[str, bool]:
    from app.engine import matchup as M

    return {"1박스": bool(M.boxscore_payload(jg)),
            "3타순": bool(M.lineups_payload(jg)),
            "7선발시즌": bool(M.starters_season_payload(jg)),
            "8타선시즌": bool(M.lineup_season_payload(jg)),
            "9불펜": bool(M.bullpen_payload(jg))}


def stage2(games: list[dict]) -> list[dict]:
    L("[rehearsal] ── 2단계 재료 조립 (자료 Y/N) ──")
    out = []
    for jg in games:
        f = material_flags(jg)
        missing_required = [k for k in REQUIRED_BEFORE_LINEUP if not f[k]]
        L("[rehearsal] [materials] game=%s %s — %s%s",
          jg.get("game_id"), jg.get("away"),
          " ".join(f"{k}={'Y' if v else 'N'}" for k, v in f.items()),
          f"  🔴 공시무관 재료 결손: {missing_required}" if missing_required else "")
        out.append({"game_id": jg.get("game_id"), "flags": f,
                    "missing": missing_required})
    return out


# ═════════════════ 3~4단계. 판정·게이트 ═════════════════

async def stage34(games: list[dict]) -> list[dict]:
    L("[rehearsal] ── 3·4단계 판정 결과와 게이트 ──")
    from app.config import get_settings
    from app.engine.deepsearch import _gate_threshold

    s = get_settings()
    out = []
    for jg in games:
        m = jg.get("matchup") or {}
        p = m.get("p_home")
        fav = m.get("우세")
        if p is None:
            L("[rehearsal] game=%s 판정 없음 — %s", jg.get("game_id"),
              jg.get("judgement_skip") or jg.get("judgement_void") or "사유 미기록")
            out.append({"game_id": jg.get("game_id"), "p_home": None})
            continue
        ours = float(p) if fav == "home" else 1.0 - float(p)
        need = _gate_threshold(jg.get("sport") or "", fav, s)
        odds_on = bool(jg.get("odds") or jg.get("market_prob") is not None)
        L("[rehearsal] game=%s %s p_home=%.2f 우세=%s 확신도=%s | "
          "확률게이트 %.2f vs 필요 %.2f → %s | 가치게이트 %s",
          jg.get("game_id"), jg.get("away"), float(p), fav, m.get("확신도"),
          ours, need, "통과" if ours >= need else "탈락",
          "대상" if odds_on else "skip(배당 없음)")
        for i, b in enumerate(m.get("근거") or [], 1):
            L("[rehearsal]   근거%d: %s", i, b)
        out.append({"game_id": jg.get("game_id"), "p_home": float(p),
                    "favored": fav, "conf": m.get("확신도"), "ours": ours,
                    "need": need, "pass": ours >= need, "odds": odds_on})
    return out


# ═════════════════ 5단계. 감시 3층 (기록 없음) ═════════════════

async def stage5(rredis, games: list[dict]) -> dict:
    """L1 전건 · L2·L3 2건. **DB 에 쓰지 않는다** — 로그로만 낸다."""
    L("[rehearsal] ── 5단계 감시 3층 (기록 없음) ──")
    from app.engine.fact_audit import PROMPT_KEY, audit

    tot = {"verified": 0, "derived": 0, "not_found": 0, "mismatch": 0}
    judged = []
    for jg in games:
        m = jg.get("matchup") or {}
        if m.get("p_home") is None:
            continue
        gid = jg.get("game_id")
        prompt = await rredis.get(PROMPT_KEY.format(game_id=gid))
        if not prompt:
            L("[rehearsal] L1 game=%s 프롬프트 보관 없음 — 대조 불가", gid)
            continue
        res = audit(m, prompt)
        tot["verified"] += res.get("verified_n", 0)
        tot["derived"] += res.get("derived_n", 0)
        tot["not_found"] += res.get("not_found_n", 0)
        tot["mismatch"] += res.get("mismatch_n", 0)
        L("[rehearsal] L1 game=%s v=%s d=%s nf=%s m=%s (프롬프트 %d자)",
          gid, res.get("verified_n"), res.get("derived_n"),
          res.get("not_found_n"), res.get("mismatch_n"), len(prompt))
        for d in (res.get("mismatch_detail") or [])[:10]:
            L("[rehearsal] L1 상세 game=%s %s", gid,
              json.dumps(d, ensure_ascii=False))
        judged.append((jg, prompt))
    L("[rehearsal] L1 집계 verified=%(verified)s derived=%(derived)s "
      "not_found=%(not_found)s mismatch=%(mismatch)s", tot)

    # L2·L3 — 확신 높은 순 2건
    from app.llm.gemini import is_available

    panel = []
    if not is_available():
        L("[rehearsal] L2·L3 휴면 — GEMINI_API_KEY 없음")
        return {"l1": tot, "panel": panel}
    judged.sort(key=lambda x: abs(float((x[0].get("matchup") or {})["p_home"]) - 0.5),
                reverse=True)
    for jg, prompt in judged[:2]:
        panel.append(await _panel_one(jg, prompt))
    return {"l1": tot, "panel": panel}


async def _panel_one(jg: dict, materials: str) -> dict:
    from app.config import get_settings
    from app.engine.matchup import clip_p_home
    from app.engine.shadow_panel import (
        _is_valid, build_independent_prompt, build_reviewer_prompt,
    )
    from app.llm.gemini import generate, parse_json_lenient

    s = get_settings()
    gid = jg.get("game_id")
    m = jg.get("matchup") or {}
    out = {"game_id": gid, "objections": [], "p_main": float(m["p_home"])}

    t0 = time.monotonic()
    raw = await generate(build_reviewer_prompt(m, materials),
                         max_tokens=s.shadow_review_max_tokens)
    objs = parse_json_lenient(raw)
    objs = objs if isinstance(objs, list) else []
    L("[rehearsal] L2 game=%s 이의 %d건 (%.1fs)", gid, len(objs),
      time.monotonic() - t0)
    for o in objs[:5]:
        v = _is_valid(o, materials)
        out["objections"].append({"o": o, "valid": v})
        L("[rehearsal] L2 game=%s valid=%s %s", gid, v,
          json.dumps(o, ensure_ascii=False))

    t0 = time.monotonic()
    raw = await generate(build_independent_prompt(materials),
                         max_tokens=s.shadow_judge_max_tokens)
    d = parse_json_lenient(raw)
    if isinstance(d, dict) and d.get("p_home") is not None:
        ps = clip_p_home(float(d["p_home"]))
        div = abs(out["p_main"] - ps)
        out.update(p_shadow=ps, divergence=round(div, 3))
        L("[rehearsal] L3 game=%s 주심=%.2f 독립=%.2f 편차=%.3f (임계 %.2f) %s "
          "(%.1fs) 근거=%s", gid, out["p_main"], ps, div, s.shadow_diverge_pp,
          "초과" if div >= s.shadow_diverge_pp else "이내",
          time.monotonic() - t0, d.get("한줄근거"))
    else:
        L("[rehearsal] L3 game=%s 계약 위반 raw=%r", gid, (raw or "")[:200])
    return out


# ═════════════════ 6단계. 재판정 경로 시뮬레이션 ═════════════════

async def stage6(rredis, jg: dict) -> dict:
    """타순 9명 주입 → 확정 승격 → T6 → 재판정 판별. **격리 안에서만.**"""
    L("[rehearsal] ── 6단계 재판정 경로 (game=%s) ──", jg.get("game_id"))
    from app.engine.deepsearch import T6_FIRST_LINEUP, first_lineup_evidence
    from app.engine.pregame_push import lineup_confirmed

    # ⚠️ T6 가 보는 곳은 `jg["research"]["{side}_lineup"]["order"]` 다
    #    (`first_lineup_evidence` 원문 확인). 껍데기 dict 가 아니라 **안에
    #    실제 타순이 있는지**를 본다 — 그래서 직전도 같은 모양으로 만든다.
    r0 = jg.get("research") or {}
    prev = {"research": {f"{s_}_lineup": dict(r0.get(f"{s_}_lineup") or {})
                         for s_ in ("home", "away")}}
    have = {s_: len((prev["research"][f"{s_}_lineup"] or {}).get("order") or [])
            for s_ in ("home", "away")}
    fake = [f"선수{i}(내야수)" for i in range(1, 10)]
    L("[rehearsal] 주입 전 lineup_status=%s · 직전 타순 home %d명 / away %d명",
      jg.get("lineup_status"), have["home"], have["away"])

    sim = dict(jg)
    sim["lineup_status"] = "confirmed"
    sim["research"] = dict(r0)
    for s_ in ("home", "away"):
        sim["research"][f"{s_}_lineup"] = {"order": list(fake)}
    conf = lineup_confirmed(fake, fake, None)
    L("[rehearsal] 9명 규칙 lineup_confirmed(9,9) = %s", conf)

    t6 = first_lineup_evidence(sim, prev)
    L("[rehearsal] T6 판별 = %s (%s)", t6,
      T6_FIRST_LINEUP if t6 else "미발동 — 직전에 이미 타순이 있었다")
    return {"game_id": jg.get("game_id"), "confirmed_rule": conf, "t6": bool(t6)}


# ═════════════════ 실행 ═════════════════

async def run(pool, inner_redis) -> None:
    """17:00 KST 이후에는 돌지 않는다 — 실슬레이트가 더 좋은 프로브다."""
    from datetime import datetime

    from zoneinfo import ZoneInfo

    from app.pipeline import today_kst

    try:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
    except Exception:
        now = None
    if now is not None and now.hour >= 17:
        L("[rehearsal] 17:00 KST 이후 — 리허설 생략, 실슬레이트 관측 우선")
        return

    date = today_kst()
    rredis = RehearsalRedis(inner_redis)
    guards = _install_guards()
    try:
        report = {}
        for sport in ("kbo", "npb"):
            rows = await stage1(pool, sport, date)
            if not rows:
                L("[rehearsal] %s 오늘 미시작 경기 0건 — 건너뛴다", sport)
                continue
            L("[rehearsal] %s build_analysis 시작 (격리 키) — 판정 유료 호출 발생",
              sport.upper())
            t0 = time.monotonic()
            from app.pipeline import build_analysis

            analysis = await build_analysis(pool, sport, date, redis=rredis,
                                            sequential_research=True)
            games = (analysis or {}).get("games") or []
            L("[rehearsal] %s build_analysis 완료 %d경기 (%.0f초)",
              sport.upper(), len(games), time.monotonic() - t0)
            stage2(games)
            await stage34(games)
            report[sport] = await stage5(rredis, games)
            if games:
                await stage6(rredis, games[0])
        L("[rehearsal] 발송 캡처 %d건 (실발송 0건)", guards["sent"]["n"])
    except Exception as exc:
        logger.error("[rehearsal] 실패: %r", exc, exc_info=True)
    finally:
        _remove_guards(guards)
        left = await _cleanup(inner_redis)
        L("[rehearsal] ══ 종료 · 격리 잔여 키 %s ══", left)


def _install_guards() -> dict:
    """발송·기록 경로를 **막는다.** 원래 함수는 돌려놓기 위해 보관한다."""
    import app.alerts as A
    import app.engine.pick_ledger as PL
    import app.notify as N
    import app.pipeline as P

    sent = {"n": 0}

    async def capture(*a, **kw):
        sent["n"] += 1
        L("[rehearsal] 🚫 텔레그램 발송 차단 (캡처 %d건째)", sent["n"])
        return None

    async def no_record(*a, **kw):
        L("[rehearsal] 🚫 pick_ledger 기록 차단")
        return {}

    # ⚠️ `alerts._send` 가 **모든 텔레그램 전송의 목**이다 (20여 개 함수가
    #    전부 이걸 통과한다). 한 곳만 막으면 전부 막힌다.
    # 🔴 목이 **둘**이다. `alerts._send`(운영 알림)와
    #    `notify.send_telegram`(카드 발송). 하나만 막으면 다른 쪽으로 나간다.
    saved = {"send": A._send, "tg": N.send_telegram,
             "record": PL.record_analysis,
             "audit": getattr(P, "_spawn_fact_audit", None)}
    A._send = capture
    N.send_telegram = capture
    PL.record_analysis = no_record
    if saved["audit"] is not None:
        P._spawn_fact_audit = lambda *a, **kw: None
    return {"sent": sent, "saved": saved}


def _remove_guards(g: dict) -> None:
    import app.alerts as A
    import app.engine.pick_ledger as PL
    import app.pipeline as P

    import app.notify as N

    s = g["saved"]
    A._send = s["send"]
    N.send_telegram = s["tg"]
    PL.record_analysis = s["record"]
    if s["audit"] is not None:
        P._spawn_fact_audit = s["audit"]
    L("[rehearsal] 가드 해제 — 실경로 복원")
