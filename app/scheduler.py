"""스케줄러 — 운영의 주체.

🔴 **v4 단계 1**: 판정·발송·채점 주기를 걷어냈다. 지금 도는 것은 **수집**뿐이다.
   STEP 5~8(시나리오·생존·카드·채점)은 단계 6~8 에서 붙는다.

🔴 기동 시 **DB 스키마를 적용**한다(그래서 배포는 스케줄러가 먼저다).
🔴 슬레이트를 돌려 카드를 내고, 결과가 들어오면 채점한다.
🔴 **발송 스위치는 사용자만 켠다** — 꺼져 있으면 카드를 만들고 보내지 않는다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from app import secrets_mask, tg, version
from app.cells import DEEP, WAKE, SourceScores
from app.cells import Q_LINEUP
from app.collect.ingest import ADAPTERS, collect, roster
from app.config import SLATE_DAYS, get_settings
from app.db import get_pool
from app.net import Net
from app.search import build_chain
from app.run import collect_slate
from app.sources import DbSources, persist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")
# 🔴 **로그 필터를 로깅 설정 바로 뒤에 건다**(§SEC). 이 줄이 없으면 그때까지의
#    모든 로그에 API 키가 평문으로 남는다 — 실사고 2026-09-07 이 그것이었다.
#    ⚠️ 단계 3 은 **라이브 검색을 처음 돌리는** 단계다. 안 걸려 있으면 그때 샌다
#       (사용자 결정 2026-09-30: 안전장치 4건을 단계 3 에서 잇는다).
secrets_mask.install_log_filter()
logger = logging.getLogger("scheduler")

KST = timezone(timedelta(hours=9))

#: 슬레이트를 도는 주기. 🔴 원본은 여기 하나다 — 문서에 베끼지 않는다.
SLATE_INTERVAL_SEC = 15 * 60
COLLECT_INTERVAL_SEC = 20 * 60
#: 🔴 1b 로스터는 **아침 1회**다(§19-d 는 명단을 아침 1회로 둔다). 등번호가
#  들어와야 동명이인이 갈리고(§7-3), 그래야 결장이 상대 팀에 안 붙는다.
ROSTER_INTERVAL_SEC = 12 * 60 * 60
#: 🔴 **라인업 주기는 §19-d 가 정한다** — *"T-70분부터 5분 간격, T-10분까지."*
#  사본 금지: 숫자를 여기 적지 않고 `cells.WAKE` 에서 읽는다. 표를 고치면
#  스케줄러가 따라온다.
#  ⚠️ 20분(`COLLECT_INTERVAL_SEC`)으로는 60분 창에서 3번밖에 못 두드린다. 그
#     사이 라인업이 바뀌면 못 잡는다 — 그래서 **따로** 돈다.
LINEUP_INTERVAL_SEC = (WAKE[Q_LINEUP][1] or 5) * 60

#: 🔴🔴 **v5 §7-1 — T-60 재실행 주기.**
#
#  ⚠️ 창이 60분(야구 70분)이므로 그보다 촘촘해야 **창을 건너뛰지 않는다.**
#     🔴 라인업 주기와 같은 간격으로 둔다 — 그 세포가 이미 그 창에서 돌고 있고,
#        재실행은 그 결과를 **읽어 판정만** 한다(새로 긁지 않는다).
RERUN_INTERVAL_SEC = LINEUP_INTERVAL_SEC

#: 🔴 수집기 상태가 하루를 산다 — §19-e 점수표가 쌓여야 소스 순서가 고쳐진다.
_NET = Net()
_SCORES = SourceScores()
#: 🔴 사슬도 하루를 산다 — Google 일일 상한(100)을 세는 주체가 이것이다.
_SEARCH = build_chain()


def today_kst() -> date:
    return datetime.now(KST).date()


async def run_once(pool, day: date | None = None,
                   leagues: list[str] | None = None) -> dict:
    """슬레이트 한 번. 반환은 발송 결과 요약이다.

    🔴 **미발송은 전건에 사유가 붙는다**(조용한 0 금지).
    """
    s = get_settings()
    day = day or today_kst()
    leagues = leagues or list(s.slate_leagues)
    src = DbSources(pool)
    results: dict = {}

    # ── 수집 먼저. 🔴 DB 가 비면 판정이 전부 "미확인"이 된다(§5).
    #
    # 🔴 **당일과 그다음 날을 함께 쌓는다**(사용자 지시 2026-10-01).
    #    *"당일 날짜 및 그다음 날짜 터울은 하루 … 저장이 되어 있어야 한다"* —
    #    그래야 사용자가 물었을 때 **바로** 답하고, 미리 분석해 둘 수 있다.
    #    ⚠️ 내일 것은 **수집만** 한다 — 분석·발송은 그날 한다(§11-11 발송 off).
    got = await collect(pool, day, leagues, net=_NET, scores=_SCORES,
                        search=_SEARCH)
    results["collect"] = got["leagues"]
    for ahead in range(1, SLATE_DAYS):
        nxt = day + timedelta(days=ahead)
        try:
            more = await collect(pool, nxt, leagues, net=_NET, scores=_SCORES,
                                 search=_SEARCH)
            results[f"collect+{ahead}d"] = more["leagues"]
        except Exception as exc:                  # noqa: BLE001
            # 🔴 내일 수집이 실패해도 오늘을 멈추지 않는다 — 사유는 남긴다
            logger.exception("[run] %s 수집 실패: %s", nxt, exc)
            results[f"collect+{ahead}d"] = f"실패: {type(exc).__name__}"
    results["collect_unknowns"] = len(got["unknowns"])
    results["collect_notes"] = len(got.get("notes") or [])
    results["search"] = got.get("search")
    if got["unknowns"]:
        logger.info("[run] 수집 미확인 %d칸: %s", len(got["unknowns"]),
                    got["unknowns"][:5])
    # 🔴 답을 찾았지만 **버린 것**도 로그에 남긴다(리뷰 B3) — 조용한 0 금지
    if got.get("notes"):
        logger.info("[run] 찾았지만 버린 것 %d건: %s", len(got["notes"]),
                    got["notes"][:5])

    body, games = await collect_slate(day, leagues, src)
    for g in games:
        try:
            await persist(pool, g)
        except Exception as exc:                  # noqa: BLE001
            logger.exception("[run] game=%s 적재 실패: %s", g.game_id, exc)

    # 🔴 **발송하지 않는다.** v4 STEP 7 카드는 단계 8 이고, 발송 스위치는
    #    단계 9 전까지 off 다(§11-11). 지금 나가는 것은 수집 나열뿐이므로
    #    보내면 근거 없는 카드가 된다.
    results["slate"] = ("collected" if games else "skipped:오늘 슬레이트가 0경기다")

    unknown_total = sum(len(g.unknowns) for g in games)
    logger.info("[run] %s %s → %d경기 · 못 잰 칸 %d · %s",
                day, leagues, len(games), unknown_total, results["slate"])
    return {"day": str(day), "games": len(games), "unknowns": unknown_total,
            # 🔴 어떤 코드가 이 사이클을 돌렸나 — 26커밋 뒤처진 채로 돈 적이 있다
            "uptime": version.uptime_text(), **results}


async def roster_once(pool, leagues: list[str] | None = None) -> dict:
    """1b 로스터 — 🔴 **등번호가 들어오는 유일한 길이다.**

    §7-3: *"동명이인은 팀+등번호로 갈린다."* 이것이 안 돌면 `resolve_by_name` 이
    늘 `미상` 을 내고(등번호 없이는 동명이인을 못 가른다), 결장이 어느 팀에도
    안 붙는다.

    ⚠️ **어느 팀 로스터를 아직 못 읽었는지 이름으로 돌려준다**(조용한 0 금지).
    """
    s = get_settings()
    leagues = leagues or list(s.slate_leagues)
    year = today_kst().year
    out: dict = {}
    for league in leagues:
        mod = ADAPTERS.get(league)
        if mod is None or not hasattr(mod, "ROSTER_CODE"):
            out[league] = {"skipped": f"{league} 로스터 소스 미구현(§13)"}
            continue
        done, failed = 0, {}
        for team in sorted(mod.ROSTER_CODE):
            got = await roster(pool, league, team, year, net=_NET)
            if got.get("players"):
                done += 1
            else:
                failed[team] = got.get("failed") or got.get("skipped") or "0명"
        out[league] = {"teams": done, "failed": failed}
    logger.info("[roster] %s", out)
    return out


async def _loop(name: str, interval: int, fn) -> None:
    while True:
        try:
            await fn()
        except Exception:                          # noqa: BLE001
            logger.exception("[%s] 주기 실패", name)
        await asyncio.sleep(interval)


async def rerun_once(pool, *, now=None, leagues: list[str] | None = None,
                     day: date | None = None) -> dict:
    """🔴🔴 **§7-1 T-60 재실행** — 창에 든 경기마다 확정 XI 를 보고 판정한다.

    ══════════════════════════════════════════════════════════════════
    🔴 이 함수가 하는 것 · **안 하는 것**
    ══════════════════════════════════════════════════════════════════

    한다:
      · 창(킥오프 -60분 · 야구 -70분)에 든 경기를 고른다
      · 라인업 세포가 이미 받아 둔 XI 를 **읽는다**
      · 낡은 XI 를 거른다(§7-1 · 크로아티아 카드)
      · 상한을 정한다(받았으면 §6-5 칸 · 못 받았으면 **0.85 강제**)
      · **1회만** 표시하고 그 기억을 DB 에 적는다(R10)

    🔴 **안 한다**: 새로 긁지 않는다. 라인업 세포가 그 창에서 이미 돌고 있고
       (`LINEUP_INTERVAL_SEC`), 재실행이 또 긁으면 **같은 페이지를 두 배로**
       두드린다. ⚠️ 그래서 `ORDER` 의 세 통로는 **그 세포가** 쓰고 여기는
       무엇으로 받았는지만 적는다(`rerun_via`).

    반환은 경기마다 `{상태, 상한, 사유}`. 🔴 **건너뛴 경기도 들어간다**(#3).
    """
    from app import rerun, slate
    at = now or datetime.now(timezone.utc)
    day = day or today_kst()
    got = await slate.window(pool, day=day, days=2)
    out: dict = {"now": at.isoformat(), "games": {}, "due": 0, "skipped": 0}
    if not got.games:
        out["why"] = got.why
        return out
    for row in got.games:
        key = f"{row['away']} @ {row['home']}"
        if leagues and row.get("league") not in leagues:
            continue
        kick, sport = row["starts_kst"], str(row.get("sport") or "")
        if not rerun.due(kick, now=at, sport=sport):
            mins = (kick - at).total_seconds() / 60.0
            out["games"][key] = {
                "state": "skipped",
                "why": (f"창 밖이다({mins:.0f}분 뒤 · 창 "
                        f"{rerun.window_min(sport)}분)")}
            out["skipped"] += 1
            continue
        out["due"] += 1
        # 🔴 **이미 갱신했나** — 기억은 DB 에 있다(프로세스가 죽어도 남는다)
        done = await pool.fetchval(
            "SELECT rerun_at FROM sufficiency WHERE game_id = $1", row["id"])
        ok, why = rerun.may_update(done_at=done)
        if not ok:
            out["games"][key] = {"state": "done", "why": why}
            continue
        # 🔴 라인업 세포가 받아 둔 XI 를 **읽는다**(새로 긁지 않는다)
        xi = await _stored_xi(pool, row["id"])
        if not xi:
            no = rerun.without_xi()
            out["games"][key] = {"state": "no_xi", "cap": no.cap,
                                 "why": no.line(), "via": "none"}
            await _mark_rerun(pool, row["id"], via="none")
            continue
        fresh, fwhy = rerun.fresh_xi(xi, kickoff=kick)
        if not fresh:
            no = rerun.without_xi()
            out["games"][key] = {"state": "stale_xi", "cap": no.cap,
                                 "why": f"{fwhy} → {no.line()}", "via": "none"}
            await _mark_rerun(pool, row["id"], via="none")
            continue
        state = rerun.with_xi(both=bool(xi.get("both")),
                              verified=bool(xi.get("verified")))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§7-1 — §5~§6 을 재실행한다.** 상한만 바꾸는 것이 아니다.
        # ══════════════════════════════════════════════════════════════
        #
        #  > 가져오면 `lineup_state` 를 `confirmed` 로 올리고 **§5~§6 을 재실행**,
        #  > 카드 1회 갱신(R10).
        #
        #  ⚠️ 확정 XI 는 **변수를 바꾼다**(로테이션·결장이 사라지거나 생긴다).
        #     상한만 풀고 변수를 그대로 두면 카드가 **옛 변수에 새 상한**을 쓴다.
        #  🔴 그리고 **M2** 가 여기서 물린다 — 재실행에서 시나리오가 줄면 실패다.
        before_n = await pool.fetchval(
            "SELECT count(*) FROM scenarios WHERE game_id = $1", row["id"]) or 0
        again = await _rerun_card(pool, row, states_note=state.line())
        after_n = int(again.get("scenarios") or 0)
        ok2, why2 = rerun.check_scenarios(before=int(before_n), after=after_n)
        out["games"][key] = {"state": state.state, "cap": state.cap,
                             "why": state.line(),
                             "via": str(xi.get("via") or "adapter"),
                             "scenarios": f"{before_n} → {after_n}",
                             "m2": ok2, "m2_why": why2,
                             "card": again}
        if not ok2:
            # 🔴 **M2 실패** — 카드를 갱신하지 않는다. 사유가 남는다.
            logger.warning("[rerun] %s — %s", key, why2)
            continue
        await _mark_rerun(pool, row["id"], via=str(xi.get("via") or "adapter"))
    return out


async def _rerun_card(pool, row, *, states_note: str = "") -> dict:
    """🔴 그 경기의 **카드를 다시 만든다**(§5~§6 재실행).

    ⚠️ 새로 긁지 않는다 — `analyze.gather` 가 세포를 돌리지만 그 세포들이
       **카세트·블랙보드**를 공유하므로 창 안에서 두 번 긁지 않는다.
    🔴 **적재는 M2 를 통과한 뒤**다 — 호출부가 센다. 여기서는 만들어만 준다.
    """
    from app import analyze
    game = {"id": row["id"], "game_id": row["id"], "home": row["home"],
            "away": row["away"], "sport": row.get("sport"),
            "league": row.get("league"), "venue": row.get("venue"),
            "ext_id": row.get("ext_id"), "starts_kst": row["starts_kst"]}
    try:
        facts, states = await analyze.gather(game)
    except Exception as exc:                            # noqa: BLE001
        return {"error": repr(exc), "scenarios": 0}
    if states_note:
        states["§7-1 재실행"] = states_note
    card = analyze.build(facts, game, board=None, states=states)
    return {"facts": len(facts),
            "scenarios": len(card.scenarios.drafts) if card.scenarios else 0,
            "insufficient": card.insufficient,
            "incomplete": card.incomplete}


async def _stored_xi(pool, game_id: int) -> dict | None:
    """🔴 라인업 세포가 적어 둔 XI. ⚠️ 없으면 `None`(지어내지 않는다).

    🔴 `lineup` 종류의 사실을 읽는다 — 새 표를 만들지 않는다.
    """
    rows = await pool.fetch(
        "SELECT value FROM background WHERE game_id = $1 "
        "AND qtype = 'lineup' ORDER BY created_at DESC LIMIT 4", game_id)
    teams: dict[str, dict] = {}
    via = ""
    for r in rows:
        v = r["value"]
        if isinstance(v, str):
            import json
            try:
                v = json.loads(v)
            except ValueError:
                continue
        if not isinstance(v, dict) or not v.get("players"):
            continue
        teams[str(v.get("team") or "")] = v
        via = via or str(v.get("via") or "")
    if not teams:
        return None
    first = next(iter(teams.values()))
    return {"players": first.get("players"),
            "match_date": first.get("match_date"),
            "both": len(teams) >= 2,
            "verified": all(bool(t.get("verified")) for t in teams.values()),
            "via": via or "adapter"}


async def _mark_rerun(pool, game_id: int, *, via: str) -> None:
    """🔴 **1회 갱신을 기억한다**(R10). ⚠️ 줄이 없으면 만들지 않는다 —
    `sufficiency` 는 카드가 적는 표이고, 카드가 없으면 갱신할 것도 없다."""
    await pool.execute(
        "UPDATE sufficiency SET rerun_at = now(), rerun_via = $2 "
        "WHERE game_id = $1 AND rerun_at IS NULL", game_id, via)


async def main() -> None:
    s = get_settings()
    pool = await get_pool(s.database_url)

    # 🔴 스키마 적용은 기동 때 한 번. 배포 순서가 이것 때문에 스케줄러 먼저다.
    async with pool.acquire() as conn:
        from app.db import apply_schema
        await apply_schema(conn)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §8-1 — 쌓인 경기 열쇠 이관**(`849825` → `statsapi:849825`)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 어댑터는 이미 표준 꼴을 쓴다. 쌓인 행은 **그 전에** 들어왔다 —
    #     실측 2026-10-04 에 `games` 46행이 **46/46 비표준**이었고, 그래서
    #     카드가 *"출처를 못 읽어 깊이 소스를 고를 수 없다"* 를 적었다.
    #  🔴 멱등이다 — 이미 표준인 행은 건드리지 않는다(기동마다 안전하다).
    from app import keymigrate
    _mig = await keymigrate.run(pool)
    logger.info("[boot] 열쇠 이관 — %s", _mig.line())
    # 🔴 어떤 코드가 도는지 **기동 로그 첫 줄에** 남긴다(실사고 2026-08-25:
    #    봇이 26커밋 뒤처진 코드로 하루 넘게 돌았고 아무도 알 수 없었다).
    logger.info("%s", version.boot_line("scheduler"))
    if (stale := version.staleness_line()):
        logger.warning("%s", stale)
    logger.info("[boot] 스키마 적용 완료 · send_enabled=%s", s.send_enabled)
    # 🔴 §10-4 — **어느 게이트가 열려 있나**를 기동 첫 줄 근처에 남긴다.
    #    ⚠️ 안 적으면 *"무엇이 남았나"* 를 로그만 보고는 알 수 없다(#3).
    from app import rules as _rules
    for _n, _g in sorted(_rules.stage_gates().items()):
        logger.info("[boot] §10-4 게이트 %d %s — %s", _n, _g.get("state"),
                    _g.get("what"))

    await asyncio.gather(
        _loop("slate", SLATE_INTERVAL_SEC, lambda: run_once(pool)),
        # 🔴 1b 로스터 — 등번호 없이는 동명이인이 안 갈린다(§7-3)
        _loop("roster", ROSTER_INTERVAL_SEC, lambda: roster_once(pool)),
        # 🔴🔴 **§7-1 T-60 재실행** — 확정 XI 를 받아 카드를 **1회** 갱신한다.
        #    ⚠️ 이 주기가 없으면 확정 XI 를 영원히 안 받고 **모든 카드가 상한
        #       0.85 에 머문다**(§6-5·§7-1).
        _loop("rerun", RERUN_INTERVAL_SEC, lambda: rerun_once(pool)),
        # 🔴 §19-d — 라인업만 5분 간격. 🔴 **경기별 세포만** 돈다(`only=`) —
        #    공식 일정·순위 페이지를 5분마다 두드리지 않는다.
        _loop("lineup", LINEUP_INTERVAL_SEC,
              lambda: collect(pool, today_kst(), list(s.slate_leagues),
                              net=_NET, scores=_SCORES, search=_SEARCH,
                              only=(Q_LINEUP,))),
        # 🔴 §19-d — 라인업은 T-70분부터 5분 간격이다. 슬레이트 주기(15분)로는
        #    못 잡으므로 수집만 따로 돌린다.
        _loop("collect", COLLECT_INTERVAL_SEC,
              lambda: collect(pool, today_kst(), list(s.slate_leagues),
                              net=_NET, scores=_SCORES, search=_SEARCH)),
    )


async def _cli(argv: list[str]) -> int:
    """🔴 **1회성 태스크 입구.** 기억 *"서버가 주체 — 로컬 맥 의존 금지"* 대로
    저장소 스크립트가 아니라 **스케줄러 자신**이 부를 수 있어야 한다.

    ```
    python -m app.scheduler            상시 루프(배포가 부르는 것)
    python -m app.scheduler prekick    킥오프 전 녹음 1회
    python -m app.scheduler score      끝난 경기를 **실제 결과로** 채점 1회
    python -m app.scheduler card <팀>  카드 1장 — 🔴 발송은 스위치가 켜져야 나간다
    python -m app.scheduler roster     로스터 1회
    python -m app.scheduler forget <이름>
                                       🔴 **배운 별칭 하나를 지운다**(③ 자가 성장)
    ```
    ⚠️ `prekick` 을 **상시 루프에 붙이지 않았다** — 같은 경기를 주기마다 다시 녹음해
       디스크가 찬다(실측: 라이브 4회에 59MB). 중복 방지가 생기면 그때 붙인다.
    """
    s = get_settings()
    pool = await get_pool(s.database_url)
    cmd = (argv[1] if len(argv) > 1 else "").strip()
    if cmd == "forget":
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **배운 것을 되짚어 지운다**(③ 조건 셋 중 하나)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 출처(경기 ID)를 남겨서 **되짚어 지울 수 있게** 한다.
        #
        #  ⚠️ 자가 성장은 **오염이 조용히 쌓이는 자리**다. 지우는 길이 없으면
        #     틀린 별칭 하나가 영원히 남고, 그 팀 질문이 계속 엉뚱한 데로 간다.
        #  🔴 사람이 이 한 줄로 뺀다 — 코드를 고칠 일이 아니다.
        from app import learn_names
        name = (argv[2] if len(argv) > 2 else "").strip()
        if not name:
            print("지울 이름을 적어라: python -m app.scheduler forget <이름>")
            for k, row in learn_names.load().items():
                print(f"  {row.get('name')!r} → {row.get('key')} "
                      f"(경기 {row.get('from_match')})")
            return 1
        ok = learn_names.forget(name)
        print(f"{'지웠다' if ok else '그 이름은 배운 적이 없다'}: {name!r}")
        return 0 if ok else 1
    if cmd == "prekick":
        import json
        got = await record_prekickoff_once(pool)
        # 🔴 결과는 **로그와 표준출력 둘 다** — 1회성 태스크는 로그만 남는다
        print(json.dumps(got, ensure_ascii=False, indent=1, default=str))
        logger.info("[prekick] 끝 — 녹음 %d · 건너뜀 %d",
                    got["recorded"], got["skipped"])
        return 0
    if cmd == "score":
        # 🔴 **실제 결과로 채점한다** — 정답지가 아니라 경기가 기준이다
        #    (사용자 지시 2026-10-02: *"스포츠는 정답이 없는거다"*)
        import json

        from app import analyze
        got = await analyze.score_finished(pool)
        print(json.dumps(got, ensure_ascii=False, indent=1, default=str))
        logger.info("[score] 채점 %d · 건너뜀 %s", got["graded"], got["skipped"])
        return 0
    if cmd == "card":
        # 🔴 카드 한 장을 만들고 **보낸다** — 스위치가 꺼져 있으면 만들고 멈춘다
        #    (§11-11). ⚠️ 주기가 아니라 **1회성**이다.
        import json
        want = argv[2] if len(argv) > 2 else ""
        if not want:
            print("`python -m app.scheduler card <팀>` — 어느 경기인지 적어라")
            return 2
        from app import analyze
        got = await analyze.deliver(pool, team=want)
        print(json.dumps(got, ensure_ascii=False))
        logger.info("[card] 보냄=%s · %s", got["sent"], got["why"])
        return 0
    if cmd == "roster":
        print(await roster_once(pool))
        return 0
    if cmd:
        print(f"모르는 명령: {cmd!r} — prekick · score · card · roster 중 하나다")
        return 2
    await main()
    return 0




# ══════════════════════════════════════════════════════════════════
# 🔴 킥오프 **전** 녹음 — 단계 4 게이트를 정직하게 재려면 이것이 필요하다
# ══════════════════════════════════════════════════════════════════
#
# 사용자 지시 2026-10-02: *"게이트가 아직 빨갛다 … 구현해라"*
#
# ## 왜 필요한가 — 측정이 **구조적으로** 못 넘는 자리였다
#
# §9 단계 4 는 *"**경기 전 시점** 웹(카세트)에서 재현"* 을 요구한다. 그런데 우리가
# 가진 카세트는 **경기 뒤에** 녹음한 것이다. 순위·폼이 경기 결과를 이미 담고 있어서
#   · 그 값을 쓰면 **경기 후 자료**이고(§12-c-2 가 이제 거부한다)
#   · 거부하면 그 변수는 **못 찾은 것**이 된다
# 어느 쪽이든 재현율이 진짜가 아니다. 실측 2026-10-02: 29% → **14%**(값 다름 0).
#
# 🔴 **고치는 길은 하나다 — 킥오프 전에 녹음해 두는 것.** 그 뒤에는 같은 카세트로
#    몇 번이고 정직하게 잴 수 있다.
#
# ⚠️ **로컬 맥에 기대지 않는다**(기억: *"서버가 주체"*). 이것은 스케줄러 **1회성
#    태스크**이고 결과는 **로그로** 남는다.

#: 🔴 킥오프 **몇 분 전**까지 녹음을 받아들이나. v4 §19-d 가 라인업을 `T-70분` 부터
#   보라고 하므로 그보다 넉넉히 둔다 — 그 전이면 확정 XI 가 아직 없다.
PREKICK_WINDOW_MIN = 180


async def record_prekickoff_once(pool, *, within_min: int = PREKICK_WINDOW_MIN,
                                 day: date | None = None,
                                 leagues: list[str] | None = None) -> dict:
    """킥오프 전 경기를 **녹음**한다. 🔴 시작한 경기는 **건너뛴다** — 사유와 함께.

    반환은 경기마다 `{상태, 사실 수, 사유}`. 🔴 조용한 0 금지 — 건너뛴 경기도 들어간다.
    """
    import os

    from app import analyze, cassette, classify, slate
    now = datetime.now(timezone.utc)
    day = day or today_kst()
    got = await slate.window(pool, day=day, days=2)
    out: dict = {"now": now.isoformat(), "games": {}, "recorded": 0,
                 "skipped": 0}
    if not got.games:
        out["why"] = got.why
        return out

    # 🔴 **녹음 모드를 여기서만 켠다.** 끝나면 돌려놓는다 — 운영이 녹음 모드로
    #    남으면 디스크가 찬다(실측: 라이브 4회에 카세트가 59MB 가 됐다).
    before = {k: os.environ.get(k) for k in (cassette.MODE_ENV, cassette.DAY_ENV)}
    os.environ[cassette.MODE_ENV] = cassette.RECORD
    os.environ[cassette.DAY_ENV] = str(day)
    try:
        for row in got.games:
            key = f"{row['away']} @ {row['home']}"
            kick = row["starts_kst"]
            if leagues and row.get("league") not in leagues:
                continue
            mins = (kick - now).total_seconds() / 60.0
            if mins <= 0:
                # 🔴 **이미 시작했다 — 녹음해도 경기 후 자료다.** 건너뛴 이유를 남긴다
                out["games"][key] = {"state": "skipped",
                                     "why": f"이미 시작했다({-mins:.0f}분 지남)"}
                out["skipped"] += 1
                continue
            if mins > within_min:
                out["games"][key] = {"state": "skipped",
                                     "why": f"아직 멀다({mins:.0f}분 뒤 · 창 "
                                            f"{within_min}분)"}
                out["skipped"] += 1
                continue
            try:
                facts, states = await analyze.gather(
                    {"home": row["home"], "away": row["away"],
                     "league": row.get("league") or "",
                     "sport": row.get("sport") or "",
                     "game_id": row.get("id"), "kickoff": kick,
                     "ext_id": row.get("ext_id"), "venue": row.get("venue")},
                    mode=DEEP)
            except Exception as exc:                        # noqa: BLE001
                # 🔴 한 경기가 터져도 나머지를 녹음한다 — 사유를 남긴다
                out["games"][key] = {"state": "error", "why": repr(exc)}
                logger.warning("[prekick] %s 녹음 실패: %r", key, exc)
                continue
            # 🔴🔴 **카드를 저장한다** — 안 하면 쌓이는 것이 없다.
            #    전 판은 사실만 모으고 끝났다 → 경기가 끝난 뒤 채점이
            #    *"카드를 저장한 적이 없다"* 로 건너뛴다. 그러면 원장이 영원히 빈다.
            #    (사용자 지시 2026-10-02 *"뭘쌓는데???"* 가 가리킨 바로 그 자리다)
            game = classify.Game(home=row["home"], away=row["away"],
                                 sport=row.get("sport") or "",
                                 league=row.get("league") or "")
            card = analyze.build(facts, game, board=None, states=states)
            saved = None
            try:
                saved = await analyze.persist(pool, int(row["id"]), card)
            except Exception as exc:                        # noqa: BLE001
                # 🔴 적재가 실패해도 녹음은 남는다 — 사유를 적는다
                logger.warning("[prekick] %s 카드 적재 실패: %r", key, exc)
            out["games"][key] = {"state": "recorded", "facts": len(facts),
                                 "minutes_before": round(mins, 1),
                                 "cells": len(states),
                                 "insufficient": card.insufficient,
                                 "scenarios": len(card.scenarios.drafts)
                                 if card.scenarios else 0,
                                 "saved": saved}
            out["recorded"] += 1
            logger.info("[prekick] %s — 킥오프 %.0f분 전 · 사실 %d건",
                        key, mins, len(facts))
    finally:
        for k, v in before.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # 🔴 **어디에 녹음됐는지 로그에 남긴다** — 측정이 그 날짜를 지목해야 한다
    out["cassette_day"] = str(day)
    logger.info("[prekick] 녹음 %d · 건너뜀 %d · 카세트 날짜 %s (%s)",
                out["recorded"], out["skipped"], day, cassette.root())
    return out


# 🔴 **진입 블록은 파일 끝이다.** 중간에 두면 그 아래 정의가 아직 안 읽혀
#    `NameError` 가 난다(실측 2026-10-02: `prekick` 이 그렇게 터졌다).
if __name__ == "__main__":
    import sys
    raise SystemExit(asyncio.run(_cli(sys.argv)))
