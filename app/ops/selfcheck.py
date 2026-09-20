"""[W1 / wiring_first §W1] 자가 점검 — **자료가 말이 되는지 기계가 센다.**

🔴 **표시 전용이다.** 결과는 Redis·export·/health 로만 간다. 확률·등급·픽에
   들어가는 경로를 만들지 않는다 — 배선을 재는 자가 판정을 건드리면 그 순간
   재는 자가 아니라 판정의 일부가 된다.

🔴 **점검이 파이프라인을 죽이지 않는다.** 자료가 비거나 모양이 달라도 예외를
   올리지 않는다. 못 재면 "못 쟀다"고 적는다(빈 목록).

🔴 **숫자를 여기 적지 않는다.** 문턱은 `config/rules.yaml ops.selfcheck.*` 가
   원본이다(사본 금지 · 실사고 2026-09-02 워치독 오탐 4건이 전부 이 실수였다).

⚠️ **오탐이 두 번째 위험이다.** 실사고 2026-09-05: 감시 오탐을 고친다며 측정
   없이 규칙을 넓혀 검증 184→137건으로 악화시켰다. 그래서 규칙마다 **정상
   자료가 안 잡히는 것**을 함께 잠근다(`tests/test_w1_selfcheck.py`).

09-20 실측으로 만든 규칙들:

    결장 명단이 양 팀에 똑같이 복사됨     마치다@가시와 · AT마드리드@레알
    결장자가 선발 XI 에도 있음            인천 무고사 · 대전 하창래
    오늘 XI 가 아님(lastStarting11)       K리그 2경기 전건
    휴식 597~621h                         포항 · 서울
    open == now (스냅샷 하나)             포항-서울 등 4경기
    KBO 등판 적재가 09-12 에 멈춤         9일째
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: 🔴 **이름표의 원본.** 보고·집계·/health 가 이 이름으로 센다. 여기 없는
#   코드를 다른 곳에서 만들지 마라 — 두 이름표는 영영 안 맞는다.
CODES: tuple = (
    "abs_same_both_sides",     # 결장 명단이 양 팀에 똑같다
    "abs_in_xi",               # 결장자가 선발 XI 에도 있다
    "xi_not_today",            # 오늘 확정 XI 가 아니다
    "rest_hours_absurd",       # 휴식 시간이 말이 안 된다
    "odds_move_exact_zero",    # 이동이 정확히 0 — 스냅샷이 하나다
    "source_blank_ratio",      # 기사 카드 출처 공란 비율이 높다
    "ingest_stale",            # 리그별 적재가 멈췄다
    "player_team_mismatch",    # 타 팀 선수가 명단에 섞였다
    "match_unmapped",          # 외부 경기·팀을 우리 행에 못 붙였다
    "derivatives_empty",       # 파생(총점·핸디) 스냅샷이 없다
    "results_pending",         # 끝났어야 할 경기가 final 이 아니다
    "starter_unknown",         # 예고 선발이 없다
    "lineup_missing",          # T-30 에 확정 라인업이 없다
)

#: `xi_status` 중 **오늘 확정**으로 인정하는 값. 원본은 위성 추출 스키마
#  (`scout_config._XI_STATUS`)의 `official` 이다 — FotMob 의
#  `lastStarting11`(지난 경기 선발)·`predicted`(예상)는 오늘이 아니다.
XI_TODAY: tuple = ("official", "confirmed")


def _th(name: str, default):
    """문턱 하나. 🔴 읽기가 실패해도 점검이 죽지 않는다.

    ⚠️ `app.flow.rules` 가 아니라 `app.engine.rules` 다 — 앞의 것은 경로에
       `flow.` 접두사를 붙이고, `ops:` 는 최상위 블록이다(실측으로 확인).
    """
    try:
        from app.engine import rules as R

        v = R.get(f"ops.selfcheck.{name}")
        return default if v is None else v
    except Exception:
        return default


def _hit(code: str, key, detail: str) -> dict:
    return {"code": code, "key": str(key), "detail": str(detail)[:300]}


def _norm(name) -> str:
    """이름 대조용 정규화. 🔴 **이미 있는 것을 쓴다** — 새 정규식을 짓지 않는다
    (`fotmob.norm` 이 발음부호 치환표까지 읽는 원본이다).

    🔴 **한글은 `norm` 이 통째로 지운다.** 실측 2026-09-21:

        norm('박건우')        → ''          ← 전부 사라진다
        norm('Brøndby IF')    → 'brondby if'
        norm('Stefan Mugoša') → 'stefan mugosa'

       `unicodedata.NFKD → ascii ignore` 라 비라틴 문자는 남지 않는다.
       빈 문자열끼리는 전부 같아 보이므로, 그대로 쓰면 **한국 선수 이름이
       모두 일치**한다(오매칭). 그래서 빈손이면 **소문자·공백 정리만** 한다.
    ⚠️ 이 되돌림은 W1 의 임시 조치다. 이름 대조의 진짜 해법은 `player_id` 이고
       그것은 W2 다(D14b).
    """
    raw = " ".join(str(name or "").lower().split())
    try:
        from app.collectors.fotmob import norm

        got = norm(str(name or ""))
        return got if got.strip() else raw
    except Exception:
        return raw


def _names(v) -> list:
    """목록 칸을 이름 목록으로. 🔴 문자열 하나가 와도 죽지 않는다."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    try:
        return [str(x) for x in v if str(x or "").strip()]
    except TypeError:
        return []


