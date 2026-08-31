"""[축구] FotMob 수집 → Sonnet 판정 → 카드. **야구와 동격의 실전 경로다.**

2026-08-31 시범 분석(7경기)으로 검증한 뒤 같은 날 실전 전환했다(사용자 결정).
발송·재판정·T-20 컷·기록·채점 전부 야구와 같은 등급으로 운영한다.

⚠️ 등급 표시를 따로 두지 않는다. 표본이 얇으면 판정이 스스로 확신도 '하'를
   내고 보드만이 된다 — 그것이 등급 표시를 대체한다. 라벨로 신뢰도를 말하는
   대신 판정이 말하게 한다.

정식 크롤러 기반 파이프라인(리그-어댑터·스켈람 전 마켓)은 docs/SOCCER_FORM.md —
야구 v1.1 완료 후 착수하며, 이 모듈은 그때까지의 실전 경로다.

⚠️ **야구 경로를 공유하지 않는다.** 판정·발송·크레딧 가드 어느 것도
   야구 코드를 수정하지 않으며, 축구 판정이 실패해도 야구에 영향이 없다
   (호출부에서 예외 격리). import 경계를 테스트로 잠갔다.

수치는 docs/SOCCER_MANUAL_PROTOCOL.md 와 같다 — 게이트 55/60/75, 클리핑
승 0.20~0.65 · 무 0.18~0.33. 수동 분석과 기준이 같아야 나중에 캘리브레이션
표본으로 합칠 수 있다.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0 Safari/537.36")
LEAGUES = {"EPL": 47, "세리에A": 55, "라리가": 87, "프리메이라리가": 61}
LEAGUE_URL = "https://www.fotmob.com/api/data/leagues"
MATCH_URL = "https://www.fotmob.com/api/data/matchDetails"

DAILY_CAP = 12          # 일일 축구 판정 상한. 초과 시 킥오프 이른 순.
JUDGE_LEAD_MIN = 180    # T-3h 판정
FINAL_CUT_MIN = 20      # 재판정 컷 T-20분
PROVISIONAL_MIN = 40    # T-40분: confirmed 못 잡으면 잠정이 최종

# 게이트 (수동 프로토콜과 동일)
GATE_HOME, GATE_AWAY, GATE_DC = 0.55, 0.60, 0.75
CLIP_WIN = (0.20, 0.65)
CLIP_DRAW = (0.18, 0.33)


def _clip(v, lo, hi):
    return max(lo, min(hi, float(v)))


def normalize(v: dict) -> tuple[float, float, float]:
    """클리핑 후 합 1.0 재정규화. **AI가 아니라 코드가 강제한다.**

    ⚠️ 셋을 각각 반올림하면 합이 1.0에서 최대 1.5e-4 어긋난다. 확률 세 개가
       1을 안 이루면 그 위에 얹는 더블찬스 계산이 미세하게 틀리므로,
       **마지막 값을 잔차로 채워** 합을 정확히 맞춘다.
    """
    ph = _clip(v.get("p_home", 0.33), *CLIP_WIN)
    pd = _clip(v.get("p_draw", 0.25), *CLIP_DRAW)
    pa = _clip(v.get("p_away", 0.33), *CLIP_WIN)
    s = ph + pd + pa
    ph, pd = round(ph / s, 4), round(pd / s, 4)
    return ph, pd, round(1.0 - ph - pd, 4)


def stars(p: float) -> str:
    return ("★★★★★" if p >= 0.60 else "★★★★" if p >= 0.55 else
            "★★★" if p >= 0.50 else "★★" if p >= 0.45 else "★")


def gate(ph: float, pd: float, pa: float) -> tuple[list[str], list[tuple[str, float]]]:
    """축구 게이트. 반환: (사람이 읽는 판정 줄, 통과 마켓 목록)."""
    lines: list[str] = []
    passed: list[tuple[str, float]] = []
    lines.append(f"승패(홈) {ph:.0%} {'≥' if ph >= GATE_HOME else '<'} {GATE_HOME:.0%}"
                 f" {'통과' if ph >= GATE_HOME else '미달'}")
    if ph >= GATE_HOME:
        passed.append(("홈 승", ph))
    lines.append(f"승패(원정) {pa:.0%} {'≥' if pa >= GATE_AWAY else '<'} {GATE_AWAY:.0%}"
                 f" {'통과' if pa >= GATE_AWAY else '미달'}")
    if pa >= GATE_AWAY:
        passed.append(("원정 승", pa))
    dcs = [("1X(홈/무)", ph + pd), ("X2(무/원정)", pd + pa), ("12(승부)", ph + pa)]
    hit = [(n, v) for n, v in dcs if v >= GATE_DC]
    if hit:
        for n, v in hit:
            lines.append(f"더블찬스 {n} {v:.0%} ≥ {GATE_DC:.0%} 통과")
            passed.append((n, v))
    else:
        n, v = max(dcs, key=lambda x: x[1])
        lines.append(f"더블찬스 최고 {n} {v:.0%} < {GATE_DC:.0%} 미달")
    return lines, passed


def gate_result(passed, confirmed: bool) -> str:
    """레저에 남길 게이트 분류. 라인업 미확정이면 추천이 될 수 없다."""
    from app.engine.pick_ledger import GATE_BOARD_ONLY, GATE_RECOMMENDED

    if not passed:
        return GATE_BOARD_ONLY
    return GATE_RECOMMENDED if confirmed else GATE_BOARD_ONLY


def render_card(g: dict) -> str:
    """시범 카드 1장. 어제 검증한 형식 그대로 + 시범 라벨."""
    v = g["verdict"]
    ph, pd, pa = g["p_home"], g["p_draw"], g["p_away"]
    confirmed = g.get("lineup_type") not in (None, "predicted")
    top = max(ph, pa)
    head = "✅ 확정판" if confirmed else "🕐 잠정"
    out = ["⚽️ 축구",
           f"[{g['league']}] {g['home']} vs {g['away']}  ({g['kickoff_kst']} KST)",
           f"판정: 홈 {ph:.0%} / 무 {pd:.0%} / 원정 {pa:.0%}"
           f"  (λ {v.get('lambda_home')}-{v.get('lambda_away')})"
           f" · {stars(top)} · 확신도 {v.get('확신도')} · {head}"]
    for i, r in enumerate(v.get("근거") or [], 1):
        out.append(f"  근거{i}. {r}")
    for i, r in enumerate(v.get("변수") or [], 1):
        out.append(f"  변수{i}. {r}")
    # [v1.1 2단계] 확정판(재판정)이면 무엇이 바뀌어 어디로 움직였는지 싣는다.
    d = v.get("직전대비") or {}
    if isinstance(d, dict):
        chg = [str(x) for x in (d.get("변경입력") or [])][:2]
        mv = str(d.get("이동") or "").strip()
        if chg or (mv and mv != "0"):
            bits = []
            if chg:
                bits.append("변경 " + ", ".join(chg))
            if mv and mv != "0":
                bits.append(f"이동 {mv}")
            out.append("직전대비: " + " · ".join(bits))
    lines, passed = gate(ph, pd, pa)
    out.append("게이트: " + " · ".join(lines))
    if passed:
        need = " · ".join(f"{n} 필요배당 {1.05 / p:.2f}" for n, p in passed)
        out.append(f"가치:   배당 미수집 — {need}")
        out.append("결론:   " + ("✅ 추천 — " if confirmed else "🕐 잠정 — ")
                   + f"확률 통과({', '.join(n for n, _ in passed)})"
                   + ("" if confirmed else "이나 라인업 미확정으로 확정 픽 아님"))
    else:
        out.append("가치:   배당 미수집 (확률 게이트 미달로 평가 생략)")
        out.append("결론:   보드만 — 확률 게이트 미달")
    if not confirmed:
        outs = len(g["home_lineup"]["결장"]) + len(g["away_lineup"]["결장"])
        out.append(f"확정 시 재확인: 라인업({g.get('lineup_type')}→확정) · "
                   f"결장 {outs}명 실제 반영 여부 · 로테이션")
    return "\n".join(out)


# ---------------------------------------------------------------- 수집 (LLM 0콜)

async def _get(client, url, params):
    try:
        r = await client.get(url, params=params)
        return r.status_code, (r.json() if r.status_code == 200 else None)
    except Exception as exc:
        logger.warning("[soccer-trial] 조회 실패 %s: %s", url, exc)
        return None, None


def lineup_state(md: dict) -> dict:
    """matchDetails → 라인업 상태. 프로브와 같은 판별을 쓴다.

    ⚠️ **예상(predicted)과 확정을 가른다.** FotMob은 킥오프 10시간 전에도
       starters 11명을 주지만 lineupType이 'predicted'다(실측 2026-08-31).
       이걸 확정으로 읽으면 잠정 카드가 확정판으로 나간다.
    """
    lu = ((md or {}).get("content") or {}).get("lineup") or {}
    st = {"lineup_type": lu.get("lineupType"), "source": lu.get("source")}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lu.get(key) or {}
        st[f"{side}_lineup"] = {
            "formation": t.get("formation"),
            "결장": [p.get("name") for p in (t.get("unavailable") or [])]}
        st[f"{side}_n"] = len(t.get("starters") or [])
    st["confirmed"] = bool(st["home_n"] >= 11 and st["away_n"] >= 11
                           and st["lineup_type"]
                           and st["lineup_type"] != "predicted")
    return st


def _last5(all_matches, team, before):
    out = []
    for m in all_matches:
        s = m.get("status") or {}
        if not s.get("finished") or not s.get("utcTime"):
            continue
        h, a = m["home"]["name"], m["away"]["name"]
        if team not in (h, a):
            continue
        try:
            dt = datetime.fromisoformat(s["utcTime"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt >= before:
            continue
        parts = (s.get("scoreStr") or "").split("-")
        if len(parts) != 2:
            continue
        try:
            hs, aws = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        home = team == h
        gf, ga = (hs, aws) if home else (aws, hs)
        out.append({"date": dt.astimezone(KST).strftime("%m/%d"),
                    "opp": a if home else h, "ha": "홈" if home else "원정",
                    "score": f"{gf}-{ga}",
                    "res": "승" if gf > ga else ("무" if gf == ga else "패")})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:5]


def _standing(table_blob, team):
    try:
        for grp in (table_blob or []):
            for row in ((grp.get("data") or {}).get("table") or {}).get("all") or []:
                if row.get("name") == team:
                    return {"순위": row.get("idx"), "승점": row.get("pts"),
                            "경기": row.get("played"), "득실": row.get("scoresStr")}
    except Exception:
        pass
    return None


async def collect(window_min: int, cap: int = DAILY_CAP) -> list[dict]:
    """앞으로 `window_min` 분 안에 시작하는 4리그 경기 원자료. **LLM 0콜.**

    상한 초과 시 킥오프 이른 순으로 자른다 — 늦은 경기는 다음 회차에 잡힌다.
    """
    import httpx

    now = datetime.now(UTC)
    games: list[dict] = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as c:
        for lg, lid in LEAGUES.items():
            _, j = await _get(c, LEAGUE_URL, {"id": lid})
            if not j:
                continue
            allm = (j.get("fixtures") or {}).get("allMatches") or []
            tbl = j.get("table") or []
            for m in allm:
                s = m.get("status") or {}
                if s.get("finished") or not s.get("utcTime"):
                    continue
                try:
                    ko = datetime.fromisoformat(s["utcTime"].replace("Z", "+00:00"))
                except ValueError:
                    continue
                if not (now <= ko <= now + timedelta(minutes=window_min)):
                    continue
                games.append({"league": lg, "match_id": int(m["id"]), "kickoff": ko,
                              "home": m["home"]["name"], "away": m["away"]["name"],
                              "_all": allm, "_tbl": tbl})
        games.sort(key=lambda g: g["kickoff"])
        if len(games) > cap:
            logger.warning("[soccer-trial] 대상 %d경기 — 상한 %d로 자른다 "
                           "(킥오프 이른 순)", len(games), cap)
            games = games[:cap]
        out = []
        for g in games:
            _, md = await _get(c, MATCH_URL, {"matchId": g["match_id"]})
            st = lineup_state(md or {})
            out.append({
                "league": g["league"], "match_id": g["match_id"],
                "kickoff": g["kickoff"],
                "kickoff_kst": g["kickoff"].astimezone(KST).strftime("%m/%d %H:%M"),
                "home": g["home"], "away": g["away"],
                "home_last5": _last5(g["_all"], g["home"], now),
                "away_last5": _last5(g["_all"], g["away"], now),
                "home_rank": _standing(g["_tbl"], g["home"]),
                "away_rank": _standing(g["_tbl"], g["away"]),
                **st})
    return out


# ---------------------------------------------------------------- 판정 (Sonnet 1콜)

PROMPT = """당신은 축구 경기 분석가다. 아래 자료만 근거로 이 경기를 판정한다.

