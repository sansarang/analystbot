"""야구 텔레그램 카드 — 매치업 JSON만 매핑. 없는 칸을 만들지 않는다."""
from __future__ import annotations

from app.config import get_settings


def _team(name: str) -> str:
    from app.bot.aliases import kr_team

    return kr_team(name or "?")


def _park(jg: dict) -> str:
    r = jg.get("research") or {}
    for v in (jg.get("stadium"), jg.get("venue"), r.get("park"), r.get("stadium")):
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and (v.get("name") or v.get("park")):
            return str(v.get("name") or v.get("park")).strip()
    return ""


def favored_side_and_p(jg: dict) -> tuple[str | None, float | None]:
    """우세 사이드와 그 승률. p_home 기반. 없으면 (None, None)."""
    m = jg.get("matchup") or {}
    p = m.get("p_home")
    if p is None:
        p = jg.get("p_claude")
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None, None
    side = m.get("우세")
    if side == "away":
        return "away", 1.0 - p
    if side == "home":
        return "home", p
    if side == "박빙":
        return "home" if p >= 0.5 else "away", p if p >= 0.5 else 1.0 - p
    if p >= 0.5:
        return "home", p
    return "away", 1.0 - p


def traffic_light(p: float | None, settings=None) -> str:
    """표시 전용. 추천 게이트가 아니다."""
    s = settings or get_settings()
    if p is None:
        return "⚪"
    if p >= s.signal_green_prob:
        return "🟢"
    if p >= s.min_win_prob:
        return "🟡"
    return "🔴"


def rec_label(jg: dict, settings=None) -> str:
    s = settings or get_settings()
    sport = jg.get("sport") or ""
    if sport == "npb" and not s.npb_last3_verified:
        return "NPB: 참고용"
    if jg.get("form_unavailable") or jg.get("judgement_void"):
        return "보드만"
    from app.collectors.lineups import pick_state as _ps

    state = jg.get("pick_state")
    if state is None:
        state = _ps(jg.get("lineup_status"))[0]
    if state != "final":
        return "보드만"
    if jg.get("judge_confidence") == "low" or jg.get("judge_pass"):
        return "보드만"
    # [A 2026-09-01] 오늘 선발의 최근 등판이 1경기 이하면 추천하지 않는다.
    #   🔴 이 규칙은 `pipeline.qualifies()` 에만 있었고 **카드 경로에는 없었다.**
    #      게이트가 둘로 갈려, 사용자가 받는 카드는 느슨한 쪽이었다.
    #      실사고 2026-09-05: NC 카드가 근거3에 "이재학 704일 만 복귀(표본 0)"
    #      라고 스스로 적어놓고 `우세 NC 66.0% · 🟢 · 추천` 으로 나갔다.
    #      같은 슬레이트의 일일 요약은 "선발 표본 부족 3경기 — 추천 자격 없음"
    #      이라고 정확히 셌다 — 요약과 카드가 서로 다른 말을 했다.
    #      이는 규칙이 생긴 계기(1:7 패)와 **같은 실패**다.
    if jg.get("starter_low_sample"):
        return "보드만"
    # [v1.4] 시장 동의 게이트. 🔴 `pipeline.qualifies` 와 **같은 함수**를 부른다 —
    #   게이트가 둘로 갈리면 카드와 요약이 서로 다른 말을 한다(2026-09-05 실사고).
    from app.pipeline import market_disagreement

    if market_disagreement({"p_market_send": jg.get("p_market_send"),
                            "p_home": jg.get("p_claude")}, s) is not None:
        return "보드만"
    side, p = favored_side_and_p(jg)
    if p is None:
        return "보드만"
    need = s.min_win_prob
    if side == "away":
        need += s.away_prob_penalty
    return "추천" if p >= need else "보드만"


