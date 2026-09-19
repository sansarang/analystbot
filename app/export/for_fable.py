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

#: 내보내기 단계. 🔴 **이 목록이 원본이다** — `main()` 의 choices 와 스케줄러
#  잡이 여기서 이름을 가져간다. 손으로 두 번 적지 않는다.
STAGES = ("t3h", "lineup")


def resolve_out_dir() -> pathlib.Path:
    """산출물을 둘 곳. 🔴 **볼륨이 있으면 볼륨이다.**

    Railway 컨테이너의 기본 파일시스템은 재배포·재시작마다 초기화된다 —
    볼륨 밖에 쓴 것은 백업이 아니라 사라질 파일이다(→ docs/FORKS.md F-18).
    로컬에는 그 변수가 없으므로 종전 다운로드 폴더가 그대로 쓰인다.
    """
    vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if vol:
        return pathlib.Path(vol) / "export"
    return pathlib.Path.home() / "Downloads" / "analystbot_export"


OUT_DIR = resolve_out_dir()

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


def out_path(date_kst: str, league: str, *, ext: str = "json",
             stage: str = "t3h") -> pathlib.Path:
    """`{날짜}_{리그}_slate[_lineup].{ext}`.

    🔴 **덮어쓰지 않는다** — `_r2`·`_r3` 로 늘린다.
    🔴 `lineup` 단계는 접미사를 붙여 T-3h 산출물과 **같은 이름을 쓰지 않는다** —
       한 파일이면 늦은 쪽이 이른 쪽을 지우고, 그러면 "라인업 전에는 무엇을
       알았나"를 되짚을 수 없다.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{date_kst}_{league}_slate" + ("_lineup" if stage == "lineup" else "")
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



# ══════════════════════════════════════════════════════════════════
# STEP 2 블록. 🔴 전부 **SELECT 만** 한다. 새 수집기를 만들지 않는다.
#    STEP 0 에서 "없음"이던 칸은 `null + reason` 그대로 둔다.
# ══════════════════════════════════════════════════════════════════

_ODDS_SQL = """
    SELECT market, side, line, odds, provider, book, snap_tag, captured_at
      FROM odds_snapshots
     WHERE game_id = $1
     ORDER BY captured_at DESC