# ── 결장·라인업 ────────────────────────────────────────────────────
def check_absences(teams, *, game_id="") -> list:
    """결장 명단의 세 가지 결함. `teams` 는 `{side: 카드}`.

    🔴 `abs_same_both_sides` — 귀속을 못 정해 **양쪽에 복사**한 것.
       그러면 ⑤의 방향이 양쪽 악재로 잡혀 **상쇄되고**, 결장이 판정에 한 번도
       닿지 않는다(실측 09-20 마치다@가시와 · AT마드리드@레알 · 한화@LG).
    🔴 `abs_in_xi` — 결장자가 **선발 XI 에도** 있는 것. 둘 중 하나는 거짓인데
       어느 쪽인지 알 수 없다(실측 09-20 인천 무고사 · 대전 하창래).
    🔴 `player_team_mismatch` — 명단의 선수가 **그 팀 소속이 아닌** 것
       (실측: 롯데 결장 목록에 박건우/NC).
    """
    out: list = []
    try:
        if not isinstance(teams, dict):
            return out
        sides = {k: (v if isinstance(v, dict) else {})
                 for k, v in teams.items() if k in ("home", "away")}
        # ① 양쪽 복사
        h = {_norm(x) for x in _names((sides.get("home") or {}).get("out"))}
        a = {_norm(x) for x in _names((sides.get("away") or {}).get("out"))}
        if h and a and h == a:
            out.append(_hit("abs_same_both_sides", game_id,
                            f"양 팀 결장 명단이 동일하다({len(h)}명): "
                            + " · ".join(sorted(h))))
        for side, card in sides.items():
            outs = _names(card.get("out"))
            # ② 결장자가 XI 에도 있다
            xi = {_norm(x) for x in _names(card.get("xi"))}
            both = [x for x in outs if _norm(x) in xi]
            if both:
                out.append(_hit("abs_in_xi", f"{game_id}:{side}",
                                "결장인데 선발 XI 에도 있다: " + " · ".join(both)))
            # ③ 타 팀 선수 혼입 — **소속을 아는 경우에만** 본다.
            #    ⚠️ 모르면 잡지 않는다. 모름을 위반으로 만들면 오탐이 된다.
            roster = card.get("roster_team_of")
            team = str(card.get("team") or "")
            if isinstance(roster, dict) and team:
                for x in outs:
                    for nm, owner in roster.items():
                        if _norm(nm) and _norm(nm) in _norm(x) \
                                and _norm(owner) != _norm(team):
                            out.append(_hit(
                                "player_team_mismatch", f"{game_id}:{side}",
                                f"{nm} 은 {owner} 소속인데 {team} 명단에 있다"))
    except Exception as exc:              # 🔴 점검이 죽지 않는다
        logger.info("[selfcheck] check_absences 실패 game=%s: %s", game_id, exc)
    return out


