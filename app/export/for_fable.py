"""[EXP-1] 페이블 분석용 자료 내보내기 — **읽기 전용 수동 커맨드.**

    python -m app.export.for_fable --league mlb --date 2026-09-19

🔴 **왜 만드나.** 페이블이 채팅에서 슬레이트를 판정할 때 웹 검색으로 선발·불펜·
   결장·배당을 다시 긁고 있고, 그 과정에서 소스 오염이 났다(다른 투수 수치 혼동,
   예상 XI 를 확정 XI 로 오독). 봇이 **이미 갖고 있는 자료**를 한 파일로 내보내
   그것만 읽게 한다.

🔴 **모르는 값은 `null` + `reason` 이다.** 0 이나 평균으로 메우지 않는다 —
   메우는 순간 "모른다"와 "그 값이다"가 같아지고, 그게 이 저장소가 반복해 겪은
   결함이다(U3 리즈 사례 · `prior.py` 규약).

🔴 **기사 수치를 공식 수치 자리에 넣지 않는다.** `season` 은 공식 원본만,
   기사에서 온 것은 `deepsearch` 에만 둔다.

⚠️ 스케줄러·발송 경로를 건드리지 않는다. DB 는 **SELECT 만** 한다.
⚠️ 다운로드 폴더 밖에 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import pathlib
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

#: 🔴 시차를 **상수로 박지 않는다** — DST 가 있으면 반드시 틀린다.
#   `tests/test_time_discipline.py` 가 그 규칙을 전수로 잠그고 있고, 이 파일이
#   처음에 고정 오프셋으로 썼다가 그 계약에 걸렸다. 계약이 먼저 잡았다.
KST = ZoneInfo("Asia/Seoul")

OUT_DIR = pathlib.Path.home() / "Downloads" / "analystbot_export"

PIPELINE_VERSION = "v1.4"

#: 리그 → `games.sport`. 🔴 축구는 `sport='soccer'` 이고 리그는 `games.league` 다.
LEAGUE_SPORT = {"mlb": "mlb", "kbo": "kbo", "npb": "npb",
                "uel": "soccer", "ucl": "soccer", "kleague": "soccer"}

#: 축구 리그 코드 → `games.league` 표기. 🔴 `app/leagues.py` 가 원본이다 —
#  여기서는 내보내기 인자용 별칭만 둔다.
SOCCER_LABEL = {"uel": "UEL", "ucl": "UCL", "kleague": "K리그1"}


# ── STEP 0 에서 "없음"으로 확인된 칸의 사유. 🔴 **손으로 지어내지 않는다** —
#    각 문장은 그때 찾은 근거다. 소스가 생기면 이 표에서 지운다.
NO_SOURCE = {
    "sr_id": "sportradar 연동 없음 (전수 검색 0건)",
    "sportradar_win": "sportradar 연동 없음 (전수 검색 0건)",
    "venue": "statsapi hydrate=venue(location) 를 받지만 _parse_games 가 무시한다 — 저장 테이블 없음",
    "park_factor": "features.park_factors 는 백테스트 도구 함수다 — 운영 경로·테이블 없음",
    "team_total": "운영 MLB 배당 실측 0행 (espn 은 h2h·spreads·totals 만)",
    "f5": "F5 배당 수집 경로 없음 (scoring 의 f5 는 확률이지 배당이 아니다)",
    "confirmed_source": "공식 예고 선발 페이지 URL 을 저장하지 않는다",
    "innings_cap": "투구수·이닝 한도 표시 없음",
    "closer": "마무리 지정 저장 없음",
    "era_14d": "14일 집계 없음",
    "doubt": "MLB Day-to-Day 는 실재하나 statsapi 로스터에 코드가 없다 (12종 전수 실측 · FORKS F-15)",
    "playoff_status": "진출·탈락 상태 저장 없음",
    "series_travel": "시리즈 차수·이동 이력 저장 없음",
}


def _null(reason_key: str) -> dict:
    """`{"value": None, "reason": ...}` 가 아니라 **형제 칸**으로 둔다.

    🔴 스키마(§2)가 `"weather": {"temp_c": null, …, "reason": "..."}` 모양이다 —
       값 옆에 사유를 둔다. 여기서 모양을 새로 만들지 않는다.
    """
    return {"reason": NO_SOURCE.get(reason_key, reason_key)}


def _git_sha() -> str:
    """배포 커밋. 컨테이너에는 .git 이 없으므로 env 를 먼저 본다."""
    sha = os.environ.get("GIT_COMMIT_SHA") or ""
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _kst(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).isoformat()


def _utc(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def out_path(date_kst: str, league: str, *, ext: str = "json") -> pathlib.Path:
    """`{날짜}_{리그}_slate.{ext}`. 🔴 **덮어쓰지 않는다** — `_r2`·`_r3` 로 늘린다."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{date_kst}_{league}_slate"
    p = OUT_DIR / f"{base}.{ext}"
    n = 1
    while p.exists():
        n += 1
        p = OUT_DIR / f"{base}_r{n}.{ext}"
    return p


