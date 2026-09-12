"""[v1.1 6단계] 트리거형 딥서치 — 판정이 막힌 경기만 스스로 조사한다.

**전 경기 상시 검색 금지.** 비용·외부 의존이 걸린 최고위험 단계라 상한을
세 겹으로 둔다: 트리거(발동 조건) · 경기당 검색 수 · 하루 발동 비율.

**야구·축구 공통이다.** 종목 분기 없이 하나의 모듈이 양쪽 판정 경로에 붙는다.
언어만 종목별로 다르다 — 원문 소스가 그 언어로 쓰여 있기 때문이다.

⚠️ 검색 결과는 **크롤 정형 데이터보다 낮은 신뢰 등급**이다. 조정은 ±10%p로
   묶고 우세 방향은 단독으로 뒤집지 못한다. 이 두 가지는 프롬프트 지시가
   아니라 **코드가 강제**한다 — 모델이 규칙을 어겨도 값이 새어 나가지 않게.
"""
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

#: 확률 조정 상한. 클리핑과 같은 방식으로 코드가 강제한다.
ADJUST_CAP_PP = 10.0   # [MKT-8 2026-09-09 사용자 지시] ±4 → ±10%p. 괴리 정보가
                       #   판정을 실제로 움직이게 한다. 상한은 코드가 강제한다.

#: 게이트 임계 ±이 값 안이면 경계 경기(T1).
BOUNDARY_PP = 3.0

# 트리거 이름
T1_BOUNDARY = "T1_경계확률"
T2_MARKET = "T2_시장괴리"
T3_ASKED = "T3_추가확인"
T4_STARTER = "T4_선발변경"
T5_LINEUP = "T5_라인업이상"
#: [2026-09-02 사용자 지시] **라인업이 처음 확정되는 순간** 조사한다.
#   🔴 종전 T4·T5 는 "직전 대비 무엇이 달라졌나"만 봤다. 그래서 **최초 공시는
#      비교 대상이 없어 아무 트리거도 안 걸렸다** — 라인업이 나온 그 순간이
#      가장 정보가 많은 시점인데 조사를 안 하고 있었다.
#      변동이 아니라 **발표**가 방아쇠다.
T6_FIRST_LINEUP = "T6_라인업최초확정"
#: [DS-3 2026-09-10 사용자 지시] **전 경기 조사.** "트리거 걸린 경기만 하지 말고
#  전부 다 해라." 아무 트리거도 안 걸린 조용한 경기에도 이것이 붙어 조사 대상이
#  된다. 진짜 트리거는 앞에 그대로 남으므로 원인 추적이 죽지 않는다.
#  ⚠️ 상한은 별개 축이다 — `deepsearch_daily_cap` 이 1.0(100%)이어야 실제로
#     전 경기가 돈다. 둘 중 하나만 열면 여전히 일부가 빠진다.
T0_ALL = "T0_전수"

#: 조사 언어 — 원문 소스가 그 언어로 쓰여 있다. 영어로만 찾으면
#: KBO 구단 공지·NPB 스포츠지가 통째로 빠진다.
SEARCH_LANG = {"kbo": "한국어", "npb": "일본어", "mlb": "영어", "soccer": "영어"}

CACHE_KEY = "deepsearch:{league}:{game_id}:{date}"
# 🔴 6h 였다. 저녁 슬레이트가 6시간을 넘기면 같은 경기를 **하루에 두 번**
#    조사한다(1차 판정 + 늦은 재판정). 날짜가 키에 있어 다음날과 충돌하지
#    않으므로 24h 로 둔다 — 당일 재조사를 막는 것이 목적이다.
CACHE_TTL = 24 * 3600


# ---------------------------------------------------------------- 트리거

def _gate_threshold(sport: str, favored: str | None, settings) -> float:
    """그 경기의 확률 임계. 원정은 프리미엄이 붙는다."""
    from app.engine.scoring import BASEBALL_SPORTS

    if sport in BASEBALL_SPORTS:
        base = float(settings.min_win_prob)
        return base + 0.05 if favored == "away" else base
    return 0.60 if favored == "away" else 0.55      # 축구 (수동 프로토콜과 동일)


def triggers(jg: dict, settings, *, prev_lineup: dict | None = None) -> list[str]:
    """이 경기가 조사 대상인가. 걸린 트리거 목록(빈 목록이면 발동 안 함).

    ⚠️ 하나라도 걸리면 발동하되 **경기당 1회**다. 여러 개가 걸려도 조사는 한 번.
    """
    m = jg.get("matchup") or {}
    p_home = jg.get("p_claude")
    favored = m.get("우세")
    sport = jg.get("sport") or ""
    out: list[str] = []

    # T1 — 게이트 임계 ±3%p (경계 경기)
    if p_home is not None and favored in ("home", "away"):
        p = float(p_home) if favored == "home" else 1.0 - float(p_home)
        need = _gate_threshold(sport, favored, settings)
        if abs(p - need) * 100 <= BOUNDARY_PP:
            out.append(T1_BOUNDARY)

    # T2 — 시장 괴리
    #   🔴 [MKT-7 2026-09-09] **이 트리거는 한 번도 발동한 적이 없었다.**
    #      옛 조건(`edge_status`·`market_divergence`)을 세팅하는 곳은
    #      `market_edge.py` 하나뿐인데 그 모듈은 운영에서 아무도 안 부른다(E-1).
    #      운영 실측: 딥서치 400건 중 발동 87 — T5 83 · T6 37 · T4 25 ·
    #      **T1 0 · T2 0 · T3 0**, `edge_status` 는 원장 763건 전부 NULL.
    #   ✅ 괴리는 `market_edge` 없이도 안다 — `p_market_send` 와 `p_claude` 뿐이다.
    #      임계값을 여기 적지 않는다: `market_variable.DIVERGENCE_PP` 가 원본이다.
    #   ⚠️ 옛 두 조건은 **그대로 둔다** — `market_edge` 가 언젠가 배선되면
    #      그 경로도 계속 살아야 한다.
    from app.engine.market_variable import divergence_variable

    if (jg.get("edge_status") == "candidate" or jg.get("market_divergence")
            or divergence_variable(jg) is not None):
        out.append(T2_MARKET)

    # T3 — 판정이 스스로 "이건 더 봐야 한다"고 말했다
    if [x for x in (m.get("추가확인") or []) if str(x).strip()]:
        out.append(T3_ASKED)

    # T4 — 재판정에서 선발이 바뀌었다
    if t4_evidence(jg)[0]:
        out.append(T4_STARTER)

    # T5 — 라인업 이상 (2026-08-31 신설)
    if t5_evidence(jg, prev_lineup)[0]:
        out.append(T5_LINEUP)
    # T0 — [DS-3] 전수. 아무것도 안 걸려도 조사한다(사용자 지시). **맨 뒤에** 붙여
    #      진짜 트리거가 앞에 오게 한다 — 발동 원인 추적을 잃지 않기 위해서다.
    out.append(T0_ALL)
    return out


# ---------------------------------------------------------------- 근거 출처
#: 발동 근거가 어디서 왔는가. 모델 자백만 믿지 않는다.
SRC_MODEL = "model"
SRC_FACT = "poller_fact"
SRC_BOTH = "both"


def _src(model_hit: bool, fact_hit: bool) -> str | None:
    if model_hit and fact_hit:
        return SRC_BOTH
    if fact_hit:
        return SRC_FACT
    if model_hit:
        return SRC_MODEL
    return None


def t4_evidence(jg: dict) -> tuple[bool, str | None]:
    """선발이 바뀌었는가. **모델 자기 보고 OR 폴러의 사실.**

    🔴 실측 2026-09-01 강제 검증: T4 가 재판정 경로에서 한 번도 걸리지
       않았다. `_run_baseball_matchups` 가 jg["matchup"] 을 새 판정으로
       통째로 덮어써, run_for_rejudge 는 주입된 직전대비가 아니라 **새
       모델이 스스로 보고한 `변경입력: []`** 를 봤다.
       그런데 선발이 바뀌었다는 **사실**은 폴러가 이미 갖고 있다 —
       `lineup_notes` 의 "홈 선발 변경: 임찬규 → 켈리".
       하드 증거가 있는데 모델 자백을 기다릴 이유가 없다.
    """
    m = jg.get("matchup") or {}
    model_hit = any("선발" in str(x)
                    for x in ((m.get("직전대비") or {}).get("변경입력") or []))
    fact_hit = any("선발 변경" in str(x) for x in (jg.get("lineup_notes") or []))
    return (model_hit or fact_hit), _src(model_hit, fact_hit)


def t5_evidence(jg: dict, prev_lineup: dict | None = None) -> tuple[bool, str | None]:
    """라인업 이상. **평가서 기반 판정 OR 직전 대비 타순 diff.**

    ⚠️ 임계값은 기존 T5 정의 그대로 **주전 2명 이상**이다 — 새 기준을
       만들지 않는다. diff 는 작업 1의 `lineup_diff` 를 그대로 쓰고,
       선발 교체 줄은 뺀다(그건 T4 의 몫이다).
    """
    model_hit = lineup_anomaly(jg, prev_lineup)
    fact_hit = False
    if prev_lineup:
        from app.engine.pregame_push import lineup_diff

        changes = [c for c in lineup_diff(_roster_sig(prev_lineup), _roster_sig(jg))
                   if "선발" not in c]
        fact_hit = len(changes) >= 2
    return (model_hit or fact_hit), _src(model_hit, fact_hit)


def _roster_sig(jg: dict) -> str:
    """`lineup_diff` 가 읽는 4칸 서명. 타순은 "1:이름,2:이름" 으로 만든다.

    야구 타순은 "김현수-오스틴-…" 문자열이라 슬롯 번호가 없다 — 그대로
    넘기면 `_order_map` 이 빈 dict 를 돌려주고 diff 가 통째로 죽는다.
    """
    def _pitcher(side: str) -> str:
        pit = (jg.get("research") or {}).get(f"{side}_pitcher") or {}
        if isinstance(pit, dict):
            return (pit.get("name") or "").strip()
        return str(pit or "").strip()

    def _order(side: str) -> str:
        names = []
        raw = _lineup_of(jg, side)
        if isinstance(raw, str):
            names = [x.split("(")[0].strip() for x in raw.split("-")]
        elif isinstance(raw, (list, tuple)):
            names = [str((x.get("name") if isinstance(x, dict) else x) or "")
                     .split("(")[0].strip() for x in raw]
        return ",".join(f"{i + 1}:{n}" for i, n in enumerate(names) if n)

    return "|".join([_pitcher("home"), _pitcher("away"),
                     _order("home"), _order("away")])


def lineup_anomaly(jg: dict, prev_lineup: dict | None = None) -> bool:
    """직전 대비 주전 2명 이상 교체, 또는 폼 평가서 핵심 선수 결장.

    🔴 **숫자가 경계에 안 걸려도 라인업 이상 자체가 조사 사유다.**
       확률이 편안한 구간에 있어도, 폼 평가서가 근거로 삼은 선수가 빠졌다면
       그 판정의 토대가 무너진 것이다.
    """
    for side in ("home", "away"):
        cur = _names(_lineup_of(jg, side))
        prev = _names(_lineup_of(prev_lineup or {}, side))
        if cur and prev and len(prev - cur) >= 2:
            return True
    # 폼 평가서가 이름을 댄 선수가 오늘 결장 명단에 있는가
    key_names = _form_key_players(jg)
    if key_names:
        out = _absent_names(jg)
        if key_names & out:
            return True
    return False


