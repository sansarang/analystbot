"""[스모크] 리그별 전 구간 완주를 **기계로 판정**한다.

🔴 왜 (2026-09-07 사용자 지시): "구현돼 있다"를 코드 존재로 주장해 왔다.
   0단계 감사에서 실제로 드러난 것 —
     · 감시 L2·L3 가 **전 기간 0행**이었다(`judge_review`·`shadow_panel`).
     · `lineups` 표에 MLB 558행뿐, KBO·NPB 0행이었다.
     · 타순 0명인데 `confirmed` 로 올라가 유료 최종이 재료 없이 나갔다.
   셋 다 코드는 있었다. **돌려보지 않아서 몰랐다.**

10단계를 경기 1건마다 PASS/FAIL 로 판정한다:
  ① 수집   — 자료별 행수 > 0
  ② 조립   — [materials] 전 자료 Y 또는 **정상 공백**(사유가 있는 N)
  ③ 렌더   — 프롬프트에 자리표시자 `{{...}}` 잔여 0
  ④ 판정   — JSON 계약 · 클립(0.32~0.68) · 변수 형식
  ⑤ 시장   — `p_market` 새김. 없으면 **사유가 남는지**가 PASS 기준
  ⑥ 게이트 — 확률·시장동의·가치·거부권 4종의 판정값이 나오는가
  ⑦ 카드   — `verdict_block` 렌더 · 결론 문단 · 시장 줄
  ⑧ 원장   — `pick_ledger` 에 넣을 형태가 만들어지는가(**기록은 안 한다**)
  ⑨ L1     — 사실 감시 집계가 나오는가
  ⑩ 안정성 — 같은 재료 2회 호출 → **우세 방향 동일**

⚠️ 격리: `tools/rehearsal` 의 것을 그대로 쓴다 — 접두 키·발송 2중 차단·
   `pick_ledger`/`judgement_audit` 미기록·종료 시 전량 삭제. 두 벌 만들면
   한 벌이 샌다.
⚠️ **실캐시를 쓰지 않는다.** 슬레이트 캐시가 비어 있으면(휴식일) 재료를
   새로 모은다 — 그것이 이 스모크의 목적이다.
⚠️ 판정 설계(프롬프트 규칙·게이트 값)를 바꾸지 않는다. 읽고 판정만 한다.

사용법:
    PYTHONPATH=. uv run python tools/smoke_e2e.py --sport kbo --date 2026-09-08
    PYTHONPATH=. uv run python tools/smoke_e2e.py --sport kbo,npb,mlb --limit 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)
L = logger.info

#: 10단계. 순서가 곧 파이프라인 순서다.
STEPS = ("①수집", "②조립", "③렌더", "④판정", "⑤시장",
         "⑥게이트", "⑦카드", "⑧원장", "⑨L1", "⑩안정성")

#: **조건부 자료** — 비어 있는 것이 정상일 수 있다. FAIL 로 세지 않는다.
#  자료10: 선발 표본이 두꺼우면 `해당없음`(`variable_ref.attach_material10`)
#  자료11: 최근 경기 이력이 없으면 빈다
_OPTIONAL = frozenset({"자료10참조", "자료11맥락"})


class Result:
    """경기 1건의 단계별 판정. **사유 없는 FAIL 을 만들지 않는다.**"""

    def __init__(self, sport: str, gid, label: str):
        self.sport, self.gid, self.label = sport, gid, label
        self.steps: dict[str, tuple[bool, str]] = {}

    def ok(self, step: str, why: str = "") -> None:
        self.steps[step] = (True, why)

    def fail(self, step: str, why: str) -> None:
        self.steps[step] = (False, why)
        L("[smoke] 🔴 %s %s %s — %s", self.sport, self.label, step, why)

    def row(self) -> str:
        cells = []
        for s in STEPS:
            got = self.steps.get(s)
            cells.append("·" if got is None else ("O" if got[0] else "X"))
        return f"   {self.sport:5s} {self.label[:26]:26s} " + " ".join(cells)

    def fails(self) -> list[tuple[str, str]]:
        return [(s, w) for s, (o, w) in self.steps.items() if not o]


async def _slate(pool, sport: str, date: str) -> list[dict]:
    """그 날짜 슬레이트의 경기 행. 종목별 날짜 기준은 파이프라인이 원본이다."""
    # ⚠️ asyncpg 는 `$2::date` 로 문자열을 캐스팅해 주지 않는다 — `date` 객체를
    #    넘겨야 한다(실측: invalid input for query argument $2).
    from datetime import date as _date

    tz = "America/New_York" if sport == "mlb" else "Asia/Seoul"
    return [dict(r) for r in await pool.fetch(
        f"""SELECT id, sport, league, ext_id, home, away, starts_at, status,
                   home_pitcher, away_pitcher, lineup_status
              FROM games
             WHERE sport = $1
               AND (starts_at AT TIME ZONE '{tz}')::date = $2
             ORDER BY starts_at, id""", sport, _date.fromisoformat(date))]


async def run_game(pool, redis, rredis, sport: str, date: str,
                   jg: dict) -> Result:
    """경기 1건 완주. 어떤 예외도 다음 경기를 막지 않는다."""
    from app.engine.starter_recent import _aware

    res = Result(sport, jg.get("game_id"),
                 f"{(jg.get('away') or '')[:11]}@{(jg.get('home') or '')[:11]}")
    cutoff = _aware(jg.get("starts_at"))

    # ═══ ① 수집 — 자료별 행수 (build_analysis 가 이미 붙였다)
    #   🔴 **정상 공백을 FAIL 로 세지 않는다.** 자료10 은 조건부 자료다 —
    #      선발 표본이 두꺼우면 `해당없음` 이 정상이고, 그것을 결함으로 세면
    #      스모크가 거짓 FAIL 을 만든다(첫 실행에서 내가 그랬다).
    #      자료3(타순)도 라인업 공시 전이면 정상 공백이다(발송 규율).
    try:
        counts = _counts(jg)
        empty = [k for k, v in counts.items()
                 if not v and k not in _OPTIONAL]
        opt_empty = [k for k, v in counts.items()
                     if not v and k in _OPTIONAL]
        why = str(counts) + (f" · 정상공백 {opt_empty}" if opt_empty else "")
        if empty:
            res.fail(STEPS[0], f"행수 0: {', '.join(empty)} · 전체 {counts}")
        else:
            res.ok(STEPS[0], why)
    except Exception as exc:
        res.fail(STEPS[0], f"{type(exc).__name__}: {exc}")
        return res

    # ═══ ② 조립 — [materials] 형태
    try:
        mats = _materials(jg)
        res.ok(STEPS[1], mats) if "🔴" not in mats else res.fail(STEPS[1], mats)
    except Exception as exc:
        res.fail(STEPS[1], f"{type(exc).__name__}: {exc}")

    # ═══ ③ 렌더 — 자리표시자 잔여
    prompt = ""
    try:
        from app.engine.matchup import (boxscore_payload, news_payload,
                                        render_matchup_prompt)
        prompt = render_matchup_prompt(jg, boxscore_payload(jg),
                                       news_payload({}, {}, jg), None)
        left = re.findall(r"\{\{[A-Z_]+\}\}", prompt)
        if left:
            res.fail(STEPS[2], f"자리표시자 잔여 {left}")
        else:
            res.ok(STEPS[2], f"{len(prompt)}자")
    except Exception as exc:
        res.fail(STEPS[2], f"{type(exc).__name__}: {exc}")
        return res

    # ═══ ④ 판정 — 계약 검사
    m = {}
    try:
        m = await _judge(jg, rredis, date)
        bad = _verdict_violations(m, sport)
        res.fail(STEPS[3], " · ".join(bad)) if bad else \
            res.ok(STEPS[3], f"p={m.get('p_home')} 우세={m.get('우세')}")
    except Exception as exc:
        res.fail(STEPS[3], f"{type(exc).__name__}: {exc}")

    # ═══ ⑤ 시장 — 값 또는 사유
    snap = {}
    try:
        from app.engine.market_baseline import CLOSE, p_market
        snap = await p_market(pool, {"id": jg.get("game_id"), "sport": sport,
                                     "home": jg.get("home"),
                                     "away": jg.get("away"),
                                     "starts_at": cutoff}, purpose=CLOSE)
        if snap.get("p") is not None:
            res.ok(STEPS[4], f"p_market={snap['p']} ({snap.get('provider')})")
        elif snap.get("reason"):
            res.ok(STEPS[4], f"값 없음 · 사유={snap['reason']} (구조적 한계)")
        else:
            res.fail(STEPS[4], "값도 사유도 없다 — 조용한 0")
    except Exception as exc:
        res.fail(STEPS[4], f"{type(exc).__name__}: {exc}")

    # ═══ ⑥ 게이트 4종
    try:
        g = _gates(jg, m, snap)
        miss = [k for k, v in g.items() if v is None]
        res.fail(STEPS[5], f"판정값 없음: {miss}") if miss else \
            res.ok(STEPS[5], json.dumps(g, ensure_ascii=False))
    except Exception as exc:
        res.fail(STEPS[5], f"{type(exc).__name__}: {exc}")

    # ═══ ⑦ 카드
    try:
        from app.engine.card import verdict_block
        jg["p_claude"] = m.get("p_home")
        jg["matchup"] = m
        block = verdict_block(jg)
        if not block:
            res.fail(STEPS[6], "판정 블록이 비었다")
        elif not any("갈림길" in x or (m.get("결론") or {}).get("판단", "")[:8] in x
                     for x in block):
            res.fail(STEPS[6], "결론 문단·갈림길이 카드에 없다")
        else:
            res.ok(STEPS[6], f"{len(block)}줄")
            res.card = "\n".join(block)
    except Exception as exc:
        res.fail(STEPS[6], f"{type(exc).__name__}: {exc}")

    # ═══ ⑧ 원장 형태 (기록은 하지 않는다)
    try:
        need = ("p_home", "우세", "확신도")
        miss = [k for k in need if m.get(k) in (None, "")]
        res.fail(STEPS[7], f"원장 필수 필드 없음: {miss}") if miss else \
            res.ok(STEPS[7], "형태 정상 (미기록)")
    except Exception as exc:
        res.fail(STEPS[7], f"{type(exc).__name__}: {exc}")

    # ═══ ⑨ L1 사실 감시
    try:
        from app.engine.fact_audit import audit
        from app.engine.starter_recent import pitcher_name
        names = {pitcher_name(jg, s): s for s in ("home", "away")
                 if pitcher_name(jg, s)}
        a = audit(m, prompt, names=names or None)
        res.ok(STEPS[8], f"v={a['verified_n']} d={a['derived_n']} "
                         f"nf={a['not_found_n']} m={a['mismatch_n']}")
        res.l1 = a
    except Exception as exc:
        res.fail(STEPS[8], f"{type(exc).__name__}: {exc}")

    # ═══ ⑩ 안정성 — 같은 재료 2회
    try:
        from app.engine.matchup import FINAL_KEY
        await rredis.delete(FINAL_KEY.format(sport=sport,
                                             game_id=jg.get("game_id"),
                                             date=date))
        jg2 = {**jg}
        jg2.pop("matchup", None)
        m2 = await _judge(jg2, rredis, date)
        same = (m.get("우세") == m2.get("우세"))
        spread = abs(float(m.get("p_home") or 0) - float(m2.get("p_home") or 0))
        (res.ok if same else res.fail)(
            STEPS[9], f"우세 {m.get('우세')} vs {m2.get('우세')} · "
                      f"p 산포 {spread * 100:.1f}%p")
    except Exception as exc:
        res.fail(STEPS[9], f"{type(exc).__name__}: {exc}")
    return res


async def build_slate(pool, rredis, sport: str, date: str) -> list[dict]:
    """**실제 수집 경로를 그대로 탄다.** 재구현하지 않는다.

    🔴 첫 스모크에서 내가 `_collect` 로 재료 부착을 손수 짰다가 자료1(usage)을
       빠뜨려 KBO 가 ①②④⑥⑦⑧ FAIL 로 나왔다. 어제 KBO 실판정은
       `[materials] 자료11=Y` 로 정상이었다 — **하네스 결함이었다.**
       파이프라인을 베끼면 베낀 쪽이 틀렸을 때 파이프라인을 의심하게 된다.
    ⚠️ `build_analysis` 는 판정까지 돌린다. 격리 redis 를 넘겨 실캐시를
       건드리지 않는다.
    """
    from app.pipeline import build_analysis

    out = await build_analysis(pool, sport, date, redis=rredis)
    return (out or {}).get("games") or []


def _counts(jg: dict) -> dict:
    """자료별 건수. 0 이면 ① FAIL 이다."""
    from app.engine import matchup as M

    r = jg.get("research") or {}
    return {
        "자료1박스": len((r.get("home_usage") or {}).get("games") or []),
        "자료4선발": len(M.starters_recent_payload(jg) or {}),
        "자료9불펜": len(M.bullpen_payload(jg) or {}),
        "자료10참조": 1 if M.material10_payload(jg) else 0,
        "자료11맥락": 1 if jg.get("material11") else 0,
        "자료12레이팅": 1 if M.elo_payload(jg) else 0,
    }


def _materials(jg: dict) -> str:
    """[materials] 한 줄. 정상 공백은 사유를 함께 적는다."""
    from app.engine import matchup as M

    slots = M.lineup_slots(jg) if hasattr(M, "lineup_slots") else 0
    if not slots:
        m3 = M.lineups_payload(jg)
        slots = min(len(((m3.get(s) or {}).get("타순") or []))
                    for s in ("home", "away")) if m3 else 0
    parts = [f"자료3={'Y' if slots >= 9 else 'N'}(타순 {slots}명)",
             f"자료4={'Y' if M.starters_recent_payload(jg) else 'N'}",
             f"자료9={'Y' if M.bullpen_payload(jg) else 'N'}",
             f"자료10={jg.get('material10_status') or '해당없음'}",
             f"자료11={'Y' if jg.get('material11') else 'N'}",
             f"자료12={'Y' if M.elo_payload(jg) else 'N'}"]
    # 자료3 은 라인업 공시 전이면 **정상 공백**이다(발송 규율: 1차는 타순 전에도).
    if not M.boxscore_payload(jg).get("home"):
        parts.append("🔴자료1 없음 — 판정 불가")
    return " ".join(parts)


async def _judge(jg: dict, rredis, date: str) -> dict:
    from app.engine.matchup import judge_matchup

    await judge_matchup(jg, rredis, date)
    return jg.get("matchup") or {}


def _verdict_violations(m: dict, sport: str) -> list[str]:
    """판정 JSON 계약. 위반을 문장으로 돌려준다."""
    from app.engine.matchup import check_flow
    from app.engine.variable_parse import parse_all

    bad = []
    p = m.get("p_home")
    if p is None:
        return ["p_home 없음 — 판정 실패"]
    if not (0.32 <= float(p) <= 0.68):
        bad.append(f"클립 위반 p={p}")
    for k in ("우세", "확신도", "근거"):
        if not m.get(k):
            bad.append(f"{k} 없음")
    rows = parse_all(m)
    unparsed = [r for r in rows if not r["parsed"]]
    if rows and unparsed:
        bad.append(f"변수 형식 위반 {len(unparsed)}/{len(rows)}")
    bad += check_flow(m, sport)
    return bad


def _gates(jg: dict, m: dict, snap: dict) -> dict:
    """게이트 4종의 **판정값**. None 이면 그 게이트가 답을 안 낸 것이다."""
    from app.config import get_settings
    from app.engine.deepsearch import _gate_threshold
    from app.pipeline import market_disagreement

    s = get_settings()
    p, fav = m.get("p_home"), m.get("우세")
    out: dict = {"확률": None, "시장동의": None, "가치": None, "거부권": None}
    if p is not None and fav in ("home", "away"):
        ours = float(p) if fav == "home" else 1.0 - float(p)
        out["확률"] = "통과" if ours >= _gate_threshold(jg["sport"], fav, s) \
            else "탈락"
    elif p is not None:
        out["확률"] = "박빙"
    out["시장동의"] = market_disagreement(
        {"p_market_send": snap.get("p"), "p_home": p}, s) or "동의"
    out["가치"] = "배당없음" if snap.get("p") is None else "산출가능"
    out["거부권"] = "행사" if m.get("확신도") == "하" else "미행사"
    return out


def report(results: list[Result], skipped: list[str] | None = None) -> bool:
    """보고하고 **통과 여부를 돌려준다.** 반환 False 면 종료 코드 1 이다.

    🔴 [SMK-1 2026-09-11] 종전에는 `ok == tot` 로 판정해서 **`tot` 이 0 이면
       0 == 0 이 참**이 됐다. 대상이 한 경기도 없는데 10단계 전부 `✅ 0/0
       PASS` 가 찍히고 "FAIL 원인: 없음" 이 붙었다 —
       실측 2026-09-11 13:37 (로컬 DB 에 오늘 슬레이트 없음, 운영에는 KBO 8건·
       NPB 3건이 있던 시각). **아무것도 검사하지 않고 전부 통과라고 말했다.**
       CLAUDE.md 5대 반복 결함의 "조용한 성공"(분모가 사라지는 실패)이다.

    ⚠️ 반대 위험: 정당하게 경기가 없는 날도 실패가 된다. 그래서 **무엇이
       0 이었는지**를 사유로 적는다 — 사람이 읽고 판단할 수 있어야 한다.
    """
    print("\n" + "=" * 78)
    print(f"   {'리그':5s} {'경기':26s} " + " ".join(s[0] for s in STEPS))
    for r in results:
        print(r.row())
    print("\n   범례: " + " · ".join(STEPS))
    tot = len(results)
    if tot == 0:
        print("   🔴 대상 0경기 — **아무것도 검사하지 않았다.** 통과가 아니다.")
    else:
        for i, s in enumerate(STEPS):
            got = [r.steps.get(s) for r in results]
            ok = sum(1 for g in got if g and g[0])
            na = sum(1 for g in got if g is None)
            mark = "✅" if ok == tot else ("🔴" if ok == 0 else "⚠️")
            print(f"   {mark} {s} {ok}/{tot} PASS"
                  + (f" · 미실행 {na}" if na else ""))
    print("\n── FAIL 원인 ──")
    any_fail = False
    for sp in (skipped or []):
        any_fail = True
        print(f"   {sp} 슬레이트 0경기 — 검사 대상이 없었다 "
              f"(휴식일인지 수집 실패인지 사람이 판단하라)")
    if tot == 0 and not skipped:
        any_fail = True
        print("   대상 0경기 — 검사 대상이 없었다")
    for r in results:
        for step, why in r.fails():
            any_fail = True
            print(f"   {r.sport} {r.label} {step}: {why}")
    if not any_fail:
        print("   없음")
    return not any_fail


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="kbo")
    ap.add_argument("--date", default="")
    ap.add_argument("--limit", type=int, default=0, help="0=전부")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        stream=sys.stdout)

    import redis.asyncio as R

    from app.config import get_settings
    from app.db import close_pool, get_pool
    from tools.rehearsal import (RehearsalRedis, _cleanup, _install_guards,
                                 _remove_guards)

    s = get_settings()
    pool = await get_pool()
    inner = R.from_url(s.redis_url, decode_responses=True)
    rredis = RehearsalRedis(inner)
    guards = _install_guards()
    results: list[Result] = []
    skipped: list[str] = []
    try:
        for sport in [x.strip() for x in args.sport.split(",") if x.strip()]:
            from app.pipeline import mlb_slate_date, today_kst
            date = args.date or (mlb_slate_date() if sport == "mlb"
                                 else today_kst())
            db_rows = await _slate(pool, sport, date)
            L("\n[smoke] ══ %s %s · DB %d경기 — 실제 수집 경로로 조립 ══",
              sport.upper(), date, len(db_rows))
            if not db_rows:
                L("[smoke] 🔴 %s %s 슬레이트 0경기 — 스모크 불가", sport, date)
                skipped.append(f"{sport} {date}")
                continue
            games = await build_slate(pool, rredis, sport, date)
            L("[smoke] build_analysis → %d경기 조립", len(games))
            if args.limit:
                games = games[:args.limit]
            for jg in games:
                t0 = time.monotonic()
                r = await run_game(pool, inner, rredis, sport, date, jg)
                L("[smoke] %s %s · %.0f초", sport, r.label,
                  time.monotonic() - t0)
                results.append(r)
    finally:
        _remove_guards(guards)
        left = await _cleanup(inner)
        L("\n[smoke] 격리 잔여 키 %s · 발송 캡처 %d건(실발송 0)",
          left, guards["sent"]["n"])
        await inner.aclose()
        await close_pool()
    # 🔴 [SMK-1] **종료 코드를 낸다.** 종전에는 무엇이 나와도 0 이라
    #    이 도구를 게이트에 걸 수 없었다.
    if not report(results, skipped):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
