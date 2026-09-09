"""[v1.1 6단계] 트리거형 딥서치 — 판정이 막힌 경기만 스스로 조사한다.

**전 경기 상시 검색 금지.** 비용·외부 의존이 걸린 최고위험 단계라 상한을
세 겹으로 둔다: 트리거(발동 조건) · 경기당 검색 수 · 하루 발동 비율.

**야구·축구 공통이다.** 종목 분기 없이 하나의 모듈이 양쪽 판정 경로에 붙는다.
언어만 종목별로 다르다 — 원문 소스가 그 언어로 쓰여 있기 때문이다.

⚠️ 검색 결과는 **크롤 정형 데이터보다 낮은 신뢰 등급**이다. 조정은 ±4%p로
   묶고 우세 방향은 단독으로 뒤집지 못한다. 이 두 가지는 프롬프트 지시가
   아니라 **코드가 강제**한다 — 모델이 규칙을 어겨도 값이 새어 나가지 않게.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 확률 조정 상한. 클리핑과 같은 방식으로 코드가 강제한다.
ADJUST_CAP_PP = 4.0

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

def daily_cap(slate_size: int, settings) -> int:
    """하루 발동 상한 = 슬레이트의 N%. 최소 1건은 허용한다.

    슬레이트가 3경기인 날 30%면 0.9라 아무것도 조사 못 한다 — 경계 경기가
    있어도 손을 놓는 것은 이 단계의 취지가 아니다.
    """
    if slate_size <= 0:
        return 0
    return max(1, int(slate_size * float(settings.deepsearch_daily_cap)))


def clamp_adjustment(p_before: float, p_after: float | None,
                     favored: str | None) -> tuple[float, str | None]:
    """조정 ±4%p 상한 + 우세 방향 단독 뒤집기 금지. **코드가 강제한다.**

    반환: (적용할 p, 사람이 읽는 사유 or None)

    ⚠️ 프롬프트에 적는 것만으로는 부족하다. 모델이 규칙을 어겨도 값이 새어
       나가지 않아야 한다 — 클리핑과 같은 태도다.
    """
    if p_after is None:
        return p_before, None
    lo, hi = p_before - ADJUST_CAP_PP / 100, p_before + ADJUST_CAP_PP / 100
    p = max(lo, min(hi, float(p_after)))
    note = None
    if abs(float(p_after) - p) > 1e-9:
        note = f"조정 상한 ±{ADJUST_CAP_PP:g}%p 적용 ({p_after:.3f}→{p:.3f})"
    # 우세 방향이 뒤집히면 되돌린다 — 검색 결과 단독으로는 방향을 못 바꾼다.
    if favored == "home" and p_before >= 0.5 > p:
        p, note = 0.5, "우세 방향 단독 뒤집기 금지 — 0.50에서 멈춤"
    elif favored == "away" and p_before <= 0.5 < p:
        p, note = 0.5, "우세 방향 단독 뒤집기 금지 — 0.50에서 멈춤"
    return round(p, 4), note


# ---------------------------------------------------------------- 조사 엔진

PROMPT = """당신은 스포츠 경기 조사원이다. 아래 판정이 확신을 세우지 못한
지점만 조사한다. 판정을 처음부터 다시 하지 않는다.

