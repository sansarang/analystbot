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
    # [SOC-10] 축구. 야구에서는 빈 값이라 `없음` 으로 빠진다.
    # 🔴 [DBM-1] 이름에 **종목을 붙인다.** `오늘 선발 라인업` 은 야구의
    #    `오늘 타순` 과 같은 것을 가리켜, 제미니가 야구 경기에서 축구 이름을
    #    부르고 빈손을 받았다(실측 2026-09-13 Seattle@Athletics: 선발·타순이
    #    DB에 다 있는데 "공개되지 않아"라고 썼다).
    ("축구 선발 라인업", "soccer_lineup_payload"),
    ("축구 부상·결장자", "soccer_injury_payload"),
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


#: 이 채널의 행 라벨. 수집 출처 집계에 그대로 쓰인다.
SOURCE = "우리 기록"


def _norm(t: str) -> str:
    return "".join(str(t or "").split()).lower()


def fetch(jg: dict, names, *, with_miss: bool = False):
    """[SRCH-7] 이름으로 DB 항목을 꺼내 **수집 행**으로 돌려준다.

    사용자 지시 2026-09-12: "양팀 선발의 상세 투구는 있다.. 없으면 안트로픽이나
    퍼플릭스한테 요청을 해서 받으라고 해야 한다."

    🔴 왜. 실측 2026-09-12: 제미니 분석글 4/4 가 "선발 투수의 최근 등판
       세부 기록을 확인하지 못했다"로 끝났는데, **그 기록은 우리 DB에 있다**
       (`선발 최근 등판`). 2단계 선별도 `DB요청` 으로 정확히 지목하고 있었다 —
       그 칸을 아무도 읽지 않았을 뿐이다.

    🔴 **못 맞춘 이름을 조용히 버리지 않는다.** 실측 2026-09-12: 4경기 중
       2경기가 "양 팀 선발 투수의 최근 등판 성적 및 평균자책점"처럼 풀어 써서
       매핑에 실패했다. `with_miss=True` 로 못 맞춘 것을 함께 돌려준다.
    ⚠️ 값이 빈 항목은 행을 만들지 않는다 — 실으면 판정이 "있다"로 읽는다.
    """
    want = [str(x).strip() for x in (names or []) if str(x).strip()]
    if not want:
        return ([], []) if with_miss else []
    have = {name: val for name, val in bundle(jg)["줄"]}
    rows: list[dict] = []
    miss: list[str] = []
    for w in want:
        wn = _norm(w)
        hit = next((k for k in have if _norm(k) == wn), None)
        if hit is None:
            # 풀어 쓴 이름 — 항목 이름의 글자가 전부 들어 있으면 그것으로 본다.
            hit = next((k for k in have
                        if all(ch in wn for ch in _norm(k))), None)
        val = have.get(hit) if hit else None
        if not (val and str(val).strip()):
            miss.append(w)
            continue
        rows.append({"질문": "", "답": f"{hit} — {str(val).strip()}",
                     "소스": SOURCE, "소스유형": "기록", "시점": "",
                     "계정": "", "url": ""})
    if miss:
        logger.info("[dbref] %s@%s DB로 못 채운 요청 %d개: %s",
                    jg.get("away"), jg.get("home"), len(miss), miss)
    return (rows, miss) if with_miss else rows


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
        # 🔴 [LLMS-1 2026-09-13 결정 D] **승자를 바꾸지 않는다.**
        #    (a) 구조에서 승자는 `p_code`(시장 뼈대 + 코드 조정)가 정한다.
        #    여기서 승자를 바꾸면 그 구조가 깨진다. 다른 의견은 버리지 않고
        #    **서술의 반대 근거**로 남긴다 — 서술 문장 3이 그것을 쓴다.
        out["반대근거"] = why or f"DB 참조가 {new_w} 쪽을 지목했다"
        out["사유"] = out["반대근거"]
        logger.info("[dbref] %s@%s DB 참조가 다른 승자를 지목 (%s → %s) — "
                    "승자는 그대로 두고 반대 근거로 남긴다: %s",
                    jg.get("away"), jg.get("home"), v.get("승자"), new_w,
                    out["반대근거"])
    logger.info("[dbref] %s@%s %s · 있음 %d · 본것 %s · 확신 %s→%s",
                jg.get("away"), jg.get("home"), out["판정"], len(b["있음"]),
                out["본것"], v.get("확신"), out["확신"])
    return out