def check_xi(teams, *, game_id="") -> list:
    """`xi_status` 가 **오늘 확정**인가.

    🔴 실측 09-20: K리그 2경기 모두 `lastStarting11` — **지난 경기 선발**이다.
       그것을 확정 XI 로 세면 오늘 빠진 선수를 오늘 뛰는 것으로 읽는다.
    ⚠️ XI 칸 자체가 없으면 잡지 않는다 — 그건 "아직 안 나왔다"이지
       "틀린 값"이 아니다(수집 누락은 `lineup_missing` 이 따로 센다).
    """
    out: list = []
    try:
        if not isinstance(teams, dict):
            return out
        for side in ("home", "away"):
            card = teams.get(side)
            if not isinstance(card, dict) or not _names(card.get("xi")):
                continue
            st = str(card.get("xi_status") or "").strip()
            if st not in XI_TODAY:
                out.append(_hit("xi_not_today", f"{game_id}:{side}",
                                f"xi_status={st or '없음'} — 오늘 확정 XI 가 아니다"))
    except Exception as exc:
        logger.info("[selfcheck] check_xi 실패 game=%s: %s", game_id, exc)
    return out


# ── 일정·휴식 ──────────────────────────────────────────────────────
def check_rest(rows) -> list:
    """휴식 시간이 말이 되나.

    🔴 실측 09-20: 포항 597.4h · 서울 621.1h. 원인은 직전 경기를
       `games(final)` 에서 찾는데 **축구 결과 적재가 끊겨** 있기 때문이다
       (D06b) — 값이 틀린 것이 아니라 **원본이 빈 것**이다.
    ⚠️ 정상값(192h = 8일)은 잡지 않는다. 문턱은 config 가 원본이다.
    """
    out: list = []
    try:
        cap = float(_th("rest_hours_max", 200))
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            try:
                v = float(r.get("rest_hours"))
            except (TypeError, ValueError):
                continue                  # 못 재는 값은 위반이 아니다
            if v > cap:
                out.append(_hit("rest_hours_absurd",
                                r.get("team") or r.get("game_id") or "",
                                f"직전 경기 {v:.1f}h 전 "
                                f"(기준 {cap:.0f}h · 원본 {r.get('basis') or '미상'})"))
    except Exception as exc:
        logger.info("[selfcheck] check_rest 실패: %s", exc)
    return out


# ── 배당 ──────────────────────────────────────────────────────────
def check_odds_move(rows) -> list:
    """이동을 잴 수 있나.

    🔴 실측 09-20: `open` 과 `now` 가 **같은 스냅샷 하나**인 경기 4건.
       그러면 이동이 `0.0` 으로 적히는데, "안 움직였다"와 "잴 수 없다"는
       다른 말이다. ⑩-b 가 그 값을 `not_priced` 판정에 쓰므로 0 으로 두면
       **움직이지 않았다는 근거**가 되어 픽이 선다.
    ⚠️ 여기서는 **세기만** 한다 — 값을 null 로 바꾸는 것은 W4 다.
    """
    out: list = []
    try:
        seen: dict = {}
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            key = (r.get("game_id"), r.get("market"), r.get("side"))
            seen.setdefault(key, set()).add(str(r.get("captured_at") or ""))
        for (gid, market, side), stamps in seen.items():
            if len(stamps) <= 1:
                out.append(_hit("odds_move_exact_zero", f"{gid}:{market}:{side}",
                                "스냅샷이 1개다 — 이동은 0 이 아니라 잴 수 없음"))
    except Exception as exc:
        logger.info("[selfcheck] check_odds_move 실패: %s", exc)
    return out


