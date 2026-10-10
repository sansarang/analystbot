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


def suspect(*, changed: int | None, off_squad: int) -> str:
    """🔴 §③ 일반화 — **7자리 이상 + 명단에도 없는 선수**면 의심 사유를 돌려준다.

    ⚠️ 못 센 칸(`changed is None`)은 의심하지 않는다(#4 추측 금지).
    """
    box = dict(table().get("suspect") or {})
    want_c = int(box.get("changed") or 7)
    want_o = int(box.get("off_squad") or 2)
    if changed is None or int(changed) < want_c:
        return ""
    if int(off_squad) < want_o:
        return ""
    return (f"바뀐 자리 {int(changed)}개(문턱 {want_c}) · 빠진 선수 중 **명단에도 "
            f"없는** 선수 {int(off_squad)}명(문턱 {want_o})")


def weaken() -> dict:
    """🔴 기준·규칙을 얼마나 낮추나 — ⚠️ **임시값**이고 그 사실이 표에 있다."""
    box = dict(table().get("weaken") or {})
    fit = dict(box.get("fit") or {})
    return {"elo": float(box.get("elo") or 1.0),
            "rules": float(box.get("rules") or 1.0),
            "provisional": bool(fit.get("provisional")),
            "why": str(fit.get("why") or "")}


def read(ref, facts, *, side: str) -> dict:
    """🔴🔴 §③ — 그 팀이 **선수단 교체 상태인가**. 돌려주는 표:

    ```
    {"on": True/False, "why": "...", "kind": "cycle"|"suspect"|"",
     "off_squad": [이름…], "since": "YYYY-MM-DD"|""}
    ```

    🔴 두 길로 켠다:
      ① **전역 주기 팀**이고 평소 XI 대비 바뀐 자리가 문턱 이상이다
      ② 어느 팀이든 **7자리 이상 + 명단에도 없는 선수 2명 이상**
    ⚠️ 확정 XI 가 아니면 **켜지 않는다**(비교할 오늘 명단이 없다).
    """
    from app.core import strategy as _st
    name = str(getattr(ref, f"{side}_name", "") or "")
    key = str(getattr(ref, side))
    got = _st.read(ref, facts, side=side)
    if not got.confirmed:
        return {"on": False, "why": f"확정 XI 전 — 안 센다({got.why})",
                "kind": "", "off_squad": [], "since": ""}
    xi = (facts.xi or {}).get(key)
    now = {str(x) for x in (getattr(xi, "players", None) or [])}
    bench = {str(x) for x in (getattr(xi, "bench", None) or [])}
    squad = {str(x) for x in ((facts.squad or {}).get(key) or [])}
    # 🔴 **빠진 선수가 명단에도 없나** — 그것이 *"이제 그 팀에 없다"* 의 표식이다
    gone: list[str] = []
    for box in dict(got.swaps or {}).values():
        for nm in (dict(box).get("out") or []):
            said = str(nm)
            if said not in now and said not in bench and said not in squad:
                gone.append(said)
    row = cycle_team(name)
    if row and (got.changed or 0) >= 4:
        return {"on": True, "kind": "cycle", "off_squad": sorted(set(gone)),
                "since": "",
                "why": (f"**전역 주기 팀**({row.get('why')}) · 바뀐 자리 "
                        f"{got.changed}개 · 빠진 선수 중 명단에도 없는 선수 "
                        f"{len(set(gone))}명 {sorted(set(gone))[:4]}")}
    said = suspect(changed=got.changed, off_squad=len(set(gone)))
    if said:
        return {"on": True, "kind": "suspect", "off_squad": sorted(set(gone)),
                "since": "", "why": f"**선수단 교체 의심** — {said}"}
    return {"on": False, "kind": "", "off_squad": sorted(set(gone)),
            "since": "",
            "why": (f"바뀐 자리 {got.changed}개 · 명단에도 없는 선수 "
                    f"{len(set(gone))}명 — 문턱 아래다")}


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
