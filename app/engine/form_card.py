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


#: 조사 답 한 줄의 길이 상한. 텔레그램 한 화면을 넘기면 아무도 안 읽는다.
_ANS_MAX = 240
#: 공시(위성) 표시 상한.
_NOTICE_MAX = 6
#: 공시가 카드에 남을 기간. **7일이다.**
#   🔴 48시간으로 잡았더니 실측 2026-09-11 game=5629 에서 15건이 전부
#      빠졌다 — MLB 트랜잭션 수집 창이 14일이라 대부분이 며칠 전 것이고,
#      그중에 유리베·로메로 IL 복귀처럼 **오늘 경기에 그대로 유효한** 것이
#      섞여 있다. 로스터 이동은 하루 지났다고 무효가 되지 않는다.
#   ⚠️ 그래도 14일 전체를 싣지는 않는다 — 그건 "최근"이 아니다.
_NOTICE_MAX_AGE_H = 168.0
#: 구장 이름 길이 상한. **이름이 아니면 싣지 않는다.**
#   실측 2026-09-11 game=5624: 구장 칸에 LLM 산문 400자가 들어와 카드 둘째
#   줄을 통째로 먹었다. 잘라 붙이면 잘린 산문이 남는다 — 이름이 아니면 뺀다.
_PARK_NAME_MAX = 40

_SRC_KR = {"pplx": "퍼플렉시티", "x": "X", "satellite": "공시",
           "크롤러": "우리 기록", "라인업": "크롤러·공시"}


def render_search_card(jg: dict, sport: str | None = None) -> str:
    """[ORD-3 2026-09-11 사용자 지시] **서치가 찾아온 것과 승자만.**

    "추천 로직도 다 삭제…수치는 전부다 삭제…" · "서술형 기본 레이팅도 삭제…" ·
    "설명도 삭제…서치에 의한 정보만 명시…" · "어느팀이 승리한다만 제미나이가 판다…"

    🔴 그래서 이 카드에는 확률·별표·신호등·가치·시장 비교·서술·근거·변수가
       **하나도 없다.** 헤더 + 갈림길별 조사 답 + 공시 + 승자. 끝이다.
    ⚠️ 자료를 여기서 다시 모으지 않는다 — `jg["order_v2"]` 가 원본이다.
    """
    # [ORD-20] v3 · v2 가 같은 모양을 낸다 — 카드는 둘을 구분하지 않는다.
    ov = jg.get("order_v3") or jg.get("order_v2") or {}
    sport = sport or jg.get("sport") or ""
    home, away = _team(jg.get("home") or "?"), _team(jg.get("away") or "?")
    league = jg.get("league") or sport.upper()
    lines = [f"{league}  {away} @ {home}"]
    _pk = _park(jg)
    if len(_pk) > _PARK_NAME_MAX:          # 이름이 아니라 산문이다 — 뺀다
        _pk = ""
    info = " ".join(x for x in (jg.get("starts_at_kst") or "", _pk) if x)
    if info.strip():
        lines.append(info)
    wx = weather_line(jg)
    if wx:
        lines.append(wx)

    # 🔴 캐시에 남은 **옛 모양**을 만나도 카드가 죽지 않는다. 배포 직후
    #    Redis 의 `analysis:*` 에는 숫자만 담긴 `order_v2` 가 남아 있고,
    #    거기에 `list()` 를 걸면 TypeError 로 그 경기 카드가 통째로 못 나간다.
    def _lst(key):
        v = ov.get(key)
        return v if isinstance(v, list) else []

    rows = [r for r in _lst("자료") if isinstance(r, dict)]
    answers = [r for r in rows if r.get("소스") != "satellite"]
    notices = [r for r in rows if r.get("소스") == "satellite"]
    # 🔴 나이를 아는 것만 최근으로 거른다. **모르는 것은 버리지 않는다** —
    #    `age_h=None` 은 "오래됐다"가 아니라 "모른다"다(NPB 가 그렇다).
    _fresh = [r for r in notices
              if r.get("age_h") is None or float(r["age_h"]) <= _NOTICE_MAX_AGE_H]
    _dropped_old = len(notices) - len(_fresh)
    notices = _fresh
    asked = [str(q) for q in _lst("질문")]

    branches = [b for b in _lst("갈림길목록") if isinstance(b, dict)]
    if branches:
        lines.append("")
        lines.append("⚡ 갈림길")
        for i, b in enumerate(branches, 1):
            q = str((b or {}).get("질문") or "").strip()
            if q:
                lines.append(f"{i}. {q}")

    lines.append("")
    lines.append("🔎 조사 결과")
    used = set()
    for q in asked:
        hits = [r for r in answers if (r.get("질문") or "") == q]
        for r in hits:
            used.add(id(r))
        lines.append(f"· {q}")
        if not hits:
            # 🔴 못 찾은 것을 지우면 카드가 다 아는 것처럼 보인다.
            lines.append("   — 찾지 못함")
            continue
        for r in hits:
            lines.append(f"   {_ans(r)}")
    # 질문에 못 붙은 답도 버리지 않는다(질문번호가 없던 응답).
    orphan = [r for r in answers if id(r) not in used]
    for r in orphan:
        lines.append(f"· {_ans(r)}")

    if notices or _dropped_old:
        lines.append("")
        lines.append("📋 최근 공시")
        for r in notices[:_NOTICE_MAX]:
            lines.append(f"· {_clip(r.get('답'), _ANS_MAX)}")
        if len(notices) > _NOTICE_MAX:
            lines.append(f"· … 외 {len(notices) - _NOTICE_MAX}건")
        if _dropped_old:
            # 🔴 뺀 것을 세어 밝힌다 — 조용히 사라지면 공시가 없었는지
            #    오래돼서 뺐는지 구분할 수 없다.
            lines.append(f"· (7일 지난 공시 {_dropped_old}건 제외)")

    w = jg.get("winner") or (jg.get("matchup") or {}).get("승자")
    if w:
        lines.append("")
        conf = (jg.get("matchup") or {}).get("확신")
        # [ORD-12] 되살린 것은 확신 한 칸뿐이다 — 설명이 아니라 라벨이다.
        lines.append(f"🏆 승리 예상 — {_team(w)}"
                     + (f" · 확신 {conf}" if conf else ""))
        # 🔴 [ORD-15] DB 참조로 승자가 바뀌었으면 **드러낸다.** 막지 않는
        #    대신 조용한 변경만 없앤다.
        if ov.get("승자변경"):
            lines.append(f"   🔴 우리 기록을 보고 승자를 바꿨다 — {ov.get('DB사유')}")
        seen = ov.get("DB본것")
        if seen:
            lines.append(f"   (우리 기록에서 본 것: {' · '.join(seen)})")

    from app.collectors.lineups import pick_state as _ps

    state = jg.get("pick_state") or _ps(jg.get("lineup_status"))[0]
    lines.append("")
    lines.append("✅ 최종 · 타순 확정" if state == "final" else "🕐 잠정 · 타순 전")
    return "\n".join(lines)


