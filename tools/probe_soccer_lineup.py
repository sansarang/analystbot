"""[축구 조사] 라인업 리드타임 + 레이트리밋 실측 프로브 — **읽기 전용**.

승인 조건 2·3의 측정 도구다 (docs/SOCCER_FORM.md 부록 B).

  ① `starters`·`unavailable`이 킥오프 **몇 분 전에** 실제로 채워지는가
     → 지시문의 T-60분은 관행값이지 실측이 아니다. 20건이 모이기 전까지
       폴링 개시는 보수적으로 T-120분으로 둔다.
  ② 호출 간격별 응답(상태·소요시간)은 어떤가 → 레이트리밋 설계 근거.

⚠️ **프로덕션에 아무것도 쓰지 않는다.** Redis·DB를 건드리지 않고
   결과를 로컬 JSONL로만 남긴다. 축구·야구 파이프라인 코드도 읽지 않는다.

⚠️ 경기당 라인업이 관측되면 **그 경기 폴링을 멈춘다.** 답을 얻은 뒤에도
   계속 때리는 것은 비공식 API에 대한 예의가 아니고, 차단을 부른다.

사용:
    python tools/probe_soccer_lineup.py --out probe.jsonl
    python tools/probe_soccer_lineup.py --lead-start 150 --interval 600
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")

# FotMob 리그 id — 실측 확인 (2026-08-31)
LEAGUES = {"EPL": 47, "SerieA": 55, "LaLiga": 87, "PrimeiraLiga": 61}

LEAGUE_URL = "https://www.fotmob.com/api/data/leagues"
MATCH_URL = "https://www.fotmob.com/api/data/matchDetails"


def _print_log(msg: str) -> None:
    print(f"[{datetime.now(KST):%m/%d %H:%M:%S} KST] {msg}", flush=True)


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> tuple:
    """(status, elapsed_ms, json|None). 예외도 값으로 돌려준다 — 프로브가 죽지 않게."""
    t0 = time.monotonic()
    try:
        r = await client.get(url, params=params)
        ms = int((time.monotonic() - t0) * 1000)
        try:
            return r.status_code, ms, r.json()
        except ValueError:
            return r.status_code, ms, None
    except Exception as exc:                      # 네트워크 실패도 측정값이다
        return f"ERR {type(exc).__name__}", int((time.monotonic() - t0) * 1000), None


async def upcoming(client: httpx.AsyncClient, hours: int, log=None) -> list[dict]:
    """앞으로 `hours` 시간 안에 시작하는 4리그 경기."""
    log = log or _print_log
    now = datetime.now(UTC)
    out = []
    for name, lid in LEAGUES.items():
        st, ms, j = await _get(client, LEAGUE_URL, {"id": lid})
        log(f"리그 {name}: {st} {ms}ms")
        if not isinstance(j, dict):
            continue
        for m in (j.get("fixtures") or {}).get("allMatches") or []:
            s = m.get("status") or {}
            if s.get("finished") or not s.get("utcTime"):
                continue
            try:
                ko = datetime.fromisoformat(s["utcTime"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if now <= ko <= now + timedelta(hours=hours):
                out.append({"league": name, "match_id": int(m["id"]), "kickoff": ko,
                            "home": m["home"]["name"], "away": m["away"]["name"]})
        await asyncio.sleep(2)
    out.sort(key=lambda x: x["kickoff"])
    return out


def _lineup_state(j: dict) -> dict:
    """matchDetails → 라인업 관측 상태. 스키마가 바뀌면 전부 0으로 떨어진다."""
    lu = ((j.get("content") or {}).get("lineup") or {}) if isinstance(j, dict) else {}
    out = {"lineup_type": lu.get("lineupType"), "source": lu.get("source")}
    for side in ("homeTeam", "awayTeam"):
        t = lu.get(side) or {}
        out[f"{side}_starters"] = len(t.get("starters") or [])
        out[f"{side}_unavailable"] = len(t.get("unavailable") or [])
        out[f"{side}_formation"] = t.get("formation")
    out["has_starters"] = out["homeTeam_starters"] >= 11 and out["awayTeam_starters"] >= 11
    out["has_unavailable"] = (out["homeTeam_unavailable"] + out["awayTeam_unavailable"]) > 0
    # 🔴 **예상 라인업과 확정 라인업을 가른다.**
    #    실측 2026-08-31: 킥오프 10시간 전에 이미 starters=11 이 잡히는데
    #    `lineupType`이 'predicted'다. 종료 경기는 'standard'였다.
    #    이 구분 없이 starters>=11 만 보면 리드타임을 T-600으로 잘못 재고,
    #    거기서 폴링을 멈춰 **진짜 확정 시점을 영영 못 본다.**
    #    수동 프로토콜의 "예상 라인업은 참고만, 확정과 구분 표기"와 같은 규율이다.
    out["has_confirmed"] = bool(
        out["has_starters"] and out["lineup_type"]
        and out["lineup_type"] != "predicted")
    return out


async def run(*, hours: int = 30, lead_start: int = 150, interval: int = 600,
              emit=None, log=None) -> dict:
    """프로브 본체. CLI와 스케줄러 잡이 **같은 코드**를 쓴다.

    emit(record) — 관측 1건을 어디에 남길지. CLI는 JSONL 파일, 서버 잡은
                   구조화 로그 라인. 두 경로가 갈라지면 숫자를 믿을 수 없다.
    log(msg)     — 사람이 읽는 진행 로그.
    """
    emit = emit or (lambda rec: None)
    log = log or _print_log
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as client:
        games = await upcoming(client, hours, log)
        if not games:
            log("대상 경기 없음 — 종료")
            return {"observed": [], "targets": 0}
        log(f"대상 {len(games)}경기")
        for g in games:
            log(f"  {g['kickoff'].astimezone(KST):%m/%d %H:%M} KST "
                f"{g['away']} @ {g['home']} [{g['league']}] id={g['match_id']}")
        pending = {g["match_id"]: g for g in games}
        done: dict[int, dict] = {}
        while pending:
            now = datetime.now(UTC)
            for mid in [m for m, g in pending.items() if now > g["kickoff"]]:
                g = pending.pop(mid)
                log(f"  킥오프 경과 — 관측 종료 {g['away']} @ {g['home']} (미관측)")
            due = [g for g in pending.values()
                   if now >= g["kickoff"] - timedelta(minutes=lead_start)]
            for g in due:
                st, ms, j = await _get(client, MATCH_URL, {"matchId": g["match_id"]})
                lead = round((g["kickoff"] - datetime.now(UTC)).total_seconds() / 60, 1)
                rec = {"at": datetime.now(UTC).isoformat(timespec="seconds"),
                       "league": g["league"], "match_id": g["match_id"],
                       "home": g["home"], "away": g["away"],
                       "kickoff": g["kickoff"].isoformat(),
                       "lead_min": lead, "status": st, "elapsed_ms": ms}
                if isinstance(j, dict):
                    rec.update(_lineup_state(j))
                emit(rec)
                flag = f"[{rec.get('lineup_type')}]"
                flag += (" 선발O" if rec.get("has_starters") else " 선발-")
                flag += ("/결장O" if rec.get("has_unavailable") else "/결장-")
                log(f"  T-{lead:6.1f}m {g['away']} @ {g['home']}: {st} {ms}ms {flag}")
                if rec.get("has_confirmed"):
                    done[g["match_id"]] = rec
                    pending.pop(g["match_id"], None)
                    log(f"  확정 라인업 관측 — 리드타임 T-{lead:.1f}분 "
                        f"({g['away']} @ {g['home']}, type={rec.get('lineup_type')})")
                await asyncio.sleep(3)
            if pending:
                await asyncio.sleep(interval)
        log(f"관측 완료 {len(done)}건 / 대상 {len(games)}건")
        for r in done.values():
            log(f"  {r['league']:<13} T-{r['lead_min']:.1f}분  {r['away']} @ {r['home']}"
                f"  source={r.get('source')}")
        if done:
            leads = sorted(r["lead_min"] for r in done.values())
            mid = len(leads) // 2
            med = leads[mid] if len(leads) % 2 else (leads[mid - 1] + leads[mid]) / 2
            log(f"리드타임 중앙값 T-{med:.1f}분 (최소 {leads[-1]:.1f} · 최대 {leads[0]:.1f})")
            log("표본 20 미만이면 관행값을 바꾸지 마라 — 야구와 같은 규율이다.")
        return {"observed": list(done.values()), "targets": len(games)}


async def main() -> int:
    ap = argparse.ArgumentParser(description="축구 라인업 리드타임·레이트리밋 프로브")
    ap.add_argument("--out", default="probe_soccer.jsonl")
    ap.add_argument("--hours", type=int, default=30)
    ap.add_argument("--lead-start", type=int, default=150)
    ap.add_argument("--interval", type=int, default=600)
    args = ap.parse_args()
    f = open(args.out, "a", encoding="utf-8")

    def emit(rec: dict) -> None:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()

    try:
        await run(hours=args.hours, lead_start=args.lead_start,
                  interval=args.interval, emit=emit)
    finally:
        f.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