def _market_why(jg: dict, settings=None) -> str | None:
    """시장 동의 게이트 탈락 사유 문구. 통과했으면 None.

    🔴 판정은 `pipeline.market_disagreement` 하나가 한다 — 여기서는 문구만 만든다.
    """
    from app.pipeline import MARKET_DISAGREE, market_disagreement

    md = market_disagreement({"p_market_send": jg.get("p_market_send"),
                              "p_home": jg.get("p_claude")}, settings)
    if md is None:
        return None
    if md == MARKET_DISAGREE:
        m, o = jg.get("p_market_send"), jg.get("p_claude")
        return f"시장 이견 (우리 {float(o):.0%} vs 시장 {float(m):.0%})"
    return "시장 미수집"


def _bet_line(jg: dict, settings=None) -> str:
    """베팅 자격 한 줄. **결론과 분리한다.**

    `보드만` 은 "승자를 모른다"가 아니라 "걸 만큼 확실하지 않다"는 뜻이다.
    이유를 함께 적지 않으면 카드의 마지막 말이 결론처럼 읽힌다(실측 2026-09-06).
    """
    s = settings or get_settings()
    label = rec_label(jg, s)
    if label != "보드만":
        return label
    side, p = favored_side_and_p(jg)
    why = None
    if jg.get("judge_confidence") == "low" or jg.get("judge_pass"):
        why = "확신도 하"
    elif jg.get("starter_low_sample"):
        why = "선발 표본 부족"
    elif _market_why(jg, s):
        # [v1.4] **정보는 보이되 추천 딱지만 뗀다** — 왜 보드만인지 적는다.
        why = _market_why(jg, s)
    elif p is not None:
        need = s.min_win_prob + (s.away_prob_penalty if side == "away" else 0.0)
        if p < need:
            why = f"추천 하한 {need:.0%} 미달 ({p:.0%})"
    from app.collectors.lineups import pick_state as _ps

    state = jg.get("pick_state") or _ps(jg.get("lineup_status"))[0]
    if state != "final":
        why = "라인업 미확정"
    return f"보드만 — {why}" if why else "보드만"


#: [WX-2 2026-09-10 사용자 지시] 카드 날씨 한 줄.
#  🔴 값이 **없으면 그 칸을 통째로 뺀다.** "강수 -%"·"풍속 None" 같은 빈 라벨을
#     만들면 그건 정보가 아니라 소음이고, 없는 것을 있는 것처럼 보이게 한다.
#  ⚠️ 풍향은 **방위만** 적는다. 외야/홈 홈런 효과 판정은 구장 방위각이 있어야
#     하고 그건 MLB 전용·비동기다(위성이 이미 발견 기사로 만들어 서술에 태운다).
#     여기서 효과를 단정하면 그건 지어낸 것이다.
_COMPASS = ("북", "북동", "동", "남동", "남", "남서", "서", "북서")


def _wind_dir(deg) -> str:
    try:
        d = float(deg)
    except (TypeError, ValueError):
        return ""
    return _COMPASS[int((d % 360) / 45.0 + 0.5) % 8]


def weather_line(jg: dict) -> str:
    """`jg["weather_card"]` → 한 줄. 재료가 없으면 빈 문자열."""
    wc = jg.get("weather_card") or {}
    if not wc:
        return ""
    if wc.get("dome"):
        return "날씨 🏟 돔구장 — 경기 영향 없음"
    bits: list[str] = []
    t = wc.get("temp_c")
    if t is not None:
        bits.append(f"기온 {float(t):.0f}도")
    w = wc.get("wind_ms")
    if w is not None:
        d = _wind_dir(wc.get("wind_from_deg"))
        bits.append(f"{d + '풍 ' if d else '풍속 '}{float(w):.1f}m/s")
    pp = wc.get("precip_pct")
    if pp is not None:
        bits.append(f"강수 {float(pp):.0f}%")
    return ("날씨 🌤 " + " · ".join(bits)) if bits else ""


