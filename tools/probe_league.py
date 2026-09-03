"""[전 리그 프로브] 3리그 × 전 구간 — 리그별 비대칭과 침묵 구간을 드러낸다.

🔴 **"없는 것"과 "안 도는 것"을 구분한다.** 2026-09-03 실사고: 감시 3층
   호출부가 아시아 사이클에만 있어 MLB 가 통째로 빠졌는데, 로그는 그냥
   조용했다. grep 으로 "코드 있음"만 보면 이런 건 안 잡힌다 — **어느
   경로에서 불리는가**를 봐야 한다.

판정 3값:
  ✅ 작동 실증 — 이번 실행에서 실제로 값이 나왔다
  ⚪ 코드 존재·실증 불가 — 사유와 실증 예정 시점을 함께 적는다
  🔴 부재 또는 고장

⚠️ **읽기 전용.** 카드를 보내지 않고, 판정을 다시 돌리지 않고, 캐시를
   덮지 않고, ledger·audit 테이블에 쓰지 않는다. 유료 호출 0건.
⚠️ ⚪ 를 ✅ 로 승격하지 마라. 오늘 MLB 자료9 가 그 함정이었다 —
   코드는 정상이었지만 그날 그 경로는 돌지 않았다.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

OK, UNK, BAD = "✅", "⚪", "🔴"
SPORTS = ("kbo", "npb", "mlb")


class Row:
    __slots__ = ("item", "res")

    def __init__(self, item: str):
        self.item = item
        self.res: dict[str, tuple[str, str]] = {}

    def set(self, sport: str, status: str, note: str) -> None:
        self.res[sport] = (status, note)


def _src(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


# ══════════════════════════ E. 게이트 공통성 ══════════════════════════

def check_gate() -> Row:
    """확률·확신도·가치 게이트가 **리그 공통 함수**를 타는가."""
    r = Row("E. 게이트 — 리그 공통 함수")
    vg = _src("app/engine/value_gate.py")
    branches = re.findall(r'sport\s*(?:==|!=)\s*["\'](kbo|npb|mlb)["\']', vg)
    from app.config import get_settings
    from app.engine.deepsearch import _gate_threshold

    s = get_settings()
    for sp in SPORTS:
        home = _gate_threshold(sp, "home", s)
        away = _gate_threshold(sp, "away", s)
        if branches:
            r.set(sp, BAD, f"value_gate 에 리그 분기 {sorted(set(branches))}")
        elif (home, away) != (0.58, 0.63):
            r.set(sp, BAD, f"임계 {home:.2f}/{away:.2f} — 58/63 이 아니다")
        else:
            r.set(sp, OK, f"분기 0건 · 임계 {home:.2f}/원정 {away:.2f} 실계산")
    return r


# ══════════════════════════ F. 트리거 공통성 ══════════════════════════

def check_triggers() -> Row:
    r = Row("F. 트리거 T4·T5·T6 — 리그 분기 없음")
    ds = _src("app/engine/deepsearch.py")
    from app.engine import deepsearch as D

    for name in ("t4_evidence", "t5_evidence", "first_lineup_evidence"):
        if not hasattr(D, name):
            for sp in SPORTS:
                r.set(sp, BAD, f"{name} 부재")
            return r
    # 판별 함수 본문에 리그 이름이 박혀 있으면 비대칭이다
    bad = []
    for name in ("t4_evidence", "t5_evidence", "first_lineup_evidence"):
        i = ds.index(f"def {name}(")
        j = ds.find("\ndef ", i + 1)
        body = ds[i:j if j > 0 else len(ds)]
        if re.search(r'["\'](kbo|npb|mlb)["\']', body):
            bad.append(name)
    for sp in SPORTS:
        if bad:
            r.set(sp, BAD, f"리그 이름이 박힌 판별 함수: {bad}")
        else:
            r.set(sp, OK, "t4·t5·t6 판별 함수 3개 모두 리그 분기 0건")
    return r


# ══════════════════════════ G. 발송 창 ══════════════════════════

def check_send_window() -> Row:
    r = Row("G. 발송 창 상수")
    from app.engine.pregame_push import NPB_FINISH_MIN, SEND_OPEN_MIN

    for sp in SPORTS:
        v = SEND_OPEN_MIN.get(sp)
        if v is None:
            r.set(sp, BAD, "SEND_OPEN_MIN 에 이 리그가 없다 — 창이 안 열린다")
        elif sp == "npb":
            r.set(sp, OK, f"T-{v}분 개시 · T-{NPB_FINISH_MIN} 종료(이원화)")
        else:
            r.set(sp, OK, f"T-{v}분 개시")
    return r


# ══════════════════════════ H. 감시 3층 호출부 ══════════════════════════

def check_monitors() -> Row:
    """🔴 오늘 잡은 유형이다 — grep 이 아니라 **어느 사이클이 부르는가**."""
    r = Row("H. 감시 3층 — 그 리그 경로에 호출부 실재")
    sch = _src("app/scheduler.py")
    from app.llm.gemini import is_available

    # `_run_shadow_panel(redis, <sports>, date)` 각 호출의 종목 인자를 읽는다
    covered: set[str] = set()
    for call in re.findall(r"_run_shadow_panel\(\s*redis,\s*([^,]+),", sch):
        arg = call.strip()
        if arg == "sports":          # 아시아 사이클 — 그 잡의 기본 종목
            covered |= {"kbo", "npb"}
        else:
            covered |= set(re.findall(r'["\'](\w+)["\']', arg))
    l1 = "_spawn_fact_audit" in _src("app/pipeline.py")
    gem = is_available()
    for sp in SPORTS:
        bits = []
        bits.append("L1 훅 " + ("있음" if l1 else "없음"))
        bits.append("L2·L3 " + ("호출됨" if sp in covered else "호출부 없음"))
        bits.append("gemini " + ("가동" if gem else "휴면"))
        if not l1 or sp not in covered:
            r.set(sp, BAD, " · ".join(bits))
        elif not gem:
            r.set(sp, UNK, " · ".join(bits) + " (키 없어 실증 불가)")
        else:
            r.set(sp, OK, " · ".join(bits))
    return r


# ══════════════════════════ I. 채점·동결 기준 ══════════════════════════

def check_ledger() -> Row:
    r = Row("I. 채점 — ledger 기록 · FREEZE_START")
    from app.engine.daily_summary import FREEZE_TARGET, freeze_start

    pl = _src("app/engine/pick_ledger.py")
    has_record = "async def record" in pl or "def record" in pl
    for sp in SPORTS:
        since = freeze_start(sp)
        if not has_record:
            r.set(sp, BAD, "pick_ledger 기록 함수 부재")
        else:
            r.set(sp, OK, f"기록 경로 있음 · N/{FREEZE_TARGET} 은 {since} 슬레이트부터")
    return r


# ══════════════════════════ J. 침묵 스캔 ══════════════════════════

SILENT = re.compile(r"except[^\n]*:\s*\n\s+pass\s*(?:\n|$)")


def check_silence() -> Row:
    """로그 없는 `except: pass` — 실패가 조용히 사라지는 자리."""
    r = Row("J. 침묵 구간 (로그 없는 except-pass)")
    hits: list[str] = []
    for p in sorted(Path("app").rglob("*.py")):
        txt = p.read_text(encoding="utf-8")
        for m in SILENT.finditer(txt):
            line = txt[:m.start()].count("\n") + 1
            hits.append(f"{p}:{line}")
    note = f"{len(hits)}곳" + (f" — {', '.join(hits[:6])}" if hits else "")
    for sp in SPORTS:
        r.set(sp, OK if not hits else UNK, note + " (전 리그 공용 코드, 수정 안 함)")
    return r


# ══════════════════════════ A. 자료 1~9 조립 ══════════════════════════

async def check_materials(redis=None) -> Row:
    """자료별 **조립 함수가 값을 내는가**. 리그별 재료 원본으로 실호출."""
    r = Row("A. 자료1~9 조립 (실수집→payload)")
    from app.engine import matchup as M

    for sp in SPORTS:
        jg = await _sample_jg(sp, redis)
        if jg is None:
            r.set(sp, UNK, "오늘 경기 재료를 못 만들었다 — 슬레이트에서 실증")
            continue
        got, miss = [], []
        for label, fn in (("1박스", M.boxscore_payload), ("3타순", M.lineups_payload),
                          ("7선발시즌", M.starters_season_payload),
                          ("8타선시즌", M.lineup_season_payload),
                          ("9불펜", M.bullpen_payload)):
            (got if fn(jg) else miss).append(label)
        note = f"채움 [{'·'.join(got) or '없음'}]"
        if miss:
            note += f" / 빈칸 [{'·'.join(miss)}]"
        r.set(sp, OK if not miss else UNK, note)
    return r


async def _sample_jg(sport: str, redis) -> dict | None:
    """그 리그 오늘 경기 1건에 재료를 실제로 붙여 본다. **저장하지 않는다.**"""
    from app.collectors.mlb_team_pitching import attach as _pen

    try:
        game = await _today_game(sport)
        if not game:
            return None
        jg = dict(game)
        jg["sport"] = sport
        if sport == "mlb":
            await _pen(jg, redis=redis)
        return jg
    except Exception as exc:
        logger.warning("[probe] %s 표본 조립 실패: %s", sport, exc)
        return None


async def _today_game(sport: str) -> dict | None:
    """DB 에서 오늘 경기 1건. 운영 밖이면 None."""
    try:
        from app.db import get_pool

        pool = await get_pool()
        row = await pool.fetchrow(
            """SELECT id AS game_id, home, away, starts_at, lineup_status
                 FROM games WHERE sport=$1 AND starts_at > now() - interval '6 hours'
                ORDER BY starts_at LIMIT 1""", sport)
        return dict(row) if row else None
    except Exception as exc:
        logger.debug("[probe] %s DB 조회 불가: %s", sport, exc)
        return None


# ══════════════════════════ B. 라인업 ══════════════════════════

async def check_lineups() -> Row:
    """수신 경로가 **살아 있는가** — 최근 수신 시각 · 9명 규칙 · 역행 감시."""
    r = Row("B. 라인업 — 수신 생존·9명·역행 감시")
    sch = _src("app/scheduler.py")
    regress_watch = 'note_lineup_regress' in sch
    for sp in SPORTS:
        try:
            from app.db import get_pool

            pool = await get_pool()
            row = await pool.fetchrow(
                """SELECT max(l.captured_at) AS last,
                          count(*) FILTER (
                              WHERE jsonb_array_length(l.batting_order) <> 9) AS bad,
                          count(*) AS n
                     FROM lineups l JOIN games g ON g.id = l.game_id
                    WHERE g.sport = $1
                      AND l.captured_at > now() - interval '30 hours'""", sp)
            conf = await pool.fetchval(
                """SELECT count(*) FROM games WHERE sport=$1
                    AND lineup_status='confirmed'
                    AND starts_at > now() - interval '18 hours'""", sp)
        except Exception as exc:
            r.set(sp, UNK, f"DB 밖 — 슬레이트에서 실증 ({type(exc).__name__})")
            continue
        if not row or not row["n"]:
            r.set(sp, UNK, "30시간 내 수신 0건 — 창 전이면 정상, 슬레이트에서 실증")
            continue
        note = (f"30h 수신 {row['n']}건 · 최근 {row['last']:%m-%d %H:%M}Z · "
                f"확정 {conf}경기 · 길이이상 {row['bad']}건 · "
                f"역행감시 {'있음' if regress_watch else '없음'}")
        r.set(sp, BAD if not regress_watch else OK, note)
    return r


# ══════════════════════════ C. 판정 ══════════════════════════

async def check_judgement(redis=None) -> Row:
    """프롬프트 보관 훅 · 예산·재시도가 **리그 공통**인가."""
    r = Row("C. 판정 — 프롬프트 보관·예산·절단 재시도")
    mu = _src("app/engine/matchup.py")
    keeps = "_keep_prompt(" in mu
    # 예산에 리그 분기가 있으면 리그마다 다른 판정을 하게 된다
    i = mu.find("async def judge_matchup")
    body = mu[i:mu.find("\nasync def ", i + 1)] if i >= 0 else ""
    branch = re.findall(r'sport\s*(?:==|!=)\s*["\'](kbo|npb|mlb)["\']', body)
    from app.config import get_settings
    from app.engine.matchup import MAX_TOKENS_CEILING

    base = int(get_settings().matchup_max_tokens)
    retry = min(base * 2, MAX_TOKENS_CEILING)
    for sp in SPORTS:
        stored = None
        if redis is not None:
            try:
                from app.engine.fact_audit import PROMPT_KEY

                keys = [k async for k in redis.scan_iter(
                    PROMPT_KEY.format(game_id="*"), count=200)]
                stored = len(keys)
            except Exception as exc:
                logger.debug("[probe] 프롬프트 키 조회 실패: %s", exc)
        note = f"예산 {base}→재시도 {retry} (분기 {len(branch)}건)"
        if branch:
            r.set(sp, BAD, note + " — 리그마다 다른 예산")
        elif not keeps:
            r.set(sp, BAD, "프롬프트 보관 훅 없음 — L1 이 영영 대조 못 한다")
        elif stored:
            r.set(sp, OK, note + f" · 보관된 프롬프트 {stored}건")
        else:
            r.set(sp, UNK, note + " · 보관 훅 있음, 저장분 0 — 슬레이트에서 실증")
    return r


# ══════════════════════════ D. 배당 ══════════════════════════

async def check_odds() -> Row:
    """provider 담당 리그가 실제로 값을 내는가. **레지스트리가 원본이다.**"""
    r = Row("D. 배당 — provider 매칭·실적재")
    from app.registry import ODDS_PROVIDERS, active_providers

    act = {p.name for p in active_providers()}
    for sp in SPORTS:
        mine = [p.name for p in ODDS_PROVIDERS if sp in p.sports and p.name in act]
        if not mine:
            r.set(sp, BAD, "담당 활성 provider 0개")
            continue
        try:
            n = await _live_odds_count(sp)
        except Exception as exc:
            r.set(sp, BAD, f"{mine} — 실호출 실패 {exc!r}")
            continue
        if n is None:
            r.set(sp, UNK, f"{mine} — 이 리그는 슬레이트에서 실증")
        elif n:
            r.set(sp, OK, f"{mine} — 지금 실호출 {n}경기 확보")
        else:
            r.set(sp, UNK, f"{mine} — 실호출 0경기 (소스에 오늘 경기 미게재)")
    return r


async def _live_odds_count(sport: str) -> int | None:
    if sport in ("kbo", "npb"):
        from app.collectors.oddsportal import fetch_league

        return len(await fetch_league(sport, force=True) or {})
    return None          # MLB=ESPN 은 경기 시작 전에만 뜬다 — 슬레이트에서 본다


# ══════════════════════════ 리포트 ══════════════════════════

async def build_matrix(redis=None) -> str:
    rows = [await check_materials(redis), await check_lineups(),
            await check_judgement(redis), await check_odds(),
            check_gate(), check_triggers(), check_send_window(),
            check_monitors(), check_ledger(), check_silence()]
    out = ["| 항목 | KBO | NPB | MLB |", "|---|---|---|---|"]
    for row in rows:
        cells = []
        for sp in SPORTS:
            st, note = row.res.get(sp, (UNK, "미실행"))
            cells.append(f"{st} {note}")
        out.append(f"| **{row.item}** | " + " | ".join(cells) + " |")
    return "\n".join(out)


async def run(redis=None) -> str:
    text = await build_matrix(redis)
    for line in text.splitlines():
        logger.info("[probe-matrix] %s", line)
    return text
