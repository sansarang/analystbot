"""[v1.1 0단계] 픽 레저 — 판정 전건을 기록하고, 결과가 들어오면 채점한다.

목적은 하나다: **규율(임계 58/63·확신도 거부권·뉴스 상한)이 맞는지를 시스템이
스스로 데이터로 답하게 하는 것.** 지금까지는 판정을 내고 발송하면 끝이라
"58%가 옳은 문턱인가"를 영원히 알 수 없었다.

⚠️ 이 모듈은 **측정 전용이다. 어떤 판정 경로도 이 표를 읽지 않는다.**
   CLAUDE.md 판정 철학("채점 성적표는 판정에 쓰지 않는다")은 그대로 유지된다 —
   바뀐 것은 "기록조차 남기지 않는다"뿐이고, 그것은 사용자 지시(v1.1 0단계)다.
   임계값 재검토는 표본이 쌓인 뒤 **별도 지시로만** 한다.

⚠️ 발송 여부와 무관하게 기록한다. 보드만·거부권 탈락 경기가 캘리브레이션
   데이터의 절반이고, 그 경기들의 원판정이 맞았는지를 봐야 거부권이 옳은지 안다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

from app.engine import shadow_blend as _shadow  # noqa: E402

# gate_result 값 집합. 엣지·가치 계열은 4·5단계에서 채워진다 —
# 지금 쓰이는 것은 추천·보드만·거부권탈락 셋뿐이다.
GATE_RECOMMENDED = "추천"
GATE_BOARD_ONLY = "보드만"
GATE_VETOED = "거부권탈락"
GATE_EDGE = "엣지"            # 4단계
GATE_VALUE_WARN = "가치주의"   # 5단계
GATE_VALUE_FAIL = "가치탈락"   # 5단계
GATE_DISCRETION = "재량"       # 수동 분류용

GATE_RESULTS = (
    GATE_EDGE, GATE_RECOMMENDED, GATE_VALUE_WARN, GATE_BOARD_ONLY,
    GATE_VETOED, GATE_VALUE_FAIL, GATE_DISCRETION,
)

# 판정 내용이 같으면 새 이력 행을 만들지 않는다. 이 조합이 "같은 판정"의 정의다.
_SIG_FIELDS = ("p_home", "favored", "confidence", "lineup_status",
               "gate_result", "model")


def gate_result_of(jg: dict, pick: dict | None) -> str:
    """이 경기가 게이트에서 어떻게 분류됐는가.

    거부권을 추천/보드만보다 **먼저** 본다 — 확신도 '하'는 확률이 아무리 높아도
    탈락이고, 그 사실 자체가 캘리브레이션의 핵심 질문이기 때문이다
    ("거부권으로 버린 경기들의 원판정은 실제로 틀렸는가?").
    """
    if jg.get("judge_pass") or jg.get("judge_confidence") == "low":
        return GATE_VETOED
    if not (pick and pick.get("recommended")):
        return GATE_BOARD_ONLY
    # [v1.1 5단계] 확률 통과 위에 가치·엣지를 얹는다. 배당이 없으면
    #   passes_value 가 None 이라 추천 그대로다 — 수집 실패가 추천을 막지 않는다.
    from app.engine.value_gate import CLS_EDGE, CLS_VALUE_WARN, classify

    cls = classify(probability_ok=True, vetoed=False,
                   p=pick.get("p"), odds=pick.get("odds"),
                   edge_status=jg.get("edge_status"))
    if cls == CLS_VALUE_WARN:
        return GATE_VALUE_WARN
    if cls == CLS_EDGE:
        return GATE_EDGE
    return GATE_RECOMMENDED


def _market_cols(jg: dict, pick: dict | None) -> dict:
    """시장 3칸. 값이 없으면 **NULL 로 남긴다** — 지어내지 않는다.

    `divergence_pp` 부호는 `market_baseline_ledger.divergence` 와 같은 방향
    (우리 − 시장, %p)이다. 두 표가 반대 부호를 쓰면 대조할 때마다 헷갈린다.
    """
    mkt = jg.get("p_market_send")
    our = jg.get("p_claude")
    div = None
    if mkt is not None and our is not None:
        div = round((float(our) - float(mkt)) * 100, 2)
    return {
        "odds": (pick or {}).get("odds"),
        "market_prob": float(mkt) if mkt is not None else None,
        "divergence_pp": div,
    }


def _probe_col(jg: dict, market: dict) -> dict:
    """시장 3칸 + **확신도 후보 기록 칸.**

    🔴 후보는 게이트로 가지 않는다. `gate_result_of` 는 여전히
       `judge_confidence`(자기신고)만 읽는다 — 계약 테스트가 잠근다.
    ⚠️ 시장값을 다시 계산하지 않는다. `_market_cols` 가 낸 것을 그대로 넘긴다.
    """
    import json

    from app.engine.confidence import probe

    got = probe(jg, market_prob=market.get("market_prob"),
                divergence_pp=market.get("divergence_pp"))
    return {**market,
            "confidence_probe": json.dumps(got, ensure_ascii=False) if got else None}


async def _fill_market(conn, ledger_id: int, row: dict) -> None:
    """이미 있는 행의 시장 칸만 채운다. **판정 칸은 손대지 않는다.**

    ⚠️ `COALESCE(기존, 새값)` 이다 — 한 번 새긴 시장값을 나중 스냅샷으로
       덮어쓰지 않는다. 판정 시점의 시장이 우리가 재려는 것이고, 경기가
       가까워질수록 시장은 정답에 수렴하므로 덮어쓰면 사후확신이 된다.
    """
    if all(row.get(k) is None
           for k in ("market_prob", "odds", "confidence_probe")):
        return
    try:
        await conn.execute(
            """UPDATE pick_ledger
                  SET odds             = COALESCE(odds, $2),
                      market_prob      = COALESCE(market_prob, $3),
                      divergence_pp    = COALESCE(divergence_pp, $4),
                      confidence_probe = COALESCE(confidence_probe, $5::jsonb)
                WHERE id = $1""",
            ledger_id, row.get("odds"), row.get("market_prob"),
            row.get("divergence_pp"), row.get("confidence_probe"))
    except Exception as exc:                       # 측정 장치가 본체를 죽이지 않는다
        logger.warning("[ledger] 시장 칸 기록 실패 id=%s: %s", ledger_id, exc)


def _side_of(jg: dict, winner: str | None) -> str | None:
    """승자 팀 이름 → `home`|`away`. 이름 대조는 `matchup._name_hits` 가 원본이다."""
    if not winner:
        return None
    from app.engine.matchup import _name_hits

    h = _name_hits(winner, jg.get("home") or "")
    a = _name_hits(winner, jg.get("away") or "")
    if h == a:
        return None
    return "home" if h else "away"


def predicted_side(favored: str | None, p_home: float | None,
                   stored: str | None = None) -> str | None:
    """채점에 쓸 예측 방향.

    `우세`가 home/away면 그대로 쓴다. '박빙'이면 방향 선언이 없으므로
    p_home으로 환산한다 — 캘리브레이션은 확률 구간별 적중률을 보는 것이라
    방향이 없으면 그 표본이 통째로 빠진다. 환산 기준을 코드에 박아 두어
    나중에 "박빙은 어떻게 셌나"를 다시 묻지 않게 한다.
    """
    if favored in ("home", "away"):
        return favored
    # [ORD-3] 확률이 없는 판정은 `predicted_side` 칸에 방향이 그대로 적혀 있다.
    if stored in ("home", "away"):
        return stored
    if p_home is None:
        return None
    return "home" if p_home >= 0.5 else "away"


def _row_from_game(jg: dict, analysis: dict, picks_by_game: dict) -> dict | None:
    """판정된 경기 1건 → 레저 행. 판정이 없으면 None(기록하지 않는다)."""
    gid = jg.get("game_id")
    matchup = jg.get("matchup") or {}
    # 🔴 [ORD-3 2026-09-11] 새 순서 판정에는 **확률이 없다** — 출력이 승자
    #    하나다. 종전 조건을 그대로 두면 그 경기들이 원장에 한 줄도 안 남고,
    #    그러면 이 방식이 맞는지 **영영 못 잰다**(조용한 손실).
    #    확률이 없으면 브라이어·AUC 는 계산할 수 없다. 남는 지표는 승자 적중률
    #    하나이고, 그 하나는 반드시 남긴다.
    if gid is None or (matchup.get("p_home") is None
                       and not matchup.get("승자")):
        return None                      # 판정 없음 — 레저는 판정의 원장이다
    pick = picks_by_game.get(gid)
    return {
        # 🔴 [WIR-1 2026-09-18] **공식 결장을 채점까지 내려보낸다.** 밑줄 키는
        #    원장 컬럼이 아니다 — `_record_side_effects` 가 받아 쓰고 끝난다.
        #    (INSERT 는 컬럼을 명시 나열하고 `_same_judgement` 는 `_SIG_FIELDS`
        #     만 훑으므로 이 키는 어디에도 새지 않는다. 확인하고 더했다.)
        #    `research["absences"]` 는 `absences.py` 가 statsapi(IL 명단 +
        #    확정 라인업)로 만든 값이다. 여기까지 와 있는데 채점이 못 봤다.
        "_absences": (jg.get("research") or {}).get("absences"),
        "game_id": int(gid),
        "sport": analysis.get("sport") or jg.get("sport") or "",
        "league": jg.get("league"),
        "date": analysis.get("date") or "",
        "p_home": jg.get("p_claude"),
        # [PROB-1] 시장 뼈대·코드 조정. 판정(LLM)은 이 값을 보지 않는다.
        # [CONF-1] 확신은 **코드 등급**이다. LLM 자기신고는 아래 섀도 칸으로.
        "code_confidence": jg.get("code_confidence"),
        # [LLMS-1 결정 D] LLM 출력은 **기록 전용** — 카드·발송에 쓰지 않는다.
        # 🔴 [P0-1 2026-09-15 결정 D] **LLM 원값을 적는다.** 코드가 덮어쓴
        #    뒤라면 `matchup["승자"]` 는 이미 코드 값이다 — 그것을 여기 적으면
        #    섀도 비교가 자기 자신과의 비교가 된다(항상 일치).
        #    대피본(`jg["llm_verdict"]`)이 있으면 그것이 원본이다.
        "llm_winner": ((jg.get("llm_verdict") or {}).get("승자")
                       if jg.get("llm_verdict") is not None
                       else (matchup.get("승자") or jg.get("winner"))),
        "llm_level": ((jg.get("llm_verdict") or {}).get("확신")
                      if jg.get("llm_verdict") is not None
                      else (matchup.get("확신") or matchup.get("확신도"))),
        # 🔴 [LAM-1 2026-09-17] **우리 마켓 확률을 버리지 않는다.**
        #    scoring 이 총점·핸디 확률을 이미 내는데 pipeline 이 담아만 두고
        #    원장에 안 실어서, 구조 픽이 총점을 영영 못 골랐다.
        "model_probs": jg.get("model_probs"),
        "p_market_spine": jg.get("p_market_spine"),
        # 🔴 [SEND-1] **실제 나간 값**을 남긴다. `p_code` 는 판정 직후(딥서치
        #    앞) 값이라 카드 숫자와 다르다 — 사후 대조는 나간 값으로 해야 한다.
        "p_code": jg.get("p_send") or jg.get("p_code"),
        "adj_pp": jg.get("adj_pp"),
        # [PA-23 · 지시문 5단계] delta 옆에 **근거**를 같이 남긴다.
        "adj_evidence": (json.dumps(jg.get("adj_evidence"), ensure_ascii=False)
                         if jg.get("adj_evidence") else None),
        # [MBF-1] 야구 모델 확률 — **기록 전용**(`model_w = 0`).
        "p_model": jg.get("p_model"),
        "model_src": jg.get("model_src"),
        "model_w": jg.get("model_w"),
        "model_gap_pp": jg.get("model_gap_pp"),
        # 🔴 `winner` 가 아니다 — 그 칸은 채점이 채우는 **실제 승자**다.
        #    예측은 `predicted_side` 에 home|away 로 넣는다(팀 이름이 아니라
        #    방향이어야 `hit` 비교가 종전 규약 그대로 된다).
        "predicted_side": _side_of(jg, matchup.get("승자") or jg.get("winner")),
        # 🔴 [U0-c → U12 2026-09-15] v3 경로는 `우세` 키를 쓰지 않는다.
        #    실측: ACL 4경기 favored 전부 NULL. 예측은 predicted_side 에만
        #    들어갔고, 그 탓에 favored 로 채점하는 옛 리포트가 v3 경기를
        #    통째로 못 봤다.
        #    ⚠️ **predicted_side 를 그대로** 넣는다. 새로 계산하지 않는다 —
        #       두 칸이 갈리면 채점이 어느 쪽인지 모른다.
        "favored": (matchup.get("우세")
                    or _side_of(jg, matchup.get("승자") or jg.get("winner"))),
        # 🔴 [P0-1 2026-09-15] 코드 승자와 LLM 승자의 불일치. 칸은 스키마에
        #    있었는데 **쓰는 코드가 없었다**(실측: 4경기 전부 NULL).
        #    원본은 `matchup.apply_code_verdict` 가 `jg["gate_vs_llm"]` 에 넣는다.
        "gate_vs_llm": jg.get("gate_vs_llm"),
        # [ORD-12] 새 순서는 `확신`(상|중|하) 한 칸만 낸다 — 종전 `확신도` 와
        #   **같은 눈금**이라 같은 컬럼에 넣는다. 새 컬럼을 만들지 않는다.
        # 🔴 [CONF-1] **코드 등급이 우선한다.** 없으면 종전 LLM 자기신고로 폴백
        #    한다 — v3 가 꺼진 경로에는 아직 코드 등급이 없다.
        "confidence": (jg.get("code_confidence")
                       or matchup.get("확신도") or matchup.get("확신")),
        "lineup_status": jg.get("lineup_status") or "none",
        "gate_result": gate_result_of(jg, pick),
        "model": jg.get("model") or matchup.get("model"),
        # [시장 2026-09-07] 파이프라인이 판정 직후 이미 계산해 둔 값을 **버리고**
        #   있었다. 컬럼은 처음부터 있었고 INSERT 만 안 썼다.
        #   🔴 실측: 원장 621행 중 divergence_pp 0 · market_prob 0 — 시장 신호가
        #      캘리브레이션에 한 번도 닿은 적이 없다. 같은 56경기에서 시장
        #      60.7% · 우리 50.0% 였는데 그 격차를 볼 방법이 없었다.
        #   ⚠️ 배당 격리는 그대로다 — 이 값은 **판정이 끝난 뒤** 붙는 기록이고,
        #      판정 프롬프트로는 가지 않는다.
        **_probe_col(jg, _market_cols(jg, pick)),
        # [BLD-1 2026-09-11] PL-1 섀도 앙상블 — **기록만 한다.**
        #   카드·게이트·판정은 이 값을 읽지 않는다. 계산이 터져도 원장 기록을
        #   막지 않는다(`safe_compute`). 리그별 50건 시점에 비교 리포트를 만든다.
        "shadow_blend": _shadow.safe_compute(jg),
    }


def _same_judgement(row: dict, existing) -> bool:
    for f in _SIG_FIELDS:
        a, b = row.get(f), existing[f]
        if f == "p_home":
            if (a is None) != (b is None):
                return False
            if a is not None and abs(float(a) - float(b)) > 1e-9:
                return False
        elif a != b:
            return False
    return True


async def _record_side_effects(conn, game_id: int, redis=None, *,
                               clv_at: str | None = None,
                               absences: list | None = None,
                               analysis: bool = True) -> None:
    """[PA-19] 판정 뒤 **저장 전용** 기록을 한 자리에서 돌린다.

    🔴 **판정이 바뀌었든 아니든 돈다.** 이 값들은 판정이 같아도 시간이 지나면
       달라진다 — 배당은 나중에 오고, 라인업은 T-60 에 뜨고, 위성 추출은 다음
       사이클에 붙는다. 종전에는 `unchanged` 에서 `continue` 로 끊겨
       사전값·게이트·가설·확인·흐름·구조·북간이 **영원히 안 찼다.**
    🔴 **하나가 터져도 나머지는 돈다.** 각각을 따로 감싼다.
    🔴 **판정을 건드리지 않는다.** 전부 저장 전용이다.
    ⚠️ `clv_at` 은 판정 시각 배당(CLV-1) 전용이다 — 판정이 안 바뀐 회차에는
       다시 찍지 않는다(그 시각은 이미 지났다).
    """
    if clv_at:
        try:
            await record_clv(conn, game_id=game_id, at=clv_at)
        except Exception as exc:
            logger.warning("[clv] game=%s 판정시각 배당 기록 실패: %s", game_id, exc)
    try:
        await record_move(conn, game_id=game_id)
    except Exception as exc:
        logger.warning("[move] game=%s 이동 분류 실패: %s", game_id, exc)
    try:
        await record_book_gap(conn, game_id=game_id)
    except Exception as exc:
        logger.warning("[book-gap] game=%s 실패: %s", game_id, exc)
    gate = None
    try:
        gate = await record_prior(conn, game_id=game_id)
    except Exception as exc:
        logger.warning("[gate] game=%s 사전값 기록 실패: %s", game_id, exc)
    # 🔴 [LDG-2 2026-09-20] **여기만 LLM 을 쓴다**(U12 분석). 나머지 넷은
    #    `odds_snapshots` 만 읽는 저장 전용이다.
    #    ⚠️ 사람이 손으로 돌리는 도구(`tools/ledger_add.py`)가 이것까지 부르면
    #       ⑫ 서술이 쓸 무료 한도를 태운다 — 실측 2026-09-20: 한 행에 gemini
    #       402 + groq 429 로 사슬 2개를 소진했다. 그래서 끌 수 있게 한다.
    #    ⚠️ 기본값은 **종전 그대로 True** 다 — 판정 경로의 동작을 바꾸지 않는다.
    if not analysis:
        logger.info("[analysis] game=%s 생략 — 저장 전용 호출(LLM 안 씀)", game_id)
        return
    try:
        await record_confirm_and_analysis(conn, game_id=game_id, gate=gate,
                                          redis=redis, absences=absences)
    except Exception as exc:
        logger.warning("[analysis] game=%s 실패: %s", game_id, exc)


async def record_analysis(pool, analysis: dict, *, trial: bool = False) -> dict:
    """분석 1슬레이트의 판정 전건을 레저에 반영. 반환: {inserted, rejudged, unchanged}.

    멱등이다 — 같은 분석을 여러 번 저장해도(캐시 재저장 등) 이력 행이 늘지 않는다.
    판정 내용이 실제로 달라졌을 때만 옛 행을 is_final=false로 내리고 새 행을 넣는다.

    `trial=True`는 시범 운영 등급(축구)이다 — 캘리브레이션에서 야구와 **분리
    집계**한다. 검증된 파이프라인과 시범 경로의 성적을 한 표에 섞으면 둘 다
    못 믿게 된다.

    ⚠️ 레저 실패가 발송을 막지 않는다. 측정 장치가 본체를 죽이면 안 된다.
    """
    stats = {"inserted": 0, "rejudged": 0, "unchanged": 0, "failed": 0}
    if pool is None or not analysis:
        return stats
    picks_by_game: dict = {}
    for p in analysis.get("picks") or []:
        # 승패(h2h) 픽이 그 경기의 대표다. 토탈·핸디로 게이트 결과를 정하면
        # 야구(승패만 평가)와 축구가 서로 다른 기준으로 기록된다.
        if p.get("market") == "h2h" and p.get("game_id") is not None:
            picks_by_game.setdefault(p["game_id"], p)

    for jg in analysis.get("games") or []:
        row = _row_from_game(jg, analysis, picks_by_game)
        if row is None:
            continue
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    existing = await conn.fetchrow(
                        "SELECT id, rejudge_count, "
                        + ", ".join(_SIG_FIELDS) +
                        " FROM pick_ledger"
                        # 🔴 [LED-1 2026-09-10] **날짜로 갈라 찾지 않는다.**
                        #    종전 `game_id AND date` 는 같은 경기가 다른 슬레이트
                        #    날짜로 한 번 더 들어오면 기존 행을 못 찾고 새 최종
                        #    행을 만들었다. 실측: is_final 209행 / 고유 경기 199
                        #    — 잉여 10건이 전부 이 경로다.
                        #    game=1853 Athletics@Texas(실제 8-5 홈승)은
                        #      09-01 p=0.60 home(적중) · 09-02 p=0.46 away(실패)
                        #    두 개의 "최종"을 갖고 있었다 — 어느 행을 읽느냐로
                        #    적중률이 바뀐다.
                        #    ⚠️ 더블헤더는 game_id 가 따로 발급된다.
                        #       한 경기 = 한 최종 판정이 맞다.
                        " WHERE game_id = $1 AND is_final"
                        " FOR UPDATE",
                        row["game_id"])
                    if existing is not None and _same_judgement(row, existing):
                        # 🔴 판정은 그대로여도 **시장은 나중에 온다.** 여기서
                        #    그냥 넘기면 판정이 배당보다 먼저 끝난 경기는
                        #    시장 칸이 영영 NULL 로 남는다.
                        #    이력 행은 늘리지 않는다 — 시장은 판정이 아니다.
                        await _fill_market(conn, existing["id"], row)
                        # 🔴 [PA-19 2026-09-16] **부수 기록도 여기서 돈다.**
                        #    종전에는 `continue` 로 끊어서 사전값·게이트·가설·
                        #    확인·흐름·구조·북간이 전부 건너뛰어졌다. 그 값들은
                        #    **판정이 같아도 시간이 지나면 달라진다** — 배당은
                        #    나중에 오고, 라인업은 T-60 에 뜨고, 위성 추출은
                        #    다음 사이클에 붙는다. 시장에 대해서만 그것을 알고
                        #    예외를 뒀는데 나머지 여섯은 안 뒀다.
                        #    🔴 실측 2026-09-16: ACLE 2경기가 `[v3]` 판정을
                        #       두 번 냈는데 원장은 judged_at 06:16 그대로 ·
                        #       사전값 None · 게이트 None · need 0 이었다.
                        #       축구는 같은 승자가 반복돼 **영원히 unchanged** 라
                        #       티어를 채우고 길을 열어도 값이 안 찼다.
                        #    ⚠️ **이력 행은 늘리지 않는다**(시장과 같은 규약).
                        # ⚠️ redis 는 안 넘긴다 — `record_confirm_and_analysis` 가
                        #    필요할 때 스스로 연다(호출부에 핸들이 없다).
                        await _record_side_effects(
                            conn, row["game_id"],
                            absences=row.get("_absences"))
                        stats["unchanged"] += 1
                        continue
                    n = 0
                    if existing is not None:
                        await conn.execute(
                            "UPDATE pick_ledger SET is_final = FALSE WHERE id = $1",
                            existing["id"])
                        n = int(existing["rejudge_count"]) + 1
                    await conn.execute(
                        """INSERT INTO pick_ledger
                             (game_id, sport, league, date, p_home, favored,
                              confidence, lineup_status, gate_result, model,
                              rejudge_count, is_final, trial,
                              odds, market_prob, divergence_pp,
                              confidence_probe, shadow_blend, predicted_side,
                              p_market, p_code, adj_pp, adj_evidence,
                              llm_winner, llm_level,
                              p_model, model_src, model_w, model_gap_pp,
                              gate_vs_llm, model_probs)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,TRUE,$12,
                                   $13,$14,$15,$16::jsonb,$17::jsonb,$18,
                                   $19,$20,$21::jsonb,$22::jsonb,$23,$24,
                                   $25,$26,$27,$28,$29,$30::jsonb)""",
                        row["game_id"], row["sport"], row["league"], row["date"],
                        row["p_home"], row["favored"], row["confidence"],
                        row["lineup_status"], row["gate_result"], row["model"], n,
                        trial,
                        row["odds"], row["market_prob"], row["divergence_pp"],
                        row["confidence_probe"],
                        json.dumps(row.get("shadow_blend"), ensure_ascii=False)
                        if row.get("shadow_blend") else None,
                        row.get("predicted_side"),
                        row.get("p_market_spine"), row.get("p_code"),
                        row.get("adj_pp"), row.get("adj_evidence"),
                        row.get("llm_winner"),
                        row.get("llm_level"),
                        row.get("p_model"), row.get("model_src"),
                        row.get("model_w"), row.get("model_gap_pp"),
                        row.get("gate_vs_llm"),
                        # 🔴 [LAM-1] 칸을 늘렸으면 **자리표도 늘린다**($30).
                        #    PA-23 에서 칸만 늘리고 안 늘려 저장이 터질 뻔했다.
                        json.dumps(row.get("model_probs"), ensure_ascii=False)
                        if row.get("model_probs") else None)
                    stats["rejudged" if existing is not None else "inserted"] += 1
                    # [PA-19] 부수 기록은 **한 곳**이다 — unchanged 분기와
                    #   같은 함수를 부른다(두 곳에 적으면 한쪽만 늘어난다).
                    await _record_side_effects(conn, row["game_id"],
                                               clv_at="verdict",
                                               absences=row.get("_absences"))
        except Exception as exc:
            # 한 경기 실패가 나머지를 막지 않는다. 다만 **조용히 넘기지 않는다** —
            # 레저가 판정의 유일한 영구 기록이 된 이상, 기록 실패는 그 판정이
            # 영원히 사라진다는 뜻이다. 호출자가 CRITICAL로 올릴 수 있게 센다.
            stats["failed"] += 1
            logger.warning("[ledger] 기록 실패 game=%s: %s", row.get("game_id"), exc)
    if stats["inserted"] or stats["rejudged"]:
        logger.info("[ledger] %s %s — 신규 %d · 재판정 %d · 변화없음 %d",
                    analysis.get("sport"), analysis.get("date"),
                    stats["inserted"], stats["rejudged"], stats["unchanged"])
    return stats


#: 🔴 [W3-2 / wiring_first 2026-09-21] **1X2 자동 채점을 해도 되는 종료 근거.**
#   원본은 여기 하나다 — `fotmob._FINAL_REASONS` 는 "종료인가"를 답하고,
#   이쪽은 "채점해도 되는가"를 답한다. 다른 질문이라 표를 나눈다.
#   ⚠️ 옛 행·다른 소스는 전부 `None` 이다. **그것은 채점한다** — 막느라 정상
#      채점까지 멈추면 고친 게 아니라 끈 것이다.
_GRADEABLE_BASIS = (None, "", "FT")


def gradeable_basis(basis) -> bool:
    """이 종료 근거로 승패를 채점해도 되는가.

    🔴 연장(`AET`)·승부차기(`Pen`)는 **안 된다.** 연장 3-2 를 정규시간 홈 승으로
       읽으면 적중 판정이 통째로 거짓이 된다 — 90분에는 2-2 무승부였을 수 있다.
    🔴 **모르는 표지도 안 된다.** 지어내지 않는다(`Awarded`·`WO` 등).
    """
    if basis is None:
        return True
    return str(basis).strip() in _GRADEABLE_BASIS


async def grade_pending(pool, sport: str | None = None) -> dict:
    """미채점 행에 결과를 붙인다. 반환: {graded, void}.

    우천취소·서스펜디드·노게임은 void=true로 닫는다 — 미채점으로 남겨 두면
    "채점 결손"과 구분되지 않아 무결손 판정을 못 한다.

    ⚠️ 진행 중(live) 경기는 건드리지 않는다. status가 final인 것만 채점한다.
    """
    out = {"graded": 0, "void": 0}
    if pool is None:
        return out
    # [C3] 변수 원장도 같은 잡에서 채점한다 — 따로 돌면 한쪽만 밀린다.
    #   ⚠️ 실패해도 픽 채점을 막지 않는다.
    #   ⚠️ **반환 dict 에 넣지 않는다.** `{graded, void}` 는 호출부·테스트가
    #      정확히 비교하는 계약이다. 결과는 로그와 `variable_ledger` 에 남고
    #      일일 요약은 원장을 직접 읽는다.
    try:
        from app.engine.variable_ledger import grade as _grade_vars

        v = await _grade_vars(pool, sport)
        if v.get("graded"):
            logger.info("[ledger] 변수 채점 동반 실행 %s", v)
    except Exception as exc:
        logger.warning("[ledger] 변수 채점 생략: %s", exc)
    # [시장 기준선] 같은 잡에서 채점한다 — **새 잡을 만들지 않는다**
    #   (타이밍 결합 회피: 따로 돌면 한쪽만 밀린다).
    #   ⚠️ 반환 계약 `{graded, void}` 는 건드리지 않는다.
    try:
        from app.engine.market_baseline import grade as _grade_market

        mb = await _grade_market(pool, sport)
        if mb.get("graded"):
            logger.info("[ledger] 시장 기준선 채점 동반 실행 %s", mb)
    except Exception as exc:
        logger.warning("[ledger] 시장 기준선 채점 생략: %s", exc)
    where_sport = " AND l.sport = $1" if sport else ""
    args = [sport] if sport else []
    rows = await pool.fetch(
        f"""SELECT l.id, l.game_id, l.sport, l.favored, l.p_home,
                  l.predicted_side,
                  g.status, g.home_score, g.away_score, g.result_basis
              FROM pick_ledger l JOIN games g ON g.id = l.game_id
             WHERE l.graded_at IS NULL
               AND g.status IN ('final', 'cancelled', 'suspended', 'postponed')
               {where_sport}""", *args)
    for r in rows:
        # 🔴 [W3-2] **연장·승부차기는 1X2 자동 채점에서 뺀다.**
        #    점수는 이미 저장돼 있다 — 채점만 사람이 확인할 때까지 미룬다.
        #    ⚠️ 조용히 사라지지 않는다: 건수를 세고 로그로 남긴다.
        if r["status"] == "final" and not gradeable_basis(r["result_basis"]):
            out["needs_90"] = out.get("needs_90", 0) + 1
            logger.warning("[ledger] game=%s 종료 근거 %r — 1X2 자동 채점에서 "
                           "제외한다(90분 점수 확인 필요)",
                           r["game_id"], r["result_basis"])
            continue
        # [CLV-1] 마감 배당을 남긴다 — `_CLV_SNAP` 이 **킥오프 이전** 마지막
        #   스냅샷만 고르므로 채점 시점에 불러도 값은 마감 배당이다.
        #   ⚠️ 저장 전용. 채점 결과(`hit`)에 이 값을 쓰지 않는다.
        try:
            await record_clv(pool, game_id=r["game_id"], at="closing")
        except Exception as exc:
            logger.warning("[clv] game=%s 마감 배당 기록 실패: %s", r["game_id"], exc)
        if r["status"] != "final" or r["home_score"] is None or r["away_score"] is None:
            await pool.execute(
                "UPDATE pick_ledger SET void = TRUE, graded_at = now() WHERE id = $1",
                r["id"])
            out["void"] += 1
            continue
        h, a = int(r["home_score"]), int(r["away_score"])
        winner = "home" if h > a else "away" if a > h else "draw"
        side = predicted_side(r["favored"], r["p_home"], r.get("predicted_side"))
        # ⚠️ **무승부는 채점 분모에서 제외한다(void 아님).** hit=None 으로 두어
        #    캘리브레이션 집계가 건너뛰게 한다. 경기는 정상 성립했으므로
        #    void(우천취소·서스펜디드)와 구분해야 한다. KBO 는 연장 12회에도
        #    동점이면 무승부다. → docs/MODEL.md
        hit = None if (side is None or winner == "draw") else (side == winner)
        await pool.execute(
            """UPDATE pick_ledger
                  SET final_score = $2, winner = $3, hit = $4, graded_at = now()
                WHERE id = $1""",
            # 🔴 **"홈-원정" 순.** 종전 f"{a}-{h}" 는 원정-홈이라 카드·중계
            #    표기와 순서가 뒤집혀 있었다. 기존 행은 건드리지 않는다 —
            #    소급 수정하면 어느 순서로 적힌 행인지 구분할 수 없게 된다.
            r["id"], f"{h}-{a}", winner, hit)
        out["graded"] += 1
        # 건별로 남긴다 — "채점 N건"만으로는 무엇이 맞고 틀렸는지 볼 수 없고,
        # 운영 DB를 직접 조회할 수 없을 때 이 로그가 유일한 확인 경로다.
        # 🔴 `game=` 이었지만 실제 값은 `pick_ledger.id` 다 — 로그를 보고
        #    games.id 로 찾으면 엉뚱한 경기가 나온다. 둘 다 적는다.
        logger.info("[ledger] 채점 ledger_id=%s game_id=%s %s 예측=%s(p_home=%s) "
                    "결과=%s(%s 홈-원정) → %s",
                    r["id"], r.get("game_id"), r.get("sport") or "", side,
                    r["p_home"], winner, f"{h}-{a}",
                    "적중" if hit else ("무승부(분모 제외)" if hit is None else "빗나감"))
    if out["graded"] or out["void"]:
        logger.info("[ledger] 채점 %d건 · void %d건", out["graded"], out["void"])
    return out


# ---------------------------------------------------------------- 소급 백필 (1회성)
#
# ⚠️ **이 절은 1회성이다.** Redis에 남아 있던 판정을 레저로 옮겨 담기 위한 것이고,
#    백필이 끝났음을 확인한 뒤에는 다음 배포에서 통째로 지워도 된다
#    (호출부: scheduler.startup_backfill_job).
#    남겨 두어도 해롭지는 않다 — 멱등이고, 처리한 키는 건너뛴다.

SLATE_KEY_RE = re.compile(r"^analysis:(?P<sport>[a-z]+):(?P<date>\d{4}-\d{2}-\d{2})$")
BACKFILL_SEEN = "ledger_backfill_seen"      # 처리한 슬레이트 키 집합 (Redis SET)


async def backfill_from_redis(pool, redis, since: str, *, dry_run: bool = False,
                              skip_seen: bool = True) -> dict:
    """Redis 슬레이트 분석(`analysis:{sport}:{date}`)을 레저로 옮긴다.

    ⚠️ 읽기만 한다 — Redis 키를 지우거나 고치지 않는다.
    ⚠️ 슬레이트 키만 쓴다. 경기별 키(`analysis:{sport}:{game_id}:{date}`)에는
       게이트 결과·라인업 상태가 없어 레저의 절반이 빈다 — 반쪽 데이터로
       캘리브레이션을 오염시키지 않는다.

    멱등성은 두 겹이다: ① 처리한 키를 `ledger_backfill_seen`에 남겨 건너뛰고
    ② 건너뛰지 못해도 `record_analysis`가 같은 판정에 이력 행을 만들지 않는다.
    ①만으로는 부족하다 — Redis가 비워지면 ②가 받아낸다.
    """
    stats = {"slates": 0, "seen": 0, "inserted": 0, "rejudged": 0,
             "unchanged": 0, "failed": 0, "skipped": 0}
    if pool is None or redis is None:
        return stats
    keys = [k async for k in redis.scan_iter(match="analysis:*", count=500)]
    for key in sorted(keys):
        m = SLATE_KEY_RE.match(key)
        if not m or m.group("date") < since:
            continue
        if skip_seen and not dry_run:
            try:
                if await redis.sismember(BACKFILL_SEEN, key):
                    stats["seen"] += 1
                    continue
            except Exception:
                pass                     # 표식 조회 실패는 백필을 막지 않는다
        raw = await redis.get(key)
        if not raw:
            stats["skipped"] += 1
            continue
        try:
            analysis = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[ledger] 백필 건너뜀 — JSON 파싱 실패: %s", key)
            stats["skipped"] += 1
            continue
        analysis.setdefault("sport", m.group("sport"))
        analysis.setdefault("date", m.group("date"))
        stats["slates"] += 1
        if dry_run:
            continue
        st = await record_analysis(pool, analysis)
        for k2 in ("inserted", "rejudged", "unchanged", "failed"):
            stats[k2] += st[k2]
        try:
            await redis.sadd(BACKFILL_SEEN, key)
        except Exception:
            pass
    return stats


# ── [CLV-1 2026-09-13] CLV 기록 — **저장 전용.** 판정은 이 값을 읽지 않는다.
#   사용자 지시(4단계): "판정의 값어치를 측정할 유일한 지표를 남긴다.
#   §4-1 '배당은 판정 입력 금지'는 그대로 — 여기서는 저장만 한다."

#: 🔴 [CLV-3] 우리가 **어느 쪽을 골랐는지**는 채점과 **같은 헬퍼**가 정한다
#   (`predicted_side`: 우세 → 저장값 → p_home 폴백). 컬럼만 읽으면 안 된다 —
#   실측 2026-09-13: `predicted_side` 컬럼이 오늘 9행 **전부 NULL** 인데
#   채점은 폴백으로 정상 동작하고 있었다. 여기서 컬럼만 보면 CLV 는 영원히 빈다.
_CLV_PICK = """
    SELECT l.favored, l.p_home, l.predicted_side, g.home, g.away
      FROM pick_ledger l JOIN games g ON g.id = l.game_id
     WHERE l.game_id = $1 AND l.is_final
     ORDER BY l.id DESC LIMIT 1
