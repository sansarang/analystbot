"""🔴🔴 **이름 세는 도움함수만 남았다** — 사용자 지시 2026-10-17.

> 옛 글 경로(s9_say) **필요없다** · 어제처럼 solar deepseek 평이 나와야 한다 ·
> 오늘 로직에서 불필요한 **옛 코드는 더이상 필요하지 않다**

🔴 이 파일은 **옛 최종 평 단계**였다(작성 `run` + 검열 `check` + `template`).
   평문은 이제 **⑯ 종합 평**(`stages/s6_verdict` · solar·deepseek)이 낸다 —
   그 입구를 지우자 `check`·`template` 과 묶음(`core/saybundle`)이 **전부
   고아**가 됐고(계약이 그렇게 말했다), 그래서 함께 걷었다.

🔴 **남긴 것은 넷뿐**이다 — `s6_verdict` 의 검열 (다)가 **이름을 셀 때** 쓴다
   (사본 금지 · `_names_in`·`_NAME`). ⚠️ 글자를 **옮기지 않고 그대로** 뒀다:
   이름 검열은 거짓양성으로 두 번 다친 자리라(자리 글자 `CB Waston` · 한
   낱말 이름) 그 판정 글자를 손대지 않는다.
"""
from __future__ import annotations

import re

#: 🔴🔴 **이 파일은 더 이상 "단계"가 아니다** — 사용자 지시 2026-10-17.
#   옛 최종 평 입구(`run`)를 지웠고 **이름 세는 도움함수**만 남았다. 계약
#   (`test_v6_7_static`)이 *"`run` 이 하나이거나 `STAGES` 선언이 있어야 한다"*
#   고 세므로, 남은 공개 이름을 여기 적는다(선언 창 · 사본이 아니다).
STAGES = ("strip_pos",)

#: 🔴 선수 이름처럼 보이는 토막 — 로마자 이름(`Jae-Hyun Go`)과 한글 이름 둘 다
_NAME = re.compile(r"[A-Z][A-Za-zÀ-ÿ'’\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'’\-]+)+"
                   r"|[가-힣]{2,4}(?=(?:이|가|은|는|을|를|의|도|와|과)?\s)")


#: 🔴🔴 **자리 글자**(포지션 접두) — 이름 앞에 붙는다. 사람 이름의 일부가 아니다.
#   ⚠️ 실사고 2026-10-16(코스타리카): 평이 *"CB **Waston**"*·*"CM **Soto**"*·
#      *"DM **López**"* 라고 썼고 검열이 셋 다 **없는 이름**이라 했다 — 묶음에는
#      `Waston`·`Soto`·`Alexander López` 가 **그대로 있었다**(실측).
#   🔴 까닭 둘: ① `_NAME` 이 **두 낱말 이상**만 이름으로 보므로 묶음의 한 낱말
#      이름(`Waston`)을 **아예 모으지 못했다** ② 문장 쪽은 접두가 붙어 두 낱말이
#      되어 후보로 잡혔다 — **비대칭**이다.
_POS = re.compile(r"^(?:GK|DF|MF|FW|CB|LCB|RCB|LB|RB|FB|WB|FB/WB|CDM|DM|CM|"
                  r"LM|RM|AM|CAM|LW|RW|ST|CF|SS)\s+", re.I)


def strip_pos(said: str) -> str:
    """🔴 이름 앞의 **자리 글자**를 떼낸다(`CB Waston` → `Waston`)."""
    got = str(said or "").strip()
    for _ in range(3):
        cut = _POS.sub("", got).strip()
        if cut == got:
            break
        got = cut
    return got


def _names_in(said: str, known: set[str], *, text: str = "") -> list[str]:
    """🔴 (r) — 글이 **인용한, 묶음에 없는** 이름들. ⚠️ 로마자 이름만 센다.

    ⚠️ 한글 토막은 보통 명사(*"오른쪽"*·*"수비"*)와 섞여 거짓 위반을 만든다 —
       실측 없이 그 둘을 가를 길이 없으므로 **로마자만** 센다(#4 추측 금지).
    🔴🔴 **자리 글자가 이름에 붙는다** — ⚠️ 실측 2026-10-10(재현): 평이
       *"새로 들어온 **LB Min-Seo Park**"* 이라고 적었고 검열이 그 다섯 글자를
       통째로 **없는 이름**이라 했다(묶음에는 `Min-Seo Park` 이 있다). 그 거짓
       위반 하나로 좋은 평이 템플릿으로 떨어졌다.
    🔴 그래서 **묶음의 이름을 품고 있으면 통과**시킨다(지어낸 이름은 어떤 이름도
       품지 않는다).
    """
    got = [x for x in _NAME.findall(str(said or ""))
           if re.match(r"^[A-Z]", x)]
    said_text = str(text or "")
    out: list[str] = []
    for nm in got:
        if any(k and (k in nm or nm in k) for k in known):
            continue
        # 🔴 ① **자리 글자를 떼고** 다시 본다(위 머리말 `CB Waston`)
        bare = strip_pos(nm)
        if bare != nm and any(k and (k in bare or bare in k) for k in known):
            continue
        # 🔴 ② **묶음 원문에 그 낱말들이 있으면** 지어낸 것이 아니다 —
        #    묶음의 한 낱말 이름(`Waston`)이나 성만 쓴 축약(`López` ←
        #    `Alexander López`)이 이 길로 통과한다. ⚠️ `text` 를 안 주면
        #    종전과 **똑같이** 동작한다(옛 호출부를 안 깨뜨린다).
        if said_text:
            words = [w for w in re.split(r"[\s·]+", bare) if w]
            if words and all(w in said_text for w in words):
                continue
        out.append(nm)
    return out
