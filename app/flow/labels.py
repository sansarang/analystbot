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

#: 🔴 [HYC-3 2026-09-23 사용자 지시 "가 해라"] **"안 봤다"와 "볼 방법이 없다"는
#   다르다.** ⑤에 분기가 아예 없는 변수(weather·travel_backtoback 등)와 그
#   종목에 모듈이 없는 변수(NPB 파크팩터)는 미상이 아니라 **미실행**이다.
#
#   실측 (오늘 9경기 · 전 기간):
#     weather           확인 0 / 등장 2,129   ⑤에 분기 없음
#     travel_backtoback 확인 0 / 등장 2,129   ⑤에 분기 없음
#     park_factor(NPB)  확인 0 / 등장   452   모듈 없음
#     요미우리@히로시마  미상 4/6 = 0.667 → 모름과반
#                       미실행 3개를 빼면 1/3 = 0.333 → 확인됨
#
# ⚠️ **미상을 숨기는 것이 아니다.** `per_var` 에 이 상태로 그대로 남아
#    export·서술에 보인다. 빠지는 것은 **분모**뿐이다.
# 🔴 목록을 어디에도 적지 않는다 — 못 찾는 것을 아는 쪽은 ⑤이고, ⑤가 그
#    자리에서 이 상태를 남긴다(계약이 잠근다).
UNRUN = "미실행"
V_OK, V_REFUTED, V_UNKNOWN = "확인됨", "반박됨", "모름과반"
VERDICTS = (V_OK, V_REFUTED, V_UNKNOWN)

#: 🔴 [CNF-2 2026-09-20] **반증의 뜻은 가설마다 다르다.**
#   딥서치(FORKS F-19): absence of evidence 는 "그 주장이 참이었다면 근거가
#   나왔을 것"인 만큼만 evidence of absence 다. 그러면 뜻은 가설의 **주장**에
#   달린다 — 게이트가 주장을 정하므로 ④가 싣고 ⑥이 읽는다.
#     H_fade  "시장 반대편을 세울 근거" → 없으면 시장이 맞다  → 철회
#     H_break "우리 픽을 무너뜨릴 근거" → 없으면 픽이 단단하다 → 강화
#     H_deriv 파생 재료                                      → 중립
#   ⚠️ 여기가 **원본**이다. 노드는 서로 import 하지 않으므로(계약) 두 노드가
#      이 표를 각자 읽는다 — 어느 노드에도 다시 적지 마라(사본 금지).
R_RETRACT, R_STRENGTHEN, R_NEUTRAL = "철회", "강화", "중립"
REFUTED_MEANS = {"H_fade": R_RETRACT, "H_break": R_STRENGTHEN,
                 "H_deriv": R_NEUTRAL, "H_none": R_NEUTRAL}

# ⑨ 확신
GRADE_A, GRADE_B, GRADE_C = "A", "B", "C"

# ⑪ 값 판정
PICK_ML, PICK_STRUCT, PICK_BOARD = "승패", "구조", "보드"
PICK_TYPES = (PICK_ML, PICK_STRUCT, PICK_BOARD)