"""

#: 킥오프 **이전** 마지막 스냅샷. 경기가 시작된 뒤의 배당은 결과를 반영한다.
#  🔴 [CLV-3 2026-09-13] **우리가 고른 쪽만** 본다($3). 한 경기에 홈·원정
#     스냅샷이 각각 쌓인다(실측 game 1741: 두산 38행 · NC 38행). side 를 안
#     가리면 마지막에 들어온 아무 쪽을 집고, 판정 시각엔 홈·마감엔 원정을
#     집으면 그 차이는 **아무 의미가 없다.**
_CLV_SNAP = """
    SELECT o.odds
      FROM odds_snapshots o
      JOIN games g ON g.id = o.game_id
     WHERE o.game_id = $1 AND o.market = 'h2h' AND o.side = $3
       AND o.captured_at <= LEAST($2::timestamptz, g.starts_at)
     ORDER BY o.captured_at DESC
     LIMIT 1
"""

#: ⚠️ `$2` 에 **명시 캐스트가 필수**다. 한 문장에서 컬럼 대입(double precision)과
#   나눗셈(numeric)에 같이 쓰이면 PostgreSQL 이 타입을 못 정한다 —
#   `AmbiguousParameterError: inconsistent types deduced for parameter $2`
#   (실측 2026-09-13 운영). 계약은 SQL **문자열**만 보므로 이런 타입 오류는
#   못 잡는다. 실DB 실행이 유일한 검증이다.
#: 🔴 `UPDATE` 안의 `CASE` 는 **갱신 전 값**을 읽는다. 지금 쓰는 칸은 `$2` 로
#   참조해야 한다 — 종전에는 둘 다 컬럼명으로 읽어 두 칸이 다 찬 뒤에도
#   `clv` 가 NULL 로 남았다(실측 2026-09-13 MLB 8건 전부 NULL).
_CLV_SAVE = {
    # 🔴 [CLV-3] 부호는 **(마감 확률 − 판정시각 확률)** 이다. 양수면 우리가
    #    마감보다 좋은 값에 잡았다는 뜻이다(2.00 에 잡아 1.50 에 닫히면 +16.67).
    #    종전에는 뺄셈이 반대라 이긴 경우가 음수로 찍혔다.
    "verdict": """
    UPDATE pick_ledger SET odds_at_verdict = $2::double precision,
           clv = CASE WHEN odds_closing IS NOT NULL
                      THEN round(((1.0/odds_closing) - (1.0/$2::double precision))::numeric * 100, 2)
                      ELSE clv END
     WHERE game_id = $1 AND is_final