[경기] {league} · {away} (원정) @ {home} (홈) · {kickoff} KST
[라인업 상태] {lineup_type}

[홈 {home} 최근 경기(리그)] {home_last5}
[원정 {away} 최근 경기(리그)] {away_last5}
[홈 순위 맥락] {home_rank}
[원정 순위 맥락] {away_rank}
[홈 결장] {home_out}
[원정 결장] {away_out}
[포메이션] 홈 {home_form} / 원정 {away_form}
[직전 판정] (재판정일 때만. 최초 판정이면 null): {prev}

[미확보 — 판정에 반영하지 마라]
- 컵·유럽대항전 경기 기록 (이 자료는 리그 경기만 담고 있다)
- 감독 발언·이적 뉴스 72h

[판정 규칙]
- 근거는 위 자료 안에서만 찾는다. 배당, 팀 명성, 사전 지식은 쓰지 않는다.
- 무승부를 잊지 마라. 축구는 결과의 약 25%가 무승부다. 박빙이면 "홈 약우세"가
  아니라 3분할로 낸다.
- 최근 결과의 액면에 속지 마라. 상대의 급(하위권 상대 연승인지)과 득실 내용
  (1점차 진땀승인지)을 근거에 명시한다.
- 표본이 적으면 확신도를 낮춘다. 시즌 개막 직후(3경기 이하)면 '중'을 넘지 않는다.
- 라인업이 'predicted'면 결장은 확정이 아니다. 결장만으로 우세를 뒤집지 마라.
- 확률 범위: 승/패 각각 0.20~0.65, 무승부 0.18~0.33. 세 확률의 합은 1.0.
- 근거는 인과 사슬로 쓴다 (무엇이 → 무엇을 → 그래서 확률에 어떻게).
- 직전 판정이 있으면: 달라진 입력(라인업 확정, 결장 확정, 새 경기 결과)을
  먼저 식별하고, 그것이 직전 근거 중 무엇을 무효화하는지 판정한 뒤 확률을
  조정한다. 바뀐 입력이 없으면 직전 판정을 유지한다.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{
  "p_home": 0.00, "p_draw": 0.00, "p_away": 0.00,
  "lambda_home": 0.0, "lambda_away": 0.0,
  "우세": "home|away|박빙",
  "근거": ["인과 사슬 3개"],
  "변수": ["판정을 흔들 요인 1~2개"],
  "확신도": "상|중|하",
  "직전대비": {{"변경입력": ["달라진 입력. 최초 판정이면 빈 배열"],
             "무효화된근거": ["직전 근거 중 더 이상 성립하지 않는 것"],
             "이동": "+N.N%p|-N.N%p|0"}}
}}"""


async def judge(g: dict) -> dict | None:
    """경기 1건 판정. Sonnet 1콜. 실패하면 None — 호출부가 건너뛴다."""
    import anthropic

    from app.config import get_settings
    from app.engine.credit_guard import abort_if_credit_gone, trip_credit

    s = get_settings()
    abort_if_credit_gone(f"soccer-trial:{g['away']}@{g['home']}")
    if s.mock_judge:
        return {"p_home": 0.4, "p_draw": 0.25, "p_away": 0.35,
                "lambda_home": 1.3, "lambda_away": 1.2, "우세": "박빙",
                "근거": ["목 판정"], "변수": [], "확신도": "하"}
    cli = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
    p = PROMPT.format(
        league=g["league"], home=g["home"], away=g["away"], kickoff=g["kickoff_kst"],
        lineup_type=g.get("lineup_type"),
        home_last5=json.dumps(g["home_last5"], ensure_ascii=False),
        away_last5=json.dumps(g["away_last5"], ensure_ascii=False),
        home_rank=json.dumps(g["home_rank"], ensure_ascii=False),
        away_rank=json.dumps(g["away_rank"], ensure_ascii=False),
        home_out=", ".join(g["home_lineup"]["결장"]) or "없음",
        away_out=", ".join(g["away_lineup"]["결장"]) or "없음",
        home_form=g["home_lineup"]["formation"], away_form=g["away_lineup"]["formation"],
        prev=json.dumps(g.get("prev_verdict"), ensure_ascii=False, default=str))
    try:
        r = await cli.messages.create(model=s.matchup_model, max_tokens=1500,
                                      messages=[{"role": "user", "content": p}])
    except anthropic.APIStatusError as exc:
        if exc.status_code == 400 and "credit" in str(exc).lower():
            trip_credit(f"soccer-trial/{s.matchup_model}", exc)
        logger.warning("[soccer-trial] 판정 실패 %s@%s: %s", g["away"], g["home"], exc)
        return None
    txt = "".join(b.text for b in r.content if b.type == "text").strip()
    try:
        return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("[soccer-trial] JSON 파싱 실패 %s@%s: %s",
                       g["away"], g["home"], exc)
        return None


async def _find_game_id(pool, g: dict) -> int | None:
    """FotMob 팀명으로 games 행을 찾는다.

    🔴 **완전 일치로는 못 찾는다.** 일정은 football-data가 적재하는데 표기가
       다르다 — 실측 2026-08-31: FotMob 'Lecce'/'Roma' vs football-data
       'US Lecce'/'AS Roma'. 그 결과 오늘 밤 축구 판정이 레저에 한 건도
       기록되지 않았고, 기록이 없으니 채점도 캘리브레이션도 불가능했다.

    킥오프 ±6시간 창의 축구 경기를 후보로 모아 `match_team_name`으로 맞춘다.
    이 저장소에 이미 있는 매처이며(football.py), **동점이면 None**을 돌려
    모호한 매칭을 거부한다 — 잘못 붙이면 남의 경기 결과로 채점된다.
    """
    from app.collectors.football import match_team_name

    rows = await pool.fetch(
        "SELECT id, home, away FROM games WHERE sport='soccer'"
        "   AND starts_at BETWEEN $1::timestamptz - interval '6 hours'"
        "                     AND $1::timestamptz + interval '6 hours'",
        g["kickoff"])
    if not rows:
        return None
    # 완전 일치가 있으면 그것이 답이다 — 매처를 거칠 이유가 없다.
    for r in rows:
        if r["home"] == g["home"] and r["away"] == g["away"]:
            return r["id"]
    home = match_team_name(g["home"], [r["home"] for r in rows])
    away = match_team_name(g["away"], [r["away"] for r in rows])
    if home is None or away is None:
        return None
    for r in rows:
        if r["home"] == home and r["away"] == away:
            logger.info("[soccer-trial] 팀명 매칭 %s@%s → %s@%s",
                        g["away"], g["home"], away, home)
            return r["id"]
    return None


async def record_trial(pool, g: dict, passed) -> None:
    """레저에 시범 등급으로 기록. **trial=true 로 야구와 분리 집계된다.**

    ⚠️ 축구는 games 표에 행이 있어야 FK가 선다. 없으면 기록을 건너뛰고
       그 사실을 남긴다 — 없는 경기 id로 조용히 실패하지 않게.
    """
    if pool is None:
        return
    gid = await _find_game_id(pool, g)
    if gid is None:
        logger.warning("[soccer-trial] games 행 없음 — 레저 기록 생략 %s@%s "
                       "(킥오프 %s)", g["away"], g["home"], g["kickoff"])
        return
    from app.engine.pick_ledger import record_analysis

    jg = {"game_id": gid, "sport": "soccer", "league": g["league"],
          "home": g["home"], "away": g["away"], "p_claude": g["p_home"],
          "lineup_status": "confirmed" if g.get("confirmed") else "predicted",
          "model": (await _model_name()),
          "judge_pass": False,
          "judge_confidence": {"상": "high", "중": "medium", "하": "low"}.get(
              (g["verdict"] or {}).get("확신도"), "medium"),
          "matchup": {"p_home": g["p_home"], "우세": (g["verdict"] or {}).get("우세"),
                      "확신도": (g["verdict"] or {}).get("확신도")}}
    picks = [{"game_id": gid, "market": "h2h",
              "recommended": bool(passed and g.get("confirmed"))}]
    from app.pipeline import today_kst

    # 축구도 정식 기록이다(2026-08-31 실전 전환). trial 컬럼은 이미 기록된
    # 행 보존용으로 남기고 신규는 false — 리그별 집계로 충분하다.
    await record_analysis(pool, {"sport": "soccer", "date": today_kst(),
                                 "games": [jg], "picks": picks})


async def _model_name() -> str:
    from app.config import get_settings

    return get_settings().matchup_model


# ---------------------------------------------------------------- 일일 잡 본체

STATE_KEY = "soccer_trial:{date}:{mid}"     # 값: "provisional" | "confirmed"
COUNT_KEY = "soccer_trial_count:{date}"
PREV_KEY = "soccer_prev_verdict:{date}:{mid}"   # [2단계] 재판정 델타 입력


async def run_once(pool, redis, *, send, now=None) -> dict:
    """T-3h 판정 · confirmed 재판정을 1회 처리. 반환: 집계.

    `send(text)`를 주입받는다 — 테스트가 실발송 없이 검사할 수 있어야 한다.

    상태는 Redis에 남긴다:
      없음        → T-3h 안이면 판정 + 발송 (잠정 또는 확정)
      provisional → confirmed 를 잡고 재판정 컷(T-20) 전이면 재판정 + 확정판 발송
      confirmed   → 더 하지 않는다 (경기당 최대 2콜)
    """
    from app.pipeline import today_kst

    now = now or datetime.now(UTC)
    date = today_kst()
    out = {"judged": 0, "resent": 0, "skipped": 0, "capped": 0}
    games = await collect(JUDGE_LEAD_MIN)
    for g in games:
        lead = (g["kickoff"] - now).total_seconds() / 60
        if lead < FINAL_CUT_MIN:
            out["skipped"] += 1
            continue                       # 재판정 컷 — 더 건드리지 않는다
        key = STATE_KEY.format(date=date, mid=g["match_id"])
        state = await redis.get(key) if redis else None
        # [v1.1 2단계] 직전 판정을 재판정 입력으로 넘긴다. 최초면 None.
        if redis is not None:
            raw = await redis.get(PREV_KEY.format(date=date, mid=g["match_id"]))
            if raw:
                try:
                    g["prev_verdict"] = json.loads(raw)
                except json.JSONDecodeError:
                    g["prev_verdict"] = None
        if state == "confirmed":
            out["skipped"] += 1
            continue
        if state == "provisional" and not g["confirmed"]:
            out["skipped"] += 1
            continue                       # 아직 예상 라인업 — 기다린다
        if redis is not None:
            n = int(await redis.get(COUNT_KEY.format(date=date)) or 0)
            if n >= DAILY_CAP:
                out["capped"] += 1
                logger.warning("[soccer-trial] 일일 상한 %d 도달 — 판정 생략 %s@%s",
                               DAILY_CAP, g["away"], g["home"])
                continue
        v = await judge(g)
        if v is None:
            out["skipped"] += 1
            continue
        ph, pd, pa = normalize(v)
        g.update({"verdict": v, "p_home": ph, "p_draw": pd, "p_away": pa})
        _, passed = gate(ph, pd, pa)
        await send(render_card(g))
        try:
            await record_trial(pool, g, passed)
        except Exception as exc:           # 기록 실패가 발송을 되돌리지 않는다
            logger.warning("[soccer-trial] 레저 기록 실패 %s@%s: %s",
                           g["away"], g["home"], exc)
        if redis is not None:
            await redis.set(key, "confirmed" if g["confirmed"] else "provisional",
                            ex=86400)
            # 다음 회차가 "무엇이 바뀌었나"를 판정할 수 있게 뼈대만 남긴다
            await redis.set(
                PREV_KEY.format(date=date, mid=g["match_id"]),
                json.dumps({k: v.get(k) for k in
                            ("p_home", "p_draw", "p_away", "우세", "근거", "확신도")},
                           ensure_ascii=False, default=str), ex=86400)
            await redis.incr(COUNT_KEY.format(date=date))
            await redis.expire(COUNT_KEY.format(date=date), 86400)
        out["resent" if state == "provisional" else "judged"] += 1
        logger.info("[soccer-trial] %s %s@%s %s %.0f%%/%.0f%%/%.0f%% (T-%.0f분)",
                    "확정판" if g["confirmed"] else "잠정",
                    g["away"], g["home"], g["league"], ph * 100, pd * 100, pa * 100,
                    lead)
    return out