def _clip(t, n: int) -> str:
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n] + "…"


def _ans(r: dict) -> str:
    """🔴 **언제 있었던 일인지를 함께 보인다.** 지난 일을 오늘 상태로 읽으면
    그건 조사가 아니라 오해다(실측 2026-09-12: 4·6·7월 기사가 섞여 왔다).
    답 문장이 이미 날짜로 시작하면 겹쳐 적지 않는다."""
    src = _SRC_KR.get(r.get("소스") or "", r.get("소스") or "")
    # [ORD-8] X 는 url 대신 **계정**이 출처 단서다 — 누가 한 말인지 밝힌다.
    acct = str(r.get("계정") or "").strip()
    if acct:
        src = f"{src} {acct}"
    t = _clip(r.get("답"), _ANS_MAX)
    when = str(r.get("시점") or "").strip()
    head = f"[{when}] " if when and not t.startswith(when) else ""
    return f"{head}{t} ({src})"


def render_form_card(jg: dict, sport: str | None = None, *,
                     revision: bool = False) -> str:
    """판정 JSON → 카드 본문. 언더오버·런라인·F5 없음."""
    # 🔴 [ORD-3] **설정이 아니라 데이터로 가른다.** `order_v2` 가 붙은 경기는
    #    새 방식으로 판정된 것이고, 한 슬레이트에 두 방식이 섞여도 각 카드가
    #    제 방식대로 그려진다.
    if jg.get("order_v3") or jg.get("order_v2"):
        return render_search_card(jg, sport)
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
