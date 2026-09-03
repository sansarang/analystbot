"""[C3] 변수 원장 — 주장(N·M)과 실측을 대조한다.

🔴 변수가 "서술"이던 동안에는 맞았는지 틀렸는지 **셀 수 없었다.**
   "이닝 소화력 예측 불가"는 참도 거짓도 아니다. 정량 형식으로 바뀐 뒤부터
   임계를 명시한 변수만 채점하고, 나머지는 `unverifiable` 로 **남긴다.**

⚠️ **발명 금지.** 변수가 임계("3이닝 미만")를 명시하지 않으면 채점하지 않는다.
   우리가 임계를 상상해서 붙이면 그 채점은 우리 상상을 채점하는 것이다.
⚠️ 파싱 실패도 행으로 남긴다 — 형식 위반율을 재는 것이 이 원장의 절반이다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

TRUE, FALSE, UNVERIFIABLE = "true", "false", "unverifiable"

#: 채점 가능한 임계 표현. **여기 없는 형태는 채점하지 않는다.**
_THRESHOLD = re.compile(
    r"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>이닝|실점|득점)\s*(?P<cmp>미만|이하|이상|초과)")


def threshold_of(risk: str) -> dict | None:
    """리스크 서술에서 임계를 읽는다. 없으면 None — 그러면 채점 대상이 아니다."""
    m = _THRESHOLD.search(risk or "")
    if not m:
        return None
    return {"value": float(m.group("val")), "unit": m.group("unit"),
            "cmp": m.group("cmp")}


def subject_of(risk: str, jg: dict) -> tuple[str | None, str | None]:
    """주체 추정 — 오늘 선발 이름이 들어 있으면 그 투수, 아니면 팀.

    ⚠️ 이름이 안 잡히면 `(None, None)` 이다. 억지로 팀으로 넘기지 않는다 —
       잘못된 주체로 채점하면 그 결과가 더 나쁘다.
    """
    from app.engine.starter_recent import pitcher_name

    for side in ("home", "away"):
        name = pitcher_name(jg, side)
        if name and name in (risk or ""):
            return name, "pitcher"
    for side in ("home", "away"):
        team = jg.get(side)
        if team and str(team) in (risk or ""):
            return str(team), "team"
    return None, None


def _cmp(actual: float, thr: dict) -> bool:
    v, c = thr["value"], thr["cmp"]
    return {"미만": actual < v, "이하": actual <= v,
            "이상": actual >= v, "초과": actual > v}[c]


def judge_realized(thr: dict | None, actual: dict | None) -> str:
    """임계와 실측으로 현실화 판정. 둘 중 하나라도 없으면 `unverifiable`."""
    if not thr or not actual:
        return UNVERIFIABLE
    key = {"이닝": "innings", "실점": "runs", "득점": "runs"}[thr["unit"]]
    got = actual.get(key)
    if got is None:
        return UNVERIFIABLE
    return TRUE if _cmp(float(got), thr) else FALSE


async def record(pool, jg: dict, ledger_id: int | None = None) -> int:
    """판정 1건의 변수를 원장에 적재. 반환 적재 행 수."""
    if pool is None or jg.get("game_id") is None:
        return 0
    from app.engine.variable_parse import parse_all

    m = jg.get("matchup") or {}
    rows = parse_all(m)
    if not rows:
        return 0
    n = 0
    for r in rows:
        p = r["parsed"] or {}
        subj, kind = subject_of(p.get("risk") or r["raw"], jg)
        try:
            await pool.execute(
                """INSERT INTO variable_ledger
                       (game_id, sport, ledger_id, raw, subject, subject_kind,
                        direction, claimed_n, claimed_m, source_ref, realized)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                int(jg["game_id"]), jg.get("sport") or "", ledger_id, r["raw"],
                subj, kind, p.get("side"), p.get("n"), p.get("m"),
                p.get("source"), None if r["parsed"] else UNVERIFIABLE)
            n += 1
        except Exception as exc:
            logger.warning("[var-ledger] 적재 실패 game=%s: %s",
                           jg.get("game_id"), exc)
    logger.info("[var-ledger] game=%s 변수 %d건 적재 (정량 %d)",
                jg.get("game_id"), n, sum(1 for r in rows if r["parsed"]))
    return n


_PENDING = """
    SELECT v.id, v.game_id, v.subject, v.subject_kind, v.raw
      FROM variable_ledger v JOIN games g ON g.id = v.game_id
     WHERE v.graded_at IS NULL AND g.status = 'final'
       AND ($1::text IS NULL OR v.sport = $1)
"""

_PITCHER_LINE = """
    SELECT a.innings, a.r FROM pitcher_appearances a
     WHERE a.game_id = $1 AND a.pitcher = $2 LIMIT 1
"""

_TEAM_RUNS = """
    SELECT CASE WHEN g.home = $2 THEN g.home_score
                WHEN g.away = $2 THEN g.away_score END AS runs
      FROM games g WHERE g.id = $1
"""


async def grade(pool, sport: str | None = None) -> dict:
    """종료 경기의 변수를 채점. 반환 {graded, realized, unverifiable}."""
    out = {"graded": 0, "realized": 0, "unverifiable": 0}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_PENDING, sport)
    except Exception as exc:
        logger.warning("[var-ledger] 채점 대상 조회 실패: %s", exc)
        return out
    for r in rows:
        actual = None
        try:
            if r["subject_kind"] == "pitcher" and r["subject"]:
                line = await pool.fetchrow(_PITCHER_LINE, r["game_id"], r["subject"])
                if line:
                    actual = {"innings": line["innings"], "runs": line["r"]}
            elif r["subject_kind"] == "team" and r["subject"]:
                runs = await pool.fetchval(_TEAM_RUNS, r["game_id"], r["subject"])
                if runs is not None:
                    actual = {"runs": runs}
        except Exception as exc:
            logger.warning("[var-ledger] 실측 조회 실패 id=%s: %s", r["id"], exc)
        verdict = judge_realized(threshold_of(r["raw"]), actual)
        try:
            await pool.execute(
                """UPDATE variable_ledger
                      SET realized = $2, actual = $3::jsonb, graded_at = now()
                    WHERE id = $1""", r["id"], verdict,
                json.dumps(actual, ensure_ascii=False, default=str) if actual else None)
        except Exception as exc:
            logger.warning("[var-ledger] 채점 기록 실패 id=%s: %s", r["id"], exc)
            continue
        out["graded"] += 1
        if verdict == TRUE:
            out["realized"] += 1
        elif verdict == UNVERIFIABLE:
            out["unverifiable"] += 1
    if out["graded"]:
        logger.info("[var-ledger] 변수 채점 %d건 · 현실화 %d · 검증불가 %d",
                    out["graded"], out["realized"], out["unverifiable"])
    return out


async def summary(pool, sports: tuple[str, ...]) -> dict | None:
    """일일 요약 한 줄용 집계. 재료가 없으면 None."""
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            """SELECT count(*) AS n,
                      count(*) FILTER (WHERE claimed_n IS NOT NULL) AS quant,
                      count(*) FILTER (WHERE realized = 'true') AS realized,
                      count(*) FILTER (WHERE realized = 'unverifiable') AS unver
                 FROM variable_ledger
                WHERE sport = ANY($1::text[])
                  AND created_at >= now() - interval '20 hours'""", list(sports))
    except Exception as exc:
        logger.debug("[var-ledger] 집계 실패: %s", exc)
        return None
    return dict(row) if row and int(row["n"]) else None
