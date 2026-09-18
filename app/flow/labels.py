"""[v1.4] 공용 라벨 — **노드끼리 import 하지 않기 위한 한 곳.**

🔴 지시문 규율 7: 노드는 서로 부르지 않는다. 그런데 ③ 라벨을 ④가 읽고,
   ⑥ 라벨을 `run.py` 가 읽는다. 그 이름표를 노드에 두면 서로 import 하게 된다 —
   그래서 **여기 한 곳**에 둔다. 계약 테스트가 노드 간 import 를 전수로 막는다.
🔴 문자열을 노드·테스트에 손으로 적지 않는다(사본 금지). 여기가 원본이다.
"""
from __future__ import annotations

# ③ 게이트
OVER, DOUBT, AGREE, BOARD = "시장과대", "가치의심", "동의", "보드고정"

#: 🔴 [F-17 2026-09-19] **시장이 아직 없을 때.** 사전값만으로 가설을 세운다.
#   "보드 고정"과 **다르다** — 보드는 "찾을 것이 없다"이고 이것은
#   "비교 대상이 없으니 내 생각을 깨는 근거를 찾는다"이다.
#   사용자 지시: "데이타가 싸여야 가설을 세우는게 아니다" ·
#               "시장에 끌려가지 않고 우리 쪽 판단을 먼저 적는 게 중요함".
PRIOR_ONLY = "사전값단독"
GATES = (OVER, DOUBT, AGREE, BOARD, PRIOR_ONLY)

# ⑥ 채점
CONFIRMED, REFUTED, UNKNOWN = "confirmed", "refuted", "unknown"
V_OK, V_REFUTED, V_UNKNOWN = "확인됨", "반박됨", "모름과반"
VERDICTS = (V_OK, V_REFUTED, V_UNKNOWN)

# ⑨ 확신
GRADE_A, GRADE_B, GRADE_C = "A", "B", "C"

# ⑪ 값 판정
PICK_ML, PICK_STRUCT, PICK_BOARD = "승패", "구조", "보드"
PICK_TYPES = (PICK_ML, PICK_STRUCT, PICK_BOARD)
