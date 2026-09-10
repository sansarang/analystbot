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


#: 지시어 → 그 경기의 어느 쪽인가. **판정이 실제로 쓰는 말**만 넣는다.
#   실측 2026-09-07: 임계는 있는데 주체를 못 잡은 16건이 전부 이 모양이었다 —
#   "홈 선발이 5이닝 이하로 조기강판 시…", "홈 타선 3경기 연속 2득점 이하…".
#   이름 대신 자리를 가리킨 것이고, 그 자리에 누가 있는지는 **이미 우리가 안다.**
_SIDE_WORDS = {"home": ("홈",), "away": ("원정", "어웨이", "아웨이")}
#: 자리 뒤에 붙는 말 → 주체 종류. 없으면 지시어로 안 친다.
_ROLE_WORDS = {"pitcher": ("선발", "선발투수", "투수"),
               "team": ("타선", "타자", "불펜", "팀")}


def subject_of(risk: str, jg: dict) -> tuple[str | None, str | None]:
    """주체 추정 — 오늘 선발 이름이 들어 있으면 그 투수, 아니면 팀.

    이름이 없어도 **`홈 선발`·`원정 타선` 같은 지시어**는 읽는다. 그 자리에
    누가 있는지는 이미 아는 사실이고, 추정이 아니다.

    ⚠️ 이름도 지시어도 없으면 `(None, None)` 이다. 억지로 팀으로 넘기지
       않는다 — 잘못된 주체로 채점하면 그 결과가 더 나쁘다.
    """
    from app.engine.starter_recent import pitcher_name

    text = risk or ""
    for side in ("home", "away"):
        name = pitcher_name(jg, side)
        if name and name in text:
            return name, "pitcher"
    # 🔴 [VAR-2 2026-09-11] **성(姓)만 써도 잡는다.** 실측: 임계는 멀쩡한데
    #    주체를 못 잡아 버려진 변수가 14건이고, 전부 이 모양이었다 —
    #      "Gilbert 5이닝 미만 또는 4실점 이상"   (선발은 `Logan Gilbert`)
    #      "펠트너가 5이닝 4실점 이상으로 조기 강판되는가"
    #    ⚠️ **3글자 이상 토큰만 본다.** 짧은 토큰은 아무 문장에나 걸려
    #       **틀린 주체로 채점**되고, 그 결과는 못 채점하는 것보다 나쁘다.
    for side in ("home", "away"):
        name = pitcher_name(jg, side)
        if not name:
            continue
        for tok in str(name).replace(".", " ").split():
            if len(tok) >= 3 and tok in text:
                return name, "pitcher"
    for side in ("home", "away"):
        team = jg.get(side)
        if team and str(team) in text:
            return str(team), "team"
    # ── 지시어. 이름이 없을 때만 본다 (이름이 이겨야 한다).
    for side in ("home", "away"):
        for word in _SIDE_WORDS[side]:
            if word not in text:
                continue
            for kind, roles in _ROLE_WORDS.items():
                if not any(f"{word} {r}" in text or f"{word}{r}" in text
                           for r in roles):
                    continue
                if kind == "pitcher":
                    name = pitcher_name(jg, side)
                    if name:
                        return name, "pitcher"
                    continue          # 선발을 모르면 팀으로 넘기지 않는다
                team = jg.get(side)
                if team:
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
    SELECT v.id, v.game_id, v.subject, v.subject_kind, v.raw, v.direction
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
        # ── [MKT-6 2026-09-09] 괴리 변수는 실측 조회가 다르다 ──────────
        #   `subject_kind` 가 투수·팀이 아니라서 위 조회가 비었고, 그대로 두면
        #   `judge_realized(None, None)` 이 **전건을 검증불가**로 만든다.
        #   이 변수의 현실화는 "시장 방향이 이겼는가" 한 줄이면 끝난다.
        from app.engine.market_variable import is_divergence, realized_of

        if is_divergence(r["raw"]):
            sc = await pool.fetchrow(
                "SELECT home_score, away_score FROM games WHERE id = $1", r["game_id"])
            got = realized_of(r["direction"], sc["home_score"], sc["away_score"]) \
                if sc else None
            verdict = UNVERIFIABLE if got is None else (TRUE if got else FALSE)
            actual = None if sc is None else {"home_score": sc["home_score"],
                                              "away_score": sc["away_score"]}
        else:
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


# ── [C5 팀별 보정 스텁 2026-09-05] ────────────────────────────────
#: 팀×변수 현실화율을 볼 최소 표본. **미만이면 숫자를 내지 않는다.**
#  🔴 왜 스텁인가: 지금 대장에 쌓인 표본이 얇다(2026-09-05 기준 채점 114건
#     중 현실화 판정 가능은 5건, 나머지는 임계 미명시로 `unverifiable`).
#     그 상태에서 팀별로 쪼개면 팀당 한 자리 수가 되고, 한 자리 수로 만든
#     보정은 보정이 아니라 잡음이다.
#  ⚠️ **이 함수는 판정에 흐르지 않는다.** 리포트·요약 표시 전용이다.
TEAM_MIN_SAMPLE = 20