def _lineup_of(jg: dict, side: str):
    """그 팀의 타순/라인업. **종목마다 저장 위치가 다르다.**

    🔴 실측 2026-09-01: T5 가 야구에서 한 번도 발동하지 않았다.
       `jg["lineup_home"]`·`jg["home_lineup"]`만 보는데 야구 analysis 캐시는
       `jg["research"]["home_lineup"]["order"]`에 담는다. 키가 어긋나
       주전 교체 분기와 핵심선수 결장 분기가 **둘 다 죽어 있었다.**
       축구(`home_lineup` dict)는 첫 두 경로에서 그대로 걸리므로 영향 없다.
    """
    for v in (jg.get(f"lineup_{side}"), jg.get(f"{side}_lineup")):
        if v:
            return v
    order = ((jg.get("research") or {}).get(f"{side}_lineup") or {})
    if isinstance(order, dict) and order.get("order"):
        return order["order"]
    # 🔴 [2026-09-04] KBO·NPB 는 크롤러가 준 타순을 research 에 **문자열**로
    #    담는다("홍창기-신민재-오스틴"). 종전에는 dict 만 보고 문자열은
    #    통째로 흘려보내 `None` 을 돌려줬다 — 그래서 T5(라인업 이상)와
    #    T6(최초 공시)가 **야구에서 여전히 죽어 있었다.**
    #    2026-09-01 에 "키가 어긋나 T5 가 한 번도 발동하지 않았다"를 고쳤는데,
    #    그때는 dict 경로만 열고 문자열 경로는 안 열었다. 같은 결함의 절반이
    #    남아 있었던 것이다(실측 2026-09-04 KBO 저녁 재판정 8건).
    if isinstance(order, str) and order.strip():
        return order
    nine = ((jg.get("today_nine") or {}).get(side) or {}).get("order")
    return nine or None


def _names(v) -> set[str]:
    if not v:
        return set()
    if isinstance(v, dict):                  # 축구 라인업 블록
        v = v.get("order") or v.get("선발") or ""
    if isinstance(v, str):
        parts = [p.split("(")[0].strip() for p in v.split("-")]
    elif isinstance(v, (list, tuple)):
        # 확정 9명은 [{"slot":1,"name":"김현수"}, …] 형태다 — str() 하면
        # dict 통째가 이름이 돼 비교가 전부 어긋난다.
        parts = [str((p.get("name") if isinstance(p, dict) else p) or "")
                 .split("(")[0].strip() for p in v]
    else:
        return set()
    return {p for p in parts if p}


def _form_key_players(jg: dict) -> set[str]:
    """폼 평가서 서술에 이름이 등장한 선수 — 판정의 토대가 된 사람들."""
    out: set[str] = set()
    for side in ("home", "away"):
        form = (jg.get("research") or {}).get(f"{side}_form") or {}
        blob = json.dumps(form, ensure_ascii=False) if form else ""
        for nm in _names(_lineup_of(jg, side)):
            if nm and nm in blob:
                out.add(nm)
    return out


def _absent_names(jg: dict) -> set[str]:
    out: set[str] = set()
    for side in ("home", "away"):
        lu = (jg.get(f"{side}_lineup") or {})
        out |= {str(x).strip() for x in (lu.get("결장") or []) if str(x).strip()}
        res = (jg.get("research") or {}).get(f"{side}_absent") or []
        out |= {str(x).strip() for x in res if str(x).strip()}
    return out


# ---------------------------------------------------------------- 상한

#: [DS-5] 그날 본 **최대** 슬레이트 크기. 상한 기준을 하루 내내 고정한다.
DAY_SIZE_KEY = "deepsearch:daysize:{sport}:{date}"


async def remember_day_size(redis, sport: str, date: str, now_size: int) -> int:
    """그날 총 경기 수(고수위선)를 기억하고 돌려준다.

    🔴 **왜 필요한가 (실측 2026-09-10 05:03).** 딥서치가 오후에 전부 막혔다:
           "슬레이트 10경기 · 후보 10 · 조사 0 · 예산 13/10 · 상한초과 생략 10"
       카운터는 **하루 누적**인데 상한은 **지금 이 순간 슬레이트 크기**로 계산됐다.
       경기가 시작돼 `status='scheduled'` 에서 빠지면 슬레이트가 줄고 상한도 줄지만
       카운터는 안 줄어든다 — 그래서 낮·저녁에는 항상 초과가 되어 **재판정·수정
       카드가 전부 딥서치 없이 나갔다.**

    ⚠️ 최대값만 올린다(내려가지 않는다). 더블헤더 추가처럼 늘어나는 경우는 따라간다.
    ⚠️ redis 가 없거나 실패하면 현재 크기를 그대로 쓴다 — 조사를 막지 않는다.
    """
    n = max(0, int(now_size or 0))
    if redis is None:
        return n
    key = DAY_SIZE_KEY.format(sport=(sport or ""), date=date)
    try:
        prev = int(await redis.get(key) or 0)
    except Exception:
        return n
    if n <= prev:
        return prev
    try:
        await redis.set(key, n, ex=CACHE_TTL)
    except Exception:
        pass
    return n


def daily_cap(slate_size: int, settings) -> int:
    """하루 발동 상한 = 슬레이트의 N%. 최소 1건은 허용한다.

    슬레이트가 3경기인 날 30%면 0.9라 아무것도 조사 못 한다 — 경계 경기가
    있어도 손을 놓는 것은 이 단계의 취지가 아니다.
    """
    if slate_size <= 0:
        return 0
    return max(1, int(slate_size * float(settings.deepsearch_daily_cap)))


#: [DS-14 2026-09-10 사용자 지시 "권한을 바꿔라"] 뒤집기 허용 조건.
#  🔴 **왜 바꾸나 — 실측이 근거다** (채점 완료 172경기, game_id 중복 제거):
#       딥서치 적용 전 88/172 = 51.2%
#       딥서치 적용 후 88/172 = 51.2%   ← 완전히 같다
#       우세가 뒤집힌 경기 **0건** · |이동| 중앙 4.0%p
#       브라이어 0.2565 → 0.2559 (개선 0.0006 = 잡음)
#     원인은 조사 품질이 아니라 **권한**이었다. 아래 가드가 0.50 에서 멈춰 세워
#     딥서치는 같은 팀 안에서 확률만 밀 수 있었다 — 승패 적중률에 기여할 길이
#     원천 차단돼 있었다.
#  ⚠️ 권한을 주되 **아무 근거로나 주지 않는다.** 뉴스 한 줄로 픽이 뒤집히면
#     그건 개선이 아니라 소음이다. 두 조건을 **모두** 요구한다.

#: 뒤집으려면 `발견` 에 이 소스유형이 하나는 있어야 한다. 공시·기록은 확인
#  가능한 사실이고, 뉴스는 아직 사실이 아닐 수 있다.
HARD_SOURCES = ("공식", "기록")

#: 뒤집은 뒤 0.50 에서 이만큼은 넘어가야 한다. 0.499 는 뒤집기가 아니라 잡음이다.
FLIP_MARGIN_PP = 2.0


def _has_hard_evidence(evidence) -> bool:
    """`발견` 중 공시·기록이 하나라도 있는가. 형식이 이상하면 **없는 것으로 본다.**"""
    for f in (evidence or []):
        if isinstance(f, dict) and str(f.get("소스유형") or "").strip() in HARD_SOURCES:
            return True
    return False


def clamp_adjustment(p_before: float, p_after: float | None,
                     favored: str | None, *, evidence=None) -> tuple[float, str | None]:
    """조정 ±10%p 상한 + **조건부** 우세 뒤집기. **코드가 강제한다.**

    반환: (적용할 p, 사람이 읽는 사유 or None)

    ⚠️ 프롬프트에 적는 것만으로는 부족하다. 모델이 규칙을 어겨도 값이 새어
       나가지 않아야 한다 — 클리핑과 같은 태도다.
    ⚠️ `evidence` 를 안 넘기면 **종전 그대로 막는다.** 기본값이 조용히
       느슨해지면 안 된다 — 호출부가 명시적으로 근거를 건네야 권한이 열린다.
    ⚠️ 조정 폭 ±10%p 와 클립은 **바꾸지 않았다.** 바뀐 것은 방향 권한뿐이다.
    """
    if p_after is None:
        return p_before, None
    lo, hi = p_before - ADJUST_CAP_PP / 100, p_before + ADJUST_CAP_PP / 100
    p = max(lo, min(hi, float(p_after)))
    note = None
    if abs(float(p_after) - p) > 1e-9:
        note = f"조정 상한 ±{ADJUST_CAP_PP:g}%p 적용 ({p_after:.3f}→{p:.3f})"

    # 🔴 [DS-15 2026-09-10] **지켜야 할 방향은 숫자로 정한다.**
    #    종전에는 `favored` 라벨을 봤다. 그건 모델이 스스로 붙인 말이고,
    #    우리가 실제로 행동하는 값은 `p_before` 다. 라벨이 "박빙"이면 검사가
    #    **아예 안 돌았다** —
    #        clamp_adjustment(0.52, 0.49, "박빙") → (0.49, None)   그냥 통과
    #        clamp_adjustment(0.52, 0.49, "home") → (0.50, 뒤집기 금지)
    #    실측: 채점 181경기 중 **31건(17%)이 박빙 라벨** — 그 경기들은 검사
    #    없이 0.50 을 넘나들 수 있었다. 오늘 텍사스@시애틀(0.52→0.49, 실제
    #    홈승)이 그 첫 발현으로 보인다.
    #    ⚠️ p_before 가 정확히 0.50 이면 지킬 방향이 없다 — 막지 않는다.
    _EPS = 1e-9
    side = ("home" if p_before > 0.5 + _EPS
            else "away" if p_before < 0.5 - _EPS else None)
    flips = ((side == "home" and p < 0.5)
             or (side == "away" and p > 0.5))
    if not flips:
        return round(p, 4), note

    margin = abs(p - 0.5) * 100
    if _has_hard_evidence(evidence) and margin >= FLIP_MARGIN_PP:
        return round(p, 4), (f"조사가 우세를 뒤집었다 — 공시·기록 근거 "
                             f"({p_before:.3f}→{p:.3f})")
    why = ("결정적이지 않다" if _has_hard_evidence(evidence)
           else "공시·기록 근거 없음")
    return 0.5, f"우세 뒤집기 금지({why}) — 0.50에서 멈춤"


# ---------------------------------------------------------------- 조사 엔진