""",
    "closing": """
    UPDATE pick_ledger SET odds_closing = $2::double precision,
           clv = CASE WHEN odds_at_verdict IS NOT NULL
                      THEN round(((1.0/$2::double precision) - (1.0/odds_at_verdict))::numeric * 100, 2)
                      ELSE clv END
     WHERE game_id = $1 AND is_final
""",
}


def _implied_prob(odds) -> float | None:
    """소수 배당 → 내재 확률. 값이 없거나 1 이하면 **None**(지어내지 않는다)."""
    try:
        v = float(odds)
    except (TypeError, ValueError):
        return None
    return 1.0 / v if v > 1.0 else None


def clv_pp(at_verdict, closing) -> float | None:
    """판정 시각 대비 마감의 확률 차이(%p).

    부호: **(마감 확률 − 판정시각 확률) × 100**. 양수면 우리가 마감보다
    **좋은 값에 잡았다** — 2.00 에 잡아 1.50 에 닫히면 `+16.67`.

    🔴 [CLV-3 2026-09-13] 종전에는 뺄셈이 반대라 **이긴 경우가 음수**로
       찍혔고, 머리말은 "양수면 좋은 값"이라고 적혀 있었다. 식과 말이
       반대였다 — 수익을 재는 유일한 지표라 부호가 뒤집히면 결론이 통째로
       뒤집힌다. `_CLV_SAVE` 의 SQL 도 같은 방향으로 맞춰 두었다.
    """
    a, b = _implied_prob(at_verdict), _implied_prob(closing)
    if a is None or b is None:
        return None
    return round((b - a) * 100, 2)


# ── [GATE-2 2026-09-14] 사전값·괴리·게이트 배선 — **저장 전용.**
#   `PRI-1`(prior)·`GATE-1`(gate)이 순수 함수를 만들었지만 부르는 곳이 없었다.
#   티어 표가 채워졌으므로(192/193) 이제 계산할 값이 있다.

#: 🔴 게이트 판정은 **말로 적는다**(`gate_reason`). 라벨을 따로 저장하지 않는
#   이유: 같은 사실을 두 칸에 적으면 한쪽만 고쳐진다(사본 금지). 라벨은 이
#   문자열의 **첫 토큰**이고, 구분자는 " · " 다.
_PRIOR_SAVE = """
    UPDATE pick_ledger
       SET p_prior = $2::double precision,
           prior_src = $3,
           p_market = COALESCE(p_market, $4::double precision),
           gate_reason = $5,
           gate_label = $6,
           gate_gap_pp = $7::double precision,
           p_base = $8::jsonb
     WHERE game_id = $1 AND is_final