def render_form_card(jg: dict, sport: str | None = None, *,
                     revision: bool = False) -> str:
    """판정 JSON → 카드 본문. 언더오버·런라인·F5 없음."""
    sport = sport or jg.get("sport") or ""
    home, away = _team(jg.get("home") or "?"), _team(jg.get("away") or "?")
    league = jg.get("league") or sport.upper()
    when = jg.get("starts_at_kst") or ""
    park = _park(jg)
    m = jg.get("matchup") or {}
    side, p = favored_side_and_p(jg)
    fav_name = home if side == "home" else away if side == "away" else None

    lines = [f"{league}  {away} @ {home}"]
    info = " ".join(x for x in (when, park) if x)
    if info:
        lines.append(info)
    _wx = weather_line(jg)          # [WX-2] 경기 시각 기준 예보
    if _wx:
        lines.append(_wx)
    if fav_name is not None and p is not None:
        # [v1.1 5단계] 별표는 우세팀 확률로. 라인업 미확정이면 "(잠정)" 병기.
        from app.engine.value_gate import required_odds, stars

        _prov = (jg.get("lineup_status") or "none") != "confirmed"
        lines.append(f"우세 {fav_name} {p * 100:.1f}%  {stars(p, provisional=_prov)}")
        lines.append(f"신호등 {traffic_light(p)}")
        # [4단계] 시장 괴리 표기 — 배당이 없으면 아무것도 붙지 않는다.
        if jg.get("market_note"):
            lines.append(str(jg["market_note"]))
        # [5단계] 가치 — 배당이 있으면 p×배당, 없으면 필요배당만 알린다.
        _odds = (jg.get("pick_summary") or {}).get("odds")
        if _odds:
            from app.engine.value_gate import value

            lines.append(f"가치 {value(p, _odds):.2f} (배당 {_odds})")
        else:
            _req = required_odds(p)
            if _req:
                lines.append(f"가치 배당 미수집 — 필요배당 {_req:.2f}")
    # [시장 기준선] 우리 vs 시장. **정보 줄이지 게이트가 아니다.**
    #   ⚠️ 값이 없으면 줄 자체를 안 낸다 — "미수집" 문구를 발명하지 않는다.
    #      바로 위 가치 줄이 이미 그 역할을 한다.
    #   ⚠️ 이견 **사유**는 만들지 않는다. 사유를 쓰려면 판정 프롬프트를
    #      건드려야 하고 그건 동결 위반이다. 수치·방향·라벨까지만.
    try:
        from app.engine.market_baseline import market_line

        # 🔴 [MKT-9 2026-09-10] **홈 기준끼리 비교한다.** `p_market_send` 는
        #    `devig_two_way` 가 낸 **홈 확률**인데 종전에는 우세팀 확률(p)을
        #    넘겨, 원정 우세 경기에서 기준이 어긋났다.
        #      실측(MIN@DET): 홈 0.47·시장 0.54 인데 카드는 "우리 53% — 시장
        #      동의(1%p)"로 찍고, 같은 카드 마지막 줄은 게이트가 낸 "시장 이견
        #      (우리 47% vs 54%)"을 달았다 — 한 카드가 두 말을 했다.
        #    ⚠️ 홈 우세면 p_fav == p_home 이라 증상이 없다. 원정 우세 전용 결함.
        _p_home = m.get("p_home")
        if _p_home is None:
            _p_home = jg.get("p_claude")
        _ml = market_line(jg.get("p_market_send"), _p_home)
        if _ml:
            lines.append(_ml)
    except Exception:
        pass
    # 🔴 [CARD-3 2026-09-10 사용자 지시] **손님상 모드 — 주방을 감춘다.**
    #    "갈림길 현지상황들을 저렇게 다 안 보여줘도 된다… 식당에서 음식을 파는데
    #     굳이 주방은 보여줄 필요가 없다."
    #    서술이 준비돼 있으면 헤더 + 서술 + 베팅 라벨만 낸다. 자료 번호·표본 수·
    #    기반영 %p·심의 메커니즘은 전부 문장 안에 녹아 사라진다.
    #    ⚠️ 헤더 숫자와 베팅 라벨은 **여기까지 규칙이 만든 것**을 그대로 쓴다 —
    #       서술이 숫자를 지어낼 수 없게 하는 방어선이다.
    #    ⚠️ 서술이 없으면(생성 실패·구경로) 아래 구조 카드로 폴백한다.
    _narr = str(jg.get("narrative_card") or "").strip()
    if _narr:
        lines.append("")
        lines.extend(_narr.splitlines())
        lines.append("")
        lines.append(_bet_line(jg))
        if revision:
            lines.append("라인업 변경 재판정")
        return "\n".join(lines)
    # 🔴 [2026-09-06] **결론이 먼저다.** 종전 카드는 확률·근거·변수만 늘어놓고
    #    마지막 줄이 `보드만`(베팅 라벨)이라 "승자를 모르겠다"로 읽혔다.
    #    판정의 답은 확률이 아니라 결론이고, 확률은 그 표현일 뿐이다.
    concl = m.get("결론") or {}
    if isinstance(concl, dict):
        winner = str(concl.get("승자") or "").strip()
        judged = str(concl.get("판단") or "").strip()
        if winner:
            lines.append(f"🎯 결론 — {_team(winner)} 승")
        if judged:
            lines.append(f"   {judged}")
    # 🔴 [CARD-1 2026-09-08] **갈림길을 결론 바로 뒤에 싣는다.**
    #    판정은 `전개.분기점` 을 내고 자료14 는 그 리스크의 발생 확률까지 냈는데,
    #    그것을 찍는 코드(`card.verdict_block`)를 쓰는 곳은 슬레이트 보드
    #    하나뿐이었다 — **발송 카드에는 6일간 한 줄도 안 나갔다**.
    #    실측 2026-09-08 KBO game=1721: 분기점 "최원태가 5이닝을 넘기며 2실점
    #    이하로 막아내는가" · 발생 확률 15% · 원정 4%p 가 전부 있었는데
    #    사용자가 받은 카드에는 없었다. PGP-2 와 같은 형태다.
    #    ⚠️ 문구를 여기 적지 않는다 — `card.branch_lines` 를 **부른다**(사본 금지).
    from app.engine.card import branch_lines

    #    🔴 [CARD-2] `jg["branch"]` 를 함께 넘긴다 — 자료14 가 DB 에서 찾은 답을
    #       갈림길 아래 한 줄로 싣는다. 물음표로 끝내지 않는다.
    lines.extend(branch_lines(m, jg.get("branch")))
    # 🔴 [DS-4] 딥서치 결과를 카드에 싣는다. **[DS-9] 위치는 갈림길 바로 아래다** —
    #    갈림길이 질문하고 조사가 답하는데 종전에는 둘 사이에 근거·변수가 끼어
    #    독자가 관계를 잇지 못했다(사용자 지적: "근거들이 따로 논다").
    #    실측(CLE@BAL): 조사가 실제로 돌아 발견 3건을 냈는데 카드에 한 글자도
    #    안 나왔다 — `form_card` 가 `jg["deepsearch"]` 를 읽지 않았다(축구 카드
    #    `soccer_trial.py` 는 읽는다). 조사했는지를 카드로 알 수 없으면
    #    "조용한 0"과 구분되지 않는다.
    #    ⚠️ 조정이 0이어도 **조사했다는 사실**은 보여준다 — 미조사와 다르다.
    #    ⚠️ 조사 자체가 없었으면 줄을 만들지 않는다(없는 것을 지어내지 않는다).
    ds = jg.get("deepsearch") or {}
    if ds:
        _sum = str(ds.get("요약") or "").strip()
        _moved = ds.get("이동_pp")
        if not _sum:
            _n = len(ds.get("발견") or [])
            _sum = f"새 사실 {_n}건" if _n else "새 사실 없음"
        _tail = (f" (이동 {float(_moved):+.1f}%p)"
                 if isinstance(_moved, (int, float)) and abs(float(_moved)) > 1e-9
                 else " (조정 없음)")
        lines.append(f"🔍 추가 조사 반영: {_sum}{_tail}")
    reasons = [str(x).strip() for x in (m.get("근거") or []) if str(x).strip()]
    for i, r in enumerate(reasons[:3], 1):
        lines.append(f"근거{i} {r}")
    variables = [str(x).strip() for x in (m.get("변수") or []) if str(x).strip()]
    for v in variables[:2]:
        # 🔴 [CARD-2] `발생 확률` 칸은 **자료14 가 답을 준 변수에만** 붙는다.
        #    비어 있는 것을 그냥 두면 사용자가 "안 찾은 것"과 "찾았는데 답이
        #    없는 것"을 구분할 수 없다. 없으면 없다고 적는다 —
        #    지어내지 않되 침묵하지도 않는다.
        #    ⚠️ **변수 문자열은 한 글자도 건드리지 않는다** — L1 사실 감시가
        #       카드의 그 줄을 프롬프트 원문과 대조한다
        #       (`test_card_emits_the_variable_verbatim`). 표시는 **다음 줄**에 둔다.
        #       처음에 같은 줄에 이어 붙였다가 그 계약을 깼고, 전체 스위트가 잡았다.
        from app.engine.variable_parse import parse_variable

        lines.append(f"변수 {v}")
        p = parse_variable(v)
        if p and p.get("q") is None:
            lines.append("     · 자료14 미조사 — 발생 확률을 찾지 못했다")
    news = m.get("뉴스반영") or {}
    if isinstance(news, dict) and news.get("적용"):
        adj = news.get("조정폭") or ""
        why = news.get("사유") or ""
        bit = " ".join(str(x) for x in (adj, why) if x).strip()
        if bit:
            lines.append(f"뉴스반영 {bit}")
    # [소식통 2026-09-06] 현지 상황이 이 승률을 뒷받침하는가.
    #   ⚠️ 확률을 바꾸지 않는다. 사용자가 숫자와 현장을 같이 보게 한다.
    try:
        from app.engine.situation_gate import card_line

        sit = card_line(jg.get("situation_check") or {})
        if sit:
            lines.append(sit)
        from app.engine.council import card_line as _council_line

        cl = _council_line(jg)
        if cl:
            lines.append(cl)
    except Exception:      # 카드가 이 한 줄 때문에 못 나가면 안 된다
        pass
    # 🔴 베팅 라벨은 **승자 판단이 아니라 걸 자격**이다. 이유를 붙여
    #    "승자를 모르겠다"로 읽히지 않게 한다.
    # 🔴 [DS-10 2026-09-10 사용자 지시] **종합 판단을 마지막에 남긴다.**
    #    "분석은 다 됐어. 그래서 종합평가는? 누가 이길 것이라는 서술이 있어야 해."
    #    카드가 조각을 나열만 하면 판단을 사용자에게 떠넘기는 것이다.
    #    ⚠️ 숫자는 전부 기존 값에서 조립한다 — 지어내기가 구조적으로 불가능하다.
    #    ⚠️ 확률·게이트·추천 라벨은 건드리지 않는다. 종합은 서술이지 계산이 아니다.
    try:
        from app.engine.synthesis import synthesize

        # [DS-11] 판단 한 줄은 **미리 계산된 값**을 쓴다 — 카드 렌더는 동기이고
        #   LLM 을 기다리면 발송이 늦는다. 파이프라인이 `synthesis_line` 을 채운다.
        _syn = jg.get("synthesis_line") or synthesize(jg)
        if _syn:
            lines.append(_syn)
    except Exception:
        pass
    lines.append(_bet_line(jg))
    if revision:
        lines.append("라인업 변경 재판정")
    return "\n".join(lines)