PROMPT = """당신은 스포츠 경기 조사원이다. 아래 판정이 확신을 세우지 못한
지점만 조사한다. 판정을 처음부터 다시 하지 않는다.

[경기] {league} · {away} (원정) @ {home} (홈) · {kickoff} KST
[현재 판정] {verdict}
[발동 트리거] {triggers}{divergence}
[판정이 요청한 추가확인] {asked}{questions}

[오늘] {today} (KST). 이 경기는 **오늘 또는 내일** 열린다.
🔴 검색은 지난 시즌 기사를 먼저 물어온다. 연도를 확인하지 않으면 **1년 전
부상·복귀 소식을 오늘 일로 착각한다.** 실측 2026-09-01: 조사가 2025년 8월
부상자명단 등재와 2025년 9월 복귀를 오늘의 컨디션 근거로 올렸다.
- 검색어에 **연도를 넣는다** (예: "{today} 선발").
- 근거로 쓰기 전에 **기사 날짜를 확인한다.** 최근 30일 밖이면 쓰지 않는다.
- 날짜를 확인할 수 없는 내용은 "미확인"으로 적고 근거에서 뺀다.

[조사 언어] 검색어는 **{lang}**로 만든다. 원문 소스가 그 언어로 쓰여 있다 —
영어로만 찾으면 구단 공지·현지 스포츠지가 통째로 빠진다.

[검색 예산] **총 {budget}회.** 이것은 하드 상한이며 초과하면 조사가 통째로
무효가 된다. 배분:
- 1~2회: 위 [판정이 요청한 추가확인]에 답한다. **이것이 최우선이다.**
- 3회째부터: 남은 예산으로 아래 체크리스트 중 **가장 승률에 영향이 큰 1~2개만**.
- **마지막 1회를 남기기 전에 반드시 결론을 낸다.** 다 못 찾았으면 찾은 것까지로
  답하고 나머지는 "미확인"으로 적는다. 예산을 다 쓰고 결론을 못 내면 실패다.

[승률 관련 확인 항목] 위 예산 안에서 **해당하는 것만** 조사한다. 전부 훑지 마라.
① 결장자의 사유·복귀 시점 (부상 정도·로테이션·징계)
② 오늘 선발 자원의 컨디션 이상 (구속 저하·복귀전·등판 간격 / 부상 복귀·주중 경기 피로)
③ 팀 내부 이슈 (감독 발언·경질설, 라커룸, 연전·원정 이동 피로)
④ 날씨·구장 특이사항 (우천 취소/지연 가능성 포함)
⑤ **선발 등판 기록이 없거나 1경기뿐인 투수** — 왜 없는지(부상 이탈·2군·데뷔·
   불펜 전향)와 **최근 실전 등판(2군·마이너 포함)** 성적을 찾는다.
   못 찾으면 "미확인"으로 적는다. 지어내지 마라.
   🔴 이걸 찾아와도 **추천이 열리지는 않는다.** 표본 하한은 코드가 따로
      집행하고, 2군 4이닝으로 1군 6이닝을 예측할 수는 없다. 목적은
      "왜 자료가 없는지"를 사용자에게 보여 주는 것이다.
   실측 2026-09-01 (NPB 요미우리전): 戸郷 翔征은 1군 등판 0으로 판정이
   "개인 폼 확인 불가"에서 멈췄다. 웹 검색 5분이면 7/7 좌측 햄스트링 이탈,
   8/26 2군 복귀전 4이닝 무실점, 감독 코멘트까지 나온다. 조사가 그걸
   안 찾은 것은 이 항목이 체크리스트에 없었기 때문이다.

🔴 **시장 숫자는 [조정]의 사유가 될 수 없다.**
   시장이 왜 그렇게 봤는지 **조사하는 것은 허용된다**(2026-09-09 개정).
   금지되는 것은 그 **숫자를 조정 사유로 삼는 것** 하나다.
   실측 2026-09-01: 조사가 스포츠북 머니라인 내재확률 51~53%를 **근거로**
   p_home 을 0.59→0.56 으로 내렸다. 추천 1건이 보드만으로 떨어졌다 —
   문제는 조사가 아니라 **숫자를 베낀 것**이었다.
   - 쓸 수 있는 근거: 조사로 **발견한 사실**(부상·결장·구속 저하·날씨·로스터·
     라인이 움직인 시점의 발표).
   - 쓸 수 없는 근거: "시장이 55%다", "머니라인이 −140이다" 같은 **가격 자체**.
   - 사실을 못 찾으면 **조정 0**. 못 찾았다는 것도 결과다.

[소스 규칙]
① 조회 우선순위: 공식 소스(구단 공홈·리그 공시·경기 기록 페이지) → 기록·통계
   사이트 → 뉴스 기사. **뉴스만으로 조사를 끝내지 않는다.**
② 확률 조정의 근거가 **단일 기사 하나뿐이면 조정 폭을 절반으로** 줄인다.
   서로 다른 소스 2개 이상이 같은 사실을 확인할 때만 전액 반영한다.
③ 근거마다 소스 유형(공식/기록/뉴스)과 URL을 남긴다.
④ **루머·익명 소스·커뮤니티발 내용은 근거로 쓰지 않는다.**

[결과의 지위]
- 검색 결과는 **크롤 정형 데이터보다 낮은 신뢰 등급**이다.
- 확률 조정은 **±10%p 이내**. 우세 방향을 검색 결과 단독으로 뒤집지 않는다.
- 조사해도 새 사실이 없으면 **조정 0**으로 두고 그렇게 적는다. 억지로 움직이지 마라.

delta_pp = **홈 승률을 몇 %p 올릴지**(원정 쪽 근거면 음수, 없으면 0). 절대 확률이
아니라 **증감**이다. 코드가 ±10%p 로 절사하고 우세 방향은 뒤집지 않는다.

[근거번호] 각 발견에 그것이 나온 **[수집된 기사] 번호**를 적어라.
   수집된 기사에서 나온 것이 아니면(네가 이미 알던 것·추론) `null` 을 적는다.
   🔴 지어내지 마라. 번호를 못 대면 `null` 이 정답이다 — 우리는 이 값으로
      "모아 준 재료가 실제로 쓰였는가"를 잰다. 틀린 번호는 그 측정을 망친다.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{
  "발견": [{{"사실": "1문장", "소스유형": "공식|기록|뉴스", "url": "...",
            "근거번호": 1}}],
  "조정": {{"delta_pp": 0, "사유": "1문장", "단일기사여부": true|false}},
  "요약": "카드에 실을 1문장"
}}"""


#: [DS-8 2026-09-10 사용자 지시] **판정이 낸 질문을 조사에 넘긴다.**
#  🔴 실측(TB@ATL): 갈림길이 "부상 복귀전 로페즈가 몇 이닝 버티나"를 물었고
#     조사는 "로페즈 IL 복귀 활성화"를 찾았는데, 둘이 만나지 않아 갈림길 아래엔
#     "자료14 미조사"가 그대로 남았다. 조사가 질문을 모르니 표적 없이 훑은 것이다.
#  ⚠️ 기존 체크리스트를 지우지 않는다 — 우선순위만 준다. 질문에 끌려가 다른
#     중요 사실을 놓치면 그것도 손실이다.
_QUESTIONS = """

[🎯 판정이 낸 갈림길·변수 — **이 질문에 답하라**]
판정은 아래 지점에서 승부가 갈린다고 봤다. 조사의 첫 목적은 **이 질문에 답하는
사실**을 찾는 것이다. DB 는 과거 통계만 안다 — 오늘의 사정(부상 복귀·투구수 제한·
결장 확정 여부)은 여기서만 나온다.
{items}
- 답이 되는 **사실**을 찾으면 [발견]에 그 질문과 묶어 적는다.
- **DB 통계가 오늘 적용되지 않는 사정**을 찾으면 그것도 답이다
  (예: "소속팀 74%는 정상 컨디션 표본인데 오늘은 부상 복귀전이다").
- 못 찾으면 "미확인"이라고 적는다. 그것도 답이다 — 지어내지 마라."""


#: [DS-2 2026-09-09] T2 가 걸렸을 때만 붙는 괴리 문단.
#  ⚠️ 안 걸린 경기에 시장 이야기를 넣으면 **그 자체가 앵커**다 —
#     실측(MKT-4): 시장 숫자를 판정 자료로 주자 |p−시장| 이 67.9% 수축했다.
_DIVERGENCE = """

[🔴 시장 괴리 — 이번 조사의 최우선 항목]
우리 판정은 {ours:.0%}({ours_side} 우세)인데 **시장은 {mkt:.0%}({mkt_side} 우세)** 다.
차이 **{gap:.1f}%p**. 이만큼 갈릴 때 실측상 우리가 50.0% · 시장이 68.3% 맞았다
(운영 원장 60경기). 그리고 그 차이는 **우리 수치로 설명되지 않았다** —
시장이 고른 팀은 최근5 승률 우위가 39%로 오히려 열세였다.
**즉 원인은 수치가 아니라 정보다. 그 정보를 찾는 것이 이 조사의 목적이다.**

- 시장이 {mkt_side} 쪽을 높게 보는 **사실**을 찾아라: 결장·부상 발표, 선발 교체,
  구속 저하, 콜업·트레이드, 날씨·구장, 팀 내부 사정.
- 찾으면 [발견]에 **사실로** 적는다. 시장 가격은 적지 마라.
- **못 찾으면 [조정]은 0 이고 [요약]에 "괴리 원인 미확인"이라고 적는다.**
  못 찾았다는 것도 결과다 — 지어내면 그게 더 나쁘다."""


def _questions_block(m: dict) -> str:
    """판정이 낸 갈림길·변수를 조사 질문으로. 없으면 빈 문자열(문단 자체가 없다)."""
    items = []
    branch = ((m.get("전개") or {}).get("분기점") or "").strip()
    if branch:
        items.append(f"  · 갈림길: {branch}")
    for v in (m.get("변수") or [])[:2]:
        v = str(v).strip()
        if v:
            items.append(f"  · 변수: {v}")
    if not items:
        return ""
    return _QUESTIONS.format(items="\n".join(items))


def build_prompt(jg: dict, trig: list[str]) -> str:
    """조사 프롬프트를 만든다. **모델을 부르지 않는다.**

    🔴 `investigate` 안에 인라인이던 것을 그대로 꺼냈다. 꺼낸 이유는
       `render_matchup_prompt` 와 같다 — 프롬프트만 검사하는 계약을 걸려면
       모델 호출 없이 만들 수 있어야 한다. 재료를 복제하면 곧 드리프트다.
    """
    import json as _json

    from app.config import get_settings

    s = get_settings()
    sport = jg.get("sport") or ""
    m = jg.get("matchup") or {}
    div = ""
    if T2_MARKET in (trig or []):
        from app.engine.market_variable import divergence_variable

        if divergence_variable(jg) is not None:
            ours, mkt = float(jg["p_claude"]), float(jg["p_market_send"])
            div = _DIVERGENCE.format(
                ours=ours, mkt=mkt, gap=abs(ours - mkt) * 100,
                ours_side="홈" if ours > 0.5 else "원정",
                mkt_side="홈" if mkt > 0.5 else "원정")
    return PROMPT.format(
        league=jg.get("league") or sport.upper(),
        home=jg.get("home"), away=jg.get("away"),
        kickoff=jg.get("starts_at_kst") or "",
        verdict=_json.dumps({k: m.get(k) for k in ("p_home", "우세", "근거", "확신도")},
                            ensure_ascii=False, default=str),
        triggers=", ".join(trig or []),
        divergence=div,
        asked=_json.dumps(m.get("추가확인") or [], ensure_ascii=False),
        questions=_questions_block(m),
        lang=SEARCH_LANG.get(sport, "영어"),
        budget=int(s.deepsearch_max_searches),
        today=_today_kst())


def _today_kst() -> str:
    """오늘(KST). 프롬프트가 연도를 모르면 작년 기사를 오늘 일로 읽는다."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


#: 조사 재료 출처. 로그·결과에 그대로 실린다 — 무엇을 읽고 낸 판단인지 남긴다.
SRC_RSS = "rss"          # 무료: Google News RSS + web_fetch
SRC_PAID = "web_search"  # (폐지) 유료 폴백이었다 — 2026-09-06 삭제
SRC_PPLX = "rss+pplx"    # [DS-3] 위성/RSS 재료 + Perplexity 조사 병행
#: 🔴 딥서치의 라우팅 역할. **`matchup` 이 아니다** — matchup 만 유료가
#   허용되고, 딥서치는 최종 판정이 아니다. 문자열을 호출부마다 적지 않는다.
DEEPSEARCH_ROLE = "deepsearch"

PAID_KEY = "deepsearch:paid:{date}"
#: 본문을 붙일 기사 수. 많이 넣으면 프롬프트만 부풀고 판단은 안 나아진다.
FETCH_TOP_N = 4
FETCH_CHARS = 1200


async def _free_articles(jg: dict, redis, *, meta: dict | None = None) -> list[dict]:
    """조사 재료. **위성 캐시를 먼저 읽고**, 없으면 기존 RSS 로 폴백한다.

    🔴 [SAT-3] 위성(`app/collectors/satellite.py`)이 미리 긁어 둔 재료는 DB에 없는
       경기 정보(부상·말소·트레이드…)이고 **본문이 이미 채워져 있다** — RSS 의
       본문 0%·팀라벨 76% 오류 문제가 없다. 재료 모양은 news_rss 와 동일하므로
       하류(`_inject_articles`·요약·±10%p)는 출처를 구분하지 못한다.

    ⚠️ 위성 캐시가 비면(어댑터 없는 종목·위성 꺼짐·수집 실패) **정확히 종전
       RSS 경로로 폴백**한다 — 회귀 없음.
    """
    sport = (jg.get("sport") or "").lower()
    gid = jg.get("game_id") or jg.get("id")
    try:
        from app.collectors.satellite import read_cache

        sat = await read_cache(redis, sport, gid)
    except Exception as exc:
        logger.warning("[deepsearch] 위성 캐시 읽기 실패 — RSS 폴백: %s", exc)
        sat = []
    if sat:
        logger.info("[deepsearch] 위성 캐시 %d건 사용 %s@%s",
                    len(sat), jg.get("away"), jg.get("home"))
        if meta is not None:
            meta["origin"] = "satellite"
        return sat

    try:
        from app.collectors.news_rss import for_game

        items = await for_game(jg, redis)
    except Exception as exc:
        logger.warning("[deepsearch] RSS 수집 실패 — 유료 폴백 판단으로: %s", exc)
        return []
    if not items:
        return []
    for it in items[:FETCH_TOP_N]:
        it["body"] = await _fetch_body(it.get("url"))
    if meta is not None:
        meta["origin"] = "rss"
    return items


#: [DS-3] PPLX 조사 프롬프트. **사실만 요구한다** — 확률·조정은 묻지 않는다.
#  판정은 기존 무료 요약기가 하고, PPLX 는 재료를 늘릴 뿐이다.
_PPLX_PROMPT = """당신은 야구 경기 조사원이다. 오늘 경기의 **승부에 영향을 주는
사실**만 웹에서 찾아 보고하라.