"""


#: [PRI-4] 올해 **리그** 성적. 🔴 컵·대항전은 애초에 이 표에 없다 —
#  `games` 는 football-data 의 **리그 일정만** 적재한다(`upsert_games_from_
#  football_data` 가 league_key 로 부른다). 그래서 리그 라벨로 거르는 것이
#  곧 컵 제외다. 종목·리그·시즌 시작일로 좁힌다.
_FORM_SQL = """
    SELECT
      count(*) FILTER (WHERE (home = $4 AND home_score > away_score)
                          OR (away = $4 AND away_score > home_score)) AS w,
      count(*) FILTER (WHERE home_score = away_score)                 AS d,
      count(*) FILTER (WHERE (home = $4 AND home_score < away_score)
                          OR (away = $4 AND away_score < home_score)) AS l
      FROM games
     WHERE sport = $1 AND league = $2 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
       AND starts_at >= $3
       AND $4 IN (home, away)
"""


async def _season_form(conn, *, sport: str, league: str, team: str,
                       start) -> tuple[int, int, int]:
    """올해 (승, 무, 패). 시즌 시작일을 모르면 **전부 0** — 지어내지 않는다."""
    if start is None or not team:
        return 0, 0, 0
    from datetime import datetime, time, timezone

    since = datetime.combine(start, time.min, tzinfo=timezone.utc)
    r = await conn.fetchrow(_FORM_SQL, sport, league, since, team)
    if r is None:
        return 0, 0, 0
    return int(r["w"] or 0), int(r["d"] or 0), int(r["l"] or 0)


def _tier_key(sport: str, league: str) -> str | None:
    """티어 파일 키. 축구는 리그 라벨→키, 야구는 종목이 곧 키다."""
    from app.leagues import league_labels

    sp = (sport or "").lower()
    if sp in ("mlb", "kbo", "npb"):
        return sp
    return league_labels().get(league)


async def gate_of(conn_or_pool, *, game_id: int) -> dict | None:
    """[GAT-1 2026-09-18] 게이트·가설 **계산 전용.** 원장에 쓰지 않는다.

    🔴 **왜 떼어냈나.** 종전에는 `record_prior` 가 계산과 원장 쓰기를 한 몸으로
       하고 있었다. 원장 행은 판정이 끝나야 생기므로(`_row_from_game`:
       "판정이 없으면 None"), **판정 전에는 라벨을 계산조차 할 수 없었다.**
       그런데 위성은 그 라벨을 보고 추출 대상을 고른다(`_DUE_SQL` 이
       `pick_ledger` 를 LEFT JOIN 한다) — 그래서 첫 판정 때는 언제나 추출이
       없고, 가설을 세워 놓고도 아무것도 확인하지 못했다.
       실측 2026-09-17 운영 로그: `§3 대상 선별 — 슬레이트 19 · 게이트 대상 0`.
       원장 실측: need 133칸 중 확인 6칸(4.5%) · 미상 55칸(41.4%).

    🔴 **라벨의 재료는 판정과 무관하다** — 티어 표(정적) · 올해 성적(`games`) ·
       배당 스냅샷(`odds_snapshots`). 판정을 기다릴 이유가 없었다.

    🔴 **계산은 여기 한 곳이다(사본 금지).** `record_prior` 도 이 함수를 부른다.
       위성이 미리 본 라벨과 원장에 적히는 라벨은 **같은 코드·같은 입력**에서
       나온다. 입력이 그 사이 변하면(배당 이동) 그건 사본이 아니라 시점 차이고,
       원장에 남는 것은 종전대로 판정 시점 값이다.

    반환 (못 재면 `None` — 티어 표가 없는 리그):
        label · gap_pp · side · p_prior · prior_src · p_base
        p_market · reason · hypothesis(JSON|None) · placeholder(bool)
        board_only(bool) · home · away · sport
    """
    from contextlib import asynccontextmanager

    from app.engine import gate as G
    from app.engine import odds_move as M
    from app.engine import prior as P

    @asynccontextmanager
    async def _conn():
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as c:
                yield c
        else:
            yield conn_or_pool

    async with _conn() as conn:
        g = await conn.fetchrow(
            "SELECT sport, league, home, away FROM games WHERE id = $1", game_id)
        if g is None:
            return None
        sport = (g["sport"] or "").lower()
        key = _tier_key(sport, g["league"])
        tiers = P.load_tiers(key) if key else {}
        if not tiers:
            logger.info("[gate] game=%s — 티어 표가 없다(%s). 기록하지 않는다",
                        game_id, key or "리그 미상")
            return None
        # 🔴 [PRI-4 2026-09-14 사용자 지시] **올해 성적을 넣는다.** gp=0 으로
        #    넣으면 team_elo 가 티어 elo 를 그대로 돌려주고, 한 단계 차이가
        #    홈 이점과 상쇄돼 사전값이 평평해진다(실측: 로마 3전 전승인데
        #    Roma@Torino 36.5/27.0/36.5).
        start = P.season_start(key)
        hw, hd, hl = await _season_form(conn, sport=sport, league=g["league"],
                                        team=g["home"], start=start)
        aw, ad, al = await _season_form(conn, sport=sport, league=g["league"],
                                        team=g["away"], start=start)
        th, sh = P.team_elo(tiers.get(g["home"]), w=hw, d=hd, lose=hl)
        ta, sa = P.team_elo(tiers.get(g["away"]), w=aw, d=ad, lose=al)
        gp_h, gp_a = hw + hd + hl, aw + ad + al

        # 빅매치는 이미 로드한 티어로 판정한다 — 새로 부르지 않는다.
        #    ⚠️ 순위를 모르면 `is_big_match` 가 0 으로 읽지 않는다(BIG-1).
        from app.engine.bigmatch import is_big_match

        tag = is_big_match(league=key or "", home=g["home"], away=g["away"],
                           rank_home=tiers.get(g["home"]),
                           rank_away=tiers.get(g["away"]))

        def _hyp(label, side, gap_pp):
            """[U5] **게이트 직후 가설을 세운다.** 검색 전에 무엇을 찾을지
            정하는 자리다 — 실패해도 판정은 그대로 간다."""
            from app.engine import hypothesis as HY

            try:
                h = HY.build(label, sport=sport, side=side,
                             bigmatch=bool(getattr(tag, "big", False)),
                             gap_pp=gap_pp)
                logger.info("[hypothesis] game=%s %s → 방향 %s · need %d · 문턱 %d",
                            game_id, label, h.direction, len(h.need),
                            h.sufficient_count)
                return json.dumps(h.as_dict(), ensure_ascii=False)
            except Exception as exc:
                logger.warning("[hypothesis] game=%s 실패 — 판정은 그대로 간다: %s",
                               game_id, exc)
                return None

        base_out = {"home": g["home"], "away": g["away"], "sport": sport}
        # 🔴 [U3 2026-09-15 사용자 지시] **티어가 비면 사전값을 만들지 않는다.**
        #    종전에는 리그 중앙(3 → 1560)으로 메워 채운 팀과 안 채운 팀이
        #    같은 근거를 가진 것처럼 보였다(리즈 사례).
        #    ⚠️ 조용히 빠지지 않는다. p_prior=NULL · prior_src='none' 으로
        #       **기록하고** 그 사실이 게이트까지 간다(U4 가 보드고정으로 읽는다).
        if th is None or ta is None:
            miss = [n for n, v in ((g["home"], th), (g["away"], ta)) if v is None]
            logger.info("[gate] game=%s 티어 미기입 %s — 사전값 없음(none)",
                        game_id, miss)
            # 🔴 [PA-6 2026-09-16] **여기서 끝내지 않는다.** 종전 `return None`
            #    은 사전값만 적고 돌아갔고, 그러면 가설 생성(U5)도, 확인 판정
            #    (U7)·분석(U12)도 통째로 건너뛰어졌다.
            # 🔴 [PA-13] 라벨을 **칸으로도** 남긴다. 텍스트는 사람이 읽고,
            #    칸은 코드가 읽는다. 여기 "보드고정"은 띄어쓰기가 없어
            #    `G.BOARD` 와 글자가 다르다 — 그래서 파싱을 못 쓴다.
            return {**base_out, "board_only": True, "label": G.BOARD,
                    "gap_pp": None, "side": None, "p_prior": None,
                    "prior_src": "none", "p_base": None, "p_market": None,
                    "placeholder": False,
                    "reason": f"보드고정 · 티어 미기입({' · '.join(miss)})",
                    "hypothesis": _hyp(G.BOARD, None, None)}
        src = "tier"
        if gp_h or gp_a:
            # ⚠️ 티어만 쓴 것과 성적이 섞인 것을 구분한다 — 나중에 "왜 이
            #    값이 나왔나"를 원장만 보고 답할 수 있어야 한다.
            src = f"{src}+form({gp_h}/{gp_a})"
        if sport == "soccer":
            pri = P.soccer_prior(th, ta)
            p_home = pri[0]
            # 🔴 [PA-24 · 지시문 8단계] **3-way 를 통째로 남긴다.** 종전에는
            #    `pri[0]` 에서 무·원정이 사라져, 조정이 얼마나 움직였는지를
            #    원장만 보고 답할 수 없었다(10단계 채점의 전제).
            p_base = {"h": pri[0], "d": pri[1], "a": pri[2]}
        else:
            p_home = P.baseball_prior(th, ta)
            pri = p_home
            # 야구는 2-way 라 홈만이다. 없는 칸을 만들지 않는다.
            p_base = {"h": p_home}

        rows = await conn.fetch(_MOVE_SNAP_SQL, game_id)
        snaps = _snap_probs(rows)
        prov = _best_provider(snaps)
        base = M.baseline([v for k, v in snaps.items() if k[0] == prov]) if prov else None
        from app.engine.market_edge import implied_probs

        # 🔴 [PA-22-b 2026-09-17 · 지시문 2단계] **위생 검사를 여기서 건다.**
        #    종전에는 마진이 이상한 배당도 그대로 게이트까지 갔다 — 실측
        #    재현: 마진 0(합 100.0%)짜리가 `시장 과대 · gap -22.46` 을 만들었다.
        #    만들어진 값으로 괴리를 재면 그 게이트는 거짓이다.
        #    ⚠️ 통과 못 하면 **시장 없음**으로 둔다(`gate.classify` 가 None 을
        #       받으면 보드 고정을 돌려준다) — 확률을 지어내지 않는다.
        from app.engine.market_edge import devig_ok, margin_ok

        mp = None
        if base:
            if not margin_ok(base["odds"]):
                logger.info("[gate] game=%s 배당 마진이 범위 밖 — 시장 없음으로 "
                            "둔다 (odds=%s)", game_id, base["odds"])
            else:
                cand = implied_probs(base["odds"])
                if devig_ok(cand):
                    mp = cand
                else:
                    logger.warning("[gate] game=%s 디빅 결과 합이 1이 아니다 — "
                                   "시장 없음으로 둔다 (%s)", game_id, cand)
        if mp:
            mkt = ((mp.get("home"), mp.get("draw"), mp.get("away"))
                   if sport == "soccer" else mp.get("home"))
        else:
            mkt = None
        # 🔴 [PA-22-b] 같은 슬레이트의 다른 경기와 **소수점까지 같은** 시장
        #    확률이면 자리표를 의심한다(실사고 SEA@ATH 40.9/59.1 두 번).
        #    ⚠️ 폐기하지 않는다 — 표시만 하고 판단은 사람이 한다.
        #    ⚠️ [GAT-1] 여기서 **쓰지 않는다.** 쓰기는 `record_prior` 몫이다.
        placeholder = False
        if mp:
            try:
                from app.engine.market_edge import placeholder_suspect

                peers = await conn.fetch(
                    """SELECT l.p_market FROM pick_ledger l
                         JOIN games g2 ON g2.id = l.game_id
                        WHERE l.is_final AND l.game_id <> $1
                          AND g2.sport = $2 AND l.p_market IS NOT NULL
                          AND l.judged_at > now() - interval '24 hours'""",
                    game_id, sport)
                others = [{"home": float(r["p_market"])} for r in peers]
                if placeholder_suspect({"home": mp.get("home")}, others):
                    logger.warning("[gate] game=%s 시장 확률이 다른 경기와 "
                                   "소수점까지 같다 — 자리표 의심 (%.4f)",
                                   game_id, mp.get("home"))
                    placeholder = True
            except Exception as exc:
                logger.info("[gate] game=%s 자리표 검사 실패: %s", game_id, exc)

        v = G.classify(pri, mkt, sport)
        # 🔴 [GATE-3 2026-09-14 사용자 지시] 기준선이 없어도 **사유를 남긴다.**
        #    종전에는 조용히 빠져나가 원장이 비었고, 그러면 "게이트를 안 돌린
        #    경기"와 "배당이 없어 못 돌린 경기"를 나중에 구분할 수 없다.
        why = v.reason if mp else (
            f"{v.reason} (이름표 붙은 기준선 스냅샷 없음"
            + (f" · 소스 {prov}" if prov else " · 배당 0건") + ")")
        mp = mp or {}
        logger.info("[gate] game=%s %s vs %s — 사전값 %.3f(%s) · 시장 %.3f · "
                    "%s gap=%s side=%s", game_id, g["home"], g["away"],
                    float(p_home), src, float(mp.get("home") or 0), v.label,
                    v.gap_pp, v.side)
        return {**base_out, "board_only": False, "label": v.label,
                "gap_pp": v.gap_pp, "side": v.side,
                "p_prior": float(p_home), "prior_src": src, "p_base": p_base,
                "p_market": mp.get("home"), "placeholder": placeholder,
                "reason": f"{v.label} · {why}",
                "hypothesis": _hyp(v.label, v.side, v.gap_pp)}


async def record_prior(conn_or_pool, *, game_id: int) -> dict | None:
    """[GATE-2] 티어 사전값과 `open` 시장을 대조해 게이트를 **원장에 남긴다.**

    반환 `{"label", "gap_pp", "side", "p_prior", "prior_src", "p_base"}` ·
    못 재면 None.

    🔴 **판정은 이 값을 읽지 않는다.** 측정 전용이다(pick_ledger 머리말 규약).
    🔴 기준선은 `open` 이다 — `odds_move.baseline` 이 그 규칙의 원본이다.
    🔴 [GAT-1 2026-09-18] 계산은 `gate_of` 가 한다 — 여기는 **쓰기만** 한다.
       계산을 두 곳에 두면 위성이 본 라벨과 원장 라벨이 갈린다(사본 금지).
    """
    from contextlib import asynccontextmanager

    from app.engine import gate as G

    @asynccontextmanager
    async def _conn():
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as c:
                yield c
        else:
            yield conn_or_pool

    async with _conn() as conn:
        res = await gate_of(conn, game_id=game_id)
        if res is None:
            return None

        async def _save_hyp():
            if res["hypothesis"] is not None:
                await conn.execute(
                    "UPDATE pick_ledger SET hypothesis = $2::jsonb "
                    "WHERE game_id = $1 AND is_final", game_id, res["hypothesis"])

        if res["board_only"]:
            await conn.execute(_PRIOR_SAVE, game_id, None, "none", None,
                               res["reason"], G.BOARD, None, None)
            await _save_hyp()
            return {"label": G.BOARD, "gap_pp": None, "side": None,
                    "p_prior": None, "prior_src": "none"}
        if res["placeholder"]:
            await conn.execute(
                "UPDATE pick_ledger SET placeholder_suspect = TRUE "
                "WHERE game_id = $1 AND is_final", game_id)
        await conn.execute(
            _PRIOR_SAVE, game_id, float(res["p_prior"]), res["prior_src"],
            res["p_market"], res["reason"], res["label"],
            None if res["gap_pp"] is None else float(res["gap_pp"]),
            json.dumps(res["p_base"], ensure_ascii=False))
        await _save_hyp()
    return {"label": res["label"], "gap_pp": res["gap_pp"], "side": res["side"],
            "p_prior": float(res["p_prior"]), "prior_src": res["prior_src"],
            "p_base": res["p_base"]}


# ── [MOV-2 2026-09-14] 배당 이동 분류 배선 — **저장 전용.** 판정은 읽지 않는다.
#   `MOV-1`(odds_move)이 규칙을 만들었지만 부르는 곳이 없었다. 이름표를 붙이는
#   쪽(TRG-2)이 생겼으니 여기서 읽어 원장에 남긴다.

#: 이름표가 붙은 승부 배당만 본다. 태그가 없는 행은 시점을 모르는 행이다.
_MOVE_SNAP_SQL = """
    SELECT o.provider, o.snap_tag, o.side, o.odds, g.home, g.away
      FROM odds_snapshots o JOIN games g ON g.id = o.game_id
     WHERE o.game_id = $1 AND o.market = 'h2h' AND o.snap_tag IS NOT NULL