# ── 적재 ──────────────────────────────────────────────────────────
def check_ingest(rows, *, as_of=None) -> list:
    """리그별 적재가 멈췄나.

    🔴 실측 2026-09-21: KBO 등판 적재 최신 **2026-09-12**(9일째).
       MLB 09-21 · NPB 09-20 은 정상 — 그 둘을 잡으면 오탐이다.
    """
    out: list = []
    try:
        cap_h = float(_th("ingest_stale_hours", 36))
        today = _as_date(as_of) or datetime.now(timezone.utc).date()
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            d = _as_date(r.get("last_d"))
            if d is None:
                continue
            gap_h = (today - d).total_seconds() / 3600 \
                if isinstance(today, datetime) else (today - d).days * 24
            if gap_h > cap_h:
                out.append(_hit("ingest_stale", r.get("league") or r.get("key") or "",
                                f"마지막 적재 {d} — {gap_h / 24:.0f}일째 "
                                f"(기준 {cap_h / 24:.1f}일)"))
    except Exception as exc:
        logger.info("[selfcheck] check_ingest 실패: %s", exc)
    return out


def _as_date(v):
    """`date` · `datetime` · ISO 문자열 → `date`. 모르면 None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, "year") and hasattr(v, "day") and not isinstance(v, str):
        return v
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except Exception:
        return None


# ── 출처 ──────────────────────────────────────────────────────────
def check_sources(cards) -> list:
    """기사 카드 중 **코드가 아는 출처**가 없는 비율.

    🔴 원본 규칙은 `n05_evidence.card_trust` 다 — 여기서 조건을 다시 적지
       않는다(사본 금지). 이 함수는 **세기만** 한다.
    """
    out: list = []
    try:
        from app.flow.nodes.n05_evidence import card_trust

        tot = bad = 0
        for c in (cards or []):
            if not isinstance(c, dict):
                continue
            box, card = c.get("box") or {}, c.get("card") or {}
            if not card:
                continue
            tot += 1
            ok, _ = card_trust(box, card)
            if not ok:
                bad += 1
        if tot:
            ratio = bad / tot
            if ratio >= float(_th("source_blank_ratio", 0.5)):
                out.append(_hit("source_blank_ratio", "전체",
                                f"출처 검증 실패 {bad}/{tot} ({ratio:.0%})"))
    except Exception as exc:
        logger.info("[selfcheck] check_sources 실패: %s", exc)
    return out


# ── 일정 기반 (결과·선발·라인업) ──────────────────────────────────
def check_schedule(rows, *, now=None) -> list:
    """끝났어야 할 경기 · 예고 선발 없음 · T-30 확정 라인업 없음.

    `rows` 는 `games` 행 모양: `starts_at`·`status`·`league`·`id` 와
    (있으면) `has_starter`·`lineup_status`.
    ⚠️ 모르는 칸은 **잡지 않는다** — 없는 칸을 위반으로 만들면 오탐이다.
    """
    out: list = []
    try:
        now = now or datetime.now(timezone.utc)
        pend_h = float(_th("results_pending_hours", 6))
        lm_min = float(_th("lineup_missing_min", 30))
        st_h = float(_th("starter_unknown_hours", 3))
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            ts = _as_dt(r.get("starts_at"))
            if ts is None:
                continue
            gid = r.get("id") or r.get("game_id") or ""
            status = str(r.get("status") or "")
            if status == "scheduled" and ts < now - timedelta(hours=pend_h):
                out.append(_hit("results_pending", gid,
                                f"{r.get('league') or ''} 시작 "
                                f"{(now - ts).total_seconds() / 3600:.0f}h 전인데 "
                                "아직 final 이 아니다"))
                continue
            if status != "scheduled":
                continue
            mins = (ts - now).total_seconds() / 60
            if "has_starter" in r and not r.get("has_starter") \
                    and 0 <= mins <= st_h * 60:
                out.append(_hit("starter_unknown", gid,
                                f"T-{mins:.0f}분인데 예고 선발이 없다"))
            if "lineup_status" in r and 0 <= mins <= lm_min \
                    and str(r.get("lineup_status") or "") not in ("confirmed",
                                                                  "official"):
                out.append(_hit("lineup_missing", gid,
                                f"T-{mins:.0f}분인데 확정 라인업이 없다 "
                                f"(status={r.get('lineup_status')})"))
    except Exception as exc:
        logger.info("[selfcheck] check_schedule 실패: %s", exc)
    return out


def _as_dt(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ── 요약 ──────────────────────────────────────────────────────────
def summarize(hits) -> str:
    """한 줄. 🔴 /health 가 이것을 그대로 쓴다 — 문구를 두 곳에 적지 않는다."""
    rows = [h for h in (hits or []) if isinstance(h, dict) and h.get("code")]
    if not rows:
        return "🟢 자가 점검 위반 없음"
    cnt: dict = {}
    for h in rows:
        cnt[h["code"]] = cnt.get(h["code"], 0) + 1
    body = " · ".join(f"{k} {v}" for k, v in
                      sorted(cnt.items(), key=lambda kv: -kv[1]))
    return f"🔴 자가 점검 위반 {len(rows)}건 — {body}"


#: Redis 키. 🔴 쓰는 쪽·읽는 쪽이 **이 함수를 같이 부른다**(키 불일치 방지 —
#  D01 이 바로 그 결함이었다).
def key_of(date_kst: str) -> str:
    return f"selfcheck:{date_kst}"


#: 결과 보관 기간(초). 하루치를 보고 다음 날 비교할 수 있으면 된다.
TTL_SEC = 3 * 24 * 3600


async def run(pool, redis, *, now=None) -> list:
    """오늘 슬레이트를 훑어 위반 목록을 만들고 Redis 에 남긴다.

    🔴 **조회만 한다.** `games`·`odds_snapshots`·`pitcher_appearances` 를 읽고
       Redis 에 결과 한 줄을 쓴다 — 판정·발송에 닿는 쓰기는 없다.
    🔴 **한 검사가 실패해도 나머지는 돈다.** 순수 함수들이 이미 예외를 삼키고,
       여기서는 질의 단위로 한 번 더 감싼다.
    ⚠️ 못 잰 항목은 **조용히 빠지지 않는다** — 로그로 남긴다(조용한 0 금지).
    """
    import json
    from zoneinfo import ZoneInfo

    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    hits: list = []

    async def _try(label, coro):
        try:
            return await coro
        except Exception as exc:
            logger.warning("[selfcheck] %s 조회 실패: %s", label, exc)
            return []

    # ① 일정 — 결과 미적재·예고 선발·확정 라인업
    rows = await _try("games", pool.fetch(_SLATE_SQL))
    hits += check_schedule([dict(r) for r in rows], now=now)

    # ② 적재 신선도 — 리그별 마지막 등판 적재일
    rows = await _try("ingest", pool.fetch(_INGEST_SQL))
    hits += check_ingest([dict(r) for r in rows], as_of=now.date())

    # ③ 배당 이동 — 오늘 경기의 h2h 스냅샷
    rows = await _try("odds", pool.fetch(_ODDS_SQL))
    hits += check_odds_move([dict(r) for r in rows])

    # ④ 매칭 — 외부 경기·팀을 우리 행에 못 붙였나
    #    🔴 [W2 2026-09-21] `CODES` 에 이름만 있고 **세는 코드가 없었다** —
    #       이 저장소의 "만들어 놓고 안 이음"이다. 여기서 잇는다.
    #    ⚠️ 오늘 경기가 있는 리그만 본다. 경기가 없으면 "못 붙였다"가 아니다.
    hits += await _try("match", _unmapped(pool))

    # ⑤ 추출 상자 — 결장·XI·출처
    try:
        from app.collectors.satellite import EXTRACT_KEY

        cards = []
        pat = EXTRACT_KEY.format(sport="*", game_id="*")
        async for k in redis.scan_iter(match=pat, count=500):
            raw = await redis.get(k)
            if not raw:
                continue
            box = json.loads(raw)
            teams = (box or {}).get("teams") or {}
            if not teams:
                continue
            gid = k.rsplit(":", 1)[-1]
            hits += check_absences(teams, game_id=gid)
            hits += check_xi(teams, game_id=gid)
            for side in ("home", "away"):
                if teams.get(side):
                    cards.append({"box": box, "card": teams[side]})
        hits += check_sources(cards)
    except Exception as exc:
        logger.warning("[selfcheck] 추출 상자 조회 실패: %s", exc)

    try:
        await redis.set(key_of(today), json.dumps(hits, ensure_ascii=False),
                        ex=TTL_SEC)
    except Exception as exc:
        logger.warning("[selfcheck] 기록 실패: %s", exc)
    logger.info("[selfcheck] %s — 위반 %d건 (%s)", today, len(hits),
                summarize(hits))
    return hits


async def _unmapped(pool) -> list:
    """오늘 우리 슬레이트의 팀 중 **FotMob 이름으로 못 찾는** 것.

    🔴 실측 2026-09-21(09-20 하루치 목록 541경기 기준):
         Brondby IF   → 'Brøndby IF'   치환표로 **풀렸다**
         SonderjyskE  → 'Sønderjyske'  치환표로 **풀렸다**
         FC Copenhagen · Jeju United FC · Club Atlético de Madrid ·
         Bayer 04 Leverkusen · Real Madrid CF  → **못 찾는다**(별칭 승인 대기)
    ⚠️ 못 찾는 것을 **자동으로 별칭에 올리지 않는다** — 사람이 승인한 행만
       간다(`config/team_alias_pending.yaml` · AC밀란 오매칭 재발 방지).
    ⚠️ FotMob 을 못 부르면(네트워크·차단) **위반이 아니다** — 못 쟀을 뿐이다.
    """
    out: list = []
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        from app.collectors.fotmob import norm, slate

        rows = await pool.fetch(
            "SELECT DISTINCT league, home, away FROM games "
            "WHERE sport = 'soccer' AND starts_at BETWEEN now() - interval '1 day' "
            "AND now() + interval '1 day'")
        if not rows:
            return out
        day = _dt.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
        theirs = await slate(day)
        if not theirs:
            logger.info("[selfcheck] FotMob 목록이 비었다 — 매칭은 못 쟀다")
            return out
        known = set()
        for r in theirs:
            for side in ("home", "away"):
                if r.get(side):
                    known.add(norm(r[side]))
        for r in rows:
            for side in ("home", "away"):
                name = str(r[side] or "")
                if name and norm(name) not in known:
                    out.append(_hit("match_unmapped", name,
                                    f"{r['league']} — FotMob 이름으로 못 찾는다"))
    except Exception as exc:
        logger.info("[selfcheck] 매칭 조회 실패: %s", exc)
    return out


#: 🔴 조회는 **여기 세 문장뿐이다.** 다른 곳에서 같은 것을 또 묻지 않는다.
_SLATE_SQL = """
    SELECT id, sport, league, starts_at, status, lineup_status,
           (home_pitcher IS NOT NULL AND away_pitcher IS NOT NULL) AS has_starter
      FROM games
     WHERE starts_at BETWEEN now() - interval '2 days'
                         AND now() + interval '1 day'
"""

_INGEST_SQL = """
    SELECT g.league,
           max((g.starts_at AT TIME ZONE 'Asia/Seoul')::date) AS last_d
      FROM pitcher_appearances pa
      JOIN games g ON g.id = pa.game_id
     GROUP BY 1
"""

_ODDS_SQL = """
    SELECT o.game_id, o.market, o.side, o.captured_at
      FROM odds_snapshots o
      JOIN games g ON g.id = o.game_id
     WHERE o.market = 'h2h'
       AND g.starts_at BETWEEN now() - interval '1 day'
                           AND now() + interval '1 day'
"""
