"""🔴🔴 **선수단 대거 변동(전역·이적)**. 사용자 지시 2026-10-10(다섯 지적 ③).

> 김천상무 같은 **군 팀**은 config에 "전역 주기 팀"으로 표시 … 전역 뒤 첫 경기들은
> "평소 XI"를 **전역 이후 경기로만** 만들고 … 전략 판정을 **로테이션으로 하지
> 않는다**(새 판정값 `squad_turnover`) … 기준(Elo)·폼·골 내용은 전역 이전 기록이므로
> **"선수단 교체 — 기준 약함"** 표시, 가중을 낮춘다.
> 일반화: 어느 팀이든 평소 XI 대비 **7자리 이상** 바뀌고 **빠진 선수가 명단에도
> 없으면** `squad_turnover` 의심으로 새 사실 검색.

🔴 표는 `config/squad_turnover.yaml` 이 든다(사본 금지 — 여기 베끼지 않는다).
🔴 이 파일은 **판정만** 한다: *"이 팀이 오늘 선수단이 바뀐 상태인가"* 와 그 사유.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CONF = "config/squad_turnover.yaml"
#: 🔴 전략 판정의 **새 값**(지시서 ③) — `로테이션·체력 관리` 로 읽지 않는다
VERDICT = "squad_turnover"
#: 🔴 카드가 붙이는 표시
WEAK_MARK = "🔴 **선수단 교체 — 기준 약함**"
#: 🔴 `squad_turnover` 를 **사람 말로**(코드 값은 그대로 둔다 — 열거값이다)
VERDICT_KO = "선수단 교체(전역·이적)"
PROVISIONAL = "🔴 **임시값**(적합 전)"


def verdict_ko(said: object) -> str:
    """🔴 판정값을 카드 글자로. ⚠️ 다른 값은 **그대로** 돌려준다."""
    got = str(said or "")
    return VERDICT_KO if got == VERDICT else got


def table() -> dict:
    from app import rules
    return dict(rules._load(CONF) or {})


def cycle_team(name: str) -> dict:
    """🔴 그 팀이 **전역 주기 팀**인가 — 맞으면 그 줄, 아니면 빈 표.

    🔴 이름 맞추기는 `discover.same_team` 하나가 한다(글자 비교를 짓지 않는다).
    """
    from app.core import discover as _d
    said = str(name or "")
    if not said:
        return {}
    for row in (table().get("cycle_teams") or []):
        box = dict(row)
        names = [str(box.get("name") or ""), *[str(x) for x in
                                               (box.get("aliases") or [])]]
        if any(_d.same_team(said, x) for x in names if x):
            return box
    return {}


def flags() -> dict:
    """🔴 깃발 문턱 — `config/squad_turnover.yaml` 의 `flags`."""
    return dict(table().get("flags") or {})


def off_matchday(facts, key: str, xi) -> tuple[list, str]:
    """🔴🔴 ① **오늘 경기 명단(선발+벤치) 기준** — 최근 N경기 선발 중 없는 선수들.

    > ① 오늘 경기 명단(선발+벤치) 기준: 최근 5경기 선발 중 오늘 명단에 없는 선수
    >   **≥ 5명** · r 도 **오늘 경기 명단 기준**으로 계산한다. 명부는 **이름
    >   매칭용으로만**.

    🔴 이름은 `discover.name_key` 로 맞춘다(성 먼저·이름 먼저가 섞인다 — 그것이
       *"명부는 이름 매칭용으로만"* 의 뜻이다).
    ⚠️ 오늘 명단이 비면 **셀 수 없다**(빈 목록 + 사유) — 모르는 것을 교체로 읽지
       않는다(#4).
    """
    from app.core import discover as _d
    box = flags()
    look = int(box.get("look_back") or 5)
    # 🔴🔴 **오늘 경기 명단 = 선발 + 벤치 + 경기 명단**(`facts.squad`).
    #    ⚠️ 실측 2026-10-10: `XI.bench` 만 보면 **12명**밖에 안 돼(벤치가 덜 찬
    #       판이 있다) 어느 팀이든 ① 이 켜졌다(안양이 13명 이탈로 잡혔다).
    #       🔴 경기 페이지가 주는 **선발 11 + 벤치 9 = 20명**이 `facts.squad` 다.
    today = {_d.name_key(x) for x in
             [*(getattr(xi, "players", None) or []),
              *(getattr(xi, "bench", None) or []),
              *((getattr(facts, "squad", None) or {}).get(key) or [])]}
    if not today:
        return [], "🔴 오늘 경기 명단이 없다 — 못 센다"
    rows = list((getattr(facts, "past_xi", None) or {}).get(key) or [])[-look:]
    if not rows:
        return [], "🔴 최근 경기 선발을 못 받았다 — 못 센다"
    out: list[str] = []
    for one in rows:
        for nm in (getattr(one, "players", None) or []):
            if _d.name_key(nm) not in today and str(nm) not in out:
                out.append(str(nm))
    return out, (f"최근 {len(rows)}경기 선발 중 오늘 경기 명단"
                 f"(선발+벤치+명단 {len(today)}명)"
                 f"에 **없는 선수 {len(out)}명**")


def r_matchday(facts, key: str, xi) -> tuple[float, str]:
    """🔴🔴 ① — **r 가중도 오늘 경기 명단 기준**이다.

    > r = 그 경기 선발 중 **오늘 명단에 있는 비율**(과거 경기마다 센 뒤 평균).

    ⚠️ 못 세면 `(1.0, 사유)` — 깎지 않는다(모르는 것으로 과거를 버리지 않는다).
    """
    from app.core import discover as _d
    box = flags()
    look = int(box.get("look_back") or 5)
    # 🔴 r 도 **같은 집합**으로 센다(①과 한 곳이다)
    today = {_d.name_key(x) for x in
             [*(getattr(xi, "players", None) or []),
              *(getattr(xi, "bench", None) or []),
              *((getattr(facts, "squad", None) or {}).get(key) or [])]}
    rows = list((getattr(facts, "past_xi", None) or {}).get(key) or [])[-look:]
    if not today or not rows:
        return 1.0, "🔴 오늘 명단이나 과거 선발이 없다 — r 을 안 깎는다(1.0)"
    said: list[float] = []
    for one in rows:
        names = [str(x) for x in (getattr(one, "players", None) or [])]
        if not names:
            continue
        hit = sum(1 for nm in names if _d.name_key(nm) in today)
        said.append(hit / len(names))
    if not said:
        return 1.0, "🔴 과거 선발 이름이 비었다 — r 1.0"
    got = sum(said) / len(said)
    return round(got, 3), (f"과거 {len(said)}경기 선발 중 오늘 명단에 있는 비율 "
                           f"평균 **{got:.2f}**(경기별 {[round(x, 2) for x in said]})")


def read(ref, facts, *, side: str) -> dict:
    """🔴🔴 **깃발 판정**(사용자 결정 2026-10-10 (a)) — 셋 중 하나면 켠다.

    ```
    {"on": True/False, "why": "...", "kind": "matchday"|"cycle_news"|"no_usual",
     "off_squad": [이름…], "r": 0.0~1.0, "r_why": "...", "reasons": ["①"…]}
    ```

    > ① 오늘 경기 명단(선발+벤치) 기준: 최근 5경기 선발 중 오늘 명단에 없는 선수
    >    **≥ 5명**
    > ② **전역 주기 팀**이고 최근 30일 안에 전역(새 사실·구단 발표)이 있다
    > ③ **평소 XI 를 만들 수 없다**(교체 이후 경기 0건)

    🔴 ② 는 **새 사실**이 있어야 판정할 수 있다 — 변수가 생긴 뒤에
       `with_news()` 가 그 깃발을 덮는다(여기서는 ①③ 만 본다).
    🔴 **구단 명부 기준은 삭제됐다** — 명부는 이름 매칭용으로만 쓴다.
    ⚠️ 확정 XI 가 아니면 **켜지 않는다**(비교할 오늘 명단이 없다).
    """
    from app.core import strategy as _st
    name = str(getattr(ref, f"{side}_name", "") or "")
    key = str(getattr(ref, side))
    xi = (facts.xi or {}).get(key)
    if xi is None or str(getattr(xi, "state", "") or "") != "confirmed":
        return {"on": False, "kind": "", "off_squad": [], "r": 1.0,
                "r_why": "확정 XI 전 — r 을 안 깎는다", "reasons": [],
                "why": f"확정 XI 전 — 안 센다(상태 "
                       f"{getattr(xi, 'state', '없음')})"}
    gone, why1 = off_matchday(facts, key, xi)
    r, why_r = r_matchday(facts, key, xi)
    want = int(flags().get("off_matchday") or 5)
    reasons: list[str] = []
    if len(gone) >= want:
        reasons.append(f"① {why1}(문턱 {want}명) — {sorted(gone)[:5]}")
    # 🔴 ③ 평소 XI 를 만들 수 없나 — `strategy.read` 가 그 사실을 사유로 든다
    got = _st.read(ref, facts, side=side)
    if "평소 XI 없음" in str(got.why or ""):
        reasons.append(f"③ {got.why}")
    row = cycle_team(name)
    said = (f"**전역 주기 팀**({row.get('why')}) · " if row else "")
    if reasons:
        return {"on": True, "kind": ("matchday" if reasons[0][0] == "①"
                                     else "no_usual"),
                "off_squad": sorted(gone), "r": r, "r_why": why_r,
                "reasons": reasons,
                "why": said + " · ".join(reasons)}
    return {"on": False, "kind": "", "off_squad": sorted(gone), "r": r,
            "r_why": why_r, "reasons": [],
            "why": (said + f"{why1} · 문턱 {want}명 아래다"
                    + (" · 평소 XI 는 있다" if got.confirmed else ""))}


def with_news(ref, got: dict, variables: list, *, side: str) -> dict:
    """🔴🔴 ② **전역 주기 팀 + 최근 30일 전역 새 사실**이면 깃발을 켠다.

    🔴 새 사실은 **변수**로 온다(`returning`·`squad_rotation` 유형의 글에 전역
       낱말이 있나). ⚠️ 날짜 칸이 없는 변수는 **창을 못 본다** — 그때는 72시간
       하위(F)가 나른 것만 센다(그 하위의 창이 이미 72시간이다).
    ⚠️ 전역 주기 팀이 아니면 **아무것도 하지 않는다**(②는 그 팀만의 조항이다).
    """
    from app import rules
    name = str(getattr(ref, f"{side}_name", "") or "")
    if not cycle_team(name) or dict(got or {}).get("on"):
        return got
    key = str(getattr(ref, side))
    words = [str(x) for x in (rules.local_words("squad_turnover", "ko") or [])
             if str(x) in ("전역", "입대", "소집 해제")]
    hit = []
    for v in (variables or []):
        if str(getattr(v, "subject", "")) != key:
            continue
        said = f"{getattr(v, 'claim', '')} {getattr(v, 'quote', '')}"
        if any(w in said for w in words):
            hit.append(str(getattr(v, "id", "")))
    if not hit:
        return got
    box = dict(got or {})
    box["on"] = True
    box["kind"] = "cycle_news"
    box["reasons"] = [*box.get("reasons", []),
                      f"② 전역 주기 팀 + **전역 새 사실** {hit[:3]}"
                      f"(창 {int(flags().get('news_days') or 30)}일 — ⚠️ 변수에 "
                      "날짜 칸이 없어 하위 F 의 72시간 창으로 본다)"]
    box["why"] = " · ".join(box["reasons"])
    return box


def past_since(rows: list, *, names: set[str]) -> tuple[list, str]:
    """🔴🔴 §③ — **평소 XI 를 "교체 이후" 경기로만** 만든다. `(쓸 경기들, 사유)`.

    > 전역 뒤 첫 경기들은 "평소 XI"를 **전역 이후 경기로만** 만들고(없으면
    > **"평소 XI 없음 — 선수단 교체"**).

    🔴 *"교체 이후"* 를 **날짜로 짓지 않는다** — 날짜를 모른다(전역일 기사는 새 사실
       B 로 들어오지만 없을 때가 많다). 🔴 대신 **그 경기 선발에 '이제 없는 선수'가
       있나**로 센다: 있으면 그 경기는 **옛 선수단**이다.
    ⚠️ 하나도 안 남으면 빈 목록이고 사유가 *"평소 XI 없음 — 선수단 교체"* 다.
    """
    if not names:
        return list(rows or []), ""
    keep = []
    for xi in (rows or []):
        said = {str(x) for x in (getattr(xi, "players", None) or [])}
        if said & names:
            continue        # 🔴 이제 없는 선수가 뛴 경기 — 옛 선수단이다
        keep.append(xi)
    if not keep:
        return [], ("🔴 **평소 XI 없음 — 선수단 교체**(최근 경기 전부에 이제 "
                    f"없는 선수가 뛰었다 · {len(names)}명)")
    if len(keep) != len(rows or []):
        return keep, (f"🔴 선수단 교체 — 최근 {len(rows or [])}경기 중 교체 이후 "
                      f"**{len(keep)}경기만** 썼다")
    return keep, ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`weaken()` 을 지웠다** — 상성 엔진 지시서 §2(2026-10-10 여섯째)
# ══════════════════════════════════════════════════════════════════
#
#  > "기준 약함 ×0.5" 등 **고정 배율 삭제** → **r 가중·호흡**.
#
#  🔴 지금 선수단 교체가 확률에 닿는 길은 **변수 `TURN-{side}`** 하나다:
#     `s5_verify._turn_vars` 가 만들고, 배치표가 `axis0·axis1·axis3·V1` 로 보내고,
#     축0 은 **호흡**으로, 축1·축3 은 **r 가중**(`config/matchup_model.yaml` 의
#     `axis1.turnover_r`)으로 센다.
#  ⚠️ `WEAK_MARK` 는 **남겨 둔다** — 카드가 *"기준 낡음"* 을 적는 글자이고 검증
#     (V1)이 그 말을 쓴다.
