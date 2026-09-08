#!/usr/bin/env python3
"""종결 선언을 가려낸다 — stdin 텍스트 → stdout 에 항목 id 공백 구분.

🔴 이 파일이 왜 따로 있나: 판정을 **실측으로 조정**해야 하기 때문이다.
   v1 은 `✅` 만 보고 판정했고, 실제 작업 이력 1,200건 재생에서 **52건(4.33%)**
   을 잘못 막았다. 전부 같은 유형이었다 —
   `## ✅ SCH-4 정상 확인` 은 "고쳤다"가 아니라 **"조사했더니 결함이 없다"**다.
   감사 세션은 그런 줄을 수십 개씩 쓴다. 그걸 막는 게이트는 하루면 꺼진다.

   그래서 판정은 **완료를 선언하는 낱말**로 한다: 종결·해결됨·수정 완료·닫는다.
   `✅` 단독은 종결이 아니다.

⚠️ 인용은 선언이 아니다: `>` 인용줄과 ``` 코드펜스 안은 세지 않는다.
   (CRW-6 항목 자체가 과거의 종결 선언을 펜스 안에 인용하고 있다.)

⚠️ 알려진 한계(거짓 음성): 낱말 없이 `## ✅ CRW-6` 만 적고 닫으면 못 잡는다.
   그 경로는 커밋·배포 게이트가 따로 본다. 오탐을 4%로 두는 것보다 낫다.
"""
import re, sys

CLOSE = re.compile(r"(종결|해결됨|해결 완료|수정 완료|수정완료|닫는다|FIXED|CLOSED)")
IDPAT = re.compile(r"\b([A-Z]{2,5}-\d+)\b")

def closure_ids(text: str) -> list[str]:
    out, head_ids, fence = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            fence = not fence
            continue
        if fence or s.startswith(">"):        # 인용·코드블록은 선언이 아니다
            continue
        if s.startswith("#"):
            head_ids = IDPAT.findall(s)       # 제목의 id 를 그 절의 주어로 삼는다
        if not CLOSE.search(s):
            continue
        out += IDPAT.findall(s) or head_ids
    return list(dict.fromkeys(out))

if __name__ == "__main__":
    print(" ".join(closure_ids(sys.stdin.read())))