"""

#: 🔴 `odds_open` 은 **고른 쪽**의 기준선 배당이다 — `odds_at_verdict`·
#   `odds_closing` 과 같은 쪽이어야 세 값이 한 줄로 읽힌다.
_MOVE_SAVE = """
    UPDATE pick_ledger
       SET odds_open = COALESCE($2::double precision, odds_open),
           move_class = $3, move_reason = $4,
           market_flow = $5::jsonb, flow_class = $3
     WHERE game_id = $1 AND is_final
"""


def _snap_probs(rows: list) -> dict[tuple[str, str], dict]:
    """(소스, 시점) → {p_home, odds{side→배당}}. 마진 제거는 원본을 쓴다."""
    from app.engine.market_edge import implied_probs

    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["provider"], r["snap_tag"])
        side = str(r["side"] or "")
        if side == r["home"]:
            slot = "home"
        elif side == r["away"]:
            slot = "away"
        elif side.lower() in ("draw", "무승부", "x"):
            slot = "draw"
        else:
            continue
        grouped.setdefault(key, {})[slot] = float(r["odds"])
    out: dict[tuple[str, str], dict] = {}
    for key, odds in grouped.items():
        probs = implied_probs(odds)
        if not probs:
            continue
        out[key] = {"provider": key[0], "snap_tag": key[1],
                    "p_home": probs.get("home"), "odds": odds}
    return out


def _best_provider(snaps: dict) -> str | None:
    """시점을 가장 많이 가진 소스. 🔴 소스를 섞으면 마진 차를 이동으로 읽는다."""
    count: dict[str, int] = {}
    for (prov, _tag) in snaps:
        count[prov] = count.get(prov, 0) + 1
    if not count:
        return None
    return sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


async def record_move(conn_or_pool, *, game_id: int,
                      news: dict | None = None) -> dict | None:
    """[MOV-2] 이름표 붙은 스냅샷으로 이동을 분류해 원장에 남긴다.

    반환 `{"move_class", "move_pp", "reason", "from", "to"}` · 못 재면 None.

    🔴 **새 소스를 부르지 않는다** — `odds_snapshots` 에 이미 있는 값만 읽는다.
    🔴 값이 없으면 **아무것도 쓰지 않는다.** "안 움직였다"(none)와 "모른다"는
       다른 말이라, 잴 수 없으면 `move_class` 를 비워 둔다(0 으로 채우지 않는다).
    ⚠️ `news` 가 없으면 `odds_move.classify` 는 `money`/`none` 만 낸다 — 근거
       없이 `news` 를 붙이면 확증이 거짓으로 선다. 딥서치 배선 전에는 정상이다.
    ⚠️ `record_clv` 와 같은 커넥션 규약을 쓴다(풀을 받으면 잠깐 빌린다).
    """
    from contextlib import asynccontextmanager

    from app.engine import odds_move as M

    @asynccontextmanager
    async def _conn():
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as c:
                yield c
        else:
            yield conn_or_pool

    async with _conn() as conn:
        rows = await conn.fetch(_MOVE_SNAP_SQL, game_id)
        snaps = _snap_probs(rows)
        prov = _best_provider(snaps)
        if not prov:
            logger.info("[move] game=%s — 이름표 붙은 배당이 없다. 기록하지 않는다",
                        game_id)
            return None
        mine = [v for k, v in snaps.items() if k[0] == prov]
        base = M.baseline(mine)
        # 기준선보다 **나중** 시점 중 가장 늦은 것과 비교한다.
        order = list(M.BASELINE_ORDER)
        later = [s for s in mine
                 if order.index(s["snap_tag"]) > order.index(base["snap_tag"])]
        if not later:
            logger.info("[move] game=%s %s — 기준선(%s) 뒤 시점이 아직 없다",
                        game_id, prov, base["snap_tag"])
            return None
        now = max(later, key=lambda s: order.index(s["snap_tag"]))
        pp = M.move_pp(now.get("p_home"), base.get("p_home"))
        # 🔴 [PA-16 · U9] **북 수를 넘긴다.** 종전에는 안 넘겨서 `steam`
        #    (3북 이상 같은 방향 3%p)이 영원히 안 떴다 — 5분류가 4분류로
        #    남아 있었다. 한 북이 흔들린 것과 시장 전체가 밀린 것은 다르다.
        #    ⚠️ 같은 시점(snap_tag)에 값을 낸 **북 수**다. 모르면 None 이고,
        #       그때는 종전대로 4분류다(없는 정보로 센 라벨을 붙이지 않는다).
        same_tag = [s for s in snaps.values()
                    if s.get("snap_tag") == now.get("snap_tag")
                    and s.get("p_home") is not None]
        n_books = len({s.get("provider") for s in same_tag}) or None
        mv = M.classify(move_pp=pp, news=news, n_books=n_books)
        # 🔴 [PA-16 · U9] 북 불일치. **표시만** 한다 — 확률을 안 건드린다.
        disagree = M.book_disagree([s["p_home"] for s in same_tag])

        pick = await conn.fetchrow(_CLV_PICK, game_id)
        side = predicted_side(pick["favored"], pick["p_home"],
                              pick["predicted_side"]) if pick else None
        o_open = base["odds"].get(side) if side in ("home", "away") else None
        # 🔴 [PA-16 · U9] 흐름을 **원장 칸으로** 남긴다. 종전에는 라벨과 사유만
        #    남고 북 수·불일치·기준선이 사라져서, 나중에 "왜 이 분류였나"를
        #    원장만 보고 답할 수 없었다.
        # 🔴 [PA-16 · U9] **흐름이 판정에 무엇을 하는가**를 함께 남긴다.
        #    news=확증 · money/steam=판돈 절반 · contra=취소.
        #    ⚠️ **저장 전용이다.** 여기서 판돈을 실제로 줄이거나 픽을 취소하지
        #       않는다 — 그건 발송 규칙(조건 B)의 몫이고 별도 단위다.
        adj_row = await conn.fetchrow(
            "SELECT adj_pp FROM pick_ledger WHERE game_id = $1 AND is_final",
            game_id)
        # ⚠️ `.get` 으로 읽는다 — 가짜 행·옛 스키마에서 KeyError 로 이동 분류가
        #    통째로 죽지 않게(PA-13 과 같은 규약).
        adj_raw = (adj_row.get("adj_pp")
                   if adj_row is not None and hasattr(adj_row, "get") else None)
        adj_map = (json.loads(adj_raw) if isinstance(adj_raw, str)
                   else (adj_raw or {}))
        adj_total = sum(float(v) for v in (adj_map or {}).values()
                        if isinstance(v, (int, float)))
        act = M.adj_confirm(mv.label, adj_pp=adj_total or None, move_pp=pp)
        flow = {"class": mv.label, "reason": mv.reason, "pp": pp,
                "from": base["snap_tag"], "to": now["snap_tag"],
                "provider": prov, "n_books": n_books,
                "book_disagree": disagree, "action": act}
        await conn.execute(_MOVE_SAVE, game_id, o_open, mv.label, mv.reason,
                           json.dumps(flow, ensure_ascii=False))
    logger.info("[move] game=%s %s %s→%s %s (%s)", game_id, prov,
                base["snap_tag"], now["snap_tag"], mv.label, mv.reason)
    return {"move_class": mv.label, "move_pp": mv.move_pp, "reason": mv.reason,
            "from": base["snap_tag"], "to": now["snap_tag"], "provider": prov,
            # [PA-16 · U9] 흐름 판단까지 돌려준다. 발송 규칙이 이것을 읽는다.
            "n_books": n_books, "book_disagree": disagree, "action": act}


async def record_clv(conn_or_pool, *, game_id: int, at: str,
                     now=None) -> float | None:
    """판정 시각(`at="verdict"`) 또는 마감(`at="closing"`) 배당을 남긴다.

    반환: 저장한 배당값(없으면 None).
    🔴 [CLV-2] **커넥션을 받으면 새로 얻지 않는다.** 실측 2026-09-13:
       `record_analysis` 가 `conn.transaction()` 안에서 풀을 넘겨 호출해
       **교착**했다(400초 타임아웃). 바깥 트랜잭션이 잠근 같은 행을 새
       커넥션이 UPDATE 하려 했기 때문이다.
       ⚠️ 호출부마다 다른 함수를 만들지 않는다 — 한 함수가 둘 다 받는다.
    ⚠️ **새 소스를 부르지 않는다** — `odds_snapshots` 에 이미 있는 값만 읽는다.
    ⚠️ 값이 없으면 **아무것도 쓰지 않는다.** 0 으로 채우지 않는다.
    """
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone

    sql = _CLV_SAVE["verdict" if at == "verdict" else "closing"]
    when = now or datetime.now(timezone.utc)

    @asynccontextmanager
    async def _conn():
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as c:
                yield c
        else:
            yield conn_or_pool

    async with _conn() as conn:
        # 🔴 [CLV-3] 고른 쪽을 먼저 정한다. 모르면 **아무것도 쓰지 않는다** —
        #    반대쪽 배당으로 채우면 CLV 가 통째로 무의미해진다.
        pick = await conn.fetchrow(_CLV_PICK, game_id)
        side = predicted_side(pick["favored"], pick["p_home"],
                              pick["predicted_side"]) if pick else None
        if side is None:
            logger.info("[clv] game=%s %s — 고른 쪽 미상, 기록하지 않는다",
                        game_id, at)
            return None
        team = pick["away"] if side == "away" else pick["home"]
        odds = await conn.fetchval(_CLV_SNAP, game_id, when, team)
        if odds is None:
            logger.info("[clv] game=%s %s — 배당 스냅샷 없음, NULL 로 남긴다",
                        game_id, at)
            return None
        await conn.execute(sql, game_id, float(odds))
    return float(odds)


# ═══════════════ [U12 2026-09-15] 확인 판정 + 분석 배선
#
# 🔴 U7 의 `confirm` 과 `analyze` 가 둘 다 **부르는 곳이 0건**이었다.
#    여기가 그 자리다 — `record_prior` 가 게이트 라벨을 돌려주는 바로 뒤.
# 🔴 **발송을 켜지 않는다.** 원장에만 남긴다(경로 전환은 U14).
# 🔴 **게이트 대상에만** 돌린다 — 전 경기에 돌리면 무료 한도가 즉시 터진다.

_CONFIRM_SAVE = """
    UPDATE pick_ledger
       SET confirmed = $2::jsonb, refuted = $3::jsonb, unknown_axes = $4::jsonb
     WHERE game_id = $1 AND is_final