[경기] {league} · {away} (원정) @ {home} (홈) · {kickoff} KST
[현재 판정] {verdict}
[발동 트리거] {triggers}{divergence}
[판정이 요청한 추가확인] {asked}

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
- 확률 조정은 **±4%p 이내**. 우세 방향을 검색 결과 단독으로 뒤집지 않는다.
- 조사해도 새 사실이 없으면 **조정 0**으로 두고 그렇게 적는다. 억지로 움직이지 마라.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{
  "발견": [{{"사실": "1문장", "소스유형": "공식|기록|뉴스", "url": "..."}}],
  "조정": {{"p_home": 0.00, "사유": "1문장", "단일기사여부": true|false}},
  "요약": "카드에 실을 1문장"
}}"""


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
#: 🔴 딥서치의 라우팅 역할. **`matchup` 이 아니다** — matchup 만 유료가
#   허용되고, 딥서치는 최종 판정이 아니다. 문자열을 호출부마다 적지 않는다.
DEEPSEARCH_ROLE = "deepsearch"

PAID_KEY = "deepsearch:paid:{date}"
#: 본문을 붙일 기사 수. 많이 넣으면 프롬프트만 부풀고 판단은 안 나아진다.
FETCH_TOP_N = 4
FETCH_CHARS = 1200


async def _free_articles(jg: dict, redis) -> list[dict]:
    """RSS 기사 + 상위 N건 본문. 실패하면 빈 목록(→ 유료 폴백 판단)."""
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
    return items


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
       ±4%p, 우세 뒤집기 금지, 신뢰 등급은 그대로다.
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
    #    프롬프트 규칙·조정 상한(±4%p)은 불변이다.
    articles = await _free_articles(jg, redis)
    source = SRC_RSS
    if not articles:
        # 🔴 [2026-09-06 사용자 지시] **유료 web_search 폴백을 삭제했다.**
        #    종전에는 RSS 0건이면 Anthropic `web_search` 도구를 직접 불렀다.
        #    조사는 보강이지 요건이 아니다 — 재료가 없으면 조사하지 않는다.
        logger.info("[deepsearch] RSS 0건 — 조사 생략(유료 검색 안 한다) %s@%s",
                    jg.get("away"), jg.get("home"))
        return None, 0, source
    prompt = _inject_articles(prompt, articles)
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


def apply_findings(jg: dict, data: dict) -> dict:
    """조사 결과를 판정에 반영. 상한·방향은 코드가 강제한다.

    ⚠️ 소스 규칙 ②(단일 기사면 조정 절반)를 **코드로도 집행한다.** 프롬프트에
       적어 두는 것만으로는 지켜졌는지 알 수 없다.
    """
    m = jg.get("matchup") or {}
    p_before = jg.get("p_claude")
    # 🔴 배당이 판정 숫자를 움직이지 않는다 — 조정을 반영하기 **전에** 거른다.
    data, dropped = strip_odds(data)
    if dropped:
        logger.warning("[deepsearch] 배당 오염 차단 %s@%s: %s",
                       jg.get("away"), jg.get("home"), " · ".join(dropped))
    adj = (data or {}).get("조정") or {}
    p_after = adj.get("p_home")
    if p_before is None or p_after is None:
        return {"moved": 0.0, "note": None}
    p_before = float(p_before)
    if adj.get("단일기사여부"):
        p_after = p_before + (float(p_after) - p_before) / 2
    p, note = clamp_adjustment(p_before, p_after, m.get("우세"))
    jg["p_claude"] = p
    m["p_home"] = p
    jg["deepsearch"] = {
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
    cap = daily_cap(len(games), s)
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
    for c in ranked:
        if out["investigated"] >= remaining:
            out["skipped"] += 1
            continue
        jg = by_id.get(c["game_id"])
        if jg is None:
            continue
        try:
            data, used, src = await investigate(jg, c["triggers"], redis=redis)
        except Exception as exc:              # 한 경기 실패가 나머지를 막지 않는다
            logger.warning("[deepsearch] 조사 실패 %s: %s", c["match"], exc)
            continue
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
        logger.info("[deepsearch] %s 트리거=%s 검색=%d 이동=%+.1f%%p",
                    c["match"], ",".join(c["triggers"]), used, res["moved"])
    if out["candidates"]:
        logger.info("[deepsearch] 슬레이트 %d경기 · 후보 %d · 조사 %d "
                    "· 예산 %d/%d(이전 %d) · 검색 %d · 상한초과 생략 %d",
                    out["slate"], len(out["candidates"]), out["investigated"],
                    used0 + out["investigated"], cap, used0,
                    out["searches"], out["skipped"])
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
    if not trig:
        return out
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

    cap = daily_cap(slate_size, s)
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