# ── 경기 1건의 빈 껍데기 (STEP 1). STEP 2 가 블록별로 채운다.

def empty_game(row: dict) -> dict:
    """`games` 한 행 → §2 스키마. **신원만 채우고 나머지는 null+reason.**"""
    return {
        "game_id": str(row.get("id") or ""),
        "sr_id": None, "sr_id_reason": NO_SOURCE["sr_id"],
        "kickoff_kst": _kst(row.get("starts_at")),
        "kickoff_utc": _utc(row.get("starts_at")),
        "home": {"abbr": None, "name": row.get("home"), "record": None,
                 "elo": None, "elo_asof": None},
        "away": {"abbr": None, "name": row.get("away"), "record": None,
                 "elo": None, "elo_asof": None},
        "venue": {"name": None, "roof": None, "park_factor_runs": None,
                  "park_factor_source": None, "reason": NO_SOURCE["venue"]},
        "weather": {"temp_c": None, "wind": None, "precip_pct": None,
                    "reason": "아직 채우지 않음 (STEP 2)"},
        "odds": {
            "snapshot_kst": None, "book": None,
            "ml": None, "ml_devig": None, "ml_required": None,
            "ah": None, "total": None,
            "team_total_home": None, "team_total_away": None,
            "team_total_reason": NO_SOURCE["team_total"],
            "f5": None, "f5_reason": NO_SOURCE["f5"],
            "open_ml": None,
            "reason": "아직 채우지 않음 (STEP 2)",
        },
        "model_probs": {"sportradar_win": None,
                        "sportradar_reason": NO_SOURCE["sportradar_win"],
                        "bot_p_prior": None, "bot_p_code": None},
        "form": {"home_last5": None, "away_last5": None,
                 "home_run_diff_last5": None, "away_run_diff_last5": None,
                 "reason": "아직 채우지 않음 (STEP 2)"},
        "starters": {
            "home": _empty_starter(), "away": _empty_starter(),
        },
        "bullpen": {"home": _empty_bullpen(), "away": _empty_bullpen()},
        "lineup": {"home": _empty_lineup(), "away": _empty_lineup()},
        "context": {"home": _empty_context(), "away": _empty_context()},
        "deepsearch": [],
        "v14_run": {"run_id": None, "n03_gate": None, "gap_pp": None,
                    "n06_verdict": None, "n08_p_code": None,
                    "n11_pick_type": None, "stop_reason": None,
                    "snapshot_rows": 0,
                    "reason": "아직 채우지 않음 (STEP 2)"},
    }


def _empty_starter() -> dict:
    return {
        "name": None, "hand": None, "id": None,
        # 🔴 [2026-09-19 사용자 결정] 시즌 라인을 **넣는다.** 내보내기는 판정이
        #    아니다 — `starter_recent.py` 도 같은 이유로 "표본 보정용 시즌 라인"을
        #    둔다(실사고 2026-09-01: 표본 1경기를 "안정적"으로 읽었다).
        #    ⚠️ 이 값이 **판정 입력으로 새면** v1.4 금지 규칙 위반이다.
        "season": {"gs": None, "ip": None, "era": None, "fip": None,
                   "k9": None, "bb9": None, "hr9": None},
        "last3": None, "days_rest": None,
        "innings_cap_flag": None, "cap_note": NO_SOURCE["innings_cap"],
        "starter_change_notes": None,
        "confirmed": None, "confirmed_source": None,
        "confirmed_reason": NO_SOURCE["confirmed_source"],
        "confirmed_kst": None,
        "reason": "아직 채우지 않음 (STEP 2)",
    }


