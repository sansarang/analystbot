"""[v1.4] 공용 라벨 — **노드끼리 import 하지 않기 위한 한 곳.**

🔴 지시문 규율 7: 노드는 서로 부르지 않는다. 그런데 ③ 라벨을 ④가 읽고,
   ⑥ 라벨을 `run.py` 가 읽는다. 그 이름표를 노드에 두면 서로 import 하게 된다 —
   그래서 **여기 한 곳**에 둔다. 계약 테스트가 노드 간 import 를 전수로 막는다.
🔴 문자열을 노드·테스트에 손으로 적지 않는다(사본 금지). 여기가 원본이다.
"""
from __future__ import annotations

# ③ 게이트
OVER, DOUBT, AGREE, BOARD = "시장과대", "가치의심", "동의", "보드고정"
GATES = (OVER, DOUBT, AGREE, BOARD)

# ⑥ 채점
CONFIRMED, REFUTED, UNKNOWN = "confirmed", "refuted", "unknown"
V_OK, V_REFUTED, V_UNKNOWN = "확인됨", "반박됨", "모름과반"
VERDICTS = (V_OK, V_REFUTED, V_UNKNOWN)

# ⑨ 확신
GRADE_A, GRADE_B, GRADE_C = "A", "B", "C"

# ⑪ 값 판정
PICK_ML, PICK_STRUCT, PICK_BOARD = "승패", "구조", "보드"
PICK_TYPES = (PICK_ML, PICK_STRUCT, PICK_BOARD)