"""

# 🔴 [ANL-4 2026-09-17] `analyze_check` 를 함께 적는다 — L1·L2·금지어를 재고
#    안 남기면 "이 결정축이 반려당한 값인가"를 원장만 보고 못 답한다.
#    ⚠️ 칸을 늘렸으면 **자리표도 늘린다.** PA-23 에서 칸만 늘리고 $N 을 안
#       늘려 원장 저장이 통째로 터질 뻔했다. 계약이 자리표 수를 잰다.
_ANALYZE_SAVE = """
    UPDATE pick_ledger
       SET main_axis = $2, counter_axis = $3, market_view = $4,
           swap_agree = $5, structure_candidates = $6::jsonb,
           analyze_model = $7, gate_vs_llm = COALESCE($8, gate_vs_llm),
           analyze_failed = $9, analyze_check = $10::jsonb
     WHERE game_id = $1 AND is_final
"""

# ═══════════════ [PA-27 2026-09-17 · 지시문 7단계] 딥서치 → 판정 되먹임
#
# 🔴 지시문 7단계: "추출된 결장 명단을 5단계 원장의 **결장 변수로 재계산**
#    (LLM 이 문장으로 반영하는 게 아니라 **코드가 delta 를 다시 매김**).
#    재계산 후 gap 재판정. 등급이 바뀌면 원장에 `regraded_by=deepsearch`."
# 🔴 종전: `rejudge.reweigh` 를 **부르는 코드가 app/ 전체에 0건**이었다.
#    U11 을 만들어 놓고 안 이었다 — analyze·gate.select·U9·U10·book_gap·예산·
#    adj_confirm·velo_drop 에 이어 **아홉 번째 "만들고 안 이었다"** 다.
#    딥서치가 결장자를 찾아내도 확률이 1%p 도 안 움직였다.
# 🔴 **저장 전용이다. 원래 값을 덮지 않는다.** `p_code`·`confidence`·`adj_pp`
#    는 그대로 두고 `*_after` 에만 남긴다. 카드도 발송도 이 칸을 아직 안 읽는다
#    — PA-14 와 같은 순서다(먼저 값을 쌓고 표를 봐야 교체가 옳은지 안다).
_REJUDGE_SAVE = """
    UPDATE pick_ledger
       SET adj_after = $2::jsonb, p_code_after = $3::double precision,
           grade_after = $4, regraded_by = $5
     WHERE game_id = $1 AND is_final
"""

# 🔴 [PA-27-d] 출처 상수는 **`rejudge` 가 원본**이다 — 여기 다시 적지 않는다.
#    거기서는 "대체 권한"까지 함께 정한다(docs/FORKS.md F-2). 이름만 베끼면
#    권한 없이 이름만 같은 사본이 된다.


async def record_rejudge(conn_or_pool, *, game_id: int, rj: dict,
                         by: str) -> bool:
    """[FOT-3] 재판정 결과를 원장에 남긴다. **저장 전용 · 유일한 쓰기 통로.**

    🔴 `_REJUDGE_SAVE` 를 쓰는 곳은 여기 **하나뿐**이다. 경로가 둘(딥서치 ·
       T-60 공식 XI)이라 SQL 을 각자 들고 있으면 곧 사본이 된다.
    🔴 `rj["changed"]` 가 거짓이면 **아무것도 안 쓴다** — 안 바뀐 것을 쓰면
       "재판정했는데 그대로"와 "재판정 안 함"이 같아진다.
    🔴 `by` 는 `rejudge.SRC_*` 다. 출처마다 대체 권한이 다르므로(FORKS F-2)
       원장에서도 갈라 둬야 나중에 어느 쪽이 맞았는지 잴 수 있다.
    ⚠️ 커넥션을 받으면 새로 얻지 않는다(`record_clv` 와 같은 규약 — 바깥
       트랜잭션 안에서 풀을 넘기면 교착한다).
    """
    from contextlib import asynccontextmanager

    if not (rj or {}).get("changed"):
        return False

    @asynccontextmanager
    async def _conn():
        if hasattr(conn_or_pool, "acquire"):
            async with conn_or_pool.acquire() as c:
                yield c
        else:
            yield conn_or_pool

    async with _conn() as conn:
        await conn.execute(
            _REJUDGE_SAVE, game_id,
            json.dumps(rj.get("adj_after") or {}, ensure_ascii=False),
            rj.get("p_code_after"), rj.get("grade_after"), by)
    return True


#: [WIR-1 2026-09-18] 그 팀의 **직전 3경기 결과.** 채점의 `last3` 재료다.
#  🔴 기사에서 뽑을 값이 아니다 — 우리 DB 에 있다. 실측: 기사 추출 확인률 0/15.
#  ⚠️ 딥서치 근거(FORKS F-11): 최근 3~5경기는 **승패 예측력이 0 에 가깝다**
#     (Razzball: "zero to negligible" · FanGraphs: 모멘텀 효과 최소).
#     그래서 이 값은 `동의` 라벨의 **파생(U/O) 득점 환경 재료로만** 쓴다 —
#     `hypothesis.build` 가 `동의` 에서만 `last3` need 를 세우는 것이 그 구현이다.
#     확률을 여기서 움직이지 않는다.
_LAST3_SQL = """
    SELECT home, away, home_score, away_score, starts_at
      FROM games
     WHERE sport = $1 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
       AND $2 IN (home, away)
       AND ($3::timestamptz IS NULL OR starts_at < $3::timestamptz)
     ORDER BY starts_at DESC
     LIMIT 3
