#!/bin/zsh
# 🔴 게이트2 — 지시서 §3-2 가 권고한 다섯 경기. **봇의 실제 핸들러**로 돈다.
cd /Users/youngjinjung/Desktop/analystbot
SP=/private/tmp/claude-501/-Users-youngjinjung-Desktop-analystbot/008eb28d-dc8c-42b3-bb25-1cbdfe6acf9a/scratchpad
run() { echo "=== $1 ==="; PYTHONPATH=. uv run python $SP/ask_bot.py "$2" > "$SP/g5_$1.log" 2>&1
        echo "exit $? · 줄 $(wc -l < $SP/g5_$1.log)"; }
run mlb   "밀워키 브루어스 vs 샌디에이고 파드리스"
# 🔴 **일정에 있는 경기로 바꿨다**(실측 2026-10-04 · 広島 vs 中日 는 오늘 없다).
#    오늘 NPB 3경기: s-c · db-t · m-e. ⚠️ 이름표에 있는 일본어 표기로 묻는다.
run npb   "横浜DeNAベイスターズ vs 阪神タイガース"
run kbo   "한화 이글스 vs 키움 히어로즈"
run unl_b "북마케도니아 vs 스코틀랜드"
run unl_a "크로아티아 vs 잉글랜드"
echo "@@@DONE@@@"