[경기] {league} · {away} (원정) @ {home} (홈)
[오늘] {today} (KST)

찾을 것 — 우리 시스템은 **최근 3~5경기 기록만** 본다. 그 창 밖의 사실이 필요하다:
- 선발 투수의 부상·복귀·구속 저하·등판 간격 이상
- 불펜 소모(연투·마무리 이탈)
- 주축 타자 부상·결장·말소
- 로스터 변동(콜업·트레이드·대표팀 차출)
- 팀 내부 사정·감독 발언, 구장·날씨 특이사항

🔴 규칙
- **최근 7일 이내** 정보만. 기사 날짜를 확인하라.
- 배당·머니라인·시장 확률은 **적지 마라**(가격은 근거가 아니다).
- 확률이나 승부 예측을 하지 마라. **사실만** 적는다.
- 못 찾으면 빈 배열로 답하라. 지어내지 마라.

JSON만 출력(백틱 금지):
{{"발견": [{{"사실": "1문장", "소스유형": "공식|기록|뉴스", "url": "..."}}]}}"""


async def _pplx_findings(prompt: str, *, max_tokens: int = 900) -> dict | None:
    """Perplexity 1콜. 얇은 래퍼 — 테스트가 여기만 바꿔치면 된다."""
    from app.research.perplexity import ask_json

    return await ask_json(prompt, max_tokens=max_tokens)


async def _pplx_articles(jg: dict) -> list[dict]:
    """[DS-3 2026-09-10 사용자 지시] PPLX 가 찾은 사실을 **재료**로 바꾼다.

    🔴 PPLX 에 판정을 넘기지 않는다. 확률 조정은 기존 무료 요약기가 하고, 여기서는
       재료(발견 사실)만 늘린다 — 유료 모델이 p_home 을 직접 움직이면 검증이 없다.

    ⚠️ 실패·크레딧 소진·미설정은 전부 빈 리스트다(ask_json 이 조용한 None).
       조사는 위성/RSS 재료만으로 계속된다 — 회귀 없음.
    """
    from app.config import get_settings

    s = get_settings()
    if not getattr(s, "deepsearch_pplx_enabled", False):
        return []
    sport = (jg.get("sport") or "").lower()
    prompt = _PPLX_PROMPT.format(
        league=jg.get("league") or sport.upper(),
        home=jg.get("home"), away=jg.get("away"), today=_today_kst())
    try:
        data = await _pplx_findings(prompt)
    except Exception as exc:
        logger.warning("[deepsearch] PPLX 조사 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict] = []
    for f in (data.get("발견") or []):
        if not isinstance(f, dict):
            continue
        fact = (f.get("사실") or "").strip()
        if not fact:
            continue
        out.append({
            "title": fact, "url": f.get("url") or "",
            "source": f"Perplexity/{f.get('소스유형') or '조사'}",
            "team": jg.get("home") or "", "age_h": None, "body": fact,
        })
    if out:
        logger.info("[deepsearch] PPLX 재료 %d건 %s@%s",
                    len(out), jg.get("away"), jg.get("home"))
    return out


async def _fetch_body(url: str | None) -> str:
    """기사 본문 앞부분. **무료 HTTP 다.** 실패하면 빈 문자열 — 제목만 쓴다."""
    if not url:
        return ""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as exc:
        logger.debug("[deepsearch] 본문 수집 실패 %s: %s", str(url)[:60], exc)
        return ""
    import re as _re

    html = _re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ",
                   html, flags=_re.S | _re.I)
    text = _re.sub(r"<[^>]+>", " ", html)
    for a, b in (("&amp;", "&"), ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(a, b)
    return _re.sub(r"\s+", " ", text).strip()[:FETCH_CHARS]


def _inject_articles(prompt: str, articles: list[dict]) -> str:
    """프롬프트의 "검색 결과" 자리에 무료 수집분을 넣는다.

    ⚠️ **프롬프트 규칙은 건드리지 않는다.** 자료를 덧붙일 뿐이다 — 조정 상한
       ±10%p, 우세 뒤집기 금지, 신뢰 등급은 그대로다.
    """
    lines = ["", "[수집된 기사] — 아래가 검색 결과다. 추가 검색 도구는 없다.",
             "각 항목: 제목 · 매체 · 몇 시간 전 · 본문 앞부분(있으면).",
             "본문이 비어 있으면 제목만으로 단정하지 마라."]
    for i, a in enumerate(articles, 1):
        age = f"{a.get('age_h')}h 전" if a.get("age_h") is not None else "시각 미상"
        lines.append(f"{i}. [{a.get('team', '')}] {a.get('title', '')} "
                     f"({a.get('source', '')} · {age})")
        body = (a.get("body") or "").strip()
        if body:
            lines.append(f"   본문: {body}")
    return prompt + "\n".join(lines)


async def _paid_budget_left(redis) -> bool:
    """유료 검색 하루 총량이 남았는가. redis 가 없으면 **막는다** (안전측)."""
    from app.config import get_settings

    cap = int(getattr(get_settings(), "deepsearch_paid_cap", 0) or 0)
    if cap <= 0:
        return False
    if redis is None:
        return False
    try:
        used = int(await redis.get(PAID_KEY.format(date=_today_kst())) or 0)
    except Exception:
        return False
    return used < cap


async def _spend_paid(redis) -> None:
    if redis is None:
        return
    try:
        key = PAID_KEY.format(date=_today_kst())
        n = await redis.incr(key)
        await redis.expire(key, 30 * 3600)
        logger.warning("[deepsearch] 유료 web_search 사용 %s회 (일일 상한 안)", n)
    except Exception as exc:
        logger.debug("[deepsearch] 유료 사용 기록 실패: %s", exc)


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


async def scout(jg: dict, materials_prompt: str, redis=None, *,
                timeout: float | None = None) -> dict | None:
    """[SCT-1] **판정 전 정찰** — 자료 + 외부 사실을 보고 **변수를 직접 정한다.**

    사용자 지시 2026-09-11: "변수를 딥서치가 정하게 하고 찾아온 딥서치를
    최종 제미나이가 분석해서 승패를 예측하게 해라."

    `materials_prompt` 는 **이미 렌더된 판정 프롬프트**다(자료1~14 포함).
    같은 재료를 그대로 쓴다 — 정찰용으로 재료를 다시 조립하면 그것이 사본이고,
    두 경로가 서로 다른 자료를 보게 된다.

    반환 `{"발견": [...], "변수": [...], "요약": str, "재료": {...}}` 또는 None.
    ⚠️ **실패는 None 이다.** 그러면 호출부가 종전 경로로 간다 — 정찰이 안 됐다고
       판정을 멈추지 않는다.
    """
    from app.config import get_settings
    from app.engine.prompts import SCOUT

    s = get_settings()
    if s.mock_judge:
        return None
    _meta: dict = {}
    articles = await _free_articles(jg, redis, meta=_meta)
    _origin = _meta.get("origin") or "none"
    _base_n = len(articles)
    pplx = await _pplx_articles(jg)
    if pplx:
        articles = list(articles) + pplx
    if not articles:
        logger.info("[scout] 재료 0건 — 정찰 생략 %s@%s",
                    jg.get("away"), jg.get("home"))
        return None
    head = SCOUT.format(league=(jg.get("sport") or "").upper(),
                        away=jg.get("away") or "", home=jg.get("home") or "",
                        today=_today_kst())
    prompt = _inject_articles(materials_prompt + "\n\n" + head, articles)
    from app.llm.judge_route import chain as _chain

    routes = [r for r in _chain(DEEPSEARCH_ROLE) if r[0] != "anthropic"]
    if not routes:
        logger.error("[scout] 후보가 없다 — 정찰 생략")
        return None
    from app.engine.team_form import _complete_free, parse_json_object

    try:
        body = await asyncio.wait_for(
            _complete_free(routes, prompt, int(s.deepsearch_max_tokens),
                           DEEPSEARCH_ROLE),
            timeout=timeout if timeout is not None
            else float(s.deepsearch_timeout_sec))
    except Exception as exc:
        logger.warning("[scout] 실패 — 종전 경로로 간다 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None
    body = body or ""
    data = parse_json_object(body)
    if not isinstance(data, dict):
        # 🔴 실패 로그는 **다음 사람이 원인을 짚을 수 있어야 한다** —
        #    몇 자가 왔는지(절단)와 본문 앞부분(형식 이탈)을 남긴다.
        #    `investigate` 와 같은 규약이다(tests/test_deepsearch.py 가 잠근다).
        logger.warning("[scout] JSON 파싱 실패 — 종전 경로로 간다 %s@%s "
                       "· %d자: %.300s", jg.get("away"), jg.get("home"),
                       len(body), body.replace("\n", " ")[:300])
        return None
    data["_재료"] = {"n": len(articles),
                     "출처": {"satellite": _base_n if _origin == "satellite" else 0,
                              "rss": _base_n if _origin == "rss" else 0,
                              "pplx": len(pplx)},
                     "urls": [(i, (a.get("url") or ""))
                              for i, a in enumerate(articles, 1)]}
    stats = citation_stats(data)
    data.pop("_재료", None)
    # 🔴 배당 오염은 여기서도 막는다 — 정찰이 가격을 근거로 쓰면 격리선이 뚫린다.
    data, dropped = strip_odds(data)
    if dropped:
        logger.warning("[scout] 배당 오염 차단: %s", " · ".join(dropped))
    out = {"발견": data.get("발견") or [], "변수": data.get("변수") or [],
           "요약": data.get("요약"), "재료": stats}
    logger.info("[scout] %s@%s 변수 %d건 · 발견 %d건 · 재료 %d건 중 인용 %d건",
                jg.get("away"), jg.get("home"), len(out["변수"]),
                len(out["발견"]), stats.get("주입"), stats.get("인용_기사"))
    return out


# ═══════════════════════════════════════════════════════════════════
# [ORD-1 2026-09-11 사용자 지시] 순서를 바꾼다 — ① 갈림길 → ② 보강 → ③ 결론 →
#   ④ 애매한 것만 DB. 아래 둘이 ①②다. ③④는 `matchup.judge_matchup` 에 있다.
# ═══════════════════════════════════════════════════════════════════

async def prescout(jg: dict, brief: str, *,
                   timeout: float | None = None) -> dict | None:
    """① **경기만 보고** 갈림길·변수·조사요청을 세운다. DB 수치를 주지 않는다.

    🔴 왜 DB 를 안 주나. 실측 2026-09-11 MLB 15경기 — 근거 45줄 중 40줄이
       자료1~14 인용이었다. 자료를 먼저 주면 자료가 답을 정하고, 조사는
       이미 정해진 답의 각주가 된다. 순서를 바꾸는 것이 이 수정의 전부다.

    반환 `{"갈림길": [...], "변수": [...], "조사요청": [...]}` 또는 None.
    ⚠️ **실패는 None 이다.** 호출부가 종전 경로로 간다 — 갈림길을 못 세웠다고
       판정을 멈추지 않는다.
    """
    from app.config import get_settings
    from app.engine.prompts import PRESCOUT

    s = get_settings()
    if s.mock_judge:
        return None
    prompt = PRESCOUT.format(league=(jg.get("league")
                                     or (jg.get("sport") or "").upper()),
                             away=jg.get("away") or "", home=jg.get("home") or "",
                             today=_today_kst(), brief=brief or "(없음)")
    from app.llm.judge_route import chain as _chain

    routes = [r for r in _chain(DEEPSEARCH_ROLE) if r[0] != "anthropic"]
    if not routes:
        logger.error("[prescout] 후보가 없다 — 종전 경로로 간다")
        return None
    from app.engine.team_form import _complete_free, parse_json_object

    try:
        body = await asyncio.wait_for(
            _complete_free(routes, prompt, int(s.deepsearch_max_tokens),
                           DEEPSEARCH_ROLE),
            timeout=timeout if timeout is not None
            else float(s.deepsearch_timeout_sec))
    except Exception as exc:
        logger.warning("[prescout] 실패 — 종전 경로로 간다 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None
    body = body or ""
    data = parse_json_object(body)
    if not isinstance(data, dict):
        logger.warning("[prescout] JSON 파싱 실패 — 종전 경로로 간다 %s@%s "
                       "· %d자: %.300s", jg.get("away"), jg.get("home"),
                       len(body), body.replace("\n", " ")[:300])
        return None
    # 🔴 배당 오염은 여기서도 막는다 — 갈림길이 가격을 물고 오면 격리선이 뚫린다.
    data, dropped = strip_odds(data)
    if dropped:
        logger.warning("[prescout] 배당 오염 차단: %s", " · ".join(dropped))
    br = [b for b in (data.get("갈림길") or []) if isinstance(b, dict)]
    asks = [str(q).strip() for q in (data.get("조사요청") or []) if str(q).strip()]
    out = {"갈림길": br,
           "변수": [str(v).strip() for v in (data.get("변수") or []) if str(v).strip()],
           "조사요청": asks[:MAX_ASKS]}
    if not br and not asks:
        logger.warning("[prescout] 갈림길·조사요청이 둘 다 비었다 — 종전 경로로 간다 "
                       "%s@%s", jg.get("away"), jg.get("home"))
        return None
    logger.info("[prescout] %s@%s 갈림길 %d · 변수 %d · 조사요청 %d",
                jg.get("away"), jg.get("home"), len(br), len(out["변수"]),
                len(out["조사요청"]))
    return out


#: 조사요청 상한. 질문이 많을수록 각 답이 얕아지고 콜이 길어진다.
MAX_ASKS = 6

#: 빈손일 때 다시 묻는 횟수(채널당 총 시도). 🔴 실측 2026-09-12:
#   파이프라인에서 "찾지 못함" 이던 질문 5개를 **그대로 다시** 물으니
#   퍼플렉시티가 5/5 답했다 — 질문이 나쁜 게 아니라 채널이 흔들린다.
#     PPLX 같은 질문 3회: 한국어 [4,4,1] · 영어 [4,4,4]
#     Grok 같은 질문 3회: 한국어 [0,0,0] · 영어 [0,2,2] (3회 누적 3/4)
#   ⚠️ **빈손일 때만** 다시 묻는다. 답이 하나라도 있으면 그대로 쓴다 —
#      두 번째 응답이 더 나으리라는 보장이 없다(PPLX 는 4→4→1 이었다).
_ASK_TRIES = 2

#: 위성 참고 목록 상한. 실측 2026-09-11: MLB 경기당 25~62건이 전부 트랜잭션
#  줄이었다. 전량을 실으면 결론 프롬프트의 절반이 무관한 이적 공시가 된다.
MAX_SAT = 15


def _fmt_asks(asks: list[str]) -> str:
    return "\n".join(f"{i}. {q}" for i, q in enumerate(asks, 1))


async def _retrying(fn, jg: dict, asks: list[str], label: str) -> list[dict]:
    """빈손이면 한 번 더 묻는다. 답이 있으면 그대로 쓴다.

    🔴 재시도 횟수를 **로그에 남긴다.** 안 남기면 호출이 왜 두 배인지
       나중에 아무도 모른다.
    """
    rows: list[dict] = []
    for i in range(1, _ASK_TRIES + 1):
        rows = await fn(jg, asks)
        if rows:
            if i > 1:
                logger.info("[reinforce] %s 재시도 %d회차에 %d건 %s@%s",
                            label, i, len(rows), jg.get("away"), jg.get("home"))
            return rows
    logger.info("[reinforce] %s %d회 모두 빈손 %s@%s",
                label, _ASK_TRIES, jg.get("away"), jg.get("home"))
    return rows


async def _ask_pplx(jg: dict, asks: list[str]) -> list[dict]:
    """퍼플렉시티에게 **①이 정한 질문만** 던진다. 실패는 빈 목록."""
    from app.config import get_settings
    from app.engine.prompts import REINFORCE_ASK

    s = get_settings()
    if not getattr(s, "deepsearch_pplx_enabled", False):
        return []
    prompt = REINFORCE_ASK.format(
        today=_today_kst(), league=jg.get("league")
        or (jg.get("sport") or "").upper(),
        away=jg.get("away"), home=jg.get("home"), questions=_fmt_asks(asks))
    try:
        data = await _pplx_findings(prompt, max_tokens=1400)
    except Exception as exc:
        logger.warning("[reinforce] PPLX 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return []
    return _rows(data, asks, "pplx")


async def _ask_grok(jg: dict, asks: list[str]) -> list[dict]:
    """X(그록)에게 같은 질문을 던진다. 실패는 빈 목록.

    ⚠️ `xsearch.fetch_for_game` 을 쓰지 않는다 — 그쪽은 **일반 속보**를 긁는
       경로이고 경기당 1회 캡이 걸려 있다. 여기는 질문이 곧 검색 범위다.
    """
    from app.config import get_settings
    from app.engine.prompts import REINFORCE_ASK

    s = get_settings()
    if s.mock_grok or not getattr(s, "xai_api_key", None):
        return []
    prompt = REINFORCE_ASK.format(
        today=_today_kst(), league=jg.get("league")
        or (jg.get("sport") or "").upper(),
        away=jg.get("away"), home=jg.get("home"), questions=_fmt_asks(asks))
    try:
        from app.research.grok import GrokClient

        text = await GrokClient()._search_call(prompt)
    except Exception as exc:
        logger.warning("[reinforce] X 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return []
    return _rows(_parse_array(text), asks, "x")


def _parse_array(text: str | None):
    """JSON **배열**을 먼저 찾는다.

    🔴 실측 2026-09-11 game=5624: Grok 이 `**[{...},{...}]**` 로 정답 2건을
       돌려줬는데 `parse_json_object` 가 **첫 객체 하나만** 떼어 dict 로 줬고,
       그래서 `_rows` 가 0건을 냈다. 그 함수는 이름대로 "object" 파서다 —
       배열 응답에는 그것을 먼저 쓰면 안 된다.
    """
    import json as _json
    import re as _re

    t = text or ""
    m = _re.search(r"\[.*\]", t, _re.S)
    if m:
        try:
            return _json.loads(m.group(0))
        except Exception:
            pass
    from app.engine.team_form import parse_json_object

    return parse_json_object(t)


def _rows(data, asks: list[str], src: str) -> list[dict]:
    """응답을 `{질문·답·소스·url}` 행으로. **답이 없는 항목은 버린다.**

    🔴 "찾지 못했다"를 답으로 실으면 결론 단계가 그것을 사실로 읽는다.
    """
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # 배열을 못 찾아 객체 하나만 온 경우 — 그 한 줄도 답이다. 버리지 않는다.
        items = next((v for k in ("발견", "답", "items")
                      if isinstance(v := data.get(k), list)), None)
        if items is None:
            items = [data] if (data.get("답") or data.get("사실")) else []
    else:
        items = []
    out: list[dict] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        ans = str(it.get("답") or it.get("사실") or "").strip()
        if not ans:
            continue
        try:
            qno = int(it.get("질문번호"))
        except (TypeError, ValueError):
            qno = 0
        out.append({"질문": asks[qno - 1] if 1 <= qno <= len(asks) else "",
                    "답": ans, "소스": src,
                    # 🔴 언제 있었던 일인가. 실측 2026-09-12: 변수를 묻기
                    #    시작하자 4·6·7월 기사가 오늘 일처럼 돌아왔다.
                    "시점": str(it.get("시점") or "").strip(),
                    "소스유형": str(it.get("소스유형") or "").strip(),
                    "url": str(it.get("url") or "").strip()})
    return out


async def reinforce(jg: dict, pre: dict, redis=None, *,
                    pool=None, timeout: float | None = None) -> dict:
    """② 위성·퍼플렉시티·X 가 **①이 정한 질문만** 보강한다.

    반환 `{"자료": [...], "출처": {...}, "질문": [...]}`.
    ⚠️ **빈 결과도 반환한다** — 0건이라는 사실이 결론 프롬프트에 그대로 실려야
       한다. 조용히 DB 로 돌아가면 앞 단계가 무의미해진 것을 아무도 모른다.
    """
    asks = list(pre.get("조사요청") or [])
    sat = await _free_articles(jg, redis)
    rows: list[dict] = []
    if asks:
        got = await asyncio.gather(
            _retrying(_ask_pplx, jg, asks, "PPLX"),
            _retrying(_ask_grok, jg, asks, "X"),
            return_exceptions=True)
        for g in got:
            if isinstance(g, list):
                rows.extend(g)
        # 🔴 [ORD-7 사용자 지시] **검색이 약한 축은 우리가 긁어 둔 것으로 답한다.**
        #    실측 2026-09-12 game=5633: "텍사스 불펜·마무리 가용"을 두 차례 모두
        #    못 찾았다. 그런데 `pitcher_appearances` 에는 그 기록이 있었다.
        #    ⚠️ 자료9 를 되살리는 것이 아니다 — **①이 물었을 때만** 답한다.
        try:
            from app.collectors import bullpen_usage

            rows.extend(await bullpen_usage.answers(pool, jg, asks))
        except Exception as exc:
            logger.warning("[reinforce] 불펜 기록 조회 실패 — 계속한다: %s", exc)
    # 🔴 위성은 **질문에 답한 것이 아니다.** 오늘 긁어 둔 공시·이적·부상 목록이고,
    #    실측 2026-09-11 game=5624 에서 48건이 전부 트랜잭션 줄이었다. 이것을
    #    "답" 칸에 섞으면 결론이 무관한 48줄을 갈림길의 근거로 읽는다.
    #    **따로, 상한을 걸어, 참고라고 밝혀** 싣는다.
    # 🔴 **최신순으로 자른다.** 실측 2026-09-11 game=5629: 위성 25건 중 7일
    #    이내가 10건이었는데 앞에서 15건을 자르니 그 10건이 통째로 밖으로
    #    밀려났다(MLB 트랜잭션은 시간순이 아니다). 자르는 기준이 순서면
    #    무엇이 남을지는 운이다.
    #    ⚠️ 나이를 모르는 것(`age_h=None`)은 **맨 뒤로 보내되 버리지 않는다** —
    #       "모른다"는 "오래됐다"가 아니다(NPB 가 그렇다).
    _by_age = sorted(sat, key=lambda a: (a.get("age_h") is None,
                                         float(a.get("age_h") or 0.0)))
    for a in _by_age[:MAX_SAT]:
        title = (a.get("title") or "").strip()
        body = (a.get("body") or "").strip()
        # 🔴 실측 2026-09-11: MLB 트랜잭션은 title == body 라 종전 코드가
        #    "X 를 IL 에 올렸다 — X 를 IL 에 올렸다" 를 만들었다. 같은 문장을
        #    두 번 싣는 것은 정보가 아니라 소음이다.
        text = title if (not body or body.startswith(title[:40])) \
            else (f"{title} — {body[:300]}" if title else body[:300])
        rows.append({"질문": "", "답": text, "소스": "satellite",
                     "소스유형": str(a.get("source") or ""),
                     "age_h": a.get("age_h"),
                     "url": str(a.get("url") or "")})
    if len(sat) > MAX_SAT:
        logger.info("[reinforce] 위성 %d건 중 %d건만 싣는다", len(sat), MAX_SAT)
    src: dict = {}
    for r in rows:
        src[r["소스"]] = src.get(r["소스"], 0) + 1
    logger.info("[reinforce] %s@%s 질문 %d · 자료 %d건 %s",
                jg.get("away"), jg.get("home"), len(asks), len(rows), src)
    return {"자료": rows, "출처": src, "질문": asks}


async def investigate(jg: dict, trig: list[str], *, timeout: float | None = None,
                      redis=None):
    """경기 1건 조사. 반환: (결과 dict | None, 검색 사용 수, 소스).

    🔴 [2026-09-06 사용자 지시] **Anthropic 을 부르지 않는다.** 최종 판정이
       아닌 자리에서 나가는 유료 호출을 전부 없앴다. 검색 사용 수는 항상 0 이다.

    ⚠️ 실패·타임아웃이면 (None, 0) — **원판정을 그대로 둔다.** 조사가 안 됐다고
       판정을 흔들지 않는다. 폴백이 곧 "조사 없음"이다.
    """
    import asyncio

    from app.config import get_settings

    s = get_settings()
    sport = jg.get("sport") or ""
    # 🔴 목 모드(FORCE_MOCK·키 없음)에서는 **호출하지 않는다.**
    #    실측 2026-08-31: 배선 직후 테스트 스위트가 api.anthropic.com 을 때려
    #    35초 → 419초가 됐다(P5-2 외부 차단이 잡았다). 판정 경로에 새 외부
    #    호출을 붙일 때는 목 분기를 **같은 커밋에서** 넣어야 한다.
    if s.mock_judge:
        return None, 0, SRC_RSS
    # 🔴 [2026-09-06 사용자 지시] 유료 크레딧 가드를 뗐다. 딥서치는 이제
    #    **무료 사슬 전용**이라 Anthropic 잔액과 무관하다. 남겨 두면 최종
    #    판정이 잔액을 소진한 순간 조사까지 함께 멈춘다 — 실제로 그 형태로
    #    종목이 통째로 멈춘 적이 있다(2026-09-04 16:37 NPB 판정 0건,
    #    2026-09-06 아침 MLB 0/85).
    m = jg.get("matchup") or {}
    prompt = build_prompt(jg, trig)
    # 🔴 [무과금 전환 2b] **검색을 우리가 대신한다.** RSS(무료)로 기사를
    #    먼저 모아 본문까지 붙여 프롬프트의 "검색 결과" 자리에 주입하면,
    #    LLM 은 읽기만 하면 되고 수수료가 0원이 된다.
    #    프롬프트 규칙·조정 상한(±10%p)은 불변이다.
    _meta: dict = {}
    articles = await _free_articles(jg, redis, meta=_meta)
    _origin = _meta.get("origin") or "none"
    _base_n = len(articles)
    source = SRC_RSS
    # 🔴 [DS-3 2026-09-10 사용자 지시] **Perplexity 병행.** 위성/RSS 가 못 물어온
    #    사실을 PPLX 가 직접 웹에서 찾아 재료에 얹는다. 실패하면 빈 리스트라
    #    기존 재료만으로 계속된다(회귀 없음).
    pplx = await _pplx_articles(jg)
    if pplx:
        articles = list(articles) + pplx
        source = SRC_PPLX
    if not articles:
        # 🔴 [2026-09-06 사용자 지시] **유료 web_search 폴백을 삭제했다.**
        #    종전에는 RSS 0건이면 Anthropic `web_search` 도구를 직접 불렀다.
        #    조사는 보강이지 요건이 아니다 — 재료가 없으면 조사하지 않는다.
        logger.info("[deepsearch] RSS 0건 — 조사 생략(유료 검색 안 한다) %s@%s",
                    jg.get("away"), jg.get("home"))
        return None, 0, source
    prompt = _inject_articles(prompt, articles)
    # 🔴 [DSM-1 2026-09-11] **무엇을 몇 건 넣었는지 세어 둔다.**
    #    종전 성과 지표는 `이동_pp` 하나였고, 0.0%p 가 두 가지를 뭉갰다 —
    #    "재료가 쓸모없었다" 와 "재료는 좋았는데 안 썼다". 위성을 고쳐도
    #    나아졌는지 증명할 방법이 없었다(실측 2026-09-11: 4경기 전부 0.0%p).
    #    ⚠️ 시그니처를 늘리지 않는다. 호출부가 둘이라 하나를 빠뜨리기 쉽다.
    _mix = {"satellite": _base_n if _origin == "satellite" else 0,
            "rss": _base_n if _origin == "rss" else 0,
            "pplx": len(pplx)}
    _urls = [(i, (a.get("url") or "")) for i, a in enumerate(articles, 1)]
    # 🔴 역할은 `matchup` 이 **아니다.** `judge_route.chain` 에서 유료가
    #    허용되는 유일한 역할이 matchup(=최종 판정)이라, 여기서 matchup 을
    #    물으면 최종 판정 설정(`JUDGE_PROVIDER=anthropic`)이 그대로 딥서치까지
    #    유료로 끌고 온다 — RSS 가 있어도 무료 우회 조건을 못 넘겼다.
    from app.llm.judge_route import chain as _chain

    _routes = [r for r in _chain(DEEPSEARCH_ROLE) if r[0] != "anthropic"]
    if not _routes:
        logger.error("[deepsearch] 무료 후보가 없다 — 조사 생략한다. "
                     "유료로 되돌아가지 않는다 %s@%s",
                     jg.get("away"), jg.get("home"))
        return None, 0, source
    from app.engine.team_form import _complete_free, parse_json_object

    try:
        body = await asyncio.wait_for(
            _complete_free(_routes, prompt, int(s.deepsearch_max_tokens),
                           DEEPSEARCH_ROLE),
            timeout=timeout if timeout is not None else float(s.deepsearch_timeout_sec))
    except TimeoutError:
        logger.warning("[deepsearch] 타임아웃 — 원판정 유지 %s@%s",
                       jg.get("away"), jg.get("home"))
        return None, 0, source
    except Exception as exc:
        logger.warning("[deepsearch] 예기치 못한 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None, 0, source
    if not body:
        logger.warning("[deepsearch] 무료 경로 실패 — 원판정 유지 %s@%s",
                       jg.get("away"), jg.get("home"))
        return None, 0, source
    # 🔴 `_complete_free` 가 돌려주는 것은 **본문 문자열**이다. 종전 유료
    #    경로는 여기서 JSON 을 파싱해 dict 를 넘겼는데, 무료 경로는 문자열을
    #    그대로 넘기고 있었다 — 호출부(`apply_findings`)는 dict 를 기대한다.
    data = parse_json_object(body)
    if isinstance(data, dict):
        data["_재료"] = {"n": len(articles), "출처": _mix, "urls": _urls}
    if data is None:
        logger.warning("[deepsearch] JSON 파싱 실패 — 원판정 유지 %s@%s "
                       "· %d자: %.300s", jg.get("away"), jg.get("home"),
                       len(body), body.replace("\n", " ")[:300])
        return None, 0, source
    return data, 0, source


#: 배당 오염 탐지어. 조사 결과에 이것이 섞이면 조정을 받지 않는다.
#   🔴 프롬프트 금지만으로는 지켜졌는지 알 수 없다 — 소스 규칙 ②를 코드로
#      집행하는 것과 같은 이유다. 실측 2026-09-01: 프롬프트가 배당을 물어봐
#      조사가 머니라인 내재확률로 p_home 을 내렸고 추천 1건이 탈락했다.
_ODDS_WORDS = ("배당", "머니라인", "스포츠북", "북메이커", "내재확률", "언더독",
               "odds", "moneyline", "sportsbook", "implied", "favorite",
               "-1.5", "+1.5")


def _odds_tainted(text: str | None) -> bool:
    """배당을 근거로 쓴 문장인가."""
    low = (text or "").lower()
    return any(w.lower() in low for w in _ODDS_WORDS)


def strip_odds(data: dict) -> tuple[dict, list[str]]:
    """배당 근거를 걷어낸다. 반환: (정화된 data, 제거 사유 목록).

    🔴 **조정 사유가 배당이면 조정 자체를 받지 않는다.** 근거 문장만 지우고
       숫자를 그대로 반영하면 배당이 p_home 을 움직인 사실은 남는다 —
       증거만 지우고 오염은 남기는 꼴이다.
    """
    if not data:
        return data, []
    dropped = []
    found = [f for f in (data.get("발견") or [])
             if not _odds_tainted(f.get("사실"))]
    if len(found) != len(data.get("발견") or []):
        dropped.append("발견에서 배당 근거 제거")
    out = {**data, "발견": found}
    adj = dict(out.get("조정") or {})
    if _odds_tainted(adj.get("사유")):
        adj.pop("p_home", None)          # 조정 폐기 — 원판정 유지
        dropped.append("조정 사유가 배당 — 조정 폐기")
        out["조정"] = adj
    return out, dropped


def _norm_url(u: str) -> str:
    """호스트+경로만 남긴다. 쿼리·프래그먼트·스킴 차이로 매칭이 깨지지 않게."""
    u = (u or "").strip().lower()
    for pre in ("https://", "http://"):
        if u.startswith(pre):
            u = u[len(pre):]
            break
    u = u.split("#")[0].split("?")[0]
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


def citation_stats(data: dict) -> dict:
    """조사가 **우리가 모아 준 재료를 실제로 썼는가.**

    🔴 [DSM-1 2026-09-11] 종전 성과 지표는 `이동_pp` 하나였다. 0.0%p 가 두
       가지를 뭉갠다 — "재료가 쓸모없었다" 와 "재료는 좋았는데 안 썼다".
       실측 2026-09-11: 4경기 전부 0.0%p · 발견 소스유형 100% 뉴스.
       위성을 고쳐도 나아졌는지 증명할 방법이 없었다.

    두 축으로 센다. **모델 자백만 믿지 않는다**(`_src` 와 같은 태도):
      · `번호` — 모델이 발견마다 적은 `근거번호`
      · `url`  — 우리가 주입 기사 url 과 맞춘 것
    ⚠️ `url` 축은 **하한**이다. 기사를 읽고 썼는데 url 을 안 적거나 다른 것을
       적을 수 있다. 보고할 때 "인용률 ≥ x%" 로만 읽어야 한다.
    """
    mat = (data or {}).get("_재료") or {}
    urls = {_norm_url(u): i for i, u in (mat.get("urls") or []) if u}
    n_in = int(mat.get("n") or 0)
    by_no: set[int] = set()
    by_url: set[int] = set()
    cited = 0
    for f in ((data or {}).get("발견") or []):
        if not isinstance(f, dict):
            continue
        hit = False
        no = f.get("근거번호")
        if isinstance(no, int) and 1 <= no <= n_in:
            by_no.add(no)
            hit = True
        i = urls.get(_norm_url(f.get("url") or ""))
        if i:
            by_url.add(i)
            hit = True
        if hit:
            cited += 1
    used = by_no | by_url
    return {"주입": n_in, "출처": mat.get("출처") or {},
            "인용_발견": cited, "인용_기사": len(used),
            "축": {"번호": len(by_no), "url": len(by_url)},
            "인용률": round(len(used) / n_in, 3) if n_in else None}


def apply_findings(jg: dict, data: dict) -> dict:
    """조사 결과를 판정에 반영. 상한·방향은 코드가 강제한다.

    ⚠️ 소스 규칙 ②(단일 기사면 조정 절반)를 **코드로도 집행한다.** 프롬프트에
       적어 두는 것만으로는 지켜졌는지 알 수 없다.
    """
    m = jg.get("matchup") or {}
    p_before = jg.get("p_claude")
    # [DSM-1] 계측을 **먼저** 뽑고 원본에서 뗀다. `strip_odds` 가 사본을
    #   돌려주므로 그 뒤에 떼면 호출부의 dict 에 내부 키가 남는다.
    stats = citation_stats(data)
    if isinstance(data, dict):
        data.pop("_재료", None)
    # 🔴 배당이 판정 숫자를 움직이지 않는다 — 조정을 반영하기 **전에** 거른다.
    data, dropped = strip_odds(data)
    if dropped:
        logger.warning("[deepsearch] 배당 오염 차단 %s@%s: %s",
                       jg.get("away"), jg.get("home"), " · ".join(dropped))
    adj = (data or {}).get("조정") or {}
    if p_before is None:
        # 판정이 없어도 **재료는 들어갔다.** 그 사실을 버리지 않는다.
        jg["deepsearch"] = {"재료": stats, "발견": [],
                            "요약": None, "조정_사유": None, "단일기사": False,
                            "이동_pp": 0.0, "상한_적용": None}
        return {"moved": 0.0, "note": None}
    p_before = float(p_before)
    # 🔴 [MKT-8] 요약기는 **부호 있는 %p 증감(delta_pp)** 을 낸다 — 절대 p_home 은
    #    절대/증분 모호(세이부 4783: 0.03 이 극단 원정으로 오해돼 반대로 클램프)라
    #    폐기했다. delta_pp 가 없으면 옛 절대 p_home 으로 폴백(하위호환).
    dpp = adj.get("delta_pp")
    if dpp is not None:
        try:
            p_after = p_before + float(dpp) / 100.0
        except (TypeError, ValueError):
            p_after = None
    else:
        pa = adj.get("p_home")
        p_after = float(pa) if pa is not None else None
    if p_after is None:
        return {"moved": 0.0, "note": None}
    if adj.get("단일기사여부"):
        p_after = p_before + (float(p_after) - p_before) / 2
    # [DS-14] 근거를 함께 넘겨야 뒤집기 권한이 열린다. 안 넘기면 종전대로 막힌다.
    p, note = clamp_adjustment(p_before, p_after, m.get("우세"),
                               evidence=(data or {}).get("발견") or [])
    jg["p_claude"] = p
    m["p_home"] = p
    jg["deepsearch"] = {
        "재료": stats,
        "발견": (data or {}).get("발견") or [],
        "요약": (data or {}).get("요약"),
        "조정_사유": adj.get("사유"),
        "단일기사": bool(adj.get("단일기사여부")),
        "이동_pp": round((p - p_before) * 100, 1),
        "상한_적용": note,
    }
    if abs(p - p_before) > 1e-9 or (data or {}).get("요약"):
        jg.setdefault("breaking_changes", []).append(
            "🔍 추가 조사 반영: " + str((data or {}).get("요약") or "새 사실 없음"))
    return {"moved": round((p - p_before) * 100, 1), "note": note}


# ---------------------------------------------------------------- 슬레이트 실행

def blind_starters(jg: dict) -> dict:
    """오늘 선발 중 **자료가 없는 쪽**을 센다. 딥서치 우선순위에 쓴다.

    🔴 종전 순서는 트리거 개수뿐이었다. 그래서 **조사가 가장 필요한 경기가
       상한에 밀렸다.** 실측 2026-09-01 NPB: 6경기 전부 후보인데 상한은 1건
       (슬레이트 6 × 30%)이었고, 순서가 트리거 수로 정해져 자료가 통째로
       없는 요미우리전이 뒤로 갔다.
         戸郷 翔征  1군 등판 0 — 7/7 햄스트링 이탈, 8/26 2군 복귀전이 전부
         高野 脩汰  선발 0 (올해 26경기 전부 중계, 오늘이 시즌 첫 선발)
       이런 경기는 크롤 데이터로 답이 안 나온다. 웹 검색이 유일한 수단이다.

    ⚠️ 새 임계값을 만들지 않는다 — `MIN_STARTS`(표본 하한)를 그대로 쓴다.
    반환: {"score": int, "zero": [side], "low": [side]}
      score 3 = 선발·구원 둘 다 0 (완전 무자료)
      score 2 = 선발 0 · 구원 있음
      score 1 = 선발 <= MIN_STARTS
    """
    r = jg.get("research") or {}
    zero, low, score = [], [], 0
    for side in ("home", "away"):
        n_start = len(r.get(f"{side}_starter_recent") or [])
        n_relief = len(r.get(f"{side}_starter_relief") or [])
        if n_start == 0 and n_relief == 0:
            zero.append(side)
            score += 3
        elif n_start == 0:
            zero.append(side)
            score += 2
        elif n_start <= _min_starts():
            low.append(side)
            score += 1
    return {"score": score, "zero": zero, "low": low}


def _min_starts() -> int:
    """표본 하한. 순환 import 를 피해 지연 조회한다."""
    from app.engine.starter_recent import MIN_STARTS

    return MIN_STARTS


async def run_for_slate(games: list[dict], redis, date: str, *,
                        settings=None, max_investigations: int | None = None,
                        prev_lineups: dict | None = None) -> dict:
    """슬레이트 전체에 대해 트리거 판별 → 상한 안에서 조사 → 반영.

    상한이 **슬레이트 단위**라 경기별로 호출하면 강제할 수 없다.

    ⚠️ 조사는 경기당 1회다. 여러 트리거가 걸려도 한 번만 부른다.
    ⚠️ 한 경기 실패가 나머지를 막지 않는다.
    ⚠️ `max_investigations`는 드라이런에서 실검색을 더 조이기 위한 것이다
       (예: 2건). 운영에서는 None으로 두고 daily_cap 만 쓴다.

    반환: {"candidates": [...], "investigated": n, "searches": n, "skipped": n}
    """
    from app.config import get_settings

    s = settings or get_settings()
    # 🔴 [DS-5] 상한 기준은 **그날 총 경기 수**다. 지금 슬레이트로 재면 경기가
    #    시작될수록 상한이 줄어 낮·저녁 조사가 통째로 막힌다(실측 2026-09-10).
    _sport0 = (games[0].get("sport") if games else "") or ""
    cap = daily_cap(await remember_day_size(redis, _sport0, date, len(games)), s)
    if max_investigations is not None:
        cap = min(cap, max_investigations)
    # 🔴 **예산은 하나다.** 종전에는 1차 판정(run_for_slate)이 로컬 카운터만
    #    쓰고, 재판정(run_for_rejudge)은 Redis 카운터만 써서 **서로를 못 봤다.**
    #    같은 슬레이트에서 1차 3건 + 재판정 3건 = 6건이 되어 상한 30%가
    #    사실상 60%로 벌어진다. 둘 다 같은 Redis 키를 읽고 쓴다.
    count_key = SLATE_COUNT_KEY.format(
        sport=(games[0].get("sport") if games else "") or "", date=date)
    used0 = int(await _get(redis, count_key) or 0)
    remaining = max(0, cap - used0)
    out = {"candidates": [], "investigated": 0, "searches": 0, "skipped": 0,
           "cap": cap, "used_before": used0, "slate": len(games)}
    for jg in games:
        trig = triggers(jg, s, prev_lineup=(prev_lineups or {}).get(jg.get("game_id")))
        if not trig:
            continue
        out["candidates"].append({"game_id": jg.get("game_id"),
                                  "match": f"{jg.get('away')}@{jg.get('home')}",
                                  "triggers": trig,
                                  "blind": blind_starters(jg)})
    # 발동 순서: **자료가 가장 없는 경기부터.** 상한은 그대로다 — 순서만 바꾼다.
    #   트리거 수만으로 줄을 세우면, 조사가 가장 필요한 경기가 상한에 밀린다.
    ranked = sorted(out["candidates"],
                    key=lambda c: (-c["blind"]["score"], -len(c["triggers"])))
    by_id = {jg.get("game_id"): jg for jg in games}
    if not getattr(s, "deepsearch_investigate", False):
        # [A안 2026-08-31] 조사 호출은 꺼두고 **트리거 판별만** 실전에 태운다.
        #   어떤 경기가 조사 대상이 되는지 먼저 관찰한다. 작동하지 않는 호출에
        #   경기당 90초를 태우지 않는다(web_search 도구 미확인).
        out["disabled"] = True
        if out["candidates"]:
            logger.info("[deepsearch] 조사 비활성(DEEPSEARCH_ENABLED=false) — "
                        "트리거만 판별: 슬레이트 %d · 후보 %d · 상한 %d · %s",
                        out["slate"], len(out["candidates"]), cap,
                        "; ".join(
                            f"{c['match']}({','.join(c['triggers'])}"
                            + (f",무자료:{','.join(c['blind']['zero'])}"
                               if c["blind"]["zero"] else "") + ")"
                            for c in ranked))
        return out
    # 🔴 [DS-7 2026-09-10] **조사를 동시에 돌린다.** 실측: 전 경기 조사(DS-3)로
    #    프리페치가 13분 32초가 됐고 "W-SEND-PENDING 3경기 — 발송 창인데 카드가
    #    없다" 경보가 떴다. 조사는 대부분 외부 I/O 대기라 순차로 돌 이유가 없다.
    #    ⚠️ **조사만 병렬이다.** apply_findings·카운터·기록은 아래에서 원래
    #       순서대로 직렬 처리한다 — 동시에 하면 상한을 넘고 순위가 무의미해진다.
    #    ⚠️ 동시성은 제한한다. 무료 LLM 은 레이트리밋(groq TPD)이 있고, 한꺼번에
    #       쏟으면 그 한도에 더 빨리 닿는다.
    import asyncio as _aio

    todo = [c for c in ranked[:remaining] if by_id.get(c["game_id"]) is not None]
    out["skipped"] = max(0, len(ranked) - len(todo))
    _sem = _aio.Semaphore(max(1, int(getattr(s, "deepsearch_concurrency", 4))))

    async def _one(c):
        async with _sem:
            try:
                return await investigate(by_id[c["game_id"]], c["triggers"],
                                         redis=redis)
            except Exception as exc:   # 한 경기 실패가 나머지를 막지 않는다
                logger.warning("[deepsearch] 조사 실패 %s: %s", c["match"], exc)
                return None, 0, None

    results = await _aio.gather(*[_one(c) for c in todo]) if todo else []

    for c, (data, used, src) in zip(todo, results):
        jg = by_id.get(c["game_id"])
        out["searches"] += used
        if data is None:
            continue
        res = apply_findings(jg, data)
        out["investigated"] += 1
        c["moved_pp"] = res["moved"]
        await _incr(redis, count_key, CACHE_TTL)      # 재판정과 같은 예산
        if redis is not None:
            try:
                await redis.set(
                    CACHE_KEY.format(league=jg.get("league") or jg.get("sport"),
                                     game_id=jg.get("game_id"), date=date),
                    json.dumps({"triggers": c["triggers"], **(jg.get("deepsearch") or {})},
                               ensure_ascii=False, default=str), ex=CACHE_TTL)
            except Exception as exc:
                logger.warning("[deepsearch] 기록 실패 %s: %s", c["match"], exc)
        # [DSM-1] 재료가 **쓰였는지**를 같은 줄에 남긴다. 이동 0.0%p 만으로는
        #   "재료가 없었다" 와 "있었는데 안 썼다" 를 구분할 수 없다.
        _m = (jg.get("deepsearch") or {}).get("재료") or {}
        c["재료"] = _m
        logger.info("[deepsearch] %s 트리거=%s 검색=%d 이동=%+.1f%%p "
                    "재료=%s(%s) 인용=%s (번호%s·url%s)",
                    c["match"], ",".join(c["triggers"]), used, res["moved"],
                    _m.get("주입"),
                    ",".join(f"{k}{v}" for k, v in (_m.get("출처") or {}).items() if v)
                    or "없음",
                    _m.get("인용_기사"),
                    (_m.get("축") or {}).get("번호"), (_m.get("축") or {}).get("url"))
    # [DSM-1] 슬레이트 합계 — **이것이 위성 개선의 채점표다.**
    _inj = sum((c.get("재료") or {}).get("주입") or 0 for c in out["candidates"])
    _cit = sum((c.get("재료") or {}).get("인용_기사") or 0 for c in out["candidates"])
    out["재료_주입"], out["재료_인용"] = _inj, _cit
    out["인용률"] = round(_cit / _inj, 3) if _inj else None
    if out["candidates"]:
        logger.info("[deepsearch] 슬레이트 %d경기 · 후보 %d · 조사 %d "
                    "· 예산 %d/%d(이전 %d) · 검색 %d · 상한초과 생략 %d "
                    "· 재료 %d건 중 인용 %d건(%s)",
                    out["slate"], len(out["candidates"]), out["investigated"],
                    used0 + out["investigated"], cap, used0,
                    out["searches"], out["skipped"], _inj, _cit,
                    f"{out['인용률']:.0%}" if out["인용률"] is not None else "—")
    return out

# ---------------------------------------------------------------- 재판정 경로

#: 재판정 딥서치 중복 방지 — 같은 (경기, 라인업)이면 다시 조사하지 않는다.
REJUDGE_KEY = "deepsearch:rejudge:{game_id}:{sig}"
#: 슬레이트 단위 발동 카운터. 재판정 경로도 **같은 상한을 쓴다.**
SLATE_COUNT_KEY = "deepsearch:count:{sport}:{date}"


def first_lineup_evidence(jg: dict, prev_lineup: dict | None) -> bool:
    """[T6] **라인업 최초 확정**인가. 변동이 아니라 발표가 방아쇠다.

    🔴 사용자 지시 2026-09-02: "라인업이 발표되면 딥서치 바로 시작해야 한다 —
       라인업 변동이 아니라." 종전 T4·T5 는 직전 대비 차이만 봤고, 최초 공시는
       비교 대상이 없어 **아무것도 안 걸렸다.** 타순이 나온 그 순간이 가장
       정보가 많은데 조사를 건너뛰고 있었다.

    조건: 지금 타순이 **확정**이고, 직전에 본 타순이 없다.
    ⚠️ 확정이 아니면(잠정·미공시) 발동하지 않는다 — 예상 타순으로 조사하면
       그 조사가 예상에 매달린다.
    ⚠️ 중복은 `(game_id, 라인업 서명)` 키가 막는다. 같은 타순으로 두 번
       조사하지 않는다.
    """
    if (jg.get("lineup_status") or "") != "confirmed":
        return False
    # 🔴 [2026-09-04] 종전에는 `research[f"{side}_lineup"]` 이 **dict 라고
    #    가정**하고 `.get("order")` 를 불렀다. KBO·NPB 는 크롤러가 준 타순을
    #    **문자열**("홍창기-신민재-…")로 담는다 — 그래서 라인업이 확정될
    #    때마다 `AttributeError: 'str' object has no attribute 'get'` 가 나고,
    #    호출부의 넓은 except 가 그것을 삼켰다:
    #      [pipeline] 재판정 딥서치 생략 — 판정은 계속: 'str' object has no …
    #    결과: **T4·T5·T6 가 야구에서 통째로 죽어 있었다.** 딥서치가 꺼져 있어도
    #    "어떤 경기가 걸리는가"를 관찰하는 것이 이 단계의 목적인데 그 관찰이
    #    한 건도 남지 않았다(실측 2026-09-04 KBO 저녁 슬레이트, 재판정 8건 전부).
    #    ⚠️ 같은 실수가 이 파일에 이미 한 번 기록돼 있다(`_lineup_of` 주석,
    #       2026-09-01 "키가 어긋나 T5 가 한 번도 발동하지 않았다"). 그때는
    #       `_lineup_of` 만 고쳤고 여기는 안 고쳤다.
    #    → **모양을 아는 곳은 한 군데뿐이어야 한다.** `_lineup_of`+`_names` 를
    #       재사용한다. 여기에 모양 분기를 다시 적으면 그것이 다음 사본이다.
    if not any(_names(_lineup_of(jg, side)) for side in ("home", "away")):
        return False
    # ⚠️ `prev_lineup` 은 **껍데기가 항상 온다** — `{"research": {"home_lineup": {},
    #    "away_lineup": {}}}`. dict 가 truthy 라고 "직전이 있다"로 읽으면
    #    T6 가 영원히 안 걸린다. **안에 실제 타순이 있는지**를 봐야 한다.
    prev_has = any(_names(_lineup_of(prev_lineup or {}, side))
                   for side in ("home", "away"))
    return not prev_has              # 직전 타순이 있으면 '변동'이라 T4·T5 소관


async def run_for_rejudge(jg: dict, redis, date: str, *, lineup_sig: str,
                          slate_size: int, prev_lineup: dict | None = None,
                          settings=None) -> dict:
    """[v1.1 6단계] 라인업 재판정 경로의 딥서치. **T4·T5 에만 반응한다.**

    🔴 실측 2026-09-01: `rejudge_after_lineup` 이 `run_for_slate` 를 부르지
       않아 T4(선발 변경)·T5(라인업 이상)가 **실전에서 발동할 경로가 아예
       없었다.** 라인업이 바뀌었을 때 조사하라고 만든 트리거인데 정작
       라인업 재판정에 연결이 없었다.

    ⚠️ 폴링 주기마다 태우는 force 방식은 쓰지 않는다 — 5분마다 크레딧을
       태울 수는 없다. 그래서 세 겹으로 조인다:
       ① T4·T5 가 걸린 경기만 (T1·T3 는 1차 판정에서 이미 봤다)
       ② 같은 (game_id, 라인업 서명) 조합당 **1회**
       ③ 슬레이트 상한(30%)을 재판정 경로에서도 **같이** 센다

    ⚠️ `DEEPSEARCH_ENABLED=false` 면 조사하지 않되 **판별·기록·로그는 남긴다.**
       어떤 경기가 T4·T5 로 걸리는지 관찰하는 것이 이 단계의 목적이다.

    반환: {"triggered", "triggers", "status", "searches", "moved_pp"}
      status: None(미발동) | "investigated" | "deduped" | "capped"
              | "disabled" | "failed"
    """
    from app.config import get_settings

    s = settings or get_settings()
    out = {"triggered": False, "triggers": [], "status": None,
           "searches": 0, "moved_pp": 0.0, "source": None}
    t4_hit, t4_src = t4_evidence(jg)
    t5_hit, t5_src = t5_evidence(jg, prev_lineup)
    t6_hit = first_lineup_evidence(jg, prev_lineup)
    trig, srcs = [], []
    if t6_hit:
        trig.append(T6_FIRST_LINEUP)
        srcs.append(SRC_FACT)        # 공시는 사실이다 — 모델 자백이 아니다
    if t4_hit:
        trig.append(T4_STARTER)
        srcs.append(t4_src)
    if t5_hit:
        trig.append(T5_LINEUP)
        srcs.append(t5_src)
    # 🔴 [DS-6 2026-09-10 사용자 지시] **재판정 수정 카드에도 딥서치를 붙인다.**
    #    실측(HOU@PHI): 타순만 바뀌자 T4/T5/T6 이 전부 미해당이라 조사가 통째로
    #    생략됐다("발동=False 트리거=-"). 상한은 여유가 있었다(13/15) — 원인은
    #    이 경로가 `triggers()` 를 부르지 않아 DS-3 의 T0_전수가 안 닿은 것이다.
    #    조사는 판정과 별개다. 라인업이 확정되는 시점이 정보가 가장 많다.
    #    ⚠️ 중복은 그대로 `(game_id, 라인업 서명)` 키가 막는다 — 5분 폴링이
    #       같은 라인업으로 반복해도 조사는 1회다.
    if not trig:
        trig.append(T0_ALL)
        srcs.append(SRC_FACT)
    out["triggered"] = True
    out["triggers"] = trig
    # 근거 출처를 남긴다 — 모델 자백으로 걸린 건과 사실로 걸린 건은
    # 나중에 트리거를 손볼 때 완전히 다른 데이터다.
    out["source"] = srcs[0] if len(set(srcs)) == 1 else SRC_BOTH
    gid = jg.get("game_id")
    sport = jg.get("sport") or ""
    dedupe_key = REJUDGE_KEY.format(game_id=gid, sig=_sig_hash(lineup_sig))
    count_key = SLATE_COUNT_KEY.format(sport=sport, date=date)

    if redis is not None and await _get(redis, dedupe_key):
        out["status"] = "deduped"
        logger.info("[deepsearch] 재판정 중복 생략 game=%s 트리거=%s source=%s",
                    gid, ",".join(trig), out["source"])
        _record(jg, out)
        return out

    # 🔴 [DS-5] 재판정도 같은 기준이다 — **수정 카드에 딥서치가 붙으려면**
    #    상한이 하루 내내 안정적이어야 한다(사용자 지시 2026-09-10).
    cap = daily_cap(await remember_day_size(redis, sport, date, slate_size), s)
    used = int(await _get(redis, count_key) or 0)
    # 🔴 [사용자 지시 2026-09-02] **T6 는 상한에 막지 않는다.**
    #    슬레이트 30% 상한은 `web_search` **검색 수수료** 때문에 걸었던 것이다.
    #    무과금 전환으로 조사가 RSS(무료)로 도니 그 근거가 사라졌다 —
    #    남는 비용은 경기당 Sonnet 1콜뿐이다.
    #    "라인업이 발표되면 딥서치 바로 시작해야 한다"는 지시는 전 경기를
    #    뜻하고, 5경기 슬레이트에서 상한 1은 그 지시를 무력화한다.
    #    ⚠️ 중복 방지는 그대로다 — `(game_id, 라인업 서명)` 당 1회.
    #       이걸 풀면 5분 폴링마다 Sonnet 을 태운다.
    if T6_FIRST_LINEUP in trig:
        logger.info("[deepsearch] T6 최초확정 — 상한 면제 game=%s (사용 %d/%d)",
                    gid, used, cap)
    elif used >= cap:
        out["status"] = "capped"
        logger.info("[deepsearch] 재판정 상한 도달 game=%s 트리거=%s source=%s "
                    "사용 %d/%d — 조사하지 않음", gid, ",".join(trig),
                    out["source"], used, cap)
        _record(jg, out)
        return out

    if not getattr(s, "deepsearch_investigate", False):
        out["status"] = "disabled"
        # 🔴 **would_have_searched 를 남긴다.** 플래그가 꺼져 있어도 어떤
        #    경기가 조사 대상이 되는지는 관찰 데이터로 쌓여야 한다.
        logger.info("[deepsearch] 재판정 트리거 발동(조사 비활성) game=%s "
                    "트리거=%s source=%s would_have_searched=%d 상한 %d/%d",
                    gid, ",".join(trig), out["source"],
                    int(s.deepsearch_max_searches), used, cap)
        _record(jg, out)
        return out

    try:
        data, searched, src = await investigate(jg, trig, redis=redis)
    except Exception as exc:                 # 조사 실패가 재판정을 막지 않는다
        out["status"] = "failed"
        logger.warning("[deepsearch] 재판정 조사 실패 game=%s: %s", gid, exc)
        _record(jg, out)
        return out
    out["searches"] = searched               # usage.server_tool_use 기준(investigate)
    if data is None:
        out["status"] = "failed"
        _record(jg, out)
        return out
    res = apply_findings(jg, data)
    out["status"] = "investigated"
    out["moved_pp"] = res["moved"]
    if redis is not None:
        await _setex(redis, dedupe_key, "1", CACHE_TTL)
        await _incr(redis, count_key, CACHE_TTL)
    # 🔴 `source` 는 **트리거 출처**(모델 자백 vs 폴러 사실)다. 검색 재료가
    #    어디서 왔는지는 다른 축이라 칸을 따로 둔다 — 무과금 전환이 실제로
    #    돌고 있는지 이 값으로만 확인된다.
    out["search_source"] = src
    out["paid_search"] = searched
    logger.info("[deepsearch] 재판정 조사 game=%s 트리거=%s source=%s "
                "search_source=%s 유료검색=%d 이동=%+.1f%%p 상한 %d/%d",
                gid, ",".join(trig), out["source"], src, searched,
                res["moved"], used + 1, cap)
    _record(jg, out)
    return out


def _record(jg: dict, out: dict) -> None:
    """판별 결과를 경기에 남긴다 — 관찰 데이터는 로그만으로 부족하다."""
    jg["deepsearch_trigger"] = {"trigger_fired": out["triggered"],
                                "triggers": out["triggers"],
                                "source": out.get("source"),
                                "deepsearch": out["status"],
                                "searches": out["searches"]}


def _sig_hash(sig: str) -> str:
    import hashlib

    return hashlib.sha1((sig or "").encode("utf-8")).hexdigest()[:16]


async def _get(redis, key):
    if redis is None:
        return None
    try:
        return await redis.get(key)
    except Exception:
        return None


async def _setex(redis, key, val, ttl) -> None:
    try:
        await redis.set(key, val, ex=ttl)
    except Exception as exc:
        logger.warning("[deepsearch] 중복키 기록 실패 %s: %s", key, exc)


async def _incr(redis, key, ttl) -> None:
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, ttl)
    except Exception as exc:
        logger.warning("[deepsearch] 카운터 증가 실패 %s: %s", key, exc)