"""


def _odds_block(rows: list, home: str, away: str, sport: str) -> dict:
    """배당. 🔴 `p`(마진 제거)와 `required`(1/배당)를 **가른다.**

    ⚠️ 섞으면 edge 가 늘 마진만큼 양수로 나온다 — v1.4 지시문이 경고한 결함이다.
    ⚠️ 없는 마켓은 빈 배열이 아니라 `null` + reason 이다.
    """
    from app.flow.odds_math import devig_2way, devig_3way, required_prob

    if not rows:
        return {"snapshot_kst": None, "book": None, "ml": None,
                "ml_devig": None, "ml_required": None, "ah": None,
                "total": None, "team_total_home": None,
                "team_total_away": None,
                "team_total_reason": NO_SOURCE["team_total"],
                "f5": None, "f5_reason": NO_SOURCE["f5"],
                "open_ml": None,
                "reason": "이 경기의 배당 스냅샷이 0행이다"}

    def _key(side: str) -> str | None:
        if side == home:
            return "home"
        if side == away:
            return "away"
        return "draw" if side.lower() in ("draw", "무", "tie") else None

    ml, ah, total, open_ml = {}, [], [], {}
    seen_ah, seen_total = set(), set()
    for r in rows:
        m, side, odds = r["market"], str(r["side"] or ""), float(r["odds"])
        line = None if r["line"] is None else float(r["line"])
        k = _key(side)
        if m == "h2h":
            if k and k not in ml:
                ml[k] = odds
            # 🔴 `open` 이 없으면 `open_proxy` 가 기준선이다 —
            #    규칙의 원본은 `odds_move.BASELINE_ORDER` 다.
            if k and r["snap_tag"] in ("open", "open_proxy") and k not in open_ml:
                open_ml[k] = odds
        elif m == "spreads" and k and (line, k) not in seen_ah:
            seen_ah.add((line, k))
            ah.append({"line": line, "side": k, "odds": odds})
        elif m == "totals":
            d = "over" if "over" in side.lower() else "under"
            if (line, d) not in seen_total:
                seen_total.add((line, d))
                total.append({"line": line, d: odds})

    devig = req = None
    if sport == "soccer" and {"home", "draw", "away"} <= set(ml):
        h, d, a = devig_3way(ml["home"], ml["draw"], ml["away"])
        devig = {"home": round(h, 4), "draw": round(d, 4), "away": round(a, 4)}
    elif {"home", "away"} <= set(ml):
        h, a = devig_2way(ml["home"], ml["away"])
        devig = {"home": round(h, 4), "away": round(a, 4)}
    if ml:
        req = {k: round(required_prob(v), 4) for k, v in ml.items()}

    newest = rows[0]
    return {
        "snapshot_kst": _kst(newest["captured_at"]),
        "book": newest["book"] or newest["provider"],
        "ml": ml or None, "ml_devig": devig, "ml_required": req,
        "ah": ah or None, "total": total or None,
        "team_total_home": None, "team_total_away": None,
        "team_total_reason": NO_SOURCE["team_total"],
        "f5": None, "f5_reason": NO_SOURCE["f5"],
        "open_ml": open_ml or None,
        "open_ml_reason": None if open_ml else "이름표 `open` 스냅샷이 없다",
    }


#: 선발 등판. 🔴 `is_starter = true` 만. 시즌 집계도 이 표에서 만든다 —
#  외부 시즌 통계 API 를 새로 붙이지 않는다(새 수집기 금지).
_STARTER_SQL = """
    -- ⚠️ 컬럼명은 **운영 DB 가 원본**이다. 스키마 파일에는 `h` 로 적혀 있지만
    --    실제 컬럼은 `hits` 다(실측 information_schema). 사본을 믿지 않는다.
    SELECT pa.innings, pa.er, pa.k, pa.bb, pa.hr, pa.hits, pa.batters,
           (g.starts_at AT TIME ZONE 'Asia/Seoul')::date d,
           g.starts_at, pa.opponent
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     WHERE pa.pitcher = $1 AND pa.is_starter = true
       AND g.starts_at < $2::timestamptz
     ORDER BY g.starts_at DESC
"""


def _starter_block(name: str | None, rows: list, change_notes) -> dict:
    """선발. 🔴 `season` 은 **공식 등판 기록의 집계**다 — 기사 수치가 아니다."""
    out = _empty_starter()
    out["starter_change_notes"] = change_notes
    if not name:
        out["reason"] = "예고 선발이 `games` 에 없다"
        return out
    out["name"] = name
    if not rows:
        out["reason"] = f"`pitcher_appearances` 에 {name} 의 선발 등판이 0행이다"
        return out

    out["last3"] = [
        {"date_kst": str(r["d"]), "opp": r["opponent"],
         "ip": float(r["innings"] or 0), "h": r["hits"], "er": r["er"],
         "bb": r["bb"], "k": r["k"],
         "pitches": None, "pitches_reason": "투구수 저장 없음"}
        for r in rows[:3]]

    ip = sum(float(r["innings"] or 0) for r in rows)
    if ip > 0:
        out["season"] = {
            "gs": len(rows), "ip": round(ip, 1),
            "era": round(9.0 * sum(int(r["er"] or 0) for r in rows) / ip, 2),
            # 🔴 FIP 는 리그 상수(cFIP)가 필요하다 — 저장돼 있지 않다.
            "fip": None,
            "k9": round(9.0 * sum(int(r["k"] or 0) for r in rows) / ip, 2),
            "bb9": round(9.0 * sum(int(r["bb"] or 0) for r in rows) / ip, 2),
            "hr9": round(9.0 * sum(int(r["hr"] or 0) for r in rows) / ip, 2),
        }
        out["season_note"] = ("우리 DB 의 선발 등판 집계다 — 공식 시즌 스탯 API "
                              "값이 아니다. FIP 는 리그 상수가 없어 null.")
    if rows and rows[0]["starts_at"] is not None:
        out["days_rest_from"] = str(rows[0]["d"])
    out["reason"] = None
    return out


def _bullpen_block(rows: list) -> dict:
    """불펜 최근 3일. 🔴 `is_starter = false` 만 — 선발이 섞이면 소모가 뒤집힌다."""
    out = _empty_bullpen()
    if not rows:
        out["reason"] = "최근 3일 불펜 등판이 0행이다"
        return out
    out["last3d"] = [{"name": r["pitcher"], "date_kst": str(r["d"]),
                      "ip": float(r["innings"] or 0),
                      "pitches": None}
                     for r in rows]
    out["ip_3d_total"] = round(sum(float(r["innings"] or 0) for r in rows), 2)
    out["reason"] = None
    return out


_BULLPEN_SQL = """
    SELECT pa.pitcher, pa.innings,
           (g.starts_at AT TIME ZONE 'Asia/Seoul')::date d
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     WHERE pa.team = $1 AND pa.is_starter = false
       AND g.starts_at <  $2::timestamptz
       AND g.starts_at >= $2::timestamptz - interval '3 days'
     ORDER BY g.starts_at DESC
