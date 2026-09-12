"""[ORD-15 · 4단계] **경기 관련 DB 를 통째로 주고, AI 가 자율로 판단한다.**

사용자 지시 2026-09-12: "경기 관련 DB를 통째로 주고, AI가 그 안에서 필요한 걸
찾아 쓰게 한다...db 관련도 ai 판단에 의해 결정나게 해라..자율적으로"

🔴 종전(ORD-13)은 ① AI 가 `DB요청` 으로 이름을 적고 ② 우리가 키워드로 맞춰
   ③ 고른 것만 붙였다. **그 왕복이 실제로 샜다** — 실측 2026-09-12: 4경기 중
   2경기가 이름을 풀어 써서("양 팀 선발 투수의 최근 등판 성적 및 평균자책점")
   매핑에 실패했다. 우리가 고르는 구조 자체가 새는 지점이었다.

🔴 그리고 종전에는 코드가 결과를 강제했다 — 모순이어도 승자 불변, 확신 강등.
   이제 **막지 않는다.** 대신 **전부 센다**:
     · 승자를 바꾸면 사유를 요구하고 **경고 로그**를 남긴다(조용한 변경 금지)
     · 바뀐 승자도 경기의 팀인지 검사한다(`apply_winner`) — 자율과 무관한 정합성
     · `본것` 을 세어 DB 의존도를 잰다
   이 저장소가 `check_flow` 에 적어 둔 "프롬프트만으로는 부족하다"의 대가를
   알고 하는 선택이다.

⚠️ `본것` 은 **자기 보고**라 상한이 아니라 **하한**으로 읽는다. 안 보고 봤다고
   적을 수 있다 — `deepsearch` 인용 계측과 같은 태도다.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 항목 이름 → 조립 함수. 🔴 이름은 `prompts.TRIAGE` 가 2단계에 제시한 말과
#  같아야 한다. ⚠️ 값의 원본은 전부 기존 `matchup.*_payload` 다.
ITEMS: tuple[tuple[str, str], ...] = (
    ("최근 3경기 박스스코어", "boxscore_payload"),
    ("오늘 타순", "lineups_payload"),
    ("선발 최근 등판", "starters_recent_payload"),
    ("불펜 최근 폼과 가용성", "bullpen_payload"),
    ("실력 레이팅", "elo_payload"),
    ("분기점 조사", "branch_payload"),
    ("일정·이동·환경", "ledger_payload"),
    ("라인업 의도", "intent_payload"),
    ("변수 대장", "material10_payload"),
)

#: 한 항목의 길이 상한. 전량이라도 무한은 아니다 — 7종 실측 약 9,300자.
ITEM_MAX = 2600


def bundle(jg: dict) -> dict:
    """경기 관련 DB 전량. 반환 `{"줄": [(이름, 값|None)], "있음": [...], "없음": [...]}`.

    🔴 **없는 것은 `없음` 으로 밝힌다.** 조용히 빠뜨리면 AI 는 원래 없는 건지
       아직 안 온 건지 구분할 수 없다 — 실측 2026-09-12: 오늘 KBO/NPB 는
       `research` 가 안 차서 9종 중 3종만 있었다.
    """
    from app.engine import matchup as MU

    rows: list[tuple[str, str | None]] = []
    have: list[str] = []
    miss: list[str] = []
    for name, fn in ITEMS:
        try:
            payload = getattr(MU, fn)(jg)
        except Exception as exc:                 # 한 항목 실패가 나머지를 막지 않는다
            logger.warning("[dbref] %s 조립 실패: %s", name, exc)
            payload = None
        if not payload:
            rows.append((name, None))
            miss.append(name)
            continue
        text = json.dumps(payload, ensure_ascii=False, default=str)
        rows.append((name, text[:ITEM_MAX] + ("…" if len(text) > ITEM_MAX else "")))
        have.append(name)
    return {"줄": rows, "있음": have, "없음": miss}


def fmt(rows: list[tuple[str, str | None]]) -> str:
    return "\n".join(f"· {n} — {t if t else '없음'}" for n, t in rows) or "(없음)"


async def recheck(jg: dict, tri: dict, v: dict, *,
                  role: str | None = None) -> dict:
    """④ 참조. **AI 가 자율로 판단한다** — 확인/확신 조정/승자 변경 전부 가능.

    반환 `{"있음","없음","본것","승자","확신","승자변경","사유","판정"}`.
    ⚠️ 호출 실패면 3단계 판정을 그대로 쓴다(ORD-1 규약) — 있던 판정을 잃지 않는다.
    """
    from app.config import get_settings
    from app.engine.prompts import DB_OPEN, fill
    from app.engine.team_form import complete_json, parse_json_object
    from app.engine.verdict import fmt_branches, level
    from app.llm.judge_route import PRELIM_ROLE

    b = bundle(jg)
    out = {"있음": b["있음"], "없음": b["없음"], "본것": [],
           "승자": v.get("승자"), "확신": level(v.get("확신")),
           "승자변경": False, "사유": "", "판정": "미조회"}
    if not b["있음"]:
        logger.info("[dbref] %s@%s 우리 기록이 통째로 비었다 — 참조 생략",
                    jg.get("away"), jg.get("home"))
        return out
    s = get_settings()
    prompt = fill(DB_OPEN,
                  LEAGUE=jg.get("league") or (jg.get("sport") or "").upper(),
                  AWAY=jg.get("away") or "", HOME=jg.get("home") or "",
                  WINNER=v.get("승자") or "", CONF=out["확신"],
                  BRANCHES=fmt_branches((tri or {}).get("갈림길")),
                  DBROWS=fmt(b["줄"]))
    try:
        text = await complete_json(prompt, model=s.matchup_model,
                                   max_tokens=int(s.matchup_max_tokens),
                                   role=role or PRELIM_ROLE, mock=False)
    except Exception as exc:
        logger.warning("[dbref] 재질의 실패 — 3단계 판정을 그대로 쓴다 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        out["판정"] = "조회실패"
        return out
    parsed = parse_json_object(text or "")
    if not isinstance(parsed, dict):
        out["판정"] = "조회실패"
        return out
    out["판정"] = "확인"
    # `본것` 은 자기 보고다 — 우리가 실제로 실은 것만 인정한다.
    out["본것"] = [x for x in (parsed.get("본것") or []) if x in b["있음"]]
    out["확신"] = level(parsed.get("확신"))
    new_w = str(parsed.get("승자") or "").strip()
    why = " ".join(str(parsed.get("사유") or "").split())
    if new_w and new_w != (v.get("승자") or ""):
        if not why:
            # 🔴 사유 없는 변경은 자율이 아니라 실수다. 받지 않는다.
            logger.warning("[dbref] 🔴 %s@%s 사유 없이 승자를 바꾸려 했다 "
                           "(%s → %s) — 되돌린다",
                           jg.get("away"), jg.get("home"), v.get("승자"), new_w)
        else:
            # 🔴 **조용한 변경만 없앤다.** 막지는 않되 반드시 드러낸다.
            logger.warning("[dbref] 🔴 %s@%s DB 참조로 승자 변경 %s → %s · %s",
                           jg.get("away"), jg.get("home"), v.get("승자"),
                           new_w, why)
            out["승자"] = new_w
            out["승자변경"] = True
            out["사유"] = why
            out["판정"] = "정정"
    logger.info("[dbref] %s@%s %s · 있음 %d · 본것 %s · 확신 %s→%s",
                jg.get("away"), jg.get("home"), out["판정"], len(b["있음"]),
                out["본것"], v.get("확신"), out["확신"])
    return out
