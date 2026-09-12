"""[ORD-13 · 4단계] **DB 는 참조용이다.** 확인하거나 반박할 뿐, 정하지 않는다.

사용자 지시 2026-09-12: "db가치를 내린다..db는 단순 참조용이다" · "나로 해라"

🔴 왜 이 단계가 필요한가. 3단계 실측(2026-09-12): 확신이 **4/4 전부 `하`** 였고
   `DB요청` 이 네 경기 모두 `['선발 최근 등판', '오늘 타순']` 이었다. 검색만으로는
   그 둘을 못 채우는데 우리는 갖고 있다.

🔴 동시에 — 붙이는 순간 DB 가 답을 정할 수 있다. ORD-1 실측: DB 를 뒤에
   붙였더니 ④가 3/3 돌았고 NYM@NYY 는 **승자째 뒤집혔다**(0.54 NYY → 0.46 NYM).
   그때는 막을 장치가 없었다. **막는 것이 이 단계의 본업이다.**

세 겹으로 내린다:
  1겹 순서 — 판정이 끝난 **뒤**에 온다.
  2겹 권한 — 근거가 될 수 없다. 3·4단계 출력에 근거 칸 자체가 없다.
  3겹 결과 — 모순이어도 **승자를 뒤집지 않는다.** 확신을 한 단계 내리고 표시만.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 요청 이름 → 조립 함수. 🔴 이름은 `prompts.TRIAGE` 가 2단계에 제시한 말과
#  **같아야 한다.** 두 곳이 다른 이름을 쓰면 요청이 영영 안 붙는다.
#  ⚠️ 값은 전부 기존 `matchup.*_payload` 다 — 숫자를 여기서 다시 계산하지 않는다.
SOURCES: dict[str, str] = {
    "최근 3경기 박스스코어": "boxscore_payload",
    "오늘 타순": "lineups_payload",
    "선발 최근 등판": "starters_recent_payload",
    "불펜 최근 폼과 가용성": "bullpen_payload",
    "실력 레이팅": "elo_payload",
}

#: 한 항목 요약의 길이 상한. 🔴 길면 그 자체로 판정을 끌고 간다.
#  전량 주입(ORD-1 때 21,000자)은 하지 않는다.
ROW_MAX = 300


#: 풀어 쓴 요청을 받기 위한 **핵심어**. 🔴 프롬프트가 이름을 그대로 쓰라고
#  이미 말한다 — 이건 그것이 안 지켜졌을 때의 그물이다.
#  ⚠️ **전부 포함**일 때만 맞춘다. 하나만 걸리게 하면 "선발"이 들어간 모든
#     요청이 등판 기록으로 빨려 들어간다.
#  실측 2026-09-12: 4경기 중 2경기가 "양 팀 선발 투수의 최근 등판 성적 및
#  평균자책점" 처럼 풀어 써서 매핑에 실패했다.
_HINTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "선발 최근 등판": (("선발", "등판"),),
    "오늘 타순": (("타순",), ("선발", "라인업"), ("라인업",)),
    "불펜 최근 폼과 가용성": (("불펜",), ("구원",)),
    "실력 레이팅": (("레이팅",), ("elo",)),
    "최근 3경기 박스스코어": (("박스스코어",), ("최근", "3경기")),
}


def _match(req: str) -> str | None:
    """요청 이름을 아는 항목에 맞춘다. 모르면 None(조용히 버리지 않는다)."""
    t = " ".join(str(req or "").split())
    if not t:
        return None
    for name in SOURCES:
        if name in t or t in name:
            return name
    low = t.lower()
    for name, groups in _HINTS.items():
        for words in groups:
            if all(w.lower() in low for w in words):
                return name
    return None


def summarize(jg: dict, requests: list[str]) -> dict:
    """요청한 것만 한 줄씩. 반환 `{"붙임": [(이름, 줄)], "모르는요청": [...]}`."""
    from app.engine import matchup as MU

    seen: list[str] = []
    rows: list[tuple[str, str]] = []
    unknown: list[str] = []
    for req in requests or []:
        name = _match(req)
        if name is None:
            unknown.append(str(req))
            continue
        if name in seen:
            continue
        seen.append(name)
        try:
            payload = getattr(MU, SOURCES[name])(jg)
        except Exception as exc:                 # 조회 실패가 판정을 막지 않는다
            logger.warning("[dbref] %s 조립 실패: %s", name, exc)
            continue
        if not payload:
            continue
        text = json.dumps(payload, ensure_ascii=False, default=str)
        rows.append((name, text[:ROW_MAX] + ("…" if len(text) > ROW_MAX else "")))
    return {"붙임": rows, "모르는요청": unknown}


def fmt(rows: list[tuple[str, str]]) -> str:
    return "\n".join(f"· {n} — {t}" for n, t in rows) or "(없음)"


def lower(conf: str) -> str:
    """확신을 한 단계 내린다. 🔴 `하` 에서는 더 내리지 않는다 — 3단계가 이미
    4/4 `하` 였다. 여기서 또 내리면 바닥에 깔려 신호가 죽는다."""
    from app.engine.verdict import LEVELS

    i = LEVELS.index(conf) if conf in LEVELS else len(LEVELS) - 1
    return LEVELS[min(i + 1, len(LEVELS) - 1)]


async def recheck(jg: dict, tri: dict, v: dict, *,
                  role: str | None = None) -> dict:
    """④ 참조. 판정을 **바꾸지 않고** 확인/모순만 붙인다.

    반환 `{"요청","붙임","판정","사유","확신"}`. 재질의 실패면 3단계 확신 그대로.
    """
    from app.config import get_settings
    from app.engine.deepsearch import _today_kst  # noqa: F401  (형식 통일)
    from app.engine.prompts import DB_CHECK, fill
    from app.engine.team_form import complete_json, parse_json_object
    from app.engine.verdict import fmt_branches
    from app.llm.judge_route import PRELIM_ROLE

    req = list((tri or {}).get("DB요청") or [])
    out = {"요청": req, "붙임": [], "판정": "미조회", "사유": "",
           "확신": v.get("확신") or "하"}
    if not req:
        return out
    got = summarize(jg, req)
    out["붙임"] = [n for n, _ in got["붙임"]]
    if got["모르는요청"]:
        # 🔴 조용히 버리지 않는다 — 무엇을 못 붙였는지 남아야 다음에 고친다.
        logger.info("[dbref] 모르는 요청 %s", got["모르는요청"])
        out["모르는요청"] = got["모르는요청"]
    if not got["붙임"]:
        logger.info("[dbref] %s@%s 요청 %d건 중 붙일 것이 없다",
                    jg.get("away"), jg.get("home"), len(req))
        return out
    s = get_settings()
    prompt = fill(DB_CHECK,
                  LEAGUE=jg.get("league") or (jg.get("sport") or "").upper(),
                  AWAY=jg.get("away") or "", HOME=jg.get("home") or "",
                  WINNER=v.get("승자") or "", CONF=v.get("확신") or "하",
                  BRANCHES=fmt_branches((tri or {}).get("갈림길")),
                  DBROWS=fmt(got["붙임"]))
    try:
        text = await complete_json(prompt, model=s.matchup_model,
                                   max_tokens=int(s.matchup_max_tokens),
                                   role=role or PRELIM_ROLE, mock=False)
    except Exception as exc:
        # 🔴 있던 판정을 재질의 실패로 잃지 않는다(ORD-1 규약).
        logger.warning("[dbref] 재질의 실패 — 3단계 판정을 그대로 쓴다 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        out["판정"] = "조회실패"
        return out
    parsed = parse_json_object(text or "")
    verdict = str((parsed or {}).get("판정") or "").strip()
    why = " ".join(str((parsed or {}).get("사유") or "").split())
    if verdict == "모순" and why:
        out["판정"] = "모순"
        out["사유"] = why
        out["확신"] = lower(out["확신"])
    else:
        # 🔴 사유 없는 모순은 셀 수 없다 — 확인으로 본다.
        out["판정"] = "확인" if verdict in ("확인", "모순") else "조회실패"
    logger.info("[dbref] %s@%s %s · 붙임 %s · 확신 %s→%s",
                jg.get("away"), jg.get("home"), out["판정"], out["붙임"],
                v.get("확신"), out["확신"])
    return out