"""


_LINEUP_SQL = """
    SELECT side, status, source, starter, batting_order, scratches, captured_at
      FROM lineups
     WHERE game_id = $1
     ORDER BY captured_at DESC
"""

#: 최근 5경기. 🔴 `_LAST3_SQL`(pick_ledger)과 같은 규칙이다 — 창만 다르다.
_FORM_SQL = """
    SELECT home, away, home_score, away_score,
           (starts_at AT TIME ZONE 'Asia/Seoul')::date d
      FROM games
     WHERE sport = $1 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
       AND $2 IN (home, away) AND starts_at < $3::timestamptz
     ORDER BY starts_at DESC
     LIMIT 5
"""

_LEDGER_SQL = """
    SELECT p_prior, p_code, gate_label, gate_gap_pp, confirmed, refuted,
           unknown_axes, predicted_side, confidence
      FROM pick_ledger
     WHERE game_id = $1 AND is_final
"""

_RUNS_SQL = """
    SELECT run_id, node, snapshot_json, created_at_utc
      FROM analysis_runs
     WHERE game_id = $1
     ORDER BY created_at_utc DESC
     LIMIT 40
"""


def _form_rows(rows: list, team: str) -> tuple:
    """최근 5경기 + 득실차. 🔴 상대전적(H2H)·BvP 를 넣지 않는다(v1.4 금지)."""
    out, diff = [], 0
    for r in rows:
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        ours, theirs = (hs, as_) if r["home"] == team else (as_, hs)
        diff += ours - theirs
        out.append({"date_kst": str(r["d"]),
                    "opp": r["away"] if r["home"] == team else r["home"],
                    "ha": "H" if r["home"] == team else "A",
                    "score": f"{ours}-{theirs}",
                    "result": "W" if ours > theirs else ("L" if ours < theirs else "D")})
    return out or None, (diff if out else None)


def _lineup_block(rows: list, side: str, absences: list | None) -> dict:
    """라인업. 🔴 **예상과 확정을 반드시 구분한다** — 예상을 확정으로 취급하면
    픽이 뒤집힐 정보를 놓친다(db/schema.sql:주석 · 이 저장소 규약)."""
    out = _empty_lineup()
    mine = [r for r in rows if (r["side"] or "") == side]
    if mine:
        r = mine[0]
        out["status"] = r["status"]
        out["posted_kst"] = _kst(r["captured_at"])
        out["source"] = r["source"]
        order = r["batting_order"]
        out["batting_order_n"] = len(order) if isinstance(order, list) else None
        out["scratches"] = r["scratches"] or None
    else:
        out["status"] = "none"
        out["reason"] = "이 경기의 `lineups` 행이 없다"
    if absences:
        out["out"] = absences
        out["regulars_missing_count"] = len(absences)
        out["out_source"] = "absences.py (statsapi IL 명단 + 확정 라인업)"
        out["reason"] = None
    elif absences is None:
        out["out_reason"] = "판정 캐시(`analysis:…`)가 없어 결장 목록을 못 읽었다"
    else:
        out["out"] = []
        out["regulars_missing_count"] = 0
    return out


def _context_block(standing: dict | None) -> dict:
    """순위 맥락. 🔴 시즌 타율·ERA 순위표를 넣지 않는다(v1.4 금지 항목)."""
    out = _empty_context()
    if not standing:
        out["reason"] = "판정 캐시에 순위 자료가 없다"
        return out
    out["record"] = standing.get("record") or standing.get("전적")
    out["gb"] = standing.get("games_behind", standing.get("게임차"))
    out["streak"] = standing.get("streak") or standing.get("연속")
    out["reason"] = None
    return out


def _v14_block(rows: list) -> dict:
    """v1.4 섀도 실행 결과. 🔴 `analysis_runs` 가 원본이다."""
    out = {"run_id": None, "n03_gate": None, "gap_pp": None,
           "n06_verdict": None, "n08_p_code": None, "n11_pick_type": None,
           "stop_reason": None, "snapshot_rows": 0, "reason": None}
    if not rows:
        out["reason"] = "이 경기의 `analysis_runs` 행이 없다 (섀도 미실행)"
        return out
    run_id = rows[0]["run_id"]
    same = [r for r in rows if r["run_id"] == run_id]
    out["run_id"] = str(run_id)
    out["snapshot_rows"] = len(same)
    snap = same[0]["snapshot_json"]
    snap = json.loads(snap) if isinstance(snap, str) else (snap or {})
    out["n03_gate"] = (snap.get("n03_gate") or {}).get("gate")
    out["gap_pp"] = (snap.get("n03_gate") or {}).get("gap_pp")
    out["n06_verdict"] = (snap.get("n06_verdict") or {}).get("verdict")
    out["n08_p_code"] = (snap.get("n08_pcode") or {}).get("p_code_pick")
    out["n11_pick_type"] = (snap.get("n11_value") or {}).get("pick_type")
    out["stop_reason"] = snap.get("stop_reason")
    out["nodes"] = [r["node"] for r in reversed(same)]
    return out


def _deepsearch_block(articles: list | None) -> list:
    """딥서치 원문. 🔴 **URL 필수 · 경기당 5개 · 300자 이내.**

    ⚠️ 이 값은 기사에서 왔다 — `season` 같은 공식 칸에 **섞지 않는다.**
    """
    out = []
    for a in (articles or [])[:5]:
        url = (a.get("url") or "").strip()
        if not url:
            continue                      # URL 없는 것은 버린다(지시문 §2)
        body = (a.get("body") or a.get("title") or "").strip()
        if not body:
            continue
        out.append({"var": "article", "side": None,
                    "excerpt": body[:300], "source_url": url,
                    "fetched_kst": a.get("fetched_at")})
    return out


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
    rows = [dict(r) for r in await pool.fetch(_SLATE_SQL, sport, day)]

    if sport == "soccer":
        want = SOCCER_LABEL.get(league)
        if want:
            rows = [r for r in rows if (r.get("league") or "") == want]

    games, used = [], set()
    pool = await get_pool()
    try:
        # 판정 캐시(결장·순위)는 슬레이트 단위로 **한 번** 읽는다.
        cache = await _read_cache(sport, date_kst)
        if cache:
            used.add("analysis_cache")
        for r in rows:
            g = await _fill(pool, r, sport, cache, used)
            games.append(g)
    finally:
        await close_pool()

    now = datetime.now(timezone.utc)
    return {
        "export_meta": {
            "generated_kst": _kst(now), "generated_utc": _utc(now),
            "league": league, "date_kst": date_kst,
            "pipeline_version": PIPELINE_VERSION, "git_sha": _git_sha(),
            # 🔴 실제로 **쓴** 소스만 적는다 — 안 쓴 것을 적으면 그게 거짓이다.
            "sources_used": sorted(used),
            "step": "STEP 2 — 블록 채움",
        },
        "games": games,
    }


async def _read_cache(sport: str, date_kst: str) -> dict:
    """판정 캐시의 `research` — 결장·순위가 거기 있다. 없으면 빈 dict.

    🔴 **새로 수집하지 않는다.** 파이프라인이 이미 만든 것을 읽는다.
    🔴 **MLB 는 캐시 키가 미 동부 날짜다**(`pipeline.mlb_slate_date`) — KST
       날짜로만 찾으면 언제나 빈손이다. 실측: `analysis:mlb:2026-09-19` 없음,
       있는 것은 `analysis:mlb:2026-09-18` 이었다.
       ⚠️ 규칙의 원본은 `pipeline.mlb_slate_date` 다 — 여기서 달력을 새로
          만들지 않고 **양쪽 날짜를 다 본다.**
    """
    from datetime import date as _d
    from datetime import timedelta as _td

    keys = [date_kst]
    if sport == "mlb":
        try:
            keys.append((_d.fromisoformat(date_kst) - _td(days=1)).isoformat())
        except ValueError:
            pass
    for key in keys:
        got = await _read_cache_one(sport, key)
        if got:
            return got
    return {}


async def _read_cache_one(sport: str, date_kst: str) -> dict:
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        rd = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            raw = await rd.get(f"analysis:{sport}:{date_kst}")
        finally:
            await rd.aclose()
    except Exception as exc:
        logger.info("[export] 판정 캐시 못 읽음: %s", exc)
        return {}
    if not raw:
        return {}
    try:
        doc = json.loads(raw)
    except ValueError:
        return {}
    return {str(g.get("game_id")): g for g in (doc.get("games") or [])}


async def _articles(sport: str, game_id) -> list:
    """위성이 모아 둔 기사. 🔴 **새로 긁지 않는다.**"""
    try:
        import redis.asyncio as aioredis

        from app.collectors.satellite import read_cache
        from app.config import get_settings

        rd = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            return await read_cache(rd, sport, game_id)
        finally:
            await rd.aclose()
    except Exception as exc:
        logger.info("[export] 위성 캐시 못 읽음 game=%s: %s", game_id, exc)
        return []


async def _fill(pool, row: dict, sport: str, cache: dict, used: set) -> dict:
    """경기 1건 — 블록을 채운다. 🔴 SELECT 와 캐시 읽기뿐이다."""
    g = empty_game(row)
    gid, ko = row["id"], row["starts_at"]
    home, away = row["home"], row["away"]
    jg = cache.get(str(gid)) or {}

    # ① odds
    g["odds"] = _odds_block([dict(x) for x in await pool.fetch(_ODDS_SQL, gid)],
                            home, away, sport)
    if g["odds"].get("ml"):
        used.add("odds_crawler")

    # ② starters
    notes = jg.get("starter_change_notes")
    for side, team in (("home", home), ("away", away)):
        name = row.get(f"{side}_pitcher")
        srows = ([dict(x) for x in await pool.fetch(_STARTER_SQL, name, ko)]
                 if name else [])
        g["starters"][side] = _starter_block(name, srows, notes)
        if srows:
            used.add("pitcher_appearances")

    # ③ bullpen
    for side, team in (("home", home), ("away", away)):
        brows = [dict(x) for x in await pool.fetch(_BULLPEN_SQL, team, ko)]
        g["bullpen"][side] = _bullpen_block(brows)
        if brows:
            used.add("pitcher_appearances")

    # ④ lineup
    lrows = [dict(x) for x in await pool.fetch(_LINEUP_SQL, gid)]
    absences = (jg.get("research") or {}).get("absences") if jg else None
    h_out, a_out = _split_absences(absences, home, away)
    g["lineup"]["home"] = _lineup_block(lrows, "home", h_out)
    g["lineup"]["away"] = _lineup_block(lrows, "away", a_out)
    if lrows:
        used.add("lineups")
    if absences:
        used.add("absences(statsapi)")

    # ⑤ form
    for side, team in (("home", home), ("away", away)):
        frows = [dict(x) for x in await pool.fetch(_FORM_SQL, sport, team, ko)]
        last5, diff = _form_rows(frows, team)
        g["form"][f"{side}_last5"] = last5
        g["form"][f"{side}_run_diff_last5"] = diff
        if frows:
            used.add("games(final)")
    g["form"]["reason"] = None if g["form"]["home_last5"] else "최근 5경기 기록이 없다"

    # ⑥ context
    res = jg.get("research") or {}
    g["context"]["home"] = _context_block(res.get("home_standing"))
    g["context"]["away"] = _context_block(res.get("away_standing"))

    # ⑦ model_probs + elo
    led = await pool.fetchrow(_LEDGER_SQL, gid)
    if led:
        g["model_probs"]["bot_p_prior"] = (None if led["p_prior"] is None
                                           else float(led["p_prior"]))
        g["model_probs"]["bot_p_code"] = (None if led["p_code"] is None
                                          else float(led["p_code"]))
        used.add("pick_ledger")
    else:
        g["model_probs"]["ledger_reason"] = "이 경기의 원장 행이 없다 (판정 전)"
    elo, asof = await _elo(sport, date_of(ko))
    for side, team in (("home", home), ("away", away)):
        box = (elo or {}).get(team)
        if isinstance(box, dict):
            g[side]["elo"] = box.get("레이팅")
            g[side]["elo_asof"] = asof
            used.add("team_elo")
        else:
            g[side]["elo_reason"] = ("elo 캐시에 이 팀이 없다"
                                      if elo else "elo 캐시가 없다(최근 4일)")

    # ⑧ deepsearch
    g["deepsearch"] = _deepsearch_block(await _articles(sport, gid))
    if g["deepsearch"]:
        used.add("satellite_articles")

    # ⑨ v14_run
    try:
        g["v14_run"] = _v14_block([dict(x) for x in
                                   await pool.fetch(_RUNS_SQL, str(gid))])
        if g["v14_run"].get("run_id"):
            used.add("analysis_runs")
    except Exception as exc:
        g["v14_run"] = {"reason": f"analysis_runs 조회 실패: {exc}"}
    return g


def date_of(ko) -> str | None:
    k = _kst(ko)
    return k[:10] if k else None


def _split_absences(absences, home: str, away: str):
    """결장 문장을 홈/원정으로. 🔴 분리 규칙의 원본은 `performance._split_absences`."""
    if absences is None:
        return None, None
    try:
        from app.engine.performance import _split_absences as _sp

        return _sp(list(absences), {"home": home, "away": away})
    except Exception:
        return [], []


async def _elo(sport: str, date_kst: str | None) -> tuple:
    """`({팀: 상자}, 그 값의 날짜)`. 🔴 **며칠 뒤로 물러나 찾는다.**

    elo 캐시는 날짜별 키다. 오늘 키가 아직 없으면(아침 슬레이트) 어제 값이
    가장 최신이다. ⚠️ 어느 날짜 값인지 `elo_asof` 로 **밝힌다** — 오늘 값인
    척하면 그게 거짓이다.
    """
    if not date_kst:
        return {}, None
    from datetime import date as _d
    from datetime import timedelta as _td

    try:
        import redis.asyncio as aioredis

        from app.config import get_settings
        from app.models import team_elo as TE

        rd = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            base = _d.fromisoformat(date_kst)
            for back in range(0, 4):
                day = (base - _td(days=back)).isoformat()
                got = await TE.load(rd, sport, day)
                if got:
                    return got, day
        finally:
            await rd.aclose()
    except Exception as exc:
        logger.info("[export] elo 못 읽음: %s", exc)
    return {}, None


# ══════════════════════════════════════════════════════════════════
# STEP 3 — MD 요약. 🔴 **JSON 에서만 만든다.** DB 를 다시 읽지 않는다
#    (JSON 이 원본, MD 는 파생 — 두 번 읽으면 두 파일이 갈린다).
#    ⚠️ 경기당 10줄 상한.
# ══════════════════════════════════════════════════════════════════

def to_md(doc: dict) -> str:
    m = doc["export_meta"]
    out = [f"# {m['date_kst']} {m['league'].upper()} 슬레이트 — 페이블용 요약",
           "",
           f"생성 {m['generated_kst']} · 커밋 `{m['git_sha']}` · "
           f"파이프라인 {m['pipeline_version']}",
           f"쓴 소스: {', '.join(m['sources_used']) or '없음'}",
           f"경기 {len(doc['games'])}건",
           "",
           "> 🔴 `null` 은 **봇이 모르는 값**이다. 추정치가 아니다 — "
           "JSON 의 `reason` 이 왜 모르는지 적는다.",
           ""]
    for g in doc["games"]:
        out += _md_game(g)
    return "\n".join(out) + "\n"


def _md_game(g: dict) -> list:
    """경기 1건 — **10줄 이내.**"""
    ko = (g.get("kickoff_kst") or "")[:16].replace("T", " ")
    o, sh, sa = g["odds"], g["starters"]["home"], g["starters"]["away"]
    bh, ba = g["bullpen"]["home"], g["bullpen"]["away"]
    lh, la = g["lineup"]["home"], g["lineup"]["away"]
    v = g["v14_run"]

    def _s(s):
        se = s.get("season") or {}
        era = se.get("era")
        return (f"{s.get('name') or '미정'}"
                + (f" (시즌 {se.get('gs')}선발 ERA {era})" if era is not None else ""))

    def _l3(s):
        r = (s.get("last3") or [None])[0]
        return (f"{r['date_kst']} {r['ip']:.1f}이닝 {r['er']}자책"
                if r else "최근 등판 기록 없음")

    ml = o.get("ml") or {}
    dv = o.get("ml_devig") or {}
    return [
        f"## {g['away']['name']} @ {g['home']['name']} · {ko} KST",
        f"- 배당 홈 {ml.get('home', '—')} / 원정 {ml.get('away', '—')}"
        f"  ·  마진 제거 홈 {dv.get('home', '—')} / 원정 {dv.get('away', '—')}",
        f"- 선발 홈 {_s(sh)} — {_l3(sh)}",
        f"- 선발 원정 {_s(sa)} — {_l3(sa)}",
        f"- 불펜 3일 홈 {bh.get('ip_3d_total', '—')}이닝 / "
        f"원정 {ba.get('ip_3d_total', '—')}이닝",
        f"- 결장 홈 {lh.get('regulars_missing_count', '—')}명({lh.get('status') or '—'})"
        f" / 원정 {la.get('regulars_missing_count', '—')}명({la.get('status') or '—'})",
        f"- 게이트 {v.get('n03_gate') or '—'} ({v.get('gap_pp')}%p)"
        f"  ·  채점 {v.get('n06_verdict') or '—'}",
        f"- p_code {v.get('n08_p_code')}  ·  픽 {v.get('n11_pick_type') or '—'}"
        f"  ·  멈춤 {v.get('stop_reason') or '—'}",
        "",
    ]


def write(doc: dict, *, stage: str = "t3h") -> tuple:
    """JSON 먼저, MD 는 그 JSON 에서. 🔴 접미사를 **맞춰** 둔다."""
    meta = doc["export_meta"]
    p = out_path(meta["date_kst"], meta["league"], stage=stage)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str),
                 encoding="utf-8")
    md = p.with_suffix(".md")
    md.write_text(to_md(doc), encoding="utf-8")
    return p, md


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="페이블 분석용 슬레이트 내보내기")
    ap.add_argument("--league", required=True, choices=sorted(LEAGUE_SPORT))
    ap.add_argument("--date", required=True, help="KST 날짜 YYYY-MM-DD")
    ap.add_argument("--stage", default="t3h", choices=list(STAGES),
                    help="t3h = 킥오프 3시간 전 · lineup = 라인업 확정 직후")
    a = ap.parse_args(argv)

    doc = asyncio.run(collect(a.league, a.date))
    doc["export_meta"]["stage"] = a.stage
    p, md = write(doc, stage=a.stage)
    n = len(doc["games"])
    logger.info("내보냄 %s · %d경기 · %d바이트", p, n, p.stat().st_size)
    logger.info("요약   %s · %d바이트", md, md.stat().st_size)
    if n == 0:
        logger.warning("🔴 경기 0건 — 그 날짜에 %s 일정이 DB 에 없다", a.league)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