"""


def _last3_line(r, team: str) -> str:
    """`"09-16 승 5-3"`. 🔴 점수 비교 한 줄이다 — 새 규칙을 만들지 않는다."""
    hs, as_ = int(r["home_score"]), int(r["away_score"])
    ours, theirs = (hs, as_) if r["home"] == team else (as_, hs)
    mark = "승" if ours > theirs else ("패" if ours < theirs else "무")
    when = r["starts_at"]
    return f"{when:%m-%d} {mark} {ours}-{theirs}" if when else f"{mark} {ours}-{theirs}"


async def record_confirm_and_analysis(conn, *, game_id: int,
                                      gate: dict | None,
                                      redis=None,
                                      absences: list | None = None) -> dict | None:
    """[U12] S6 확인 판정 + S11 분석을 원장에 남긴다. **저장 전용.**

    ⚠️ 이름이 `record_analysis` 가 아니다 — 그건 이 파일 257행의 **원장 저장
       본체**다. 같은 이름을 쓰면 뒤 정의가 앞을 덮어 원장이 통째로 멈춘다
       (실제로 한 번 그렇게 썼다가 즉시 고쳤다).

    ⚠️ 실패해도 판정을 막지 않는다(CLV·이동과 같은 규약).
    """
    from app.engine import gate as G

    # 🔴 [CNF-1 2026-09-18] **문을 함수 맨 위에 두지 않는다.** 이 함수는 둘을
    #    한다 — S6 확인 판정은 **순수 함수·0원**이고, S11 분석만 LLM 을 쓴다.
    #    문이 위에 있어서 공짜인 채점까지 같이 막혔다.
    #    실측 2026-09-18 운영 원장(최근 5일): `동의` 가설 18건 중 **채점 0건**
    #    (가치 의심 10/10 · 시장 과대 10/10 은 정상). `동의` 가설은 `last3` 두
    #    칸을 세우는데(파생 U/O 재료), 찾으라 해놓고 찾았는지 세지 않았다 —
    #    `hypothesis.py` 머리말이 경고한 "S9 가 무엇이 충족됐나로 고를 수 없다".
    #    ⚠️ 비용 문은 **S11 앞으로 내렸다**(아래). LLM 호출은 한 건도 안 는다.
    label = (gate or {}).get("label")

    g = await conn.fetchrow(
        # 🔴 [ANL-9] 예고 선발을 함께 읽는다 — 목표 분석이 "선발 축이 전부"라고
        #    한 축인데 분석 입력에 없었다.
        "SELECT id, sport, league, home, away, starts_at, "
        "home_pitcher, away_pitcher FROM games WHERE id = $1",
        game_id)
    if g is None:
        return None

    row = await conn.fetchrow(
        # 🔴 [ANL-5] `p_prior` 를 함께 읽는다 — 아래 blk 에 하드코딩 None 을
        #    넣고 있었다. 원장에는 값이 있는데(실측 0.5487 / 0.68 / 0.574)
        #    분석은 "p_prior None" 을 보고 있었다.
        # 🔴 [MKT-4] `odds` 를 함께 읽는다 — 요구 확률(1/배당)의 재료다.
        "SELECT hypothesis, p_code, adj_pp, p_market, predicted_side, "
        "confidence, p_prior, odds, model_probs FROM pick_ledger "
        "WHERE game_id = $1 AND is_final", game_id)
    if row is None:
        return None

    # ── S6 확인 판정 (U7)
    out: dict = {}
    collected = {}
    own_redis = None
    if redis is None:
        # 호출자(`record_analysis`)는 redis 를 들고 있지 않다. 게이트 대상은
        # 슬레이트당 한 자릿수라 여기서 열고 닫는다.
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings

            redis = own_redis = aioredis.from_url(
                get_settings().redis_url, decode_responses=True)
        except Exception as exc:
            logger.info("[analysis] redis 연결 실패: %s", exc)
    try:
        if redis is not None:
            from app.collectors.satellite import read_extract

            # 🔴 `read_extract` 는 `{"gathered_at", "teams"}` 로 감싸 돌려준다.
            #    `confirm` 이 원하는 것은 **teams 안쪽**이다 — 통째로 넘기면
            #    home·away 칸이 없어 need 전건이 '미상'이 된다.
            collected = (await read_extract(redis, g["sport"], game_id)
                         or {}).get("teams") or {}
    except Exception as exc:
        logger.info("[analysis] game=%s 수집 캐시 없음: %s", game_id, exc)
    finally:
        if own_redis is not None:
            try:
                await own_redis.aclose()
            except Exception:
                pass

    # 🔴 [WIR-1 2026-09-18] **이미 가진 사실을 채점 입력에 합친다.**
    #    종전에는 위성 기사 추출만 봤다 — 실측 `out` 확인률 9.6% · `last3` 0%.
    #    그런데 둘 다 우리가 이미 갖고 있다:
    #      결장    `absences.py` 가 statsapi(IL 명단 + 확정 라인업)로 산출해
    #              `research["absences"]` 에 넣는다 (실측 2026-09-18 운영 캐시:
    #              "Cincinnati Reds의 Hunter Greene(선발) Injured 60-Day로 결장")
    #      최근3   `games` 표에 끝난 경기가 있다
    #    ⚠️ **덮지 않고 합친다.** 기사는 휴식·부진 같은 IL 밖 결장을 잡고
    #       (absences.py 머리말), 공식은 IL 을 잡는다. 충돌 우선순위는
    #       FORKS F-2(공식이 이긴다)가 이미 정했다 — 여기서 새 규칙을 만들지 않는다.
    #    ⚠️ **LLM 콜 0.** 새 수집도 외부 호출도 없다.
    merged_from = []
    if absences:
        try:
            from app.engine.performance import _split_absences

            h_out, a_out = _split_absences(list(absences),
                                           {"home": g["home"], "away": g["away"]})
            for side, got in (("home", h_out), ("away", a_out)):
                if not got:
                    continue
                box = dict(collected.get(side) or {})
                # 이름이 아니라 문장이다 — `confirm` 은 **비었나**만 본다.
                box["out"] = list(dict.fromkeys(list(box.get("out") or []) + got))
                collected[side] = box
            if h_out or a_out:
                merged_from.append(f"공식결장 {len(h_out)}/{len(a_out)}")
        except Exception as exc:
            logger.warning("[analysis] game=%s 공식 결장 합치기 실패: %s",
                           game_id, exc)
    try:
        for side in ("home", "away"):
            box = dict(collected.get(side) or {})
            if box.get("last3"):
                continue                      # 기사가 이미 채웠으면 그대로 둔다
            rows3 = await conn.fetch(_LAST3_SQL, g["sport"], g[side],
                                     g["starts_at"])
            if not rows3:
                continue
            box["last3"] = [_last3_line(r, g[side]) for r in rows3]
            collected[side] = box
        if any((collected.get(s) or {}).get("last3") for s in ("home", "away")):
            merged_from.append("DB최근3")
    except Exception as exc:
        logger.warning("[analysis] game=%s 최근 3경기 조회 실패: %s", game_id, exc)
    # 🔴 조용한 0 금지 — "기사에서 왔다"와 "우리 것이 붙었다"를 구분 못 하면
    #    다음 사람이 확인률을 잘못 읽는다.
    if merged_from:
        logger.info("[analysis] game=%s 채점 입력 보강 — %s",
                    game_id, " · ".join(merged_from))

    try:
        from app.engine import hypothesis as HY

        hyp_raw = row["hypothesis"]
        hyp = json.loads(hyp_raw) if isinstance(hyp_raw, str) else (hyp_raw or {})
        need = tuple(HY.Need(n["field"], n["side"], n.get("why", ""))
                     for n in (hyp.get("need") or []))
        h = HY.Hypothesis(hyp.get("direction"), need,
                          int(hyp.get("sufficient_count") or 2),
                          hyp.get("reason") or "")
        conf = HY.confirm(h, collected)
        await conn.execute(_CONFIRM_SAVE, game_id,
                           json.dumps(conf["confirmed"], ensure_ascii=False),
                           json.dumps(conf["refuted"], ensure_ascii=False),
                           json.dumps(conf["unknown"], ensure_ascii=False))
        out["confirm"] = conf
    except Exception as exc:
        logger.warning("[analysis] game=%s 확인 판정 실패: %s", game_id, exc)

    # 🔴 [CNF-1] **문은 채점 바로 뒤다.** 위(S6)만 공짜라서 풀었고, 아래는
    #    종전 그대로 `OVER|DOUBT` 만 지나간다.
    #    ⚠️ **일부러 여기까지만 연다.** 아래에는 구조 픽(`ST.candidates`)과
    #       S7 재판정이 있고 그것들도 순수 함수지만, 지시받은 것은 "채점이
    #       안 되는 것"이다. 범위를 넓히면 그건 고치는 것이 아니라 만드는 것이다.
    #       (`동의` 에서 구조 픽이 필요하다는 것은 별개 건으로 남긴다 —
    #        실측 2026-09-18: `structure_pick` 은 **모든 라벨에서 93건 전건
    #        NULL** 이라 여기를 열어도 오늘은 아무것도 안 나온다.)
    if label not in (G.OVER, G.DOUBT):
        return out

    # ── 파생 디빅 부착 (U10)
    adj_raw = row["adj_pp"]
    adj = json.loads(adj_raw) if isinstance(adj_raw, str) else (adj_raw or {})
    from zoneinfo import ZoneInfo

    ks = g["starts_at"]
    KST = ZoneInfo("Asia/Seoul")
    blk = {"home": g["home"], "away": g["away"], "league": g["league"],
           # 🔴 [ANL-5] 종전 `None` 하드코딩. 없으면 그때 None 이다 —
           #    0.5 로 채우지 않는다.
           "p_prior": row["p_prior"], "p_market": row["p_market"],
           "gap_pp": (gate or {}).get("gap_pp"), "gate": label,
           "adj_pp": adj, "p_code": row["p_code"],
           "kickoff_kst": (ks.astimezone(KST).strftime("%m-%d %H:%M")
                           if ks is not None else None),
           "home_facts": collected.get("home") or {},
           "away_facts": collected.get("away") or {}}
    # 🔴 [STD-1 2026-09-17] **팀 성적을 붙인다.** 목표 분석의 첫 축이고,
    #    새 소스 없이 `games(status='final')` 로 만든다.
    # ⚠️ 시즌 전체가 아니라 **보유 구간**이다 — 그 사실을 함께 싣는다.
    # ⚠️ 실패해도 분석을 막지 않는다.
    try:
        from app.engine.standings import table as _std_table

        srows = await conn.fetch(
            """SELECT home, away, home_score, away_score FROM games
                WHERE sport = $1 AND status = 'final'
                  AND home_score IS NOT NULL AND starts_at < $2::timestamptz
                ORDER BY starts_at""",
            g["sport"], g["starts_at"])
        if srows:
            blk["standings"] = _std_table([dict(r) for r in srows])
            first = await conn.fetchval(
                """SELECT min(starts_at)::date FROM games
                    WHERE sport = $1 AND status = 'final'
                      AND home_score IS NOT NULL""", g["sport"])
            blk["standings_note"] = (f"보유 구간 {first} 이후 {len(srows)}경기"
                                     if first else "보유 구간")
    except Exception as exc:
        logger.info("[analysis] game=%s 팀 성적 없음: %s", game_id, exc)

    # 🔴 [MKT-4 2026-09-17] **요구 확률을 붙인다.** 디빅 확률은 "방향이 맞나",
    #    요구 확률은 "값이 있나" 를 답한다. 종전에는 뒤를 아무도 계산하지 않아
    #    "방향은 맞지만 가격이 엣지를 다 먹었다"를 코드가 말할 수 없었다.
    # ⚠️ 게이트·추천은 안 바꾼다 — 보여주는 숫자다.
    try:
        from app.engine import market_edge as ME

        side = str(row["predicted_side"] or "").lower()
        p_ours = (row["p_code"] if side == "home"
                  else (1.0 - row["p_code"]) if side == "away" else None)
        blk["odds"] = row["odds"]
        blk["break_even"] = ME.break_even(row["odds"])
        blk["price_edge_pp"] = ME.price_edge_pp(p_ours, row["odds"])
    except Exception as exc:
        logger.info("[analysis] game=%s 가격 재료 없음: %s", game_id, exc)

    # 🔴 [ANL-9] **선발을 붙인다.** `attach_starter_recent` 는 pipeline 이 쓰는
    #    그 함수다 — 다시 만들지 않는다(사본 금지). `conn` 은 `.fetch` 가 있어
    #    pool 자리에 그대로 맞는다.
    # ⚠️ 실패해도 분석을 막지 않는다 — 선발 줄만 없다.
    try:
        from app.engine.starter_recent import attach_starter_recent

        sjg = {"sport": g["sport"], "starts_at": g["starts_at"],
               "home_pitcher": g["home_pitcher"],
               "away_pitcher": g["away_pitcher"]}
        await attach_starter_recent(sjg, conn)
        res = sjg.get("research") or {}
        for side in ("home", "away"):
            nm = str(g[f"{side}_pitcher"] or "").strip()
            if nm:
                blk[f"{side}_starter"] = {
                    "name": nm,
                    "recent": res.get(f"{side}_starter_recent") or []}
    except Exception as exc:
        logger.info("[analysis] game=%s 선발 재료 없음: %s", game_id, exc)
    try:
        from app.engine.structure import attach_derived, derived_probs

        rows = await conn.fetch(
            """SELECT market, side, line, odds FROM odds_snapshots
                WHERE game_id = $1 AND market IN ('spreads','totals')
                  AND snap_tag IS NOT NULL""", game_id)
        blk = attach_derived(blk, [dict(r) for r in rows],
                             home=g["home"], away=g["away"])
        # 🔴 [PA-17 · U10] **후보를 뽑아 원장에 남긴다.** 종전에는 파생 디빅을
        #    만들어 놓고 `structure.candidates` 를 아무도 안 불러서 구조 픽이
        #    통째로 버려졌다(PART A 실측 structure_pick 0/2경기).
        # 🔴 **저장 전용이다.** 승패 판정·확신을 건드리지 않는다 — 구조 픽은
        #    파생 시장 후보일 뿐이고, 발송 여부는 조건 B 의 몫이다.
        from app.engine import structure as ST

        der = derived_probs([dict(r) for r in rows])
        # 🔴 [LAM-1 2026-09-17] **우리 총점 확률을 넘긴다.** 없으면 종전대로
        #    총점은 건너뛴다(지어내지 않는다).
        # ⚠️ JSON 을 거치면 라인 키가 **문자열**이 된다("7.5") — 숫자로 되돌린다.
        mp = row["model_probs"]
        mp = json.loads(mp) if isinstance(mp, str) else (mp or {})
        ours = {}
        for k, v in ((mp.get("totals") or {}) if isinstance(mp, dict) else {}).items():
            try:
                ours[float(k)] = v
            except (TypeError, ValueError):
                continue
        picks = ST.candidates(p_code=row["p_code"], derived=der,
                              home=g["home"], away=g["away"],
                              ours_totals=ours or None)
        if picks:
            top = max(picks, key=lambda x: x.edge_pp)
            payload = {"market": top.market, "side": top.side,
                       "line": top.line, "edge_pp": top.edge_pp,
                       # ⚠️ 필드는 `reason` 이다 — 처음에 `why` 로 적었다가
                       #    조용히 except 로 빠졌다(로그만 남았다).
                       "grade": ST.grade(top.edge_pp), "why": top.reason,
                       "n_candidates": len(picks)}
            await conn.execute(
                "UPDATE pick_ledger SET structure_pick = $2::jsonb "
                "WHERE game_id = $1 AND is_final",
                game_id, json.dumps(payload, ensure_ascii=False))
            logger.info("[structure] game=%s %s %s %+.1f%%p 등급 %s (후보 %d)",
                        game_id, top.market, top.side, top.edge_pp,
                        payload["grade"], len(picks))
        else:
            logger.info("[structure] game=%s 구조 후보 없음 (edge < %s%%p)",
                        game_id, ST.EDGE_MIN_PP)
    except Exception as exc:
        logger.info("[analysis] game=%s 파생 디빅 없음: %s", game_id, exc)

    # ── S7 재판정 — 딥서치 결장 명단을 **결장 변수로 다시 매긴다** (PA-27)
    #
    # 🔴 `collected` 는 위성 추출 결과다. `out` 은 기사가 말한 **결장자 이름**
    #    이고, `EXTRACT_SCHEMA` 가 그 이름의 원본이다 — 여기서 새로 짓지 않는다.
    # 🔴 `reweigh` 는 `{side: {bench_notable, surprise_in}}` 모양을 받는다
    #    (`fotmob.diff_xi` 와 같은 모양). 결장 명단은 `bench_notable` 자리다.
    # ⚠️ **선수 시장가치가 없다.** 추출은 이름만 준다 — `importance` 가 1.0
    #    중립으로 잡히고 한 명당 1.5%p 로 세어진다. 가치를 지어내지 않는다.
    # ⚠️ 축 이름은 `라인업결장` 으로 찍힌다(`reweigh` 의 `KEY_OUT`). 출처가
    #    T-60 라인업이 아니라 딥서치라는 것은 `regraded_by` 가 말한다.
    try:
        from app.engine import rejudge as RJ
        from app.engine.scout_config import EXTRACT_SCHEMA

        # 🔴 결장 명단 칸 이름은 **추출 스키마가 원본**이다. 스키마에서
        #    사라지면 조용히 빈 diff 가 되는 대신 경고가 뜨게 한다
        #    (아래 except 가 받아 `재판정 실패` 로 남긴다). 계약이 함께 잰다.
        out_key = "out"
        assert out_key in EXTRACT_SCHEMA, "추출 스키마에 결장 칸이 없다"
        diff = {}
        for side in ("home", "away"):
            names = (collected.get(side) or {}).get(out_key) or []
            if names:
                diff[side] = {"bench_notable": list(names), "surprise_in": []}
        if diff:
            # 🔴 [PA-27-d] **부분 출처라고 밝힌다.** 기사 명단은 기사에 이름이
            #    난 선수만 담는다 — `주전결장`(오늘 타순 전체 집계)이 이미
            #    있으면 그 앞에서 물러난다(docs/FORKS.md F-2).
            rj = RJ.reweigh(adj=adj, p_code=row["p_code"], diff=diff,
                            sport=g["sport"], grade=row["confidence"],
                            source=RJ.SRC_NEWS)
            if await record_rejudge(conn, game_id=game_id, rj=rj,
                                    by=RJ.SRC_NEWS):
                out["rejudge"] = rj
                logger.info(
                    "[rejudge] game=%s 딥서치 결장 %s → p_code %s → %s · "
                    "등급 %s → %s%s", game_id,
                    {k: len(v["bench_notable"]) for k, v in diff.items()},
                    row["p_code"], rj["p_code_after"], row["confidence"],
                    rj["grade_after"],
                    " · 등급이 바뀌었다" if rj["grade_after"] != row["confidence"]
                    else "")
            else:
                # 🔴 [PA-27-d] 안 쓴 이유를 남긴다 — "조용한 0"은 결함이다.
                logger.info("[rejudge] game=%s 재판정 안 함 — %s",
                            game_id, rj.get("why"))
        else:
            logger.info("[rejudge] game=%s 추출에 결장자 이름이 없다 — 재판정 안 함",
                        game_id)
    except Exception as exc:
        logger.warning("[analysis] game=%s 재판정 실패: %s", game_id, exc)

    # ── S11 분석 (U12)
    try:
        from app.engine import analyze as AN

        res = await AN.run({"game_id": game_id}, blk, gate_label=label,
                           code_winner=row["predicted_side"],
                           code_level=row["confidence"])
        led = res.get("ledger") or {}
        if led:
            await conn.execute(
                _ANALYZE_SAVE, game_id, led.get("main_axis"),
                led.get("counter_axis"), led.get("market_view"),
                led.get("swap_agree"), led.get("structure_candidates"),
                led.get("analyze_model"), led.get("gate_vs_llm"),
                bool(led.get("analyze_failed")),
                json.dumps(led.get("analyze_check") or {}, ensure_ascii=False))
        out["analyze"] = {k: res.get(k) for k in ("l1", "l2", "banned", "skipped")}
    except Exception as exc:
        logger.warning("[analysis] game=%s 분석 실패: %s", game_id, exc)
    return out



# ═══════════════ [PA-14 2026-09-16 · 지시문 Phase D1] 북 간 비교
#
# 🔴 `book_gap` 은 만들어져 있는데 **운영 호출이 0건**이었다 —
#    analyze·gate.select·U9 흐름·U10 구조에 이어 다섯 번째다.
# 🔴 **저장 전용이다.** 지시문 D1 은 "괴리 기준선을 p_market 에서 p_sharp 로
#    교체"까지 말하지만 여기서는 가지 않는다 — 게이트를 바꾸는 일이라 별도
#    단위다. 먼저 값을 쌓고 표를 봐야 교체가 옳은지 안다.
# 🔴 **사설 평균으로 샤프를 대체하지 않는다.** 한쪽이 없으면 NULL 이다.

_BOOKS_SQL = """
    SELECT DISTINCT ON (book, side) book, side, odds
      FROM odds_snapshots
     WHERE game_id = $1 AND market = 'h2h' AND book = ANY($2::text[])
     ORDER BY book, side, captured_at DESC
