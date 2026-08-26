"""[A-1단계] 딥서치가 주던 값을 **이미 수집한 데이터로 직접 산출**한다.

왜 이관하는가:
  이 필드들은 외부 유료 API에 의존하면서도 채움률이 낮았다(실측 2026-08-27,
  KBO 캐시 5건): bullpen_overused 1/5 · form_reversal 0/5 · splits 2/5.
  그런데 **같은 정보를 우리가 이미 갖고 있다** — 투수 소모(kbo_usage)와
  순위표(standings)에서 결정적으로 유도된다. 크롤링을 늘리지 않고도
  채움률이 오르고 비용이 0이 된다.

⚠️ **임의 임계값을 만들지 않는다.** 예를 들어 `bullpen_overused`의 원래 정의는
   "최근 3일 소모가 **리그 평균 대비** 과다한 쪽"이다. 그 정의를 그대로 계산할 뿐,
   "평균의 1.3배" 같은 새 상수를 만들지 않는다. 튜닝된 상수는 측정되지 않은
   파라미터이고, 그것이 사고를 만든 적이 있다.

⚠️ **해석하지 않는다.** '총력전'·'뒷문이 얇다'는 2단 해석봇의 일이다.
   여기서는 사실만 만든다.
"""

import logging

logger = logging.getLogger(__name__)


def bullpen_overused(usage: dict, jg: dict) -> str | None:
    """[λ ⑤단계 입력] 최근 3경기 구원 소모가 **리그 평균 대비** 과다한 쪽.

    반환은 기존 딥서치 필드와 **같은 어휘**다: "홈" | "원정" | "양팀" | "없음".
    스코어링(`_bullpen_factor`)이 "홈"·"원정"만 계수로 쓰므로 어휘가 달라지면
    조용히 무시된다.

    비교 지표는 **상대한 타자 수**(`relief_batters_l3`)다. 이닝은 아웃카운트만
    세지만 타자 수는 위기 상황의 부담까지 반영한다(투구수 필드가 응답에 없어
    이것이 가장 가까운 대리 지표다 — 2026-08-27 확인).

    ⚠️ 리그 표본이 없으면 **None**을 돌려준다. "없음"으로 채우면 '측정했는데
       과다하지 않다'와 '측정 못 했다'가 구분되지 않는다.
    """
    vals = {t: v.get("relief_batters_l3") for t, v in (usage or {}).items()
            if isinstance(v, dict) and v.get("relief_batters_l3") is not None}
    if len(vals) < 3:
        return None                      # 리그 평균을 낼 표본이 아니다
    mean = sum(vals.values()) / len(vals)
    home, away = vals.get(jg.get("home")), vals.get(jg.get("away"))
    if home is None or away is None:
        return None
    hi_h, hi_a = home > mean, away > mean
    if hi_h and hi_a:
        return "양팀"
    if hi_h:
        return "홈"
    if hi_a:
        return "원정"
    return "없음"


def motivation(research: dict, jg: dict) -> str | None:
    """[표시·판정 참고] 이 경기의 무게 — 순위·게임차·잔여경기 **사실만**.

    ⚠️ '총력전'·'정리 모드'로 단정하지 않는다. 그 판단은 2단 해석봇이 한다.
       딥서치는 산문으로 결론까지 써 줬지만, 결론을 사실 칸에 넣으면
       3단이 판단을 사실로 읽는다.
    """
    parts = []
    for side, label in (("home", "홈"), ("away", "원정")):
        s = research.get(f"{side}_standing") or {}
        if not s.get("rank"):
            continue
        bit = f"{label} {jg.get(side, '')} {s['rank']}위"
        if s.get("games_behind") is not None:
            bit += f"(선두와 {s['games_behind']}G)"
        if s.get("remaining") is not None:
            bit += f" 잔여 {s['remaining']}경기"
        parts.append(bit)
    return " · ".join(parts) or None


def splits(research: dict) -> str | None:
    """[표시] 홈/원정 성적 요약 — 순위표의 승패로 사실만."""
    parts = []
    for side, label in (("home", "홈팀"), ("away", "원정팀")):
        s = research.get(f"{side}_standing") or {}
        if s.get("w") is None:
            continue
        parts.append(f"{label} 시즌 {s['w']}승 {s['l']}패 {s.get('d', 0)}무")
    return " · ".join(parts) or None