def _empty_bullpen() -> dict:
    return {"last3d": None, "ip_3d_total": None,
            "closer": None, "closer_reason": NO_SOURCE["closer"],
            "era_14d": None, "era_14d_reason": NO_SOURCE["era_14d"],
            "reason": "아직 채우지 않음 (STEP 2)"}


def _empty_lineup() -> dict:
    return {"status": None, "posted_kst": None, "source": None,
            "out": None, "regulars_missing_count": None,
            "doubt": None, "doubt_reason": NO_SOURCE["doubt"],
            "reason": "아직 채우지 않음 (STEP 2)"}


def _empty_context() -> dict:
    return {"gb": None, "streak": None, "record": None,
            "playoff_status": None,
            "playoff_reason": NO_SOURCE["playoff_status"],
            "series_game": None, "travel": None,
            "series_travel_reason": NO_SOURCE["series_travel"],
            "reason": "아직 채우지 않음 (STEP 2)"}


_SLATE_SQL = """
    SELECT id, sport, league, home, away, starts_at, status,
           home_pitcher, away_pitcher, lineup_status
      FROM games
     WHERE sport = $1
       AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2
     ORDER BY starts_at
"""


async def collect(league: str, date_kst: str) -> dict:
    """슬레이트 → §2 문서. **SELECT 만 한다.**"""
    from app.db import close_pool, get_pool

    sport = LEAGUE_SPORT.get(league)
    if sport is None:
        raise SystemExit(f"모르는 리그: {league} (가능: {', '.join(LEAGUE_SPORT)})")

    # 🔴 asyncpg Date 코덱은 **문자열을 못 받는다**(`'str' object has no
    #    attribute 'toordinal'`). 이 저장소가 이미 겪은 함정이다 —
    #    실사고 2026-08-28 17:25: `$2::date` + 문자열로 파이프라인이 통째로 실패했고
    #    시그만 남아 다음 폴링이 재시도를 스킵했다(`pipeline.py` 주석이 그 기록이다).
    from datetime import date as _date

    try:
        day = _date.fromisoformat(date_kst)
    except ValueError:
        raise SystemExit(f"날짜 형식이 아니다: {date_kst} (YYYY-MM-DD)")

    pool = await get_pool()
    try:
        rows = [dict(r) for r in await pool.fetch(_SLATE_SQL, sport, day)]
    finally:
        await close_pool()

    if sport == "soccer":
        want = SOCCER_LABEL.get(league)
        if want:
            rows = [r for r in rows if (r.get("league") or "") == want]

    now = datetime.now(timezone.utc)
    return {
        "export_meta": {
            "generated_kst": _kst(now), "generated_utc": _utc(now),
            "league": league, "date_kst": date_kst,
            "pipeline_version": PIPELINE_VERSION, "git_sha": _git_sha(),
            # 🔴 실제로 **쓴** 소스만 적는다. STEP 2 가 블록을 채우며 늘린다.
            "sources_used": [],
            "step": "STEP 1 스켈레톤 — 신원만 채웠다",
        },
        "games": [empty_game(r) for r in rows],
    }


def write(doc: dict) -> pathlib.Path:
    meta = doc["export_meta"]
    p = out_path(meta["date_kst"], meta["league"])
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str),
                 encoding="utf-8")
    return p


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="페이블 분석용 슬레이트 내보내기")
    ap.add_argument("--league", required=True, choices=sorted(LEAGUE_SPORT))
    ap.add_argument("--date", required=True, help="KST 날짜 YYYY-MM-DD")
    a = ap.parse_args(argv)

    doc = asyncio.run(collect(a.league, a.date))
    p = write(doc)
    n = len(doc["games"])
    logger.info("내보냄 %s · %d경기 · %d바이트", p, n, p.stat().st_size)
    if n == 0:
        logger.warning("🔴 경기 0건 — 그 날짜에 %s 일정이 DB 에 없다", a.league)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