"""

_GAP_SAVE = """
    UPDATE pick_ledger
       SET pinnacle_gap = $2::double precision, pinnacle_gap_label = $3
     WHERE game_id = $1 AND is_final
"""


async def record_book_gap(conn, *, game_id: int) -> dict | None:
    """[D1] 샤프 대 사설 괴리를 원장에 남긴다. **저장 전용.**

    ⚠️ 실패해도 판정을 막지 않는다(CLV·이동과 같은 규약).
    ⚠️ 북 이름·문턱은 `book_gap` 이 원본이다 — 여기 적지 않는다.
    """
    from app.engine import book_gap as BG

    rows = await conn.fetch(_BOOKS_SQL, game_id, [BG.SHARP_BOOK, BG.SOFT_BOOK])
    by_book: dict[str, dict] = {}
    for r in rows:
        by_book.setdefault(r["book"], {})[r["side"]] = r["odds"]

    sharp = by_book.get(BG.SHARP_BOOK)
    soft = by_book.get(BG.SOFT_BOOK)
    got = BG.pinnacle_gap(soft, sharp)
    if not got:
        logger.info("[book-gap] game=%s 한쪽 북이 없다 — NULL 로 둔다 "
                    "(샤프 %s · 사설 %s)", game_id,
                    "있음" if sharp else "없음", "있음" if soft else "없음")
        return None
    await conn.execute(_GAP_SAVE, game_id, float(got["gap_pp"]), got["label"])
    logger.info("[book-gap] game=%s %s %+.2f%%p — %s", game_id,
                got["side"], got["gap_pp"], got["label"])
    return got
