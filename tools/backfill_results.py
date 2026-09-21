"""[W3-4 / wiring_first §W3-4] 결과 소급 적재 — FotMob 하루치를 날짜로 훑는다.

    python -m tools.backfill_results --days 60 --dry-run     # 먼저 이것
    python -m tools.backfill_results --days 60 --write       # 그 다음

🔴 **새 적재기를 만들지 않는다.** 적재 규칙(팀 매칭·점수 coalesce·conflict·
   `apply_result`)은 전부 `fotmob.upsert_slate` 그대로다. 이 도구가 하는 일은
   **날짜를 돌리는 것**뿐이다.

🔴 **날짜당 한 번만 받는다.** FotMob 하루치 목록은 한 번 받으면 전 리그가
   들어 있다(실측 541경기). 리그마다 다시 받으면 요청이 4배가 되고 그만큼
   차단 위험이 는다.

🔴 **차단 신호에 즉시 멈춘다.** 실제 날짜는 언제나 경기가 있으므로
   **연속 빈손**은 차단이다. 계속 두드리지 않는다.

⚠️ 요청 간격은 `fotmob._pace`(2초)가 이미 강제한다 — 여기서 다시 재지 않는다.
⚠️ 원본 JSON 을 날짜별로 캐시한다. 같은 날을 두 번 받지 않는다.
⚠️ 이름을 못 붙인 경기는 `upsert_slate` 이 **행을 만들지 않고** 로그를 남긴다.
   소급이라고 느슨해지지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import pathlib
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: 연속 빈손이 이만큼이면 멈춘다. 🔴 실제 날짜는 언제나 경기가 있다.
EMPTY_STOP = 3


def _cache_dir(cache_dir=None) -> pathlib.Path:
    """원본 JSON 캐시. 🔴 볼륨이 있으면 거기 — 배포로 날아가지 않는다.

    ⚠️ [W3-4] 위치를 **인자로 받는다.** 전역 `/tmp` 하나면 앞 실행이 남긴
       캐시가 다음 실행의 판단을 바꾼다 — 실제로 테스트가 순서에 따라
       갈렸다(빈 응답 중단 검사가 앞 실행 캐시를 읽어 안 멈췄다).
    """
    import os

    if cache_dir is not None:
        d = pathlib.Path(cache_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d
    base = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "/tmp"
    d = pathlib.Path(base) / "fotmob_slate"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = pathlib.Path("/tmp/fotmob_slate")
        d.mkdir(parents=True, exist_ok=True)
    return d


async def _slate_cached(day: str, fetch, cache_dir=None) -> list:
    f = _cache_dir(cache_dir) / f"{day}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8")) or []
        except Exception as exc:
            logger.info("[backfill] 캐시 손상 %s — 다시 받는다: %s", day, exc)
    rows = await fetch(day)
    if rows:
        try:
            f.write_text(json.dumps(rows, ensure_ascii=False, default=str),
                         encoding="utf-8")
        except Exception as exc:
            logger.info("[backfill] 캐시 기록 실패 %s: %s", day, exc)
    return rows


async def run(pool=None, *, days: int = 60, dry_run: bool = True,
              slate=None, upsert=None, now=None, leagues=None,
              cache_dir=None) -> dict:
    """`now-days` ~ 어제를 훑는다. 반환은 무엇을 했는지 전부 센 dict."""
    from app.leagues import LEAGUES

    if slate is None:
        from app.collectors.fotmob import slate as slate
    if upsert is None:
        from app.collectors.fotmob import upsert_slate as upsert

    keys = list(leagues or [k for k, c in LEAGUES.items()
                            if c.get("result_source") == "fotmob"])
    now = now or datetime.now(timezone.utc)
    out: dict = {"days": days, "leagues": keys, "fetched_days": 0,
                 "matched": 0, "saved": 0, "would_save": 0,
                 "empty_days": 0, "stopped": None, "failed": []}
    empty_run = 0
    # 🔴 **어제부터 거꾸로** 간다. 최근 자료가 폼·휴식에 먼저 필요하고,
    #    차단당해도 쓸모 있는 쪽이 먼저 들어와 있다.
    for i in range(1, days + 1):
        day = (now - timedelta(days=i)).strftime("%Y%m%d")
        try:
            rows = await _slate_cached(day, slate, cache_dir)
        except Exception as exc:
            out["failed"].append({"day": day, "error": f"{type(exc).__name__}: {exc}"[:200]})
            logger.warning("[backfill] %s 조회 실패: %s", day, exc)
            empty_run += 1
            if empty_run >= EMPTY_STOP:
                out["stopped"] = f"조회 실패 {empty_run}일 연속 — 즉시 중단"
                break
            continue
        out["fetched_days"] += 1
        if not rows:
            out["empty_days"] += 1
            empty_run += 1
            # 🔴 실제 날짜는 언제나 경기가 있다. 연속 빈손은 **차단 신호**다.
            if empty_run >= EMPTY_STOP:
                out["stopped"] = (f"빈 응답 {empty_run}일 연속 — 차단으로 보고 "
                                  "즉시 중단한다")
                logger.error("[backfill] %s", out["stopped"])
                break
            continue
        empty_run = 0
        for key in keys:
            try:
                if dry_run:
                    from app.collectors.fotmob import league_matches

                    n = sum(1 for r in rows
                            if league_matches(r.get("league") or "", key)
                            and r.get("status") == "final")
                    out["would_save"] += n
                    if n:
                        logger.info("[backfill] (dry) %s %s — 종료 %d경기", day, key, n)
                    continue
                r = await upsert(pool, day, league_key=key, rows=rows) or {}
                out["matched"] += int(r.get("matched") or 0)
                out["saved"] += int(r.get("saved") or 0)
            except Exception as exc:
                out["failed"].append({"day": day, "league": key,
                                      "error": f"{type(exc).__name__}: {exc}"[:200]})
                logger.warning("[backfill] %s %s 적재 실패: %s", day, key, exc)
    logger.info("[backfill] %s — 조회 %d일 · 빈날 %d · 매칭 %d · 저장 %d · "
                "(dry)예정 %d · 실패 %d%s",
                "DRY-RUN" if dry_run else "WRITE", out["fetched_days"],
                out["empty_days"], out["matched"], out["saved"],
                out["would_save"], len(out["failed"]),
                f" · 중단: {out['stopped']}" if out["stopped"] else "")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    # 🔴 **--dry-run 이 기본이다.** 쓰기는 명시해야 한다(지시문).
    ap.add_argument("--write", action="store_true",
                    help="실제로 적재한다. 없으면 dry-run.")
    ap.add_argument("--leagues", default=None,
                    help="쉼표로 구분한 리그 키. 없으면 result_source=fotmob 전부")
    args = ap.parse_args()

    from app.db import close_pool, get_pool

    logging.basicConfig(level=logging.INFO)
    pool = await get_pool()
    try:
        got = await run(pool, days=args.days, dry_run=not args.write,
                        leagues=(args.leagues.split(",") if args.leagues else None))
        print(json.dumps(got, ensure_ascii=False, indent=2, default=str))
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