async def team_report(pool, sports: tuple[str, ...]) -> list[dict]:
    """팀×변수 현실화 리포트. 표본 미만이면 `status='표본 부족'` 만 돌려준다.

    반환 행: {team, n, realized, unverifiable, rate|None, status}
    `rate` 는 표본이 `TEAM_MIN_SAMPLE` 이상일 때만 채운다 — 그 전에는
    **숫자를 만들지 않는다.** 얇은 표본의 비율은 보는 순간 믿게 된다.
    """
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """SELECT g.home AS team, count(*) AS n,
                      count(*) FILTER (WHERE v.realized = 'true') AS realized,
                      count(*) FILTER (WHERE v.realized = 'unverifiable') AS unver
                 FROM variable_ledger v JOIN games g ON g.id = v.game_id
                WHERE v.sport = ANY($1::text[]) AND v.graded_at IS NOT NULL
                GROUP BY g.home ORDER BY n DESC""", list(sports))
    except Exception as exc:
        logger.debug("[var-ledger] 팀별 집계 실패: %s", exc)
        return []
    out = []
    for r in rows:
        n = int(r["n"])
        gradable = n - int(r["unver"])
        enough = gradable >= TEAM_MIN_SAMPLE
        out.append({
            "team": r["team"], "n": n, "realized": int(r["realized"]),
            "unverifiable": int(r["unver"]),
            "rate": (round(int(r["realized"]) / gradable, 3)
                     if enough and gradable else None),
            "status": "집계" if enough else
                      f"표본 부족 (채점가능 {gradable}/{TEAM_MIN_SAMPLE})",
        })
    return out


# ── [상황 변수 2026-09-06] 유형별 효과 측정 ─────────────────────────
# 🔴 **prior 는 우리 채점 데이터가 만든다.** 상황 유형은 처음엔 연구 근거가
#    없으므로 프롬프트가 %p 를 ±1.0 으로 묶어둔다. 여기서 유형별로 20건이
#    쌓이고 리그 평균 대비 유의 편차가 나오면, 그때 비로소 그 유형에 %p 를
#    실을 자격이 생긴다.
#    ⚠️ 승격은 **사람이 승인해 프롬프트에 반영**한다. 이 함수는 후보만 낸다 —
#       측정이 스스로 판정 입력을 바꾸면 감시가 아니라 되먹임이 된다.
SITUATION_MIN_SAMPLE = 20

#: 유의하다고 보는 최소 편차(비율 포인트). 이보다 작으면 잡음으로 본다.
SITUATION_MIN_EDGE = 0.15

_SIT_ROWS = """
    SELECT v.sport, v.raw, v.realized
      FROM variable_ledger v
     WHERE v.raw LIKE '%[상황]%'
       AND ($1::text IS NULL OR v.sport = $1)
"""

_ALL_ROWS = """
    SELECT v.sport, v.realized
      FROM variable_ledger v
     WHERE ($1::text IS NULL OR v.sport = $1)
"""


def situation_kind_of(raw: str) -> str | None:
    """변수 원문에서 상황 유형을 읽는다. `[상황] retirement — …` 형식."""
    from app.registry import situation_types

    s = raw or ""
    if "[상황]" not in s:
        return None
    for kind in situation_types():
        if kind in s:
            return kind
    return None


async def situation_report(pool, sport: str | None = None) -> dict:
    """유형별 표본·현실화율. 20건 미만은 `표본 부족`으로만 답한다.

    반환: `{"baseline": float|None, "types": [{유형, n, true, rate, status}]}`
    """
    out: dict = {"baseline": None, "types": []}
    if pool is None:
        return out
    try:
        rows = await pool.fetch(_SIT_ROWS, sport)
        allrows = await pool.fetch(_ALL_ROWS, sport)
    except Exception as exc:
        logger.warning("[var-ledger] 상황 리포트 조회 실패: %s", exc)
        return out

    # 리그 평균 — 채점 가능한 것만 센다. `unverifiable` 은 분모가 아니다.
    gradable = [r["realized"] for r in allrows if r["realized"] in (TRUE, FALSE)]
    base = (sum(1 for v in gradable if v == TRUE) / len(gradable)
            if gradable else None)
    out["baseline"] = round(base, 4) if base is not None else None

    buckets: dict[str, list[str]] = {}
    for r in rows:
        kind = situation_kind_of(r["raw"])
        if not kind:
            continue
        buckets.setdefault(kind, []).append(r["realized"])

    for kind, vals in sorted(buckets.items()):
        g = [v for v in vals if v in (TRUE, FALSE)]
        rec: dict = {"유형": kind, "n": len(vals), "채점가능": len(g)}
        if len(g) < SITUATION_MIN_SAMPLE:
            rec["status"] = f"표본 부족 ({len(g)}/{SITUATION_MIN_SAMPLE})"
            rec["rate"] = None
        else:
            rate = sum(1 for v in g if v == TRUE) / len(g)
            rec["rate"] = round(rate, 4)
            edge = None if base is None else rate - base
            rec["edge"] = None if edge is None else round(edge, 4)
            if edge is not None and abs(edge) >= SITUATION_MIN_EDGE:
                rec["status"] = ("prior 승격 후보 "
                                 f"(리그 {base:.0%} 대비 {edge:+.0%})")
            else:
                rec["status"] = "유의 편차 없음 — %p 상한 유지"
        out["types"].append(rec)
    logger.info("[var-ledger] 상황 유형 %d종 · 리그 기준선 %s",
                len(out["types"]), out["baseline"])
    return out


def situation_lines(report: dict) -> list[str]:
    """일일 요약에 실을 줄. 후보가 없으면 한 줄로 끝낸다."""
    types = (report or {}).get("types") or []
    if not types:
        return []
    lines = ["🧭 상황 변수 유형별"]
    for t in types:
        lines.append(f"  · {t['유형']:14s} {t['채점가능']:3d}건 — {t['status']}")
    return lines