# 최근 폼과 시즌 평균이 어긋났다고 볼 최소 차이.
#   ⚠️ 이것은 **표시용 문턱**이지 확률 계수가 아니다. 판정이 읽고 스스로
#     판단하며, λ에는 들어가지 않는다.
_ERA_GAP = 1.50


def form_reversal(research: dict, jg: dict) -> list[str]:
    """[판정 프롬프트 입력] 시즌 평균과 최근 폼이 **역전된 항목**.

    딥서치는 이 필드를 KBO에서 0/5로 채웠다(실측). 우리가 가진 값으로 직접
    만든다 — 선발의 시즌 ERA와 최근 등판 평균이닝, 그리고 최근 3경기 결과다.

    ⚠️ 없는 것을 만들지 않는다. 비교할 두 값이 다 있을 때만 문장을 낸다.
    """
    out: list[str] = []
    for side, label in (("home", "홈"), ("away", "원정")):
        team = jg.get(side, "")
        p = research.get(f"{side}_pitcher") or {}
        era_s, era_r = p.get("era_season"), p.get("era_recent")
        if era_s is not None and era_r is not None and abs(era_r - era_s) >= _ERA_GAP:
            worse = era_r > era_s
            out.append(f"{label} 선발 {p.get('name', '')} 시즌 ERA {era_s} vs "
                       f"최근 {era_r} — {'악화' if worse else '개선'}")
        # 순위(시즌 누적)와 최근 3경기 결과가 어긋나는 경우
        st = research.get(f"{side}_standing") or {}
        u = research.get(f"{side}_usage") or {}
        res = (u.get("results_l3") or "")
        if st.get("rank") and len(res) >= 3:
            wins = res.count("W")
            if st["rank"] <= 3 and wins == 0:
                out.append(f"{label} {team} {st['rank']}위인데 최근 3경기 {res} — 부진")
            elif st["rank"] >= 8 and wins == 3:
                out.append(f"{label} {team} {st['rank']}위인데 최근 3경기 전승 — 상승")
    return out


def apply(research: dict, jg: dict, usage_table: dict | None = None) -> list[str]:
    """자체 산출값을 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ **이미 값이 있으면 덮지 않는다.** MLB·유럽은 아직 딥서치가 이 필드들을
       채우며(실측: MLB expert_picks 10/15·form_reversal 8/15), 그쪽을 지우면
       안 된다. 이 함수는 **빈칸만** 채운다.
    """
    filled = []
    # ⚠️ `bullpen_overused`는 **일부러 채우지 않는다.** (2026-08-27 측정)
    #   원래 정의("리그 평균 대비 과다한 쪽")를 그대로 계산해 보니 변별력이 없다:
    #     한화 86(평균의 1.64배) · LG 58(1.11) · NC 54(1.03) · 키움 53(1.01)
    #     — 10팀 중 4팀이 평균 초과라 매 경기 발동하고, 진짜 이상치와 3% 초과가
    #       같은 통에 들어간다.
    #   딥서치와 대조했더니 실제로 갈렸다(#670 NC@LG: 딥서치 "홈" vs 산출 "양팀").
    #   `_bullpen_factor`는 "홈"·"원정"일 때만 계수를 붙이므로 이 차이가
    #   **λ를 바꾼다.** 변별력 있는 문턱은 결과 데이터로 재야 하는데, 아직
    #   예측이 기록되지 않아(#49) 잴 수 없다.
    #   → 임의 임계값을 만드는 대신 **숫자 사실만** 카드에 남긴다
    #     (`{side}_usage.relief_batters_l3`). 해석은 2단 해석봇의 일이다.
    #   함수 자체는 남겨둔다 — 채점 회로가 복구되면 문턱을 실측해 다시 켠다.
    for key, fn in (("motivation", lambda: motivation(research, jg)),
                    ("splits", lambda: splits(research))):
        if research.get(key):
            continue
        v = fn()
        if v:
            research[key] = v
            filled.append(key)
    if not research.get("form_reversal"):
        v = form_reversal(research, jg)
        if v:
            research["form_reversal"] = v
            filled.append("form_reversal")
    return filled
